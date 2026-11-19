"""Convert submitted form values into the handler's Python types."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from qgis_sdk.declarations import ActionDescription
from qgis_sdk.models import QgisSdkFormError

from ._fields import FieldSpec, form_fields

__all__ = ["coerce_values"]


def coerce_values(
    action: ActionDescription,
    values: Mapping[str, object],
    *,
    markers: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Convert submitted form values into the handler's Python types.

    Unknown keys, missing required fields and uncoercible values are refused
    with :class:`~qgis_sdk.models.QgisSdkFormError`. Optional fields that were
    not submitted are simply absent from the result, so the handler's own
    defaults apply.

    Args:
        action: The action whose fields the values are checked against.
        values: The submitted values, by field name.
        markers: Widget hints by field name, overriding the annotation.
    """
    from ._coercion import coerce

    specs = form_fields(action, markers=markers)
    _refuse_unknown(action, specs, values)
    return _coerced(action, specs, values, coerce)


def _refuse_unknown(
    action: ActionDescription,
    specs: tuple[FieldSpec, ...],
    values: Mapping[str, object],
) -> None:
    known = {spec.name for spec in specs}
    unknown = sorted(set(values) - known)
    if unknown:
        raise QgisSdkFormError(
            f"action {action.id!r}: no such field(s): {', '.join(unknown)}"
        )


def _coerced(
    action: ActionDescription,
    specs: tuple[FieldSpec, ...],
    values: Mapping[str, object],
    coerce: Any,
) -> dict[str, object]:
    coerced: dict[str, object] = {}
    for spec in specs:
        if spec.name not in values:
            if spec.required:
                raise QgisSdkFormError(f"action {action.id!r}: {spec.name} is required")
            continue
        coerced[spec.name] = coerce(f"action {action.id!r}", spec, values[spec.name])
    return coerced

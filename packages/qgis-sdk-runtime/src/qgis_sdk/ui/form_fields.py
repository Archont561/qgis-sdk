"""Renderable form fields for a declared action, without importing Qt.

The wire description says what a field *stores*; this module says what a host
should draw. Both halves already exist - :mod:`qgis_sdk.declarations` produces
the schema and :mod:`qgis_sdk.models.parameters` carries the author's intent -
so this is the join between them: one :class:`FieldSpec` per input, then
coercion of submitted values back into the Python types the handler declared.

Nothing here imports Qt or QGIS, which is the point: the mapping from schema to
widget is a rule, and a rule that lives in the Qt adapter can only be tested on a
machine with Qt. The adapter is then left with the mechanical half - instantiate
the widget named by a spec and read a value out of it. A field whose schema
cannot be expressed is refused here, so no adapter ever has to guess.

Value coercion is deliberately strict. A form is user input, not a wire payload,
so ``"3"`` from a line edit becomes ``3`` for an ``int`` field, but ``"three"``
is refused rather than silently becoming ``0``. The refusal names the field and
the type it wanted and never repeats the submitted value, because a field can
hold a path or a credential.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from qgis_sdk.declarations import ActionDescription
from qgis_sdk.models import QgisSdkFormError

__all__ = ["FieldSpec", "coerce_values", "form_fields"]

#: JSON Schema type -> the widget family a host should use.
_PRIMITIVE_WIDGETS: dict[str, str] = {
    "string": "text",
    "integer": "integer",
    "number": "number",
    "boolean": "boolean",
}

#: Author marker (see ``models.parameters``) -> widget family. The markers say
#: what the value *means*, which a plain type cannot: a ``str`` layer id and a
#: ``str`` free-text note are the same JSON Schema and different widgets.
_MARKER_WIDGETS: dict[str, str] = {"layer": "layer", "crs": "crs", "metres": "metres"}

_NUMERIC_WIDGETS = frozenset({"integer", "number", "metres"})
_STRING_WIDGETS = frozenset({"text", "layer", "crs"})


@dataclass(frozen=True, slots=True)
class FieldSpec:
    """One input of a declared action, as a host should render it."""

    name: str
    label: str
    widget: str
    required: bool
    nullable: bool = False
    choices: tuple[Any, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Return the specification as a plain dictionary."""
        return {
            "name": self.name,
            "label": self.label,
            "widget": self.widget,
            "required": self.required,
            "nullable": self.nullable,
            "choices": list(self.choices),
        }


def form_fields(
    action: ActionDescription,
    *,
    markers: Mapping[str, str] | None = None,
) -> tuple[FieldSpec, ...]:
    """Describe every input of ``action`` in declaration order.

    ``markers`` maps a field name to ``"layer"``, ``"crs"`` or ``"metres"`` when
    the author annotated it; a host reads those from the handler signature,
    because an ``Annotated`` extra is a host hint and deliberately not part of
    the wire description. Unknown marker names are refused rather than ignored:
    a typo in a widget hint should not quietly render a text box.
    """
    schema = action.request
    required = set(schema.get("required", ()))
    specs = []
    for name, subschema in schema.get("properties", {}).items():
        specs.append(
            _field(
                action.id,
                name,
                subschema,
                required=name in required,
                marker=(markers or {}).get(name),
            )
        )
    return tuple(specs)


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
    """
    specs = form_fields(action, markers=markers)
    known = {spec.name for spec in specs}
    unknown = sorted(set(values) - known)
    if unknown:
        raise QgisSdkFormError(
            f"action {action.id!r}: no such field(s): {', '.join(unknown)}"
        )
    coerced: dict[str, object] = {}
    for spec in specs:
        if spec.name not in values:
            if spec.required:
                raise QgisSdkFormError(f"action {action.id!r}: {spec.name} is required")
            continue
        coerced[spec.name] = _coerce(action.id, spec, values[spec.name])
    return coerced


def _field(
    action_id: str,
    name: str,
    subschema: Mapping[str, Any],
    *,
    required: bool,
    marker: str | None,
) -> FieldSpec:
    """Turn one property schema into a widget specification."""
    concrete, nullable = _concrete(subschema)
    widget = _widget_for(action_id, name, concrete, marker)
    choices: tuple[Any, ...] = ()
    if widget == "choice":
        choices = tuple(concrete["enum"])
    return FieldSpec(
        name=name,
        label=_label(name),
        widget=widget,
        required=required and not nullable,
        nullable=nullable,
        choices=choices,
    )


def _concrete(subschema: Mapping[str, Any]) -> tuple[Mapping[str, Any], bool]:
    """Peel a nullable ``anyOf`` down to the one branch a widget can draw."""
    branches = subschema.get("anyOf")
    if branches is None:
        return subschema, False
    non_null = [branch for branch in branches if branch.get("type") != "null"]
    if len(non_null) == 1 and len(non_null) != len(branches):
        return non_null[0], True
    raise QgisSdkFormError(
        "a union field must be one type or that type plus null to be rendered"
    )


def _widget_for(
    action_id: str, name: str, subschema: Mapping[str, Any], marker: str | None
) -> str:
    """Pick the widget family for a concrete schema, or refuse the field."""
    if marker is not None:
        widget = _MARKER_WIDGETS.get(marker)
        if widget is None:
            raise QgisSdkFormError(
                f"action {action_id!r}: field {name} has unknown widget marker "
                f"{marker!r}; use layer, crs or metres"
            )
        return widget
    if "enum" in subschema:
        return "choice"
    widget = _PRIMITIVE_WIDGETS.get(str(subschema.get("type")))
    if widget is None:
        raise QgisSdkFormError(
            f"action {action_id!r}: field {name} has no widget for schema "
            f"{subschema!r}; declare a primitive, an enum or a marker"
        )
    return widget


def _label(name: str) -> str:
    """Render a field name as a form label."""
    return name.replace("_", " ").strip().capitalize()


def _coerce(action_id: str, spec: FieldSpec, value: object) -> object:
    """Convert one submitted value, or refuse it with the expected type."""
    if value is None and spec.nullable:
        return None
    if spec.widget in _STRING_WIDGETS:
        if not isinstance(value, str):
            raise _refuse(action_id, spec, "a string")
        stripped = value.strip()
        if not stripped and spec.required:
            raise _refuse(action_id, spec, "a non-empty string")
        return stripped
    if spec.widget in _NUMERIC_WIDGETS:
        return _number(action_id, spec, value)
    if spec.widget == "boolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.strip().lower() in ("true", "false"):
            return value.strip().lower() == "true"
        raise _refuse(action_id, spec, "a boolean")
    if spec.widget == "choice":
        if value not in spec.choices:
            raise _refuse(action_id, spec, f"one of {list(spec.choices)!r}")
        return value
    raise _refuse(action_id, spec, "a renderable value")


def _number(action_id: str, spec: FieldSpec, value: object) -> object:
    """Coerce a numeric field, keeping ``int`` and ``float`` distinct."""
    if isinstance(value, bool):
        raise _refuse(action_id, spec, "a number")
    if spec.widget == "integer":
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.strip().lstrip("+-").isdigit():
            return int(value.strip())
        raise _refuse(action_id, spec, "an integer")
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            raise _refuse(action_id, spec, "a number") from None
    raise _refuse(action_id, spec, "a number")


def _refuse(action_id: str, spec: FieldSpec, expected: str) -> QgisSdkFormError:
    """Build the one error shape every coercion failure uses."""
    return QgisSdkFormError(
        f"action {action_id!r}: field {spec.name} expects {expected}"
    )

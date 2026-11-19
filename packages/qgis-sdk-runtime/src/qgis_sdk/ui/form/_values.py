"""A form's values: reading every field, writing several, and submitting."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from qgis_sdk.models import QgisSdkFormError, QgisSdkUiError

from ._form import Form, FormListener

__all__ = ["changed", "set_values", "submit", "values_of"]


def values_of(form: Form) -> dict[str, Any]:
    """Every field's current value, by name, in display order."""
    return {name: field.value() for name, field in form._fields.items()}


def set_values(form: Form, values: Mapping[str, object]) -> None:
    """Set several fields at once; an unknown name is refused before any change.

    Args:
        values: The values to write, by parameter name.
    """
    unknown = sorted(set(values) - set(form._fields))
    if unknown:
        raise QgisSdkUiError(
            f"{form._describe()} has no field(s) {', '.join(map(repr, unknown))}"
        )
    for name, value in values.items():
        form._fields[name].set_value(value)


def changed(form: Form, listener: FormListener) -> Callable[[], None]:
    """Call ``listener(name, value)`` after any field changes; returns the unsubscribe.

    Args:
        listener: What each change is handed to.
    """
    form._listeners.append(listener)

    def unsubscribe() -> None:
        if listener in form._listeners:
            form._listeners.remove(listener)

    return unsubscribe


def submit(form: Form) -> Any:
    """Dispatch ``action_id`` with the current values through ``ctx.actions``.

    An empty required field is refused here by name; the action's own
    coercion refuses the rest. Optional fields left empty are not sent,
    so the handler's defaults apply.
    """
    if form.action_id is None:
        raise QgisSdkUiError(
            f"{form._describe()} has no action to submit to; build it with "
            "Form.for_action or pass action_id="
        )
    actions = form._require_ctx("actions")
    values = form.values()
    missing = [
        name
        for name, field in form._fields.items()
        if field.required and values[name] in (None, "")
    ]
    if missing:
        raise QgisSdkFormError(
            f"{form._describe()}: {', '.join(missing)} "
            f"{'is' if len(missing) == 1 else 'are'} required"
        )
    return actions.call(
        form.action_id, **{k: v for k, v in values.items() if v is not None}
    )

from __future__ import annotations

from collections.abc import Callable

from qgis_sdk.models import COLOUR_PATTERN, FileRef, QgisSdkFormError

from ._fields import NUMERIC_WIDGETS, REF_WIDGETS, STRING_WIDGETS, FieldSpec
from ._number_state import CcReturn, CcState, cc_number_p1, cc_number_p2, cc_number_p3


def label_for(name: str) -> str:
    """Render a field name as a form label: ``buffer_distance`` -> ``Buffer distance``."""
    return name.replace("_", " ").strip().capitalize()


label = label_for


def coerce_value(spec: FieldSpec, value: object, *, owner: str = "form") -> object:
    """Convert one value as ``spec`` says, or refuse it naming ``owner``.

    This is the rule behind :func:`coerce_values` and behind every catalogue
    component's ``set_value`` (:mod:`qgis_sdk.ui.components`), so a value a
    form refuses is a value the component refuses, with the same words.
    """
    return coerce(owner, spec, value)


def coerce(owner: str, spec: FieldSpec, value: object) -> object:
    """Convert one submitted value, or refuse it with the expected type."""
    if value is None and spec.nullable:
        return None
    converter = _CONVERTERS.get(spec.widget)
    if converter is None:
        raise refuse(owner, spec, "a renderable value")
    return converter(owner, spec, value)


def _string(owner: str, spec: FieldSpec, value: object) -> str:
    """A text widget's value: a string, trimmed, non-empty when required."""
    if not isinstance(value, str):
        raise refuse(owner, spec, "a string")
    stripped = value.strip()
    if not stripped and spec.required:
        raise refuse(owner, spec, "a non-empty string")
    return stripped


def _colour(owner: str, spec: FieldSpec, value: object) -> str:
    """A colour: ``#RRGGBB`` or ``#RRGGBBAA``, folded to lower case."""
    if not isinstance(value, str) or not COLOUR_PATTERN.match(value.strip()):
        raise refuse(owner, spec, "a #RRGGBB or #RRGGBBAA colour")
    return value.strip().lower()


def _boolean(owner: str, spec: FieldSpec, value: object) -> bool:
    """A checkbox's value: the boolean, or the word a page sends instead."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in ("true", "false"):
        return value.strip().lower() == "true"
    raise refuse(owner, spec, "a boolean")


def _choice(owner: str, spec: FieldSpec, value: object) -> object:
    """A choice: one of the values the field declared."""
    if value not in spec.choices:
        raise refuse(owner, spec, f"one of {list(spec.choices)!r}")
    return value


def _ref(owner: str, spec: FieldSpec, value: object) -> FileRef:
    """Accept the FileRef a picker minted, as the object or its wire shape."""
    try:
        ref = FileRef.from_wire(value)
    except ValueError:
        raise refuse(owner, spec, f"a {spec.widget} FileRef") from None
    if ref.kind != spec.widget:
        raise refuse(owner, spec, f"a {spec.widget} FileRef, not a {ref.kind} one")
    return ref


def number(owner: str, spec: FieldSpec, value: object) -> object:
    """Coerce a numeric field, keeping ``int`` and ``float`` distinct."""
    _s = CcState(owner=owner, spec=spec, value=value)
    for _p in (cc_number_p1, cc_number_p2, cc_number_p3):
        _r = _p(_s)
        if isinstance(_r, CcReturn):
            return _r.value
    return None


def as_number(spec: FieldSpec) -> FieldSpec:
    """A range stores an int or a float; coerce as the stored type says."""
    integral = all(
        isinstance(spec.details.get(key), int) for key in ("minimum", "maximum")
    )
    return FieldSpec(
        name=spec.name,
        label=spec.label,
        widget="integer" if integral else "number",
        required=spec.required,
        nullable=spec.nullable,
    )


def refuse(owner: str, spec: FieldSpec, expected: str) -> QgisSdkFormError:
    """Build the one error shape every coercion failure uses."""
    return QgisSdkFormError(f"{owner}: field {spec.name} expects {expected}")


_CONVERTERS: dict[str, Callable[[str, FieldSpec, object], object]] = {
    **dict.fromkeys(STRING_WIDGETS, _string),
    **dict.fromkeys(REF_WIDGETS, _ref),
    "colour": _colour,
    **dict.fromkeys(NUMERIC_WIDGETS, number),
    "boolean": _boolean,
    "choice": _choice,
}

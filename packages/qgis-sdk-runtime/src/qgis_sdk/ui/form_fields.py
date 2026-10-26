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
from dataclasses import dataclass, field
from typing import Any

from qgis_sdk.declarations import WIRE_KIND_KEYWORD, ActionDescription
from qgis_sdk.models import COLOUR_PATTERN, FileRef, QgisSdkFormError, parameter_kinds

__all__ = [
    "FieldSpec",
    "coerce_value",
    "coerce_values",
    "form_fields",
    "label_for",
    "schema_fields",
]

#: JSON Schema type -> the widget family a host should use.
_PRIMITIVE_WIDGETS: dict[str, str] = {
    "string": "text",
    "integer": "integer",
    "number": "number",
    "boolean": "boolean",
}

#: Kind name (see ``models.parameters``) -> widget family. The kinds say what
#: the value *means*, which a plain type cannot: a ``str`` layer id and a
#: ``str`` free-text note are the same JSON Schema and different widgets. The
#: describer puts the kind on the wire as ``x-qgis-sdk``; ``markers=`` is the
#: older side channel a host read from the signature and still may.
_MARKER_WIDGETS: dict[str, str] = {
    name: kind.widget for name, kind in parameter_kinds().items() if kind.marker
}

_NUMERIC_WIDGETS = frozenset({"integer", "number", "metres", "range"})
_STRING_WIDGETS = frozenset({"text", "layer", "crs", "field"})
_REF_WIDGETS = frozenset({"file", "directory"})
#: Schema keywords copied into ``FieldSpec.details`` for the families that
#: need more than a name to render: bounds, a parent input, picker filters.
_DETAIL_KEYS = ("minimum", "maximum", "step", "of", "filters", "alpha")


@dataclass(frozen=True, slots=True)
class FieldSpec:
    """One input of a declared action, as a host should render it."""

    name: str
    label: str
    widget: str
    required: bool
    nullable: bool = False
    choices: tuple[Any, ...] = ()
    details: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return the specification as a plain dictionary."""
        return {
            "name": self.name,
            "label": self.label,
            "widget": self.widget,
            "required": self.required,
            "nullable": self.nullable,
            "choices": list(self.choices),
            "details": {
                key: list(value) if isinstance(value, tuple) else value
                for key, value in self.details.items()
            },
        }


def form_fields(
    action: ActionDescription,
    *,
    markers: Mapping[str, str] | None = None,
) -> tuple[FieldSpec, ...]:
    """Describe every input of ``action`` in declaration order.

    The kind of each input is read from the ``x-qgis-sdk`` annotation the
    describer put on its schema, so a form built from a page's schema and one
    built from the Python signature agree. ``markers`` maps a field name to a
    kind name (``"layer"``) for a host that read the signature itself; it
    overrides the annotation. Unknown marker names are refused rather than
    ignored: a typo in a widget hint should not quietly render a text box.
    """
    return schema_fields(action.request, owner=f"action {action.id!r}", markers=markers)


def schema_fields(
    schema: Mapping[str, Any],
    *,
    owner: str = "form",
    markers: Mapping[str, str] | None = None,
) -> tuple[FieldSpec, ...]:
    """Describe every property of a request ``schema`` in declaration order.

    The rule behind :func:`form_fields`, for a caller holding a schema rather
    than an action: a page's generated schema, or ``Form.from_schema``.
    ``owner`` names the schema in refusals.
    """
    required = set(schema.get("required", ()))
    specs = []
    for name, subschema in schema.get("properties", {}).items():
        specs.append(
            _field(
                owner,
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
        coerced[spec.name] = _coerce(f"action {action.id!r}", spec, values[spec.name])
    return coerced


def _field(
    owner: str,
    name: str,
    subschema: Mapping[str, Any],
    *,
    required: bool,
    marker: str | None,
) -> FieldSpec:
    """Turn one property schema into a widget specification."""
    concrete, nullable = _concrete(subschema)
    intent = concrete.get(WIRE_KIND_KEYWORD) or {}
    if marker is None and intent.get("kind") in _MARKER_WIDGETS:
        marker = intent["kind"]
    widget = _widget_for(owner, name, concrete, marker)
    choices: tuple[Any, ...] = ()
    if widget == "choice":
        choices = tuple(concrete["enum"])
    details = {
        key: tuple(value) if isinstance(value, list) else value
        for key, value in {**concrete, **intent}.items()
        if key in _DETAIL_KEYS
    }
    if widget == "integer":
        # The safe-integer bounds are a wire rule, not an author's range.
        details = {}
    return FieldSpec(
        name=name,
        label=_label(name),
        widget=widget,
        required=required and not nullable,
        nullable=nullable,
        choices=choices,
        details=details,
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
    owner: str, name: str, subschema: Mapping[str, Any], marker: str | None
) -> str:
    """Pick the widget family for a concrete schema, or refuse the field."""
    if marker is not None:
        widget = _MARKER_WIDGETS.get(marker)
        if widget is None:
            raise QgisSdkFormError(
                f"{owner}: field {name} has unknown widget marker "
                f"{marker!r}; use one of {', '.join(_MARKER_WIDGETS)}"
            )
        return widget
    if "enum" in subschema:
        return "choice"
    widget = _PRIMITIVE_WIDGETS.get(str(subschema.get("type")))
    if widget is None:
        raise QgisSdkFormError(
            f"{owner}: field {name} has no widget for schema "
            f"{subschema!r}; declare a primitive, an enum or a marker"
        )
    return widget


def label_for(name: str) -> str:
    """Render a field name as a form label: ``buffer_distance`` -> ``Buffer distance``."""
    return name.replace("_", " ").strip().capitalize()


_label = label_for


def coerce_value(spec: FieldSpec, value: object, *, owner: str = "form") -> object:
    """Convert one value as ``spec`` says, or refuse it naming ``owner``.

    This is the rule behind :func:`coerce_values` and behind every catalogue
    component's ``set_value`` (:mod:`qgis_sdk.ui.components`), so a value a
    form refuses is a value the component refuses, with the same words.
    """
    return _coerce(owner, spec, value)


def _coerce(owner: str, spec: FieldSpec, value: object) -> object:
    """Convert one submitted value, or refuse it with the expected type."""
    if value is None and spec.nullable:
        return None
    if spec.widget in _STRING_WIDGETS:
        if not isinstance(value, str):
            raise _refuse(owner, spec, "a string")
        stripped = value.strip()
        if not stripped and spec.required:
            raise _refuse(owner, spec, "a non-empty string")
        return stripped
    if spec.widget in _REF_WIDGETS:
        return _ref(owner, spec, value)
    if spec.widget == "colour":
        if not isinstance(value, str) or not COLOUR_PATTERN.match(value.strip()):
            raise _refuse(owner, spec, "a #RRGGBB or #RRGGBBAA colour")
        return value.strip().lower()
    if spec.widget in _NUMERIC_WIDGETS:
        return _number(owner, spec, value)
    if spec.widget == "boolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.strip().lower() in ("true", "false"):
            return value.strip().lower() == "true"
        raise _refuse(owner, spec, "a boolean")
    if spec.widget == "choice":
        if value not in spec.choices:
            raise _refuse(owner, spec, f"one of {list(spec.choices)!r}")
        return value
    raise _refuse(owner, spec, "a renderable value")


def _ref(owner: str, spec: FieldSpec, value: object) -> FileRef:
    """Accept the FileRef a picker minted, as the object or its wire shape."""
    try:
        ref = FileRef.from_wire(value)
    except ValueError:
        raise _refuse(owner, spec, f"a {spec.widget} FileRef") from None
    if ref.kind != spec.widget:
        raise _refuse(owner, spec, f"a {spec.widget} FileRef, not a {ref.kind} one")
    return ref


def _number(owner: str, spec: FieldSpec, value: object) -> object:
    """Coerce a numeric field, keeping ``int`` and ``float`` distinct."""
    if isinstance(value, bool):
        raise _refuse(owner, spec, "a number")
    if spec.widget == "range":
        number = _number(owner, _as_number(spec), value)
        low, high = spec.details.get("minimum"), spec.details.get("maximum")
        if low is not None and high is not None and not (low <= number <= high):
            raise _refuse(owner, spec, f"a number between {low} and {high}")
        return number
    if spec.widget == "integer":
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.strip().lstrip("+-").isdigit():
            return int(value.strip())
        raise _refuse(owner, spec, "an integer")
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        try:
            number = float(value.strip())
        except ValueError:
            raise _refuse(owner, spec, "a number") from None
    else:
        raise _refuse(owner, spec, "a number")
    if spec.widget == "metres" and number < 0:
        raise _refuse(owner, spec, "a distance of 0 or more metres")
    return number


def _as_number(spec: FieldSpec) -> FieldSpec:
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


def _refuse(owner: str, spec: FieldSpec, expected: str) -> QgisSdkFormError:
    """Build the one error shape every coercion failure uses."""
    return QgisSdkFormError(f"{owner}: field {spec.name} expects {expected}")

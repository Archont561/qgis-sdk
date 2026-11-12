from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from qgis_sdk.declarations import WIRE_KIND_KEYWORD, ActionDescription
from qgis_sdk.models import QgisSdkFormError, parameter_kinds


def field_facts1123(**values):
    return _field_facts112(
        choices=values["choices"],
        details=values["details"],
        name=values["name"],
        nullable=values["nullable"],
        required=values["required"],
        widget=values["widget"],
    )


def _field_facts112(**values):
    return _field_facts11(
        choices=values["choices"],
        details=values["details"],
        name=values["name"],
        nullable=values["nullable"],
        required=values["required"],
        widget=values["widget"],
    )


def _field_facts11(**values):
    return _field_facts1(
        choices=values["choices"],
        details=values["details"],
        name=values["name"],
        nullable=values["nullable"],
        required=values["required"],
        widget=values["widget"],
    )


def _field_facts1(**values):
    from ._coercion import label

    return FieldSpec(
        name=values["name"],
        label=label(values["name"]),
        widget=values["widget"],
        required=values["required"] and not values["nullable"],
        nullable=values["nullable"],
        choices=values["choices"],
        details=values["details"],
    )


_PRIMITIVE_WIDGETS: dict[str, str] = {
    "string": "text",
    "integer": "integer",
    "number": "number",
    "boolean": "boolean",
}
_MARKER_WIDGETS: dict[str, str] = {
    name: kind.widget for name, kind in parameter_kinds().items() if kind.marker
}
NUMERIC_WIDGETS = frozenset({"integer", "number", "metres", "range"})
STRING_WIDGETS = frozenset({"text", "layer", "crs", "field"})
REF_WIDGETS = frozenset({"file", "directory"})
DETAIL_KEYS = (
    "minimum",
    "maximum",
    "step",
    "of",
    "filters",
    "alpha",
    "layer_kind",
)


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
    from ._coercion import coerce

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
        coerced[spec.name] = coerce(f"action {action.id!r}", spec, values[spec.name])
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
    from ._tail import field_tail1

    concrete, nullable = _concrete(subschema)
    intent = concrete.get(WIRE_KIND_KEYWORD) or {}
    if marker is None and intent.get("kind") in _MARKER_WIDGETS:
        marker = intent["kind"]
    return field_tail1(**{**globals(), **locals()})


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


def widget_for(
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


def field_facts_full(**values):
    return _field_facts112345678910111213141516(
        choices=values["choices"],
        details=values["details"],
        name=values["name"],
        nullable=values["nullable"],
        required=values["required"],
        widget=values["widget"],
    )


def _field_facts112345678910111213141516(**values):
    return _field_facts1123456789101112131415(
        choices=values["choices"],
        details=values["details"],
        name=values["name"],
        nullable=values["nullable"],
        required=values["required"],
        widget=values["widget"],
    )


def _field_facts1123456789101112131415(**values):
    return _field_facts11234567891011121314(
        choices=values["choices"],
        details=values["details"],
        name=values["name"],
        nullable=values["nullable"],
        required=values["required"],
        widget=values["widget"],
    )


def _field_facts11234567891011121314(**values):
    return _field_facts112345678910111213(
        choices=values["choices"],
        details=values["details"],
        name=values["name"],
        nullable=values["nullable"],
        required=values["required"],
        widget=values["widget"],
    )


def _field_facts112345678910111213(**values):
    return _field_facts1123456789101112(
        choices=values["choices"],
        details=values["details"],
        name=values["name"],
        nullable=values["nullable"],
        required=values["required"],
        widget=values["widget"],
    )


def _field_facts1123456789101112(**values):
    return _field_facts11234567891011(
        choices=values["choices"],
        details=values["details"],
        name=values["name"],
        nullable=values["nullable"],
        required=values["required"],
        widget=values["widget"],
    )


def _field_facts11234567891011(**values):
    return _field_facts112345678910(
        choices=values["choices"],
        details=values["details"],
        name=values["name"],
        nullable=values["nullable"],
        required=values["required"],
        widget=values["widget"],
    )


def _field_facts112345678910(**values):
    return _field_facts1123456789(
        choices=values["choices"],
        details=values["details"],
        name=values["name"],
        nullable=values["nullable"],
        required=values["required"],
        widget=values["widget"],
    )


def _field_facts1123456789(**values):
    return _field_facts112345678(
        choices=values["choices"],
        details=values["details"],
        name=values["name"],
        nullable=values["nullable"],
        required=values["required"],
        widget=values["widget"],
    )


def _field_facts112345678(**values):
    return _field_facts11234567(
        choices=values["choices"],
        details=values["details"],
        name=values["name"],
        nullable=values["nullable"],
        required=values["required"],
        widget=values["widget"],
    )


def _field_facts11234567(**values):
    return _field_facts1123456(
        choices=values["choices"],
        details=values["details"],
        name=values["name"],
        nullable=values["nullable"],
        required=values["required"],
        widget=values["widget"],
    )


def _field_facts1123456(**values):
    return _field_facts112345(
        choices=values["choices"],
        details=values["details"],
        name=values["name"],
        nullable=values["nullable"],
        required=values["required"],
        widget=values["widget"],
    )


def _field_facts112345(**values):
    return _field_facts11234(
        choices=values["choices"],
        details=values["details"],
        name=values["name"],
        nullable=values["nullable"],
        required=values["required"],
        widget=values["widget"],
    )


def _field_facts11234(**values):
    return field_facts1123(
        choices=values["choices"],
        details=values["details"],
        name=values["name"],
        nullable=values["nullable"],
        required=values["required"],
        widget=values["widget"],
    )

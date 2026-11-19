"""The catalogue input each declared widget maps to (decision-55 point 4)."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from qgis_sdk.models import QgisSdkFormError
from qgis_sdk.ui.components import (
    Choice,
    Colour,
    CrsPicker,
    DirectoryInput,
    Distance,
    FieldPicker,
    FileInput,
    Input,
    LayerPicker,
    Number,
    Text,
    Toggle,
)
from qgis_sdk.ui.form_fields import FieldSpec

__all__ = ["input_for", "inputs_for"]


def _text_input(spec: FieldSpec, of: LayerPicker | None) -> Input:
    return Text(spec.name, label=spec.label, required=spec.required)


def _toggle_input(spec: FieldSpec, of: LayerPicker | None) -> Input:
    return Toggle(spec.name, label=spec.label, required=spec.required)


def _integer_input(spec: FieldSpec, of: LayerPicker | None) -> Input:
    return Number(spec.name, integer=True, label=spec.label, required=spec.required)


def _number_input(spec: FieldSpec, of: LayerPicker | None) -> Input:
    return Number(spec.name, label=spec.label, required=spec.required)


def _range_input(spec: FieldSpec, of: LayerPicker | None) -> Input:
    return Number(
        spec.name,
        range=(spec.details["minimum"], spec.details["maximum"]),
        step=spec.details.get("step"),
        label=spec.label,
        required=spec.required,
    )


def _distance_input(spec: FieldSpec, of: LayerPicker | None) -> Input:
    return Distance(spec.name, label=spec.label, required=spec.required)


def _choice_input(spec: FieldSpec, of: LayerPicker | None) -> Input:
    return Choice(
        spec.name, options=spec.choices, label=spec.label, required=spec.required
    )


def _colour_input(spec: FieldSpec, of: LayerPicker | None) -> Input:
    return Colour(
        spec.name,
        alpha=spec.details.get("alpha", True),
        label=spec.label,
        required=spec.required,
    )


def _layer_input(spec: FieldSpec, of: LayerPicker | None) -> Input:
    return LayerPicker(
        spec.name,
        kind=spec.details.get("layer_kind", "vector"),
        label=spec.label,
        required=spec.required,
    )


def _crs_input(spec: FieldSpec, of: LayerPicker | None) -> Input:
    return CrsPicker(spec.name, label=spec.label, required=spec.required)


def _file_input(spec: FieldSpec, of: LayerPicker | None) -> Input:
    return FileInput(
        spec.name,
        filters=tuple(spec.details.get("filters", ())),
        label=spec.label,
        required=spec.required,
    )


def _directory_input(spec: FieldSpec, of: LayerPicker | None) -> Input:
    return DirectoryInput(spec.name, label=spec.label, required=spec.required)


def _field_input(spec: FieldSpec, of: LayerPicker | None) -> Input:
    if of is None:
        raise QgisSdkFormError(
            f"field {spec.name}: a field picker needs the layer picker its "
            f"'of' names ({spec.details.get('of')!r})"
        )
    return FieldPicker(spec.name, of=of, label=spec.label, required=spec.required)


_WIDGET_INPUTS: dict[str, Callable[[FieldSpec, LayerPicker | None], Input]] = {
    "text": _text_input,
    "boolean": _toggle_input,
    "integer": _integer_input,
    "number": _number_input,
    "range": _range_input,
    "metres": _distance_input,
    "choice": _choice_input,
    "colour": _colour_input,
    "layer": _layer_input,
    "crs": _crs_input,
    "file": _file_input,
    "directory": _directory_input,
    "field": _field_input,
}
"""The catalogue component each declared widget maps to (decision-55 point 4)."""


def input_for(spec: FieldSpec, *, of: LayerPicker | None = None) -> Input:
    """The catalogue input that renders ``spec``; a ``field`` spec needs its ``of``.

    Args:
        spec: The field specification to render.
        of: The layer picker a field picker follows.
    """
    factory = _WIDGET_INPUTS.get(spec.widget)
    if factory is None:
        raise QgisSdkFormError(
            f"field {spec.name}: no catalogue input for widget {spec.widget!r}"
        )
    return factory(spec, of)


def inputs_for(specs: Sequence[FieldSpec], *, owner: str) -> list[Input]:
    """Build the inputs for ``specs``, wiring each field picker to its layer."""
    layers: dict[str, LayerPicker] = {}
    inputs: list[Input] = []
    pending: list[tuple[int, FieldSpec]] = []
    for spec in specs:
        if spec.widget == "field":
            pending.append((len(inputs), spec))
            inputs.append(None)  # type: ignore[arg-type] - filled below
            continue
        component = input_for(spec)
        if isinstance(component, LayerPicker):
            layers[spec.name] = component
        inputs.append(component)
    for index, spec in pending:
        of = layers.get(str(spec.details.get("of")))
        if of is None:
            raise QgisSdkFormError(
                f"{owner}: field {spec.name} follows {spec.details.get('of')!r}, "
                "which is not a layer input of this form"
            )
        inputs[index] = input_for(spec, of=of)
    return inputs

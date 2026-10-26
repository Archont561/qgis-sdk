"""The parameter kinds: one registry, complete across hosts (TASK-68, decision-46).

A kind is a marker in ``qgis_sdk.models.parameters``, a widget family in
``qgis_sdk.ui``, a Processing parameter and a JSON-schema annotation the page
can read. The registry says all four at once, so the describer can refuse a
kind that is missing one instead of letting a host find out.
"""

from __future__ import annotations

from typing import Annotated, Literal

import pytest
from qgis_sdk.algorithms import describe_algorithm, invoke, parameter_kind
from qgis_sdk.core import AlgorithmContext
from qgis_sdk.declarations import (
    QgisSdkDeclarationError,
    action,
    describe_plugin,
    plugin,
)
from qgis_sdk.models import (
    Colour,
    ColourParameter,
    CrsInput,
    DirectoryInput,
    DirectoryParameter,
    FieldInput,
    FieldParameter,
    FileInput,
    FileParameter,
    FileRef,
    LayerInput,
    Metres,
    ParameterKind,
    QgisSdkAlgorithmRejectedError,
    Range,
    RangeParameter,
    VectorLayerInfo,
    parameter_kinds,
)
from qgis_sdk.providers import Provider
from qgis_sdk.ui.form_fields import coerce_values, form_fields

KIND_NAMES = (
    "layer",
    "crs",
    "metres",
    "file",
    "directory",
    "field",
    "range",
    "colour",
    "enum",
    "string",
    "integer",
    "number",
    "boolean",
)


def test_the_registry_lists_every_kind_with_all_four_host_faces() -> None:
    kinds = parameter_kinds()

    assert tuple(kinds) == KIND_NAMES
    for kind in kinds.values():
        assert isinstance(kind, ParameterKind)
        assert kind.widget, kind.name
        assert kind.processing.startswith("QgsProcessingParameter"), kind.name
        assert kind.expected, kind.name
        assert kind.accepted, kind.name


def test_the_registry_is_read_only() -> None:
    with pytest.raises(TypeError):
        parameter_kinds()["layer"] = None  # type: ignore[index]


@pytest.mark.parametrize(
    ("annotation", "kind"),
    [
        (LayerInput, "layer"),
        (CrsInput, "crs"),
        (Metres, "metres"),
        (FileInput(), "file"),
        (FileInput(filters=("*.gpkg", "*.shp")), "file"),
        (Annotated[FileRef, FileParameter()], "file"),
        (DirectoryInput(), "directory"),
        (Annotated[FileRef, DirectoryParameter()], "directory"),
        (FieldInput(of="layer"), "field"),
        (Annotated[str, FieldParameter(of="layer")], "field"),
        (Range(0, 10), "range"),
        (Annotated[int, RangeParameter(minimum=0, maximum=10)], "range"),
        (Colour(), "colour"),
        (Annotated[str, ColourParameter()], "colour"),
        (Literal["fast", "safe"], "enum"),
        (str, "string"),
        (int, "integer"),
        (float, "number"),
        (bool, "boolean"),
    ],
)
def test_every_spelling_maps_to_its_kind(annotation, kind) -> None:
    assert parameter_kind("f.x", annotation) == kind


@pytest.mark.parametrize(
    ("annotation", "message"),
    [
        (Annotated[str, FileParameter()], "a file input stores a FileRef"),
        (Annotated[str, DirectoryParameter()], "a directory input stores a FileRef"),
        (Annotated[int, FieldParameter(of="layer")], "a field input must be a str"),
        (
            Annotated[str, RangeParameter(minimum=0, maximum=1)],
            "a range must be a number",
        ),
        (Annotated[int, ColourParameter()], "a colour input must be a str"),
        (Literal[1, 2], "enum choices must be strings"),
        (Literal["a", 1], "enum choices must be strings"),
        (FileRef, "a FileRef input needs FileInput"),
        (Annotated[str, object()], "unknown parameter marker"),
    ],
)
def test_a_marker_on_a_type_it_does_not_fit_is_refused(annotation, message) -> None:
    with pytest.raises(QgisSdkDeclarationError, match=message):
        parameter_kind("f.x", annotation)


def test_a_range_refuses_inverted_or_missing_bounds() -> None:
    with pytest.raises(ValueError, match="minimum .* below .* maximum"):
        RangeParameter(minimum=10, maximum=0)
    with pytest.raises(ValueError, match="a step is positive"):
        Range(0, 10, step=0)


def test_a_file_filter_is_a_glob_tuple_in_declaration_order() -> None:
    assert FileParameter(filters=["*.gpkg", "*.shp"]).filters == ("*.gpkg", "*.shp")
    with pytest.raises(ValueError, match="a file filter is a glob"):
        FileParameter(filters=("gpkg",))


def test_a_field_input_names_the_layer_input_it_belongs_to() -> None:
    with pytest.raises(ValueError, match="names the layer input"):
        FieldParameter(of="")


# -- the describer ----------------------------------------------------------


def _provider() -> Provider:
    return Provider(id="test", title="Test provider")


def test_the_describer_reports_the_new_kinds() -> None:
    provider = _provider()

    @provider.algorithm
    def classify(
        ctx: AlgorithmContext,
        layer: LayerInput,
        attribute: FieldInput(of="layer"),
        source: FileInput(filters=("*.csv",)),
        folder: DirectoryInput(),
        weight: Range(0.0, 1.0),
        fill: Colour(),
        mode: Literal["fast", "safe"],
    ) -> VectorLayerInfo: ...

    description = describe_algorithm(classify)

    assert description.kinds == {
        "layer": "layer",
        "attribute": "field",
        "source": "file",
        "folder": "directory",
        "weight": "range",
        "fill": "colour",
        "mode": "enum",
    }
    properties = description.inputs_schema["properties"]
    assert properties["attribute"] == {
        "type": "string",
        "x-qgis-sdk": {"kind": "field", "of": "layer"},
    }
    assert properties["source"]["title"] == "FileRef"
    assert properties["source"]["x-qgis-sdk"] == {"kind": "file", "filters": ["*.csv"]}
    assert properties["folder"]["x-qgis-sdk"] == {"kind": "directory"}
    assert properties["weight"] == {
        "type": "number",
        "minimum": 0.0,
        "maximum": 1.0,
        "x-qgis-sdk": {"kind": "range"},
    }
    assert properties["fill"] == {"type": "string", "x-qgis-sdk": {"kind": "colour"}}
    assert properties["mode"] == {"enum": ["fast", "safe"]}


def test_a_field_input_of_an_unknown_or_non_layer_input_is_refused() -> None:
    """The provider validates before it commits, so the refusal is at decoration."""
    provider = _provider()

    with pytest.raises(QgisSdkDeclarationError, match="attribute: of='layer' names no"):

        @provider.algorithm
        def orphan(
            ctx: AlgorithmContext, attribute: FieldInput(of="layer")
        ) -> VectorLayerInfo: ...

    with pytest.raises(
        QgisSdkDeclarationError, match="attribute: of='name' names a string"
    ):

        @provider.algorithm
        def misparented(
            ctx: AlgorithmContext, name: str, attribute: FieldInput(of="name")
        ) -> VectorLayerInfo: ...


def test_the_wire_annotation_rides_on_actions_too() -> None:
    @plugin(id="kinds", title="Kinds")
    class Kinds:
        @action
        def paint(
            self, layer: LayerInput, fill: Colour(), weight: Range(1, 5)
        ) -> None: ...

    (paint,) = describe_plugin(Kinds).actions
    properties = paint.request["properties"]

    assert properties["layer"] == {"type": "string", "x-qgis-sdk": {"kind": "layer"}}
    assert properties["fill"]["x-qgis-sdk"] == {"kind": "colour"}
    assert properties["weight"] == {
        "type": "integer",
        "minimum": 1,
        "maximum": 5,
        "x-qgis-sdk": {"kind": "range"},
    }


# -- values at invocation ------------------------------------------------------


def _ref(kind: str = "file") -> FileRef:
    return FileRef(id="a" * 16, name="x", operations=("read",), kind=kind)


def test_invoke_checks_the_new_kinds_before_running_anything() -> None:
    provider = _provider()
    calls = []

    @provider.algorithm
    def classify(
        ctx: AlgorithmContext,
        source: FileInput(),
        folder: DirectoryInput(),
        weight: Range(0.0, 1.0),
        fill: Colour(),
        mode: Literal["fast", "safe"],
    ) -> VectorLayerInfo:
        calls.append(1)
        raise AssertionError("never reached")

    from qgis_sdk.core import PluginContext, ResourceScope
    from qgis_sdk.testing import RecordingNotifications

    scope = ResourceScope()
    ctx = PluginContext(notifications=RecordingNotifications(scope), scope=scope)

    with pytest.raises(QgisSdkAlgorithmRejectedError) as refused:
        invoke(
            classify,
            ctx,
            source="/tmp/x",
            folder=_ref("file"),
            weight=2.0,
            fill="red",
            mode="slow",
        )

    reasons = refused.value.reasons
    assert "source must be a FileRef, not str" in reasons
    assert "folder must be a directory FileRef, not a file FileRef" in reasons
    assert "weight must be between 0.0 and 1.0" in reasons
    assert "fill must be a #RRGGBB or #RRGGBBAA colour" in reasons
    assert "mode must be one of fast, safe" in reasons
    assert calls == []


# -- the form rule reads the annotation from the schema ----------------------


def test_form_fields_derive_the_widget_from_the_wire_annotation() -> None:
    @plugin(id="kinds", title="Kinds")
    class Kinds:
        @action
        def paint(
            self,
            layer: LayerInput,
            attribute: FieldInput(of="layer"),
            source: FileInput(filters=("*.csv",)),
            folder: DirectoryInput(),
            weight: Range(0, 5),
            fill: Colour(),
            mode: Literal["fast", "safe"],
        ) -> None: ...

    (paint,) = describe_plugin(Kinds).actions

    specs = form_fields(paint)

    assert [(spec.name, spec.widget) for spec in specs] == [
        ("layer", "layer"),
        ("attribute", "field"),
        ("source", "file"),
        ("folder", "directory"),
        ("weight", "range"),
        ("fill", "colour"),
        ("mode", "choice"),
    ]
    by_name = {spec.name: spec for spec in specs}
    assert by_name["attribute"].details == {"of": "layer"}
    assert by_name["source"].details == {"filters": ("*.csv",)}
    assert by_name["weight"].details == {"minimum": 0, "maximum": 5}
    assert by_name["mode"].choices == ("fast", "safe")
    assert by_name["source"].to_dict()["details"] == {"filters": ["*.csv"]}


def test_coercion_returns_the_models_the_handler_declared() -> None:
    @plugin(id="kinds", title="Kinds")
    class Kinds:
        @action
        def paint(
            self,
            source: FileInput(),
            folder: DirectoryInput(),
            weight: Range(0, 5),
            fill: Colour(),
            layer: LayerInput,
            attribute: FieldInput(of="layer"),
        ) -> None: ...

    (paint,) = describe_plugin(Kinds).actions
    directory = _ref("directory")

    values = coerce_values(
        paint,
        {
            "source": _ref().to_wire(),
            "folder": directory,
            "weight": "3",
            "fill": "#FF0000",
            "layer": "layer-1",
            "attribute": "name",
        },
    )

    assert values == {
        "source": _ref(),
        "folder": directory,
        "weight": 3,
        "fill": "#ff0000",
        "layer": "layer-1",
        "attribute": "name",
    }

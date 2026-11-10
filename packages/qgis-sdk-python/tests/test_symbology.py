"""Symbology, labelling and the style manager: models, the fake and the wire.

TASK-93. The surface is curated on purpose (decision-16: do not mirror the
renderer API), so these tests pin three things: what the four renderers and the
three symbols are allowed to hold, that a description survives the wire and the
fake unchanged, and that the catalogue carries the seven new operations under
four named grants - three of which are destructive, because each replaces how a
layer is drawn.

The QGIS half is not here: ``tests/services/test_symbology_contract.py`` holds
both backends to one contract, and the native-only edges live in
``tests/services/test_native_styles_symbology.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from qgis_sdk.bridge import Dispatcher
from qgis_sdk.bridge.authority import HostAuthority
from qgis_sdk.bridge.host import (
    HOST_OPERATIONS,
    HostServices,
    granted_operations,
    host_grant_names,
    register_host_operations,
)
from qgis_sdk.bridge.protocol import BRIDGE_PROTOCOL_VERSION
from qgis_sdk.core import ResourceScope
from qgis_sdk.files import FilesService
from qgis_sdk.models import (
    LABELLING,
    RENDERER,
    RENDERER_KIND_NAMES,
    STYLE_ENTRY,
    STYLE_FORMATS,
    STYLE_MANAGER_KINDS,
    SYMBOL_KINDS,
    CategorizedRenderer,
    Category,
    FillSymbol,
    GraduatedClass,
    GraduatedRenderer,
    Labelling,
    LineSymbol,
    MarkerSymbol,
    QgisSdkStyleTextError,
    QgisSdkUnsupportedCapabilityError,
    Rule,
    RuleBasedRenderer,
    SingleSymbolRenderer,
    StyleEntry,
    StyleText,
    labelling_from_wire,
    renderer_from_wire,
    style_entry_from_wire,
)
from qgis_sdk.models import symbology as models
from qgis_sdk.testing import (
    FakeLayers,
    FakeProject,
    FakeStyles,
    OtherLayerDeclaration,
    RecordingNotifications,
    VectorLayerDeclaration,
)

ORIGIN = "qgis://desktop"
POINTS = Path("fixtures/points.geojson")
LINES = Path("fixtures/lines.geojson")
POLYGONS = Path("fixtures/areas.geojson")
MESH = Path("fixtures/lagoon.2dm")


def _marker(color: str = "#ff0000", **detail: Any) -> MarkerSymbol:
    return MarkerSymbol(color=color, **detail)


# -- the vocabulary -----------------------------------------------------------


def test_the_four_renderer_kinds_are_named_in_wire_order() -> None:
    assert RENDERER_KIND_NAMES == (
        "single_symbol",
        "categorized",
        "graduated",
        "rule_based",
    )


def test_the_three_symbol_kinds_are_named_in_wire_order() -> None:
    assert SYMBOL_KINDS == ("marker", "line", "fill")


def test_every_renderer_has_a_titled_schema_and_a_model() -> None:
    assert set(models.RENDERER_SCHEMAS) == set(RENDERER_KIND_NAMES)
    assert set(models.SYMBOL_SCHEMAS) == set(SYMBOL_KINDS)
    for kind, schema in models.RENDERER_SCHEMAS.items():
        assert schema["properties"]["kind"] == {"enum": [kind]}
        assert schema["title"] in (
            "SingleSymbolRenderer",
            "CategorizedRenderer",
            "GraduatedRenderer",
            "RuleBasedRenderer",
        )
        assert issubclass(models.RENDERERS[kind], object)


def test_the_union_names_every_renderer_and_every_symbol() -> None:
    assert len(RENDERER["anyOf"]) == len(RENDERER_KIND_NAMES)
    assert len(models.SYMBOL["anyOf"]) == len(SYMBOL_KINDS)


# -- symbols ------------------------------------------------------------------


def test_a_colour_is_normalised_to_lower_case_hex() -> None:
    assert _marker("#FF0000").color == "#ff0000"
    assert FillSymbol("#AbCdEf").color == "#abcdef"


@pytest.mark.parametrize("value", ["red", "#ff000", "#ff00000", "ff0000", "#gggggg"])
def test_a_colour_that_is_not_hex_is_refused_where_it_is_declared(value: str) -> None:
    with pytest.raises(ValueError, match="#rrggbb"):
        _marker(value)


def test_a_size_is_positive_and_an_outline_may_be_absent() -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        _marker(size=0)
    assert _marker(outline_width=0).outline_width == 0.0


def test_a_marker_shape_is_one_the_sdk_models() -> None:
    assert models.MARKER_SHAPES == (
        "circle",
        "square",
        "diamond",
        "triangle",
        "star",
    )
    with pytest.raises(ValueError, match="marker shape"):
        _marker(shape="pentagon")


def test_every_symbol_round_trips_through_the_wire() -> None:
    for symbol in (
        MarkerSymbol("#ff0000", size=3.5, shape="star", outline_color="#0000ff"),
        LineSymbol("#00ff00", width=1.25),
        FillSymbol("#0000ff", outline_color="#ffffff", outline_width=0),
    ):
        wire = symbol.to_wire()
        assert models.symbol_from_wire(wire) == symbol
        assert wire["kind"] == symbol.kind


def test_a_renderer_names_the_symbol_kind_it_draws() -> None:
    assert models.symbol_kind(SingleSymbolRenderer(symbol=_marker())) == "marker"
    assert (
        models.symbol_kind(
            CategorizedRenderer(field="v", categories=(Category("a", "A", _marker()),))
        )
        == "marker"
    )
    assert (
        models.symbol_kind(
            GraduatedRenderer(
                field="v",
                classes=(GraduatedClass(0.0, 1.0, "0-1", LineSymbol("#00ff00")),),
            )
        )
        == "line"
    )
    assert (
        models.symbol_kind(
            RuleBasedRenderer(rules=(Rule("v = 1", "One", FillSymbol("#0000ff")),))
        )
        == "fill"
    )


@pytest.mark.parametrize(
    ("renderer", "geometry", "allowed"),
    [
        (SingleSymbolRenderer(symbol=_marker()), "point", True),
        (SingleSymbolRenderer(symbol=_marker()), "line", False),
        (SingleSymbolRenderer(symbol=LineSymbol("#00ff00")), "line", True),
        (SingleSymbolRenderer(symbol=FillSymbol("#0000ff")), "polygon", True),
        (SingleSymbolRenderer(symbol=FillSymbol("#0000ff")), "point", False),
        # A kind with no symbol of its own is not this rule's business.
        (SingleSymbolRenderer(symbol=_marker()), "mesh", True),
    ],
)
def test_a_symbol_is_checked_against_the_geometry_it_would_draw(
    renderer: Any, geometry: str, allowed: bool
) -> None:
    reason = models.symbol_fits_geometry(renderer, geometry)

    assert (reason is None) is allowed, reason
    if reason is not None:
        assert geometry in reason, reason


def test_a_symbol_of_an_unknown_kind_is_refused_by_name() -> None:
    with pytest.raises(ValueError, match="marker, line, fill"):
        models.symbol_from_wire({"kind": "picture"})


# -- renderers ----------------------------------------------------------------


def test_a_single_symbol_renderer_round_trips() -> None:
    renderer = SingleSymbolRenderer(symbol=_marker())
    assert renderer_from_wire(renderer.to_wire()) == renderer
    assert renderer.to_wire()["kind"] == "single_symbol"


def test_a_categorized_renderer_round_trips() -> None:
    renderer = CategorizedRenderer(
        field="kind",
        categories=(
            Category(value="a", label="A", symbol=_marker("#ff0000")),
            Category(value="b", label="B", symbol=_marker("#0000ff")),
        ),
    )
    assert renderer_from_wire(renderer.to_wire()) == renderer
    assert [category.value for category in renderer.categories] == ["a", "b"]


def test_a_categorized_renderer_names_each_value_once() -> None:
    with pytest.raises(ValueError, match="names each value once"):
        CategorizedRenderer(
            field="kind",
            categories=(
                Category("a", "A", _marker()),
                Category("a", "A again", _marker()),
            ),
        )


def test_a_categorized_renderer_draws_at_least_one_category() -> None:
    with pytest.raises(ValueError, match="at least one category"):
        CategorizedRenderer(field="kind", categories=())


def test_a_graduated_renderer_round_trips_with_its_mode() -> None:
    renderer = GraduatedRenderer(
        field="value",
        mode="jenks",
        classes=(
            GraduatedClass(0.0, 1.0, "0-1", _marker("#ffffcc")),
            GraduatedClass(1.0, 2.0, "1-2", _marker("#e31a1c")),
        ),
    )
    assert renderer_from_wire(renderer.to_wire()) == renderer
    assert renderer.mode == "jenks"


def test_a_graduated_class_runs_upwards() -> None:
    with pytest.raises(ValueError, match="lower to its upper"):
        GraduatedClass(2.0, 1.0, "backwards", _marker())


def test_graduated_classes_are_ordered() -> None:
    with pytest.raises(ValueError, match="run upwards"):
        GraduatedRenderer(
            field="value",
            classes=(
                GraduatedClass(2.0, 3.0, "2-3", _marker()),
                GraduatedClass(0.0, 1.0, "0-1", _marker()),
            ),
        )


def test_a_graduated_mode_is_one_the_sdk_names() -> None:
    assert models.GRADUATED_MODES == (
        "equal_interval",
        "quantile",
        "jenks",
        "std_dev",
        "pretty",
        # An answer, not a request: QGIS reports it for a hand-edited renderer.
        "custom",
    )
    with pytest.raises(ValueError, match="graduated mode"):
        GraduatedRenderer(
            field="value",
            classes=(GraduatedClass(0.0, 1.0, "0-1", _marker()),),
            mode="kmeans",
        )


def test_a_custom_classification_is_a_mode_a_caller_may_declare() -> None:
    """The ranges are given either way; ``custom`` says QGIS will not recompute."""
    renderer = GraduatedRenderer(
        field="value",
        mode="custom",
        classes=(GraduatedClass(0.0, 2.5, "0-2.5", _marker()),),
    )

    assert renderer_from_wire(renderer.to_wire()).mode == "custom"


def test_a_rule_based_renderer_round_trips_with_its_rules() -> None:
    renderer = RuleBasedRenderer(
        rules=(
            Rule(filter="value > 2", label="High", symbol=_marker("#e31a1c")),
            Rule(filter="value <= 2", label="Low", symbol=_marker(), enabled=False),
        )
    )
    assert renderer_from_wire(renderer.to_wire()) == renderer
    assert [rule.enabled for rule in renderer.rules] == [True, False]


def test_a_rule_needs_an_expression() -> None:
    with pytest.raises(ValueError, match="not blank"):
        Rule(filter="   ", label="Everything", symbol=_marker())


def test_a_renderer_of_an_unknown_kind_is_refused_naming_the_four() -> None:
    with pytest.raises(ValueError, match="single_symbol"):
        renderer_from_wire({"kind": "heatmap", "radius": 12})


# -- labelling ----------------------------------------------------------------


def test_labelling_round_trips_and_switches_off() -> None:
    on = Labelling(enabled=True, field="name", size=12, color="#112233")
    off = Labelling()

    assert labelling_from_wire(on.to_wire()) == on
    assert labelling_from_wire(off.to_wire()) == off
    assert off.field is None


def test_labelling_on_needs_the_field_it_labels() -> None:
    with pytest.raises(ValueError, match="field to label"):
        Labelling(enabled=True)
    with pytest.raises(ValueError, match="field to label"):
        Labelling(enabled=True, field="   ")


# -- the style manager --------------------------------------------------------


def test_a_style_entry_names_a_kind_the_manager_holds() -> None:
    assert STYLE_MANAGER_KINDS == ("symbol", "color_ramp", "label_settings")
    assert style_entry_from_wire(
        StyleEntry("circle", "symbol").to_wire()
    ) == StyleEntry("circle", "symbol")
    with pytest.raises(ValueError, match="style entry"):
        StyleEntry("circle", "gradient")


def test_style_text_names_its_dialect() -> None:
    assert STYLE_FORMATS == ("qml", "sld")
    assert StyleText(format="sld", text="<StyledLayerDescriptor/>").to_wire() == {
        "format": "sld",
        "text": "<StyledLayerDescriptor/>",
    }
    with pytest.raises(ValueError, match="style format"):
        StyleText(format="json", text="{}")


def test_the_style_manager_schema_is_one_object() -> None:
    assert STYLE_ENTRY["properties"]["kind"]["enum"] == list(STYLE_MANAGER_KINDS)
    assert LABELLING["properties"]["field"]["anyOf"][1] == {"type": "null"}


# -- the fake -----------------------------------------------------------------


@dataclass
class _Styles:
    """The dimensions a style backend is asked about in this module."""

    scope: ResourceScope
    layers: FakeLayers
    styles: FakeStyles

    def __post_init__(self) -> None:
        self.layers.register(
            VectorLayerDeclaration(
                POINTS,
                name="points",
                geometry_type="point",
                field_names=("id", "value"),
            )
        )
        self.layers.register(
            VectorLayerDeclaration(
                LINES, name="lines", geometry_type="line", field_names=("id", "value")
            )
        )
        self.layers.register(
            VectorLayerDeclaration(
                POLYGONS,
                name="areas",
                geometry_type="polygon",
                field_names=("id", "value"),
            )
        )
        self.layers.register_layer(
            OtherLayerDeclaration(
                MESH,
                name="lagoon",
                kind="mesh",
                detail={"vertex_count": 3, "face_count": 1, "group_count": 1},
            )
        )


def _scope() -> tuple[ResourceScope, FakeLayers, FakeStyles]:
    scope = ResourceScope()
    layers = FakeLayers(scope)
    styles = FakeStyles(layers, scope)
    holder = _Styles(scope, layers, styles)
    assert holder.styles is styles
    return scope, layers, styles


def test_a_fresh_layer_answers_the_renderer_its_geometry_implies() -> None:
    scope, layers, styles = _scope()
    try:
        for source, symbol_kind in (
            (POINTS, "marker"),
            (LINES, "line"),
            (POLYGONS, "fill"),
        ):
            info = layers.open_vector(source)
            renderer = styles.symbology(info.id)
            assert isinstance(renderer, SingleSymbolRenderer), renderer
            assert renderer.symbol.kind == symbol_kind
    finally:
        scope.close()


@pytest.mark.parametrize(
    "renderer",
    [
        SingleSymbolRenderer(symbol=_marker()),
        CategorizedRenderer(field="value", categories=(Category("a", "A", _marker()),)),
        GraduatedRenderer(
            field="value", classes=(GraduatedClass(0.0, 1.0, "0-1", _marker()),)
        ),
        RuleBasedRenderer(rules=(Rule("value > 1", "High", _marker()),)),
    ],
    ids=RENDERER_KIND_NAMES,
)
def test_the_fake_answers_back_the_renderer_it_was_given(renderer: Any) -> None:
    scope, layers, styles = _scope()
    try:
        info = layers.open_vector(POINTS)
        styles.set_symbology(info.id, renderer)
        assert styles.symbology(info.id) == renderer
    finally:
        scope.close()


def test_a_symbol_its_geometry_cannot_draw_is_refused_by_name() -> None:
    scope, layers, styles = _scope()
    try:
        areas = layers.open_vector(POLYGONS)
        with pytest.raises(Exception) as error:
            styles.set_symbology(areas.id, SingleSymbolRenderer(symbol=_marker()))
        assert "marker" in str(error.value)
        assert "polygon" in str(error.value)
    finally:
        scope.close()


def test_a_mesh_is_not_something_a_renderer_can_be_set_on() -> None:
    scope, layers, styles = _scope()
    try:
        mesh = layers.open_mesh(MESH)
        for call in (
            lambda: styles.symbology(mesh.id),
            lambda: styles.set_symbology(
                mesh.id, SingleSymbolRenderer(symbol=_marker())
            ),
            lambda: styles.labelling(mesh.id),
            lambda: styles.set_labelling(mesh.id, Labelling()),
            lambda: styles.export_style(mesh.id, "qml"),
        ):
            with pytest.raises(QgisSdkUnsupportedCapabilityError) as error:
                call()
            assert "mesh" in str(error.value)
    finally:
        scope.close()


def test_a_fill_symbol_round_trips_on_a_polygon_layer() -> None:
    scope, layers, styles = _scope()
    try:
        areas = layers.open_vector(POLYGONS)
        renderer = SingleSymbolRenderer(
            symbol=FillSymbol("#0000ff", outline_color="#ffffff", outline_width=0.0)
        )
        styles.set_symbology(areas.id, renderer)
        assert styles.symbology(areas.id) == renderer
    finally:
        scope.close()


def test_labelling_round_trips_on_the_fake() -> None:
    scope, layers, styles = _scope()
    try:
        info = layers.open_vector(POINTS)
        assert styles.labelling(info.id).enabled is False
        styles.set_labelling(info.id, Labelling(enabled=True, field="value", size=9))
        assert styles.labelling(info.id) == Labelling(
            enabled=True, field="value", size=9
        )
        styles.set_labelling(info.id, Labelling())
        assert styles.labelling(info.id).enabled is False
    finally:
        scope.close()


def test_the_fake_round_trips_its_own_style_document() -> None:
    scope, layers, styles = _scope()
    try:
        info = layers.open_vector(POINTS)
        renderer = CategorizedRenderer(
            field="value",
            categories=(Category("a", "A", _marker("#ff0000")),),
        )
        styles.set_symbology(info.id, renderer)
        styles.set_labelling(info.id, Labelling(enabled=True, field="value"))

        for format in STYLE_FORMATS:
            text = styles.export_style(info.id, format)
            assert text.format == format
            styles.import_style(info.id, text.text, format)

        assert styles.symbology(info.id) == renderer
        assert styles.labelling(info.id).field == "value"
    finally:
        scope.close()


def test_style_text_of_another_dialect_is_refused() -> None:
    scope, layers, styles = _scope()
    try:
        info = layers.open_vector(POINTS)
        qml = styles.export_style(info.id, "qml")
        with pytest.raises(QgisSdkStyleTextError) as error:
            styles.import_style(info.id, qml.text, "sld")
        assert error.value.format == "sld"
        assert error.value.code == "style_text_rejected"
    finally:
        scope.close()


def test_style_text_that_is_not_a_document_is_refused() -> None:
    scope, layers, styles = _scope()
    try:
        info = layers.open_vector(POINTS)
        with pytest.raises(QgisSdkStyleTextError):
            styles.import_style(info.id, "<not json>", "qml")
        with pytest.raises(QgisSdkStyleTextError):
            styles.import_style(info.id, '{"something": "else"}', "qml")
    finally:
        scope.close()


def test_the_style_manager_lists_by_kind() -> None:
    scope = ResourceScope()
    try:
        layers = FakeLayers(scope)
        styles = FakeStyles(
            layers,
            scope,
            styles=(
                StyleEntry("circle", "symbol"),
                StyleEntry("square", "symbol"),
                StyleEntry("Blues", "color_ramp"),
            ),
        )
        assert [entry.name for entry in styles.list_styles("symbol")] == [
            "circle",
            "square",
        ]
        assert [entry.name for entry in styles.list_styles()] == [
            "circle",
            "square",
            "Blues",
        ]
        with pytest.raises(ValueError, match="style manager kind"):
            styles.list_styles("gradient")
    finally:
        scope.close()


def test_a_style_operation_after_the_scope_closes_is_refused() -> None:
    from qgis_sdk.models import QgisSdkScopeClosedError

    scope, layers, styles = _scope()
    info = layers.open_vector(POINTS)
    scope.close()
    with pytest.raises(QgisSdkScopeClosedError):
        styles.symbology(info.id)


# -- the host surface ---------------------------------------------------------


def test_the_catalogue_gains_seven_operations_under_four_grants() -> None:
    by_id = {operation.id: operation for operation in HOST_OPERATIONS}

    assert {
        "symbology.get": "symbology.read",
        "symbology.set": "symbology.write",
        "labelling.get": "symbology.read",
        "labelling.set": "symbology.write",
        "styles.list": "styles.read",
        "styles.export": "styles.read",
        "styles.import": "styles.write",
    } == {
        name: by_id[name].grant
        for name in (
            "symbology.get",
            "symbology.set",
            "labelling.get",
            "labelling.set",
            "styles.list",
            "styles.export",
            "styles.import",
        )
    }
    for grant in ("symbology.read", "symbology.write", "styles.read", "styles.write"):
        assert grant in host_grant_names()


def test_the_set_operations_are_the_ones_that_replace_a_style() -> None:
    destructive = {
        operation.id for operation in HOST_OPERATIONS if operation.destructive
    }
    for operation in (
        "styles.apply",
        "symbology.set",
        "labelling.set",
        "styles.import",
    ):
        assert operation in destructive, operation
    for operation in (
        "symbology.get",
        "labelling.get",
        "styles.list",
        "styles.export",
        "layers.list",
    ):
        assert operation not in destructive, operation


def test_a_read_grant_does_not_select_a_write_operation() -> None:
    """The vocabulary is what narrows a page, so read must not imply write."""
    read_only = granted_operations(["symbology.read", "styles.read"])
    assert "symbology.get" in read_only
    assert "labelling.get" in read_only
    assert "styles.export" in read_only
    for operation in ("symbology.set", "labelling.set", "styles.import"):
        assert operation not in read_only


def test_the_wire_result_of_a_get_is_a_titled_union() -> None:
    by_id = {operation.id: operation for operation in HOST_OPERATIONS}
    assert by_id["symbology.get"].result is RENDERER
    assert by_id["labelling.get"].result is LABELLING
    assert by_id["symbology.set"].result_name is None
    assert by_id["styles.export"].result_name == "StyleText"


@dataclass
class _Settings:
    def get(self, key: str, default: str | None = None) -> str | None:
        return default


def _bridge(
    layers: FakeLayers, styles: FakeStyles, scope: ResourceScope, *, only: Any = None
) -> tuple[Dispatcher, HostAuthority]:
    authority = HostAuthority()
    services = HostServices(
        layers=layers,
        project=FakeProject(layers, scope),
        settings=_Settings(),  # type: ignore[arg-type]
        styles=styles,
        notifications=RecordingNotifications(scope),
        authority=authority,
        files=FilesService(authority, scope, owner="plugin:demo"),
    )
    dispatcher = Dispatcher(
        description={"schema_version": 1, "id": "demo.plugin", "title": "Demo"},
        authorize=lambda binding, operation: True,
    )
    register_host_operations(dispatcher, services, only=only)
    return dispatcher, authority


def _call(dispatcher: Dispatcher, operation: str, payload: dict) -> dict:
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    return dispatcher.dispatch(
        binding,
        {
            "protocol": BRIDGE_PROTOCOL_VERSION,
            "call_id": "call",
            "operation": operation,
            "payload": payload,
        },
    )


def test_a_page_round_trips_a_renderer_across_the_wire() -> None:
    scope, layers, styles = _scope()
    try:
        info = layers.open_vector(POINTS)
        dispatcher, _ = _bridge(layers, styles, scope)
        renderer = CategorizedRenderer(
            field="value",
            categories=(
                Category("a", "A", _marker("#ff0000")),
                Category("b", "B", _marker("#0000ff")),
            ),
        )

        answered = _call(
            dispatcher,
            "symbology.set",
            {"layer_id": info.id, "renderer": renderer.to_wire()},
        )
        assert answered["ok"] is True, answered

        read = _call(dispatcher, "symbology.get", {"layer_id": info.id})
        assert read["ok"] is True, read
        assert read["value"]["kind"] == "categorized"
        assert read["value"]["field"] == "value"
        assert renderer_from_wire(read["value"]) == renderer
    finally:
        scope.close()


def _points_declaration() -> VectorLayerDeclaration:
    return VectorLayerDeclaration(
        POINTS,
        name="points",
        geometry_type="point",
        field_names=("id", "value"),
    )


def test_a_page_reads_a_labelling_and_the_style_list() -> None:
    scope = ResourceScope()
    try:
        layers = FakeLayers(scope)
        layers.register(_points_declaration())
        styles = FakeStyles(layers, scope, styles=(StyleEntry("circle", "symbol"),))
        info = layers.open_vector(POINTS)
        styles.set_labelling(info.id, Labelling(enabled=True, field="value"))
        dispatcher, _ = _bridge(layers, styles, scope)

        labelling = _call(dispatcher, "labelling.get", {"layer_id": info.id})
        assert labelling["ok"] is True, labelling
        assert labelling_from_wire(labelling["value"]) == Labelling(
            enabled=True, field="value"
        )

        listed = _call(dispatcher, "styles.list", {})
        assert listed["ok"] is True, listed
        assert listed["value"]["items"] == [{"name": "circle", "kind": "symbol"}]

        refused = _call(dispatcher, "styles.list", {"kind": "gradient"})
        assert refused["ok"] is False, refused
    finally:
        scope.close()


def test_a_renderer_of_an_unknown_kind_never_reaches_a_handler() -> None:
    scope, layers, styles = _scope()
    try:
        info = layers.open_vector(POINTS)
        dispatcher, _ = _bridge(layers, styles, scope)
        refused = _call(
            dispatcher,
            "symbology.set",
            {"layer_id": info.id, "renderer": {"kind": "heatmap"}},
        )
        assert refused["ok"] is False, refused
        assert refused["error"]["code"] == "invalid_payload"
    finally:
        scope.close()


def test_a_host_without_the_write_grant_cannot_reach_a_set() -> None:
    """``only=`` is what a granted surface becomes: the operation is absent."""
    scope, layers, styles = _scope()
    try:
        info = layers.open_vector(POINTS)
        dispatcher, _ = _bridge(
            layers,
            styles,
            scope,
            only=list(granted_operations(["symbology.read", "styles.read"])),
        )

        read = _call(dispatcher, "symbology.get", {"layer_id": info.id})
        assert read["ok"] is True, read

        refused = _call(
            dispatcher,
            "symbology.set",
            {
                "layer_id": info.id,
                "renderer": SingleSymbolRenderer(_marker()).to_wire(),
            },
        )
        assert refused["ok"] is False, refused
    finally:
        scope.close()

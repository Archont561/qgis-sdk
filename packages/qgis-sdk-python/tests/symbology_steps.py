"""Steps for the symbology feature: one fake runtime, one layer, one renderer.

The fake answers from the description it was handed, so what these scenarios
prove is that the *models* carry a renderer, a symbol and a labelling whole -
the numbers a page reads are the numbers a plugin wrote. The QGIS dialects are
not here on purpose: the fake round-trips its own document, and the contract
suite is where real QML and SLD are proven against a real QGIS.

The one thing that is not modelled here is QGIS itself, so the "unmodelled
renderer" scenario uses the wire reader, which is the path every backend shares:
a page that sent a heatmap renderer is refused by the same list on either side.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from pytest_bdd import given, parsers, then, when
from qgis_sdk.core import ResourceScope
from qgis_sdk.models import (
    QgisSdkUnsupportedCapabilityError,
    StyleEntry,
    renderer_from_wire,
)
from qgis_sdk.models.symbology import (
    CategorizedRenderer,
    Category,
    GraduatedClass,
    GraduatedRenderer,
    Labelling,
    MarkerSymbol,
    Rule,
    RuleBasedRenderer,
    SingleSymbolRenderer,
)
from qgis_sdk.testing import (
    FakeLayers,
    FakeStyles,
    OtherLayerDeclaration,
    VectorLayerDeclaration,
)

REFERENCE = Path(__file__).resolve().parent / "fixtures" / "reference"
POINTS = REFERENCE / "points.geojson"
MESH = REFERENCE / "lagoon.2dm"
#: The fields the declared layer carries: ``kind`` and ``name`` are the ones the
#: categorization and the labelling name, ``value`` the one a graduation bands.
POINT_FIELDS = ("id", "value", "kind", "name")


@dataclass
class SymbologyWorld:
    """The fake runtime the symbology scenarios arrange and observe."""

    scope: ResourceScope
    layers: FakeLayers
    styles: FakeStyles
    layer_id: str | None = None
    mesh_id: str | None = None
    renderer: object | None = None
    labelling: object | None = None
    export: object | None = None
    entries: tuple[StyleEntry, ...] = ()
    wire_kinds: tuple[str, ...] = ()
    refused: Exception | None = None
    entries_by_kind: dict[str, int] = field(default_factory=dict)


def _runtime() -> SymbologyWorld:
    scope = ResourceScope()
    layers = FakeLayers(scope)
    layers.register(
        VectorLayerDeclaration(
            POINTS,
            name="points",
            geometry_type="point",
            field_names=POINT_FIELDS,
            crs="EPSG:4326",
        )
    )
    layers.register_layer(
        OtherLayerDeclaration(
            MESH,
            name="lagoon",
            kind="mesh",
            detail={"vertex_count": 3, "face_count": 1, "group_count": 1},
        )
    )
    styles = FakeStyles(
        layers,
        scope,
        styles=(
            StyleEntry(name="circle", kind="symbol"),
            StyleEntry(name="Blues", kind="color_ramp"),
            StyleEntry(name="street", kind="label_settings"),
        ),
    )
    return SymbologyWorld(scope=scope, layers=layers, styles=styles)


def _points(world: SymbologyWorld) -> str:
    if world.layer_id is None:
        world.layer_id = world.layers.open_vector(POINTS).id
    return world.layer_id


def _marker(color: str, size: float = 2.0, outline: str = "#000000") -> MarkerSymbol:
    return MarkerSymbol(color=color, size=size, outline_color=outline)


# -- background ---------------------------------------------------------------


@given(
    "a runtime with symbology, labelling and a style manager", target_fixture="world"
)
def runtime() -> SymbologyWorld:
    """One fake runtime: a declared point layer, a mesh, and three style entries."""
    return _runtime()


@given(parsers.parse('the points are labelled by "{field}"'))
def points_labelled(world: SymbologyWorld, field: str) -> None:
    world.styles.set_labelling(_points(world), Labelling(enabled=True, field=field))


# -- a fresh layer ------------------------------------------------------------


@when("the plugin opens the reference points")
def open_points(world: SymbologyWorld) -> None:
    world.renderer = world.styles.symbology(_points(world))


@then("the layer is drawn by a single symbol renderer")
def single_symbol(world: SymbologyWorld) -> None:
    assert isinstance(world.renderer, SingleSymbolRenderer), world.renderer


@then("its symbol is a marker")
def its_symbol_is_marker(world: SymbologyWorld) -> None:
    assert world.renderer.symbol.kind == "marker", world.renderer.symbol


# -- categorized --------------------------------------------------------------


@when(parsers.parse('the plugin draws the points by category of "{field}"'))
def draw_categorized(world: SymbologyWorld, field: str) -> None:
    renderer = CategorizedRenderer(
        field=field,
        categories=(
            Category(value="a", label="A", symbol=_marker("#ff0000")),
            Category(value="b", label="B", symbol=_marker("#0000ff")),
        ),
    )
    world.styles.set_symbology(_points(world), renderer)
    world.renderer = world.styles.symbology(_points(world))


@then(parsers.parse('the layer is drawn by a categorized renderer on "{field}"'))
def categorized_on(world: SymbologyWorld, field: str) -> None:
    assert isinstance(world.renderer, CategorizedRenderer), world.renderer
    assert world.renderer.field == field


@then(
    parsers.parse(
        'it lists {count:d} categories, the first for value "{value}" in "{color}"'
    )
)
def category_listing(world: SymbologyWorld, count: int, value: str, color: str) -> None:
    categories = world.renderer.categories
    assert len(categories) == count, categories
    assert categories[0].value == value
    assert categories[0].symbol.color == color


# -- graduated ----------------------------------------------------------------


@when(
    parsers.parse('the plugin draws the points by graduated "{field}" in four classes')
)
def draw_graduated(world: SymbologyWorld, field: str) -> None:
    renderer = GraduatedRenderer(
        field=field,
        mode="quantile",
        classes=(
            GraduatedClass(
                lower=0.0, upper=1.0, label="0-1", symbol=_marker("#ffffcc")
            ),
            GraduatedClass(
                lower=1.0, upper=2.0, label="1-2", symbol=_marker("#fed976")
            ),
            GraduatedClass(
                lower=2.0, upper=3.0, label="2-3", symbol=_marker("#fd8d3c")
            ),
            GraduatedClass(
                lower=3.0, upper=4.0, label="3-4", symbol=_marker("#e31a1c")
            ),
        ),
    )
    world.styles.set_symbology(_points(world), renderer)
    world.renderer = world.styles.symbology(_points(world))


@then(parsers.parse('the layer is drawn by a graduated renderer on "{field}"'))
def graduated_on(world: SymbologyWorld, field: str) -> None:
    assert isinstance(world.renderer, GraduatedRenderer), world.renderer
    assert world.renderer.field == field


@then(parsers.parse("it lists {count:d} classes between {lower:f} and {upper:f}"))
def class_listing(
    world: SymbologyWorld, count: int, lower: float, upper: float
) -> None:
    classes = world.renderer.classes
    assert len(classes) == count, classes
    assert classes[0].lower == lower
    assert classes[-1].upper == upper


@then(parsers.parse('the renderer classifies by "{mode}"'))
def classified_by(world: SymbologyWorld, mode: str) -> None:
    assert world.renderer.mode == mode, world.renderer.mode


# -- rule-based ---------------------------------------------------------------


@when("the plugin draws the points by two rules")
def draw_rules(world: SymbologyWorld) -> None:
    renderer = RuleBasedRenderer(
        rules=(
            Rule(filter="value > 2", label="High", symbol=_marker("#e31a1c")),
            Rule(filter="value <= 2", label="Low", symbol=_marker("#2b8cbe")),
        )
    )
    world.styles.set_symbology(_points(world), renderer)
    world.renderer = world.styles.symbology(_points(world))


@then("the layer is drawn by a rule-based renderer")
def rule_based(world: SymbologyWorld) -> None:
    assert isinstance(world.renderer, RuleBasedRenderer), world.renderer


@then(parsers.parse('its rules filter on "{first}" and "{second}"'))
def rule_filters(world: SymbologyWorld, first: str, second: str) -> None:
    assert [rule.filter for rule in world.renderer.rules] == [first, second]


# -- the wire -----------------------------------------------------------------


@when("each renderer is described for the wire")
def describe_each_renderer(world: SymbologyWorld) -> None:
    renderers = (
        SingleSymbolRenderer(symbol=_marker("#ff0000")),
        CategorizedRenderer(
            field="kind", categories=(Category("a", "A", _marker("#111111")),)
        ),
        GraduatedRenderer(
            field="value",
            classes=(GraduatedClass(0.0, 1.0, "0-1", _marker("#222222")),),
        ),
        RuleBasedRenderer(rules=(Rule("value > 1", "High", _marker("#333333")),)),
    )
    world.wire_kinds = tuple(renderer.to_wire()["kind"] for renderer in renderers)
    # Every description a wire carries reads back as the model that wrote it.
    world.entries = tuple(renderer_from_wire(r.to_wire()) for r in renderers)


@then("the wire kinds read single_symbol, categorized, graduated and rule_based")
def wire_kinds(world: SymbologyWorld) -> None:
    assert world.wire_kinds == (
        "single_symbol",
        "categorized",
        "graduated",
        "rule_based",
    ), world.wire_kinds


# -- refusals -----------------------------------------------------------------


@when("the plugin asks for a symbology this SDK does not model")
def ask_for_unmodelled(world: SymbologyWorld) -> None:
    try:
        renderer_from_wire({"kind": "heatmap", "radius": 12})
    except ValueError as error:
        world.refused = error


@then("it is refused naming the four renderer kinds")
def refused_unmodelled(world: SymbologyWorld) -> None:
    assert isinstance(world.refused, ValueError), world.refused
    for kind in ("single_symbol", "categorized", "graduated", "rule_based"):
        assert kind in str(world.refused), str(world.refused)


@when(parsers.parse("the plugin asks a mesh for its symbology"))
def ask_mesh(world: SymbologyWorld) -> None:
    world.mesh_id = world.layers.open_mesh(MESH).id
    try:
        world.styles.symbology(world.mesh_id)
    except QgisSdkUnsupportedCapabilityError as error:
        world.refused = error


@then("the SDK refuses it as a mesh")
def refused_mesh(world: SymbologyWorld) -> None:
    assert isinstance(world.refused, QgisSdkUnsupportedCapabilityError), world.refused
    assert "mesh" in str(world.refused), str(world.refused)


# -- symbols ------------------------------------------------------------------


@when("the plugin draws the points with a 3.5 mm red marker outlined in blue")
def draw_marker(world: SymbologyWorld) -> None:
    world.styles.set_symbology(
        _points(world),
        SingleSymbolRenderer(
            symbol=MarkerSymbol(
                color="#ff0000",
                size=3.5,
                outline_color="#0000ff",
                outline_width=0.4,
            )
        ),
    )
    world.renderer = world.styles.symbology(_points(world))


@then(
    parsers.parse(
        'the symbol answers "{color}", {size:f} and an outline in "{outline}"'
    )
)
def symbol_answers(
    world: SymbologyWorld, color: str, size: float, outline: str
) -> None:
    symbol = world.renderer.symbol
    assert symbol.color == color
    assert symbol.size == size
    assert symbol.outline_color == outline


# -- labelling ----------------------------------------------------------------


@when(parsers.parse('the plugin labels the points by "{field}"'))
def label_points(world: SymbologyWorld, field: str) -> None:
    world.styles.set_labelling(_points(world), Labelling(enabled=True, field=field))
    world.labelling = world.styles.labelling(_points(world))


@then(parsers.parse('the layer\'s labelling is on, on "{field}", at {size:d} points'))
def labelling_on(world: SymbologyWorld, field: str, size: int) -> None:
    assert world.labelling.enabled is True
    assert world.labelling.field == field
    assert world.labelling.size == size


@when("the plugin switches labelling off")
def labelling_off(world: SymbologyWorld) -> None:
    world.styles.set_labelling(_points(world), Labelling())
    world.labelling = world.styles.labelling(_points(world))


@then("the layer's labelling is off")
def labelling_is_off(world: SymbologyWorld) -> None:
    assert world.labelling.enabled is False, world.labelling


@when("a labelling is declared on with no field")
def labelling_without_field(world: SymbologyWorld) -> None:
    try:
        Labelling(enabled=True)
    except ValueError as error:
        world.refused = error


@then("the declaration is refused naming the field it needs")
def refused_labelling(world: SymbologyWorld) -> None:
    assert isinstance(world.refused, ValueError), world.refused
    assert "field" in str(world.refused), str(world.refused)


# -- style text ---------------------------------------------------------------


@when("the plugin exports the layer's style as QML")
def export_qml(world: SymbologyWorld) -> None:
    world.styles.set_symbology(
        _points(world),
        CategorizedRenderer(
            field="kind",
            categories=(Category("a", "A", _marker("#ff0000")),),
        ),
    )
    world.export = world.styles.export_style(_points(world), "qml")


@when("the plugin imports that text back")
def import_back(world: SymbologyWorld) -> None:
    world.styles.set_symbology(
        _points(world), SingleSymbolRenderer(symbol=_marker("#00ff00"))
    )
    world.styles.import_style(_points(world), world.export.text, "qml")


@then("the layer keeps its renderer")
def keeps_renderer(world: SymbologyWorld) -> None:
    renderer = world.styles.symbology(_points(world))
    assert isinstance(renderer, CategorizedRenderer), renderer
    assert renderer.categories[0].symbol.color == "#ff0000"


# -- the style manager --------------------------------------------------------


@when("the plugin reads the style manager")
def read_style_manager(world: SymbologyWorld) -> None:
    world.entries = world.styles.list_styles()
    world.entries_by_kind = {}
    for entry in world.entries:
        world.entries_by_kind[entry.kind] = world.entries_by_kind.get(entry.kind, 0) + 1


@then("it lists a symbol, a colour ramp and a label setting")
def style_manager_listing(world: SymbologyWorld) -> None:
    assert world.entries_by_kind == {
        "symbol": 1,
        "color_ramp": 1,
        "label_settings": 1,
    }, world.entries_by_kind

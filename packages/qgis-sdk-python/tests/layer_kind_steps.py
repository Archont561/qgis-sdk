"""Steps for the layer-kinds feature: one runtime, one layer of each kind.

The fake answers from the *declaration* rather than from the bytes - a mesh is
declared with its vertex and face counts, a point cloud with its point total -
so the paths below are identities a plugin names, not datasets this module
parses. Only the vector and raster fixtures next to them are real files, which
is why those two features read the disk and this one does not.

A form scenario declares an action with two layer inputs of different kinds and
reads the wire the host would render, so "the picker offers this kind" and "the
page is told which kind" are one assertion rather than two that could drift.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pytest_bdd import given, parsers, then, when
from qgis_sdk.core import PluginContext, ResourceScope
from qgis_sdk.declarations._describe import describe_plugin
from qgis_sdk.declarations._plugin import action, plugin
from qgis_sdk.models import (
    AnnotationLayerInfo,
    CanvasExtent,
    MeshLayerInfo,
    PointCloudLayerInfo,
    QgisSdkLayerNotFoundError,
    TiledSceneLayerInfo,
    VectorTileLayerInfo,
)
from qgis_sdk.models.parameters import (
    LayerParameter,
    MeshInput,
    TiledSceneInput,
)
from qgis_sdk.testing import (
    FakeLayers,
    FakeRasters,
    OtherLayerDeclaration,
    VectorLayerDeclaration,
)
from qgis_sdk.ui.components import LayerPicker
from qgis_sdk.ui.form import input_for
from qgis_sdk.ui.form_fields import FieldSpec, form_fields


def _kind_runtime_phase1(world):
    world.layers.register_layer(
        OtherLayerDeclaration(
            VECTOR_TILES,
            name="basemap",
            kind="vector_tile",
            crs="EPSG:3857",
            detail={"source_type": "xyz", "min_zoom": 0, "max_zoom": 14},
        )
    )
    world.layers.register_layer(
        OtherLayerDeclaration(
            TILED_SCENE,
            name="city",
            kind="tiled_scene",
            crs="EPSG:4978",
            detail={
                "extent": {"x_min": 21.0, "y_min": 52.0, "x_max": 21.3, "y_max": 52.2}
            },
        )
    )
    world.layers.register_annotation("notes", item_count=3)
    return world


REFERENCE = Path(__file__).resolve().parent / "fixtures" / "reference"
MESH = REFERENCE / "lagoon.2dm"
POINT_CLOUD = REFERENCE / "survey.laz"
VECTOR_TILES = REFERENCE / "basemap.mbtiles"
TILED_SCENE = REFERENCE / "city.slpk"
POINTS = REFERENCE / "points.geojson"
GRID = REFERENCE / "elevation.asc"


@dataclass
class KindWorld:
    """The fake runtime the layer-kind scenarios arrange and observe."""

    scope: ResourceScope
    layers: FakeLayers
    rasters: FakeRasters
    opened: dict[str, object] = None  # type: ignore[assignment]
    refused: Exception | None = None
    specs: tuple[FieldSpec, ...] = ()
    pickers: tuple[object, ...] = ()
    declared_action: object = None
    declared: Exception | None = None

    def __post_init__(self) -> None:
        if self.opened is None:
            self.opened = {}


def _runtime() -> KindWorld:
    """One runtime whose layers service can open every kind."""
    scope = ResourceScope()
    rasters = FakeRasters(scope)
    rasters.register(
        GRID,
        name="elevation",
        extent=CanvasExtent(x_min=20.0, y_min=51.0, x_max=21.0, y_max=52.0),
        data_types=("Float64",),
        no_data=(None,),
        resolution=(0.1, 0.1),
        crs="EPSG:4326",
    )
    layers = FakeLayers(scope, rasters=rasters)
    return KindWorld(scope=scope, layers=layers, rasters=rasters)


@given("a runtime that can open every layer kind", target_fixture="kind_world")
def kind_runtime() -> KindWorld:
    """One fake runtime holding every kind's declaration, nothing opened yet."""
    world = _runtime()
    world.layers.register_layer(
        OtherLayerDeclaration(
            MESH,
            name="lagoon",
            kind="mesh",
            crs="EPSG:4326",
            detail={"vertex_count": 4, "face_count": 2, "group_count": 1},
        )
    )
    world.layers.register_layer(
        OtherLayerDeclaration(
            POINT_CLOUD,
            name="survey",
            kind="point_cloud",
            crs="EPSG:25833",
            detail={"point_count": 12, "attribute_names": ("X", "Y", "Z", "Intensity")},
        )
    )
    return _kind_runtime_phase1(world)


# -- opening one kind ---------------------------------------------------------


@when("the plugin opens the bundled mesh")
def open_mesh(kind_world: KindWorld) -> None:
    kind_world.opened["mesh"] = kind_world.layers.open_mesh(MESH)


@when("the plugin opens the bundled point cloud")
def open_point_cloud(kind_world: KindWorld) -> None:
    kind_world.opened["point_cloud"] = kind_world.layers.open_point_cloud(POINT_CLOUD)


@when("the plugin opens the bundled vector tiles")
def open_vector_tiles(kind_world: KindWorld) -> None:
    kind_world.opened["vector_tile"] = kind_world.layers.open_vector_tile(VECTOR_TILES)


@when("the plugin opens the bundled annotations")
def open_annotations(kind_world: KindWorld) -> None:
    kind_world.opened["annotation"] = kind_world.layers.open_annotation("notes")


@when("the plugin opens the bundled tiled scene")
def open_tiled_scene(kind_world: KindWorld) -> None:
    kind_world.opened["tiled_scene"] = kind_world.layers.open_tiled_scene(TILED_SCENE)


@then(
    parsers.parse(
        "the mesh describes {vertices:d} vertices, {faces:d} faces and {groups:d} dataset group"
    )
)
def mesh_description(
    kind_world: KindWorld, vertices: int, faces: int, groups: int
) -> None:
    mesh = kind_world.opened["mesh"]

    assert isinstance(mesh, MeshLayerInfo)
    assert mesh.kind == "mesh"
    assert (mesh.vertex_count, mesh.face_count, mesh.group_count) == (
        vertices,
        faces,
        groups,
    )


@then(parsers.parse("the point cloud describes {points:d} points"))
def point_cloud_description(kind_world: KindWorld, points: int) -> None:
    cloud = kind_world.opened["point_cloud"]

    assert isinstance(cloud, PointCloudLayerInfo)
    assert cloud.kind == "point_cloud"
    assert cloud.point_count == points


@then(
    parsers.parse(
        'the point cloud lists the attributes "{first}", "{second}", "{third}" and "{fourth}"'
    )
)
def point_cloud_attributes(
    kind_world: KindWorld, first: str, second: str, third: str, fourth: str
) -> None:
    cloud = kind_world.opened["point_cloud"]

    assert isinstance(cloud, PointCloudLayerInfo)
    assert cloud.attribute_names == (first, second, third, fourth)


@then(parsers.parse('the vector tile layer describes an "{source_type}" source'))
def vector_tile_source(kind_world: KindWorld, source_type: str) -> None:
    tiles = kind_world.opened["vector_tile"]

    assert isinstance(tiles, VectorTileLayerInfo)
    assert tiles.kind == "vector_tile"
    assert tiles.source_type == source_type


@then(parsers.parse("the vector tile layer covers zooms {low:d} to {high:d}"))
def vector_tile_zooms(kind_world: KindWorld, low: int, high: int) -> None:
    tiles = kind_world.opened["vector_tile"]

    assert isinstance(tiles, VectorTileLayerInfo)
    assert (tiles.min_zoom, tiles.max_zoom) == (low, high)


@then(parsers.parse("the annotation layer describes {items:d} items"))
def annotation_items(kind_world: KindWorld, items: int) -> None:
    notes = kind_world.opened["annotation"]

    assert isinstance(notes, AnnotationLayerInfo)
    assert notes.kind == "annotation"
    assert notes.item_count == items


@then(
    parsers.parse(
        "the tiled scene describes the box {x_min:f}, {y_min:f}, {x_max:f}, {y_max:f}"
    )
)
def tiled_scene_box(
    kind_world: KindWorld, x_min: float, y_min: float, x_max: float, y_max: float
) -> None:
    scene = kind_world.opened["tiled_scene"]

    assert isinstance(scene, TiledSceneLayerInfo)
    assert scene.kind == "tiled_scene"
    assert (
        scene.extent.x_min,
        scene.extent.y_min,
        scene.extent.x_max,
        scene.extent.y_max,
    ) == (x_min, y_min, x_max, y_max)


# -- listing every kind -------------------------------------------------------


@given("the plugin has opened one layer of every kind")
def open_one_of_each(kind_world: KindWorld) -> None:
    kind_world.layers.register(
        VectorLayerDeclaration(
            POINTS, name="points", geometry_type="point", field_names=("id", "value")
        )
    )
    kind_world.layers.open_vector(POINTS)
    kind_world.rasters.open_raster(GRID)
    kind_world.layers.open_mesh(MESH)
    kind_world.layers.open_point_cloud(POINT_CLOUD)
    kind_world.layers.open_vector_tile(VECTOR_TILES)
    kind_world.layers.open_annotation("notes")
    kind_world.layers.open_tiled_scene(TILED_SCENE)


@when("the layers service lists the project")
def list_every_kind(kind_world: KindWorld) -> None:
    kind_world.opened["kinds"] = [info.kind for info in kind_world.layers.list_layers()]


@then(
    "the kinds read vector, mesh, point_cloud, vector_tile, annotation, "
    "tiled_scene and raster"
)
def listed_kinds(kind_world: KindWorld) -> None:
    """Every kind appears once: the layers this service owns, then the rasters.

    The rasters come last because a sibling service opens them; a project that
    wants one order reads the project's tree instead of this list.
    """
    assert kind_world.opened["kinds"] == [
        "vector",
        "mesh",
        "point_cloud",
        "vector_tile",
        "annotation",
        "tiled_scene",
        "raster",
    ]


# -- a dataset opened as the wrong kind ---------------------------------------


@when("the plugin opens the mesh as a point cloud")
def open_mesh_as_point_cloud(kind_world: KindWorld) -> None:
    try:
        kind_world.layers.open_point_cloud(MESH)
    except QgisSdkLayerNotFoundError as error:
        kind_world.refused = error


@then("the SDK refuses it as a missing layer")
def refused_as_missing(kind_world: KindWorld) -> None:
    assert isinstance(kind_world.refused, QgisSdkLayerNotFoundError)


# -- a layer input names its kind --------------------------------------------


@plugin(id="kinds", title="Kinds")
class KindPlugin:
    """A plugin whose one action takes two layer inputs of different kinds."""

    ctx: PluginContext

    @action(id="inspect", title="Inspect")
    def inspect(self, mesh: MeshInput, scene: TiledSceneInput) -> None:
        """Two layer inputs whose kinds differ."""


@given('a form with a "mesh" layer input and a "tiled_scene" layer input')
def form_with_two_kinds(kind_world: KindWorld) -> None:
    (kind_world.declared_action,) = describe_plugin(KindPlugin).actions


@when("the form fields are described for the wire")
def describe_form_fields(kind_world: KindWorld) -> None:
    """Read the fields a host renders, then build the inputs it renders them with.

    Both, because they are the two halves of one promise: the wire says which
    kind and the picker filters by it, and a page that trusted only the first
    would offer every layer a project holds.
    """
    kind_world.specs = form_fields(kind_world.declared_action)
    kind_world.pickers = tuple(input_for(spec) for spec in kind_world.specs)


@then(parsers.parse('the first input offers kind "{kind}"'))
def first_input_kind(kind_world: KindWorld, kind: str) -> None:
    assert kind_world.specs[0].details["layer_kind"] == kind
    picker = kind_world.pickers[0]
    assert isinstance(picker, LayerPicker)
    assert picker.layer_kind == kind


@then(parsers.parse('the second input offers kind "{kind}"'))
def second_input_kind(kind_world: KindWorld, kind: str) -> None:
    assert kind_world.specs[1].details["layer_kind"] == kind
    picker = kind_world.pickers[1]
    assert isinstance(picker, LayerPicker)
    assert picker.layer_kind == kind


@when(parsers.parse('a layer input asks for kind "{kind}"'))
def layer_input_of_unknown_kind(kind_world: KindWorld, kind: str) -> None:
    try:
        LayerParameter(kind=kind)  # type: ignore[arg-type]
    except ValueError as error:
        kind_world.declared = error


@then(parsers.parse('the declaration is refused naming the seven kinds and "any"'))
def refused_kind_names(kind_world: KindWorld) -> None:
    assert isinstance(kind_world.declared, ValueError)
    message = str(kind_world.declared)
    for kind in (
        "vector",
        "raster",
        "mesh",
        "point_cloud",
        "vector_tile",
        "annotation",
        "tiled_scene",
        "any",
    ):
        assert kind in message, message

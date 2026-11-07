"""Every layer kind: its description, its open operation and its filter.

TASK-91. A layer kind is not a flag on one description: a mesh, a point cloud, a
vector tile layer, an annotation layer and a 3D tiled scene each answer the
numbers that kind actually has, and each carries its own ``kind`` on the wire so
a page draws one row per layer without asking twice. This module pins four
things: the seven names and the order the wire enum reads them in, each model's
shape and what it refuses, the fake answering every kind and refusing a dataset
opened as the wrong one, and the host surface - five open operations, no new
grant name, the answer typed per kind.
"""

from __future__ import annotations

import gzip
import json
import sqlite3
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import layer_kind_fixtures as fixture_files
import pytest
from qgis_sdk.bridge import Dispatcher
from qgis_sdk.bridge.authority import HostAuthority
from qgis_sdk.bridge.host import HOST_OPERATIONS, HostServices, register_host_operations
from qgis_sdk.bridge.protocol import BRIDGE_PROTOCOL_VERSION
from qgis_sdk.core import ResourceScope
from qgis_sdk.files import FilesService
from qgis_sdk.models import (
    LAYER_KIND_NAMES,
    AnnotationLayerInfo,
    CanvasExtent,
    MeshLayerInfo,
    PointCloudLayerInfo,
    QgisSdkLayerNotFoundError,
    QgisSdkScopeClosedError,
    QgisSdkUiError,
    QgisSdkUnsupportedCapabilityError,
    TiledSceneLayerInfo,
    VectorTileLayerInfo,
    layer_info,
)
from qgis_sdk.models import layers as layer_models
from qgis_sdk.models.parameters import LAYER_KINDS_FOR_INPUT, LayerParameter
from qgis_sdk.testing import (
    FakeLayers,
    FakeProject,
    FakeRasters,
    RecordingNotifications,
)
from qgis_sdk.ui.components import LayerPicker

ORIGIN = "qgis://desktop"

MESH = Path("fixtures/lagoon.2dm")
POINT_CLOUD = Path("fixtures/survey.laz")
VECTOR_TILES = Path("fixtures/basemap.mbtiles")
TILED_SCENE = Path("fixtures/city.slpk")
POINTS = Path("fixtures/points.geojson")
GRID = Path("fixtures/elevation.asc")

#: The five kinds this task adds, in the order the enum reads them.
NEW_KINDS = ("mesh", "point_cloud", "vector_tile", "annotation", "tiled_scene")


# -- the vocabulary ----------------------------------------------------------


def test_the_seven_kinds_are_named_in_wire_order() -> None:
    assert LAYER_KIND_NAMES == ("vector", "raster", *NEW_KINDS)
    assert len(set(LAYER_KIND_NAMES)) == len(LAYER_KIND_NAMES)


def test_every_kind_has_a_model_and_a_schema() -> None:
    """A kind without a model or a schema is a name a page cannot render."""
    for kind in LAYER_KIND_NAMES:
        assert kind in layer_models.LAYER_INFO_SCHEMAS, kind
        assert layer_models.layer_kind_of(layer_models.LAYER_INFO_SCHEMAS[kind]) == kind


# -- the models --------------------------------------------------------------


def test_a_mesh_answers_its_counts_and_round_trips() -> None:
    mesh = MeshLayerInfo(
        id="layer-1",
        name="lagoon",
        crs="EPSG:4326",
        vertex_count=4,
        face_count=2,
        group_count=1,
    )

    assert layer_info(mesh) == {
        "kind": "mesh",
        "id": "layer-1",
        "name": "lagoon",
        "vertex_count": 4,
        "face_count": 2,
        "group_count": 1,
        "crs": "EPSG:4326",
    }
    assert MeshLayerInfo.from_wire(layer_info(mesh)) == mesh


def test_a_point_cloud_answers_its_points_and_attributes() -> None:
    cloud = PointCloudLayerInfo(
        id="layer-2",
        name="survey",
        crs=None,
        point_count=12,
        attribute_names=("X", "Y", "Z"),
    )

    assert layer_info(cloud) == {
        "kind": "point_cloud",
        "id": "layer-2",
        "name": "survey",
        "point_count": 12,
        "attribute_names": ["X", "Y", "Z"],
        "crs": None,
    }
    assert PointCloudLayerInfo.from_wire(layer_info(cloud)) == cloud


def test_a_vector_tile_layer_answers_its_source_type_and_zooms() -> None:
    tiles = VectorTileLayerInfo(
        id="layer-3",
        name="basemap",
        crs="EPSG:3857",
        source_type="xyz",
        min_zoom=0,
        max_zoom=14,
    )

    assert layer_info(tiles) == {
        "kind": "vector_tile",
        "id": "layer-3",
        "name": "basemap",
        "source_type": "xyz",
        "min_zoom": 0,
        "max_zoom": 14,
        "crs": "EPSG:3857",
    }
    assert VectorTileLayerInfo.from_wire(layer_info(tiles)) == tiles


def test_an_annotation_layer_answers_how_many_items_it_holds() -> None:
    notes = AnnotationLayerInfo(id="layer-4", name="notes", crs=None, item_count=3)

    assert layer_info(notes) == {
        "kind": "annotation",
        "id": "layer-4",
        "name": "notes",
        "item_count": 3,
        "crs": None,
    }
    assert AnnotationLayerInfo.from_wire(layer_info(notes)) == notes


def test_a_tiled_scene_answers_where_it_sits() -> None:
    scene = TiledSceneLayerInfo(
        id="layer-5",
        name="city",
        crs="EPSG:4978",
        extent=CanvasExtent(x_min=21.0, y_min=52.0, x_max=21.3, y_max=52.2),
    )

    assert layer_info(scene)["extent"] == {
        "x_min": 21.0,
        "y_min": 52.0,
        "x_max": 21.3,
        "y_max": 52.2,
        "crs": None,
    }
    assert TiledSceneLayerInfo.from_wire(layer_info(scene)) == scene


@pytest.mark.parametrize(
    "build, message",
    [
        (
            lambda: MeshLayerInfo(
                id="a", name="m", crs=None, vertex_count=-1, face_count=0, group_count=0
            ),
            "vertex_count",
        ),
        (
            lambda: PointCloudLayerInfo(
                id="a", name="p", crs=None, point_count=-2, attribute_names=()
            ),
            "point_count",
        ),
        (
            lambda: VectorTileLayerInfo(
                id="a", name="v", crs=None, source_type="", min_zoom=0, max_zoom=2
            ),
            "source_type",
        ),
        (
            lambda: VectorTileLayerInfo(
                id="a", name="v", crs=None, source_type="xyz", min_zoom=5, max_zoom=2
            ),
            "zoom",
        ),
        (
            lambda: AnnotationLayerInfo(id="a", name="n", crs=None, item_count=-1),
            "item_count",
        ),
        (
            lambda: TiledSceneLayerInfo(
                id="a",
                name="t",
                crs=None,
                extent=CanvasExtent(x_min=1.0, y_min=2.0, x_max=0.0, y_max=3.0),
            ),
            "x_min",
        ),
    ],
)
def test_a_description_refuses_a_number_its_kind_cannot_have(
    build: Any, message: str
) -> None:
    with pytest.raises((TypeError, ValueError)) as raised:
        build()

    assert message in str(raised.value).lower()


def test_every_kind_names_its_model_and_the_union_holds_them_all() -> None:
    union = layer_models.LAYER_INFO_SCHEMAS
    titles = [layer_models.layer_kind_of(union[kind]) for kind in LAYER_KIND_NAMES]

    assert titles == list(LAYER_KIND_NAMES)
    for kind in LAYER_KIND_NAMES:
        assert layer_models.LAYER_INFO_NAMES[kind] == union[kind]["title"]


def test_a_description_refuses_a_field_its_kind_does_not_have() -> None:
    with pytest.raises(ValueError):
        MeshLayerInfo.from_wire(
            {
                "kind": "mesh",
                "id": "a",
                "name": "m",
                "vertex_count": 1,
                "face_count": 0,
                "group_count": 0,
                "crs": None,
                "band_count": 3,
            }
        )


# -- the fake ----------------------------------------------------------------


def _layers() -> tuple[ResourceScope, FakeLayers, FakeRasters]:
    scope = ResourceScope()
    rasters = FakeRasters(scope)
    return scope, FakeLayers(scope, rasters=rasters), rasters


def _declare_every_kind(layers: FakeLayers) -> None:
    layers.register(
        POINTS, name="points", geometry_type="point", field_names=("id", "value")
    )
    layers.register_layer(
        MESH,
        name="lagoon",
        kind="mesh",
        crs="EPSG:4326",
        vertex_count=4,
        face_count=2,
        group_count=1,
    )
    layers.register_layer(
        POINT_CLOUD,
        name="survey",
        kind="point_cloud",
        crs="EPSG:25833",
        point_count=12,
        attribute_names=("X", "Y", "Z"),
    )
    layers.register_layer(
        VECTOR_TILES,
        name="basemap",
        kind="vector_tile",
        crs="EPSG:3857",
        source_type="xyz",
        min_zoom=0,
        max_zoom=14,
    )
    layers.register_layer(
        TILED_SCENE,
        name="city",
        kind="tiled_scene",
        crs="EPSG:4978",
        extent={"x_min": 21.0, "y_min": 52.0, "x_max": 21.3, "y_max": 52.2},
    )


def test_the_fake_opens_every_kind_and_answers_the_same_ids() -> None:
    scope, layers, _ = _layers()
    _declare_every_kind(layers)

    opened = {
        "vector": layers.open_vector(POINTS),
        "mesh": layers.open_mesh(MESH),
        "point_cloud": layers.open_point_cloud(POINT_CLOUD),
        "vector_tile": layers.open_vector_tile(VECTOR_TILES),
        "tiled_scene": layers.open_tiled_scene(TILED_SCENE),
        "annotation": layers.open_annotation("notes"),
    }
    scope.close()

    assert {kind: info.kind for kind, info in opened.items()} == {
        "vector": "vector",
        "mesh": "mesh",
        "point_cloud": "point_cloud",
        "vector_tile": "vector_tile",
        "tiled_scene": "tiled_scene",
        "annotation": "annotation",
    }
    assert opened["mesh"] == MeshLayerInfo(
        id=opened["mesh"].id,
        name="lagoon",
        crs="EPSG:4326",
        vertex_count=4,
        face_count=2,
        group_count=1,
    )


def test_an_annotation_layer_is_created_empty_when_nothing_is_declared() -> None:
    scope, layers, _ = _layers()

    notes = layers.open_annotation("sketch")
    scope.close()

    assert isinstance(notes, AnnotationLayerInfo)
    assert notes.item_count == 0


def test_a_dataset_opened_as_another_kind_is_refused_as_missing() -> None:
    scope, layers, _ = _layers()
    _declare_every_kind(layers)

    with pytest.raises(QgisSdkLayerNotFoundError):
        layers.open_point_cloud(MESH)

    scope.close()


def test_the_new_kinds_are_listed_after_the_vectors_and_before_the_rasters() -> None:
    scope, layers, rasters = _layers()
    _declare_every_kind(layers)
    rasters.register(
        GRID,
        name="elevation",
        extent=CanvasExtent(x_min=21.0, y_min=52.0, x_max=21.3, y_max=52.2),
        data_types=("Float64",),
        no_data=(None,),
        resolution=(0.1, 0.1),
        crs="EPSG:4326",
    )

    layers.open_mesh(MESH)
    rasters.open_raster(GRID)
    layers.open_vector(POINTS)

    kinds = [info.kind for info in layers.list_layers()]
    scope.close()

    assert kinds == ["vector", "mesh", "raster"]


def test_a_vector_only_method_refuses_another_kind_by_name() -> None:
    scope, layers, _ = _layers()
    _declare_every_kind(layers)
    mesh = layers.open_mesh(MESH)

    with pytest.raises(QgisSdkUnsupportedCapabilityError) as raised:
        layers.selection(mesh.id)

    scope.close()
    assert "mesh" in str(raised.value)


def test_every_kind_is_refused_after_the_scope_closes() -> None:
    scope, layers, _ = _layers()
    _declare_every_kind(layers)
    scope.close()

    for open_one in (
        lambda: layers.open_mesh(MESH),
        lambda: layers.open_point_cloud(POINT_CLOUD),
        lambda: layers.open_vector_tile(VECTOR_TILES),
        lambda: layers.open_tiled_scene(TILED_SCENE),
        lambda: layers.open_annotation("notes"),
    ):
        with pytest.raises(QgisSdkScopeClosedError):
            open_one()


# -- layer inputs and pickers ------------------------------------------------


def test_a_layer_input_names_every_kind_and_the_any_picker() -> None:
    assert LAYER_KINDS_FOR_INPUT == (*LAYER_KIND_NAMES, "any")
    for kind in NEW_KINDS:
        assert LayerParameter(kind=kind).kind == kind  # type: ignore[arg-type]


class _PickerContext:
    """As much of a view's context as a picker touches: a scope and the services.

    A picker lists through ``ctx.layers`` and subscribes to ``ctx.scope`` and
    nothing else, so a test that builds a whole ``UiContext`` would be arranging
    surfaces it never reads. ``project`` is absent, which is the state a view
    opens in before the project service is shared.
    """

    def __init__(self, layers: FakeLayers, scope: ResourceScope) -> None:
        self.layers = layers
        self.scope = scope
        self._services: dict[str, object] = {"layers": layers}

    def has(self, name: str) -> bool:
        return name in self._services


@pytest.mark.parametrize("kind", NEW_KINDS)
def test_a_picker_narrows_the_listing_to_its_own_kind(kind: str) -> None:
    scope, layers, _ = _layers()
    _declare_every_kind(layers)
    vector = layers.open_vector(POINTS)
    mesh = layers.open_mesh(MESH)
    cloud = layers.open_point_cloud(POINT_CLOUD)
    opened = {"mesh": mesh, "point_cloud": cloud}
    # Every picker of a new kind lists the layer of that kind and no other; the
    # two kinds no declaration opens in this module list nothing, which is the
    # answer a project holding none of them gives.
    picker = LayerPicker(kind, kind=kind)  # type: ignore[arg-type]
    picker.attach(_PickerContext(layers, scope))  # type: ignore[arg-type]
    listing = [option.id for option in picker.options()]
    every = LayerPicker("any", kind="any")
    every.attach(_PickerContext(layers, scope))  # type: ignore[arg-type]
    listed_by_any = {option.id for option in every.options()}
    scope.close()

    assert listing == ([opened[kind].id] if kind in opened else [])
    assert {opened["mesh"].id, opened["point_cloud"].id, vector.id} <= listed_by_any


def test_a_picker_refuses_a_kind_a_layer_input_does_not_offer() -> None:
    with pytest.raises(QgisSdkUiError, match="mesh"):
        LayerPicker("sound", kind="sound")  # type: ignore[arg-type]


# -- the host surface --------------------------------------------------------


def test_the_catalogue_gains_five_opens_and_no_new_grant() -> None:
    by_id = {operation.id: operation for operation in HOST_OPERATIONS}

    for kind in NEW_KINDS:
        operation = by_id[f"layers.open_{kind}"]
        assert operation.grant == "layers.open", kind

    # The surface grew by seven operations and four grants for symbology
    # (TASK-93); the counts are reviewed here rather than inferred, so a batch
    # that adds an operation without deciding its grant fails this test.
    assert len(HOST_OPERATIONS) == 75
    assert len({operation.grant for operation in HOST_OPERATIONS}) == 26


def test_each_open_answers_its_own_model() -> None:
    by_id = {operation.id: operation for operation in HOST_OPERATIONS}

    for kind in NEW_KINDS:
        operation = by_id[f"layers.open_{kind}"]
        assert operation.result_name == layer_models.LAYER_INFO_NAMES[kind], kind


@dataclass
class _Settings:
    def get(self, key: str, default: str | None = None) -> str | None:
        return default


@dataclass
class _Styles:
    def apply_style(self, layer_id: str, style: str) -> None:  # pragma: no cover
        raise AssertionError("styles are not part of this slice")


def _bridge(
    layers: FakeLayers, scope: ResourceScope
) -> tuple[Dispatcher, HostAuthority]:
    authority = HostAuthority()
    services = HostServices(
        layers=layers,
        project=FakeProject(layers, scope),
        settings=_Settings(),  # type: ignore[arg-type]
        styles=_Styles(),  # type: ignore[arg-type]
        notifications=RecordingNotifications(scope),
        authority=authority,
        files=FilesService(authority, scope, owner="plugin:demo"),
    )
    dispatcher = Dispatcher(
        description={"schema_version": 1, "id": "demo.plugin", "title": "Demo"},
        authorize=lambda binding, operation: True,
    )
    register_host_operations(dispatcher, services)
    return dispatcher, authority


def _grantable(tmp_path: Path, source: Path) -> Path:
    """Write the file a ref must name: the authority reads the disk, not a fake.

    A granted ref is a promise that the file exists, so a scenario about the wire
    needs bytes on disk even though the fake answers from the declaration - the
    empty file is enough, because the bytes are never parsed here.
    """
    dataset = tmp_path / source.name
    dataset.write_bytes(b"")
    return dataset


def _declare_at(layers: FakeLayers, dataset: Path, kind: str, **detail: object) -> None:
    """Declare ``dataset`` on disk as ``kind``, with the fields that kind needs."""
    layers.register_layer(dataset, name=dataset.stem, kind=kind, **detail)  # type: ignore[arg-type]


def test_a_page_opens_a_mesh_with_a_granted_ref_and_reads_it_back(
    tmp_path: Path,
) -> None:
    dataset = _grantable(tmp_path, MESH)
    scope, layers, _ = _layers()
    _declare_at(
        layers,
        dataset,
        "mesh",
        crs="EPSG:4326",
        vertex_count=4,
        face_count=2,
        group_count=1,
    )
    dispatcher, authority = _bridge(layers, scope)
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    ref = authority.grant_file(binding, dataset, source="picker")

    opened = dispatcher.dispatch(
        binding,
        {
            "protocol": BRIDGE_PROTOCOL_VERSION,
            "call_id": "call",
            "operation": "layers.open_mesh",
            "payload": {"file": ref.to_wire()},
        },
    )
    listed = dispatcher.dispatch(
        binding,
        {
            "protocol": BRIDGE_PROTOCOL_VERSION,
            "call_id": "call",
            "operation": "layers.list",
            "payload": {},
        },
    )
    scope.close()

    assert opened["ok"] is True
    assert opened["value"]["kind"] == "mesh"
    assert opened["value"]["vertex_count"] == 4
    assert [item["kind"] for item in listed["value"]["items"]] == ["mesh"]


def test_an_annotation_layer_is_opened_by_name_rather_than_by_ref() -> None:
    scope, layers, _ = _layers()
    dispatcher, _authority = _bridge(layers, scope)
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)

    opened = dispatcher.dispatch(
        binding,
        {
            "protocol": BRIDGE_PROTOCOL_VERSION,
            "call_id": "call",
            "operation": "layers.open_annotation",
            "payload": {"name": "sketch"},
        },
    )
    scope.close()

    assert opened["ok"] is True
    assert opened["value"]["kind"] == "annotation"
    assert opened["value"]["item_count"] == 0


def test_every_open_is_typed_and_answered_by_a_handler(tmp_path: Path) -> None:
    """A declared operation with no handler fails at dispatch, not at build."""
    scope, layers, _ = _layers()
    dispatcher, authority = _bridge(layers, scope)
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)

    detail = {
        "point_cloud": {"point_count": 12, "attribute_names": ("X", "Y", "Z")},
        "vector_tile": {"source_type": "xyz", "min_zoom": 0, "max_zoom": 14},
        "tiled_scene": {
            "extent": {"x_min": 21.0, "y_min": 52.0, "x_max": 21.3, "y_max": 52.2}
        },
    }
    for kind, source in (
        ("point_cloud", POINT_CLOUD),
        ("vector_tile", VECTOR_TILES),
        ("tiled_scene", TILED_SCENE),
    ):
        dataset = _grantable(tmp_path, source)
        _declare_at(layers, dataset, kind, **detail[kind])
        ref = authority.grant_file(binding, dataset, source="picker")
        answered = dispatcher.dispatch(
            binding,
            {
                "protocol": BRIDGE_PROTOCOL_VERSION,
                "call_id": "call",
                "operation": f"layers.open_{kind}",
                "payload": {"file": ref.to_wire()},
            },
        )
        assert answered["ok"] is True, answered
        assert answered["value"]["kind"] == kind

    scope.close()


# -- the fixtures a native half opens ----------------------------------------
# TASK-91's native half needs one file per kind. The mesh is a checked-in ``.2dm``
# and an annotation layer is created rather than opened; the other three are
# containers a text repository cannot review as blobs - a LAS point cloud, an
# MBTiles vector tile source and a 3D Tiles tileset - so the suite builds them
# instead. These tests are what keeps the builders honest in the pure lane: a
# builder that wrote a header PDAL refuses would otherwise only fail inside the
# opt-in native run, where nobody reads the diff.


def test_the_point_cloud_fixture_is_a_las_1_2_file_the_provider_can_read(
    tmp_path: Path,
) -> None:
    path = fixture_files.write_point_cloud(tmp_path / "survey.las")

    raw = path.read_bytes()

    assert raw[:4] == b"LASF"
    assert raw[24:26] == bytes((1, 2)), "version 1.2"
    assert struct.unpack_from("<H", raw, 94)[0] == 227, "header size"
    assert struct.unpack_from("<I", raw, 96)[0] == 227, "offset to point data"
    assert raw[104] == 0, "point data format 0"
    assert struct.unpack_from("<H", raw, 105)[0] == 20, "point record length"
    assert struct.unpack_from("<I", raw, 107)[0] == len(
        fixture_files.POINT_CLOUD_POINTS
    )
    assert len(raw) == 227 + 20 * len(fixture_files.POINT_CLOUD_POINTS)


def test_the_point_cloud_fixture_declares_the_box_its_points_cover(
    tmp_path: Path,
) -> None:
    """A LAS header carries the extent, and PDAL trusts it: it must be right."""
    raw = fixture_files.write_point_cloud(tmp_path / "survey.las").read_bytes()

    max_x, min_x, max_y, min_y, max_z, min_z = struct.unpack_from("<6d", raw, 179)
    xs = [x for x, _, _ in fixture_files.POINT_CLOUD_POINTS]
    ys = [y for _, y, _ in fixture_files.POINT_CLOUD_POINTS]
    zs = [z for _, _, z in fixture_files.POINT_CLOUD_POINTS]

    assert (min_x, max_x) == (min(xs), max(xs))
    assert (min_y, max_y) == (min(ys), max(ys))
    assert (min_z, max_z) == (min(zs), max(zs))


def test_the_vector_tile_fixture_is_an_mbtiles_database_with_a_tile(
    tmp_path: Path,
) -> None:
    path = fixture_files.write_vector_tiles(tmp_path / "basemap.mbtiles")

    with sqlite3.connect(path) as database:
        tables = {
            row[0]
            for row in database.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        metadata = dict(database.execute("SELECT name, value FROM metadata"))
        (tile,) = database.execute("SELECT tile_data FROM tiles").fetchone()

    assert {"metadata", "tiles"} <= tables
    assert metadata["format"] == "pbf", "MBTiles serves Mapbox vector tiles"
    assert metadata["name"] == fixture_files.VECTOR_TILE_NAME
    assert metadata["minzoom"] == "0"
    assert metadata["maxzoom"] == "2"
    # An empty MVT message is a valid tile with no layers: the contract opens
    # the layer, it never renders one, so the tile only has to be well formed.
    assert gzip.decompress(tile) == b""


def test_the_tiled_scene_fixture_is_a_tileset_covering_the_declared_region(
    tmp_path: Path,
) -> None:
    path = fixture_files.write_tiled_scene(tmp_path / "scene" / "tileset.json")

    tileset = json.loads(path.read_text(encoding="utf-8"))

    assert tileset["asset"]["version"] == "1.0"
    assert tileset["root"]["boundingVolume"]["region"] == list(
        fixture_files.TILED_SCENE_REGION
    )
    # No content: opening a scene builds the tile index from the tileset, and a
    # tile with no content is the smallest tileset 3D Tiles allows.
    assert "content" not in tileset["root"]
    assert tileset["root"]["geometricError"] == 0

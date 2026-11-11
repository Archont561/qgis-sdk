"""The project and raster operations on the wire: declared, answered, annotated.

Two properties are not visible in a schema and are asserted here. A destructiveness
annotation is either present on the operations that discard project state or the
agent consent list cannot ask about them (decision-27 point 2, decision-49 point
4), so every operation is classified by hand and the declaration is compared with
that list. And the projector's operations answer with the model the page validates
against, so the tree, the entries and a sampled value cross unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from qgis_sdk.bridge import BridgeErrorCode, Dispatcher
from qgis_sdk.bridge.authority import FileOperation, FilePolicy, HostAuthority
from qgis_sdk.bridge.host import (
    HOST_OPERATIONS,
    HostServices,
    register_host_operations,
)
from qgis_sdk.bridge.protocol import BRIDGE_PROTOCOL_VERSION
from qgis_sdk.core import ResourceScope
from qgis_sdk.models.canvas import CanvasExtent, CanvasPoint
from qgis_sdk.testing import (
    FakeLayers,
    FakeProject,
    FakeRasters,
    RecordingNotifications,
    VectorLayerDeclaration,
)


def _the_project_stream_emits_phase1(binding, dispatcher, doubles, info):
    dispatcher.dispatch(
        binding,
        {
            "protocol": BRIDGE_PROTOCOL_VERSION,
            "call_id": "call",
            "operation": "project.add_layer",
            "payload": {"layer_id": info.id},
        },
    )
    frames = doubles.project.changes

    assert [frame.kind for frame in frames] == ["layers"]
    assert frames[0].layer_ids == (info.id,)


ORIGIN = "qgis://desktop"

#: The operations that replace or discard project state. Written out by hand,
#: because an annotation nothing ever confirms is a comment.
DESTRUCTIVE = {
    "project.read",
    "project.write",
    "project.save",
    "project.remove_layer",
    "project.remove_bookmark",
    "project.unset_variable",
    "project.unset_property",
    # TASK-89: an export replaces a file the page's own write ref names.
    "layouts.export",
    "layouts.atlas",
    # TASK-93: each of these replaces how a layer is drawn or labelled, and a
    # packaged style is applied over whatever the layer had.
    "styles.apply",
    "symbology.set",
    "labelling.set",
    "styles.import",
    # TASK-92: attaching an authentication configuration replaces how a
    # connection authenticates - the old password stops being spent.
    "auth.attach",
}

#: The operations that spend stored authentication material or read or re-bind
#: the credential registry. Its own axis, never folded into ``destructive``
#: (TASK-92): the consent list asks "will this change my project?" and "will
#: this touch my credentials?" as two questions, and a read that spends a
#: password must not hide among the writes.
CREDENTIAL = {
    "network.fetch",
    "connections.browse",
    "connections.test",
    "connections.open_layer",
    "auth.configurations",
    "auth.attach",
}


@dataclass
class _Doubles:
    """The runtime's own fakes, plus the services the bridge is handed."""

    scope: ResourceScope
    layers: FakeLayers
    rasters: FakeRasters
    project: FakeProject
    services: HostServices

    @property
    def authority(self) -> HostAuthority:
        """The one authority the bridge resolves refs through."""
        return self.services.authority


@dataclass
class _Styles:
    def apply_style(self, layer_id: str, style: str) -> None:  # pragma: no cover
        raise AssertionError("styles are not part of this slice")


@dataclass
class _Settings:
    def get(
        self, key: str, default: str | None = None
    ) -> str | None:  # pragma: no cover
        return default


def _sites_declaration(dataset: Path) -> VectorLayerDeclaration:
    return VectorLayerDeclaration(
        dataset, name="sites", geometry_type="point", field_names=("id",)
    )


@pytest.fixture
def doubles(tmp_path: Path) -> _Doubles:
    scope = ResourceScope()
    rasters = FakeRasters(scope)
    layers = FakeLayers(scope, rasters=rasters)
    dataset = tmp_path / "sites.geojson"
    dataset.write_text("{}", encoding="utf-8")
    layers.register(_sites_declaration(dataset))
    rasters.register(
        tmp_path / "elevation.tif",
        name="elevation",
        extent=CanvasExtent(x_min=21.0, y_min=52.0, x_max=21.3, y_max=52.2),
        crs="EPSG:4326",
        values=(7.0,),
    )
    project = FakeProject(layers, scope)
    services = HostServices(
        layers=layers,
        project=project,
        rasters=rasters,
        settings=_Settings(),  # type: ignore[arg-type]
        styles=_Styles(),  # type: ignore[arg-type]
        notifications=RecordingNotifications(scope),
        authority=HostAuthority(),
    )
    return _Doubles(
        scope=scope, layers=layers, rasters=rasters, project=project, services=services
    )


def _dispatcher(doubles: _Doubles) -> Dispatcher:
    dispatcher = Dispatcher(
        description={"schema_version": 1, "id": "demo.plugin", "title": "Demo"},
        authorize=lambda binding, operation: True,
    )
    register_host_operations(dispatcher, doubles.services)
    return dispatcher


def _call(
    dispatcher: Dispatcher, operation: str, payload: Any = None, *, binding: Any = None
) -> dict:
    if binding is None:
        binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    return dispatcher.dispatch(
        binding,
        {
            "protocol": BRIDGE_PROTOCOL_VERSION,
            "call_id": "call",
            "operation": operation,
            "payload": {} if payload is None else payload,
        },
    )


# -- the annotation ---------------------------------------------------------


def test_the_destructive_annotation_names_exactly_the_operations_that_replace_state() -> (
    None
):
    declared = {operation.id for operation in HOST_OPERATIONS if operation.destructive}

    assert declared == DESTRUCTIVE


def test_every_operation_says_whether_it_is_destructive() -> None:
    from qgis_sdk.bridge.host import host_description

    for action in host_description()["actions"]:
        assert isinstance(action["destructive"], bool), action["id"]


def test_the_credential_annotation_names_exactly_the_operations_that_touch_them() -> (
    None
):
    declared = {operation.id for operation in HOST_OPERATIONS if operation.credential}

    assert declared == CREDENTIAL


def test_every_operation_says_whether_it_touches_credentials() -> None:
    from qgis_sdk.bridge.host import host_description

    described = host_description()
    for record in [*described["actions"], *described["streams"]]:
        assert isinstance(record["credential"], bool), record["id"]
        # The two axes cross in one record: showing one never hides the other.
        assert {"destructive", "credential"} <= set(record), record["id"]


# -- the tree ---------------------------------------------------------------


def test_the_tree_crosses_as_a_closed_model(doubles: _Doubles, tmp_path: Path) -> None:
    dispatcher = _dispatcher(doubles)
    info = doubles.layers.open_vector(tmp_path / "sites.geojson")

    added = _call(dispatcher, "project.add_layer", {"layer_id": info.id})

    assert added["ok"] is True
    assert added["value"] == {
        "nodes": [
            {
                "id": info.id,
                "name": "sites",
                "kind": "layer",
                "visible": True,
                "parent": None,
            }
        ]
    }
    assert _call(dispatcher, "project.tree")["value"] == added["value"]


def test_hiding_a_node_answers_the_tree_it_produced(
    doubles: _Doubles, tmp_path: Path
) -> None:
    dispatcher = _dispatcher(doubles)
    info = doubles.layers.open_vector(tmp_path / "sites.geojson")
    _call(dispatcher, "project.add_layer", {"layer_id": info.id})

    hidden = _call(
        dispatcher, "project.set_visible", {"node_id": info.id, "visible": False}
    )

    assert hidden["ok"] is True
    assert hidden["value"]["nodes"][0]["visible"] is False


def test_a_removal_is_declared_and_answers_the_tree(
    doubles: _Doubles, tmp_path: Path
) -> None:
    dispatcher = _dispatcher(doubles)
    info = doubles.layers.open_vector(tmp_path / "sites.geojson")
    _call(dispatcher, "project.add_layer", {"layer_id": info.id})

    removed = _call(dispatcher, "project.remove_layer", {"layer_id": info.id})

    assert removed["ok"] is True
    assert removed["value"] == {"nodes": []}


# -- entries and bookmarks --------------------------------------------------


def test_variables_round_trip_as_entries(doubles: _Doubles) -> None:
    dispatcher = _dispatcher(doubles)

    set_reply = _call(
        dispatcher, "project.set_variable", {"name": "author", "value": "Ada"}
    )

    assert set_reply["value"] == [{"key": "author", "value": "Ada"}]
    assert _call(dispatcher, "project.variables")["value"] == set_reply["value"]
    assert (
        _call(dispatcher, "project.unset_variable", {"name": "author"})["value"] == []
    )


def test_properties_round_trip_as_entries(doubles: _Doubles) -> None:
    dispatcher = _dispatcher(doubles)

    set_reply = _call(
        dispatcher, "project.set_property", {"name": "sdk", "value": "yes"}
    )

    assert set_reply["value"] == [{"key": "sdk", "value": "yes"}]
    assert _call(dispatcher, "project.properties")["value"] == set_reply["value"]


def test_a_bookmark_is_an_extent_a_page_can_zoom_to(doubles: _Doubles) -> None:
    dispatcher = _dispatcher(doubles)
    extent = CanvasExtent(x_min=21.0, y_min=52.0, x_max=21.2, y_max=52.2).to_wire()

    added = _call(
        dispatcher, "project.add_bookmark", {"name": "home", "extent": extent}
    )

    assert added["value"] == [{"name": "home", "extent": extent}]
    assert (
        _call(dispatcher, "project.bookmark", {"name": "home"})["value"]
        == added["value"][0]
    )


def test_an_unknown_bookmark_is_refused_with_its_own_code(doubles: _Doubles) -> None:
    dispatcher = _dispatcher(doubles)

    refused = _call(dispatcher, "project.bookmark", {"name": "nowhere"})

    # A service error crosses as a failed operation, not as a new wire code:
    # the code vocabulary belongs to the bridge, and the refusal names itself
    # in the message the page logs.
    assert refused["ok"] is False
    assert refused["error"]["code"] == BridgeErrorCode.OPERATION_FAILED.value
    assert "nowhere" in refused["error"]["message"]


# -- the file ---------------------------------------------------------------


def _write_ref(doubles: _Doubles, binding: Any, path: Path):
    return doubles.authority.grant_file(
        binding,
        path,
        FilePolicy(operations=(FileOperation.WRITE,), source="picker"),
    )


def test_writing_a_project_goes_through_a_host_minted_ref(
    doubles: _Doubles, tmp_path: Path
) -> None:
    dispatcher = _dispatcher(doubles)
    destination = tmp_path / "saved.qgs"
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    ref = _write_ref(doubles, binding, destination)

    written = _call(
        dispatcher, "project.write", {"file": ref.to_wire()}, binding=binding
    )

    assert written["ok"] is True
    assert written["value"] == {"path": str(destination)}
    assert destination.is_file()


def test_a_page_cannot_hand_a_bare_path_to_a_project_call(
    doubles: _Doubles, tmp_path: Path
) -> None:
    dispatcher = _dispatcher(doubles)

    refused = _call(dispatcher, "project.write", {"file": str(tmp_path / "x.qgs")})

    assert refused["ok"] is False
    assert refused["error"]["code"] == BridgeErrorCode.INVALID_PAYLOAD.value


# -- rasters ----------------------------------------------------------------


def test_a_raster_sample_crosses_as_a_point_and_its_values(
    doubles: _Doubles, tmp_path: Path
) -> None:
    dispatcher = _dispatcher(doubles)
    info = doubles.rasters.open_raster(tmp_path / "elevation.tif")

    sampled = _call(
        dispatcher,
        "rasters.sample",
        {
            "layer_id": info.id,
            "point": CanvasPoint(x=21.1, y=52.1, crs="EPSG:4326").to_wire(),
        },
    )

    assert sampled["ok"] is True
    assert sampled["value"] == {
        "point": {"x": 21.1, "y": 52.1, "crs": "EPSG:4326"},
        "values": [7.0],
    }


def test_a_band_outside_the_raster_is_refused_by_code(
    doubles: _Doubles, tmp_path: Path
) -> None:
    dispatcher = _dispatcher(doubles)
    info = doubles.rasters.open_raster(tmp_path / "elevation.tif")

    refused = _call(dispatcher, "rasters.statistics", {"layer_id": info.id, "band": 2})

    assert refused["ok"] is False
    assert refused["error"]["code"] == BridgeErrorCode.OPERATION_FAILED.value
    assert "band 2" in refused["error"]["message"]


def test_a_raster_lists_among_the_layers_with_its_kind(
    doubles: _Doubles, tmp_path: Path
) -> None:
    dispatcher = _dispatcher(doubles)
    info = doubles.rasters.open_raster(tmp_path / "elevation.tif")

    page = _call(dispatcher, "layers.list")["value"]

    assert [item["kind"] for item in page["items"]] == ["raster"]
    assert page["items"][0]["id"] == info.id
    assert page["items"][0]["band_count"] == 1


# -- the stream -------------------------------------------------------------


def test_the_project_stream_emits_its_frames_in_order(
    doubles: _Doubles, tmp_path: Path
) -> None:
    dispatcher = _dispatcher(doubles)
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    opened = dispatcher.dispatch(
        binding,
        {
            "protocol": BRIDGE_PROTOCOL_VERSION,
            "kind": "subscribe",
            "call_id": "sub",
            "operation": "project.changed",
            "payload": {},
        },
    )
    assert opened["ok"] is True
    info = doubles.layers.open_vector(tmp_path / "sites.geojson")

    _the_project_stream_emits_phase1(binding, dispatcher, doubles, info)

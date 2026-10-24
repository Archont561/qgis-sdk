"""The curated host surface: declared, answered, and unable to drift.

Decision-27 makes the inventory the contract. Two things therefore have to be
true at once, and the tests here check both: every curated Protocol method is
either on the wire or recorded as deliberately absent, and the operations that
are on the wire really answer, page, validate and refuse as declared - without
Qt, QGIS or a browser anywhere in the picture.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from qgis_sdk.bridge import BridgeErrorCode, Dispatcher
from qgis_sdk.bridge.authority import HostAuthority
from qgis_sdk.bridge.host import (
    DEFAULT_PAGE,
    DEFERRED_HOST_METHODS,
    HOST_OPERATIONS,
    MAX_PAGE,
    HostServices,
    host_description,
    host_grants,
    register_host_operations,
)
from qgis_sdk.bridge.protocol import BRIDGE_PROTOCOL_VERSION, HOST_SCHEMA_VERSION
from qgis_sdk.models.errors import QgisSdkBridgeError
from qgis_sdk.models.layers import VectorLayerInfo
from qgis_sdk.network import NetworkGrant
from qgis_sdk.services.algorithms import Algorithms
from qgis_sdk.services.contracts import Notifications
from qgis_sdk.services.layers import Layers
from qgis_sdk.services.network import NetworkTransport
from qgis_sdk.services.project import Project
from qgis_sdk.services.settings import Settings
from qgis_sdk.services.styles import Styles
from qgis_sdk.testing import FakeNetworkTransport, reply

ORIGIN = "qgis://desktop"

#: The five curated Protocols plus Algorithms: decision-27 defers the sixth
#: because it starts work, which needs the job surface rather than a call.
PROTOCOLS: dict[str, type] = {
    "Layers": Layers,
    "Project": Project,
    "Settings": Settings,
    "Styles": Styles,
    "Notifications": Notifications,
    "Algorithms": Algorithms,
}


def _methods(protocol: type) -> set[str]:
    """Return the public method names a Protocol declares."""
    return {
        name
        for name, value in vars(protocol).items()
        if not name.startswith("_") and callable(value)
    }


@dataclass
class FakeLayers:
    layers: list[VectorLayerInfo] = field(default_factory=list)
    opened: list[Path] = field(default_factory=list)

    def open_vector(self, source: Path) -> VectorLayerInfo:
        assert isinstance(source, Path)
        self.opened.append(source)
        info = _info(len(self.layers))
        self.layers.append(info)
        return info

    def list_layers(self) -> tuple[VectorLayerInfo, ...]:
        return tuple(self.layers)

    def layer(self, layer_id: str) -> VectorLayerInfo:
        for info in self.layers:
            if info.id == layer_id:
                return info
        raise AssertionError(f"unknown layer {layer_id}")

    def selection(
        self, layer_id: str
    ) -> tuple[int, ...]:  # pragma: no cover - deferred
        raise AssertionError("selection is not on the wire")


@dataclass
class FakeProject:
    ids: list[str] = field(default_factory=list)

    def layer_ids(self) -> tuple[str, ...]:
        return tuple(self.ids)

    def add_layer(self, layer_id: str) -> None:  # pragma: no cover - deferred
        raise AssertionError("add_layer is not on the wire")


@dataclass
class FakeSettings:
    values: dict[str, str] = field(default_factory=dict)

    def get(self, key: str, default: str | None = None) -> str | None:
        return self.values.get(key, default)

    def set(self, key: str, value: str) -> None:  # pragma: no cover - deferred
        raise AssertionError("set is not on the wire")


@dataclass
class FakeStyles:
    applied: list[tuple[str, str]] = field(default_factory=list)

    def apply_style(self, layer_id: str, style: str) -> None:
        self.applied.append((layer_id, style))


@dataclass
class FakeNotifications:
    messages: list[str] = field(default_factory=list)

    def info(self, message: str) -> None:
        self.messages.append(message)


def _info(index: int) -> VectorLayerInfo:
    return VectorLayerInfo(
        id=f"layer-{index}",
        name=f"Layer {index}",
        geometry_type="point",
        field_names=("id",),
        crs="EPSG:4326",
    )


def _services(
    count: int = 5,
    *,
    authority: HostAuthority | None = None,
    network: FakeNetworkTransport | None = None,
) -> HostServices:
    return HostServices(
        layers=FakeLayers(layers=[_info(index) for index in range(count)]),
        project=FakeProject(ids=[f"layer-{index}" for index in range(count)]),
        settings=FakeSettings(values={"theme": "dark"}),
        styles=FakeStyles(),
        notifications=FakeNotifications(),
        authority=authority if authority is not None else HostAuthority(),
        network=network,
    )


def _empty(*, allow: bool = True) -> Dispatcher:
    """Return a dispatcher with nothing registered yet."""
    return Dispatcher(
        description={"schema_version": 1, "id": "demo.plugin", "title": "Demo"},
        authorize=(lambda binding, operation: True) if allow else None,
    )


def _dispatcher(
    services: HostServices, *, only: list[str] | None = None, allow: bool = True
) -> Dispatcher:
    dispatcher = _empty(allow=allow)
    register_host_operations(dispatcher, services, only=only)
    return dispatcher


def _call(
    dispatcher: Dispatcher,
    operation: str,
    payload: Any = None,
    *,
    binding: Any = None,
) -> dict:
    if binding is None:
        binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    request = {
        "protocol": BRIDGE_PROTOCOL_VERSION,
        "call_id": "call",
        "operation": operation,
        "payload": {} if payload is None else payload,
    }
    return dispatcher.dispatch(binding, request)


def _subscribe(
    dispatcher: Dispatcher, operation: str, payload: Any = None, *, binding: Any = None
) -> dict:
    if binding is None:
        binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    return dispatcher.dispatch(
        binding,
        {
            "protocol": BRIDGE_PROTOCOL_VERSION,
            "kind": "subscribe",
            "call_id": "sub",
            "operation": operation,
            "payload": {} if payload is None else payload,
        },
    )


# -- the inventory ---------------------------------------------------------


def test_every_protocol_method_is_either_on_the_wire_or_recorded_as_absent() -> None:
    """The manifest is the inventory: a new Protocol method cannot slip through."""
    on_the_wire = {operation.source for operation in HOST_OPERATIONS}
    accounted_for = on_the_wire | set(DEFERRED_HOST_METHODS)
    missing = sorted(
        f"{name}.{method}"
        for name, protocol in PROTOCOLS.items()
        for method in _methods(protocol)
        if f"{name}.{method}" not in accounted_for
    )
    assert missing == [], (
        "these Protocol methods are neither on the host surface nor recorded as "
        f"deferred: {missing}"
    )


#: Where an operation's ``source`` may point: the curated Protocols, plus the
#: two TASK-20 owners that are not Protocols - the authority behind file refs
#: and the network transport behind the fetch stream.
SOURCES: dict[str, type] = {
    **PROTOCOLS,
    "HostAuthority": HostAuthority,
    "NetworkTransport": NetworkTransport,
}


def test_each_operation_wraps_a_method_its_source_really_has() -> None:
    for operation in HOST_OPERATIONS:
        owner, _, method = operation.source.partition(".")
        assert owner in SOURCES, operation.source
        assert method in _methods(SOURCES[owner]), operation.source


def test_a_deferred_method_says_who_owns_it() -> None:
    for source, reason in DEFERRED_HOST_METHODS.items():
        assert source in {
            f"{name}.{method}"
            for name, protocol in PROTOCOLS.items()
            for method in _methods(protocol)
        }, source
        assert len(reason) > 30, source


def test_nothing_on_the_wire_takes_a_filesystem_path() -> None:
    """A page-supplied path is arbitrary local file read, so none is exposed."""
    for operation in HOST_OPERATIONS:
        properties = operation.request.get("properties", {})
        assert "path" not in properties, operation.id
        assert "source" not in properties, operation.id


def test_every_operation_carries_a_canonical_grant_and_a_gui_affinity() -> None:
    grants = host_grants()
    assert set(grants) == {operation.id for operation in HOST_OPERATIONS}
    assert set(grants.values()) == {
        "layers.read",
        "layers.open",
        "project.read",
        "settings.read",
        "notifications.info",
        "styles.apply",
        "files.export",
        "network.fetch",
    }
    for operation in HOST_OPERATIONS:
        # A namespace-wide flag would grant every future method at once.
        assert operation.grant.count(".") == 1
        assert operation.affinity == "gui"


def test_the_description_is_the_manifest_in_the_generator_shape() -> None:
    described = host_description()
    assert described["schema_version"] == HOST_SCHEMA_VERSION
    assert described["id"] == "qgis.host"
    assert [action["id"] for action in described["actions"]] == [
        operation.id for operation in HOST_OPERATIONS if operation.events is None
    ]
    assert [stream["id"] for stream in described["streams"]] == [
        operation.id for operation in HOST_OPERATIONS if operation.events is not None
    ]
    for action in described["actions"]:
        assert action["request"]["type"] == "object"
        result = action["result"]
        assert (
            result.get("additionalProperties") is False
            or result.get("type") == "null"
            or "anyOf" in result
        )
    for stream in described["streams"]:
        assert stream["request"]["type"] == "object"
        assert "result" not in stream
        assert set(stream["events"]) == {"data"}


# -- paging ----------------------------------------------------------------


def test_a_page_carries_a_cursor_only_when_something_is_left() -> None:
    dispatcher = _dispatcher(_services(5))

    first = _call(dispatcher, "layers.list", {"limit": 2})
    assert first["ok"] is True
    page = first["value"]
    assert [item["id"] for item in page["items"]] == ["layer-0", "layer-1"]
    assert page["truncated"] is True
    assert page["next_cursor"] == "2"

    rest = _call(dispatcher, "layers.list", {"cursor": page["next_cursor"], "limit": 2})
    assert [item["id"] for item in rest["value"]["items"]] == ["layer-2", "layer-3"]
    assert rest["value"]["next_cursor"] == "4"

    last = _call(dispatcher, "layers.list", {"cursor": "4", "limit": 2})
    assert [item["id"] for item in last["value"]["items"]] == ["layer-4"]
    assert last["value"]["truncated"] is False
    assert "next_cursor" not in last["value"]


def test_a_page_past_the_end_is_empty_rather_than_an_error() -> None:
    dispatcher = _dispatcher(_services(2))
    reply = _call(dispatcher, "layers.list", {"cursor": "99"})
    assert reply["ok"] is True
    assert reply["value"] == {"items": [], "truncated": False}


def test_the_default_and_maximum_page_sizes_are_declared() -> None:
    request = next(op for op in HOST_OPERATIONS if op.id == "layers.list").request
    limit = request["properties"]["limit"]
    assert limit["maximum"] == MAX_PAGE
    assert DEFAULT_PAGE <= MAX_PAGE

    dispatcher = _dispatcher(_services(3))
    too_large = _call(dispatcher, "layers.list", {"limit": MAX_PAGE + 1})
    assert too_large["ok"] is False
    assert too_large["error"]["code"] == BridgeErrorCode.INVALID_PAYLOAD.value


# -- the answers -----------------------------------------------------------


def test_layers_get_returns_a_plain_value_and_never_a_native_object() -> None:
    dispatcher = _dispatcher(_services(1))
    reply = _call(dispatcher, "layers.get", {"layer_id": "layer-0"})
    assert reply["ok"] is True
    assert reply["value"] == {
        "id": "layer-0",
        "name": "Layer 0",
        "geometry_type": "point",
        "field_names": ["id"],
        "crs": "EPSG:4326",
    }


def test_settings_get_returns_the_default_and_then_null() -> None:
    dispatcher = _dispatcher(_services(1))
    stored = _call(dispatcher, "settings.get", {"key": "theme"})
    assert stored["value"] == "dark"
    absent = _call(dispatcher, "settings.get", {"key": "missing"})
    assert absent["ok"] is True
    assert absent["value"] is None
    defaulted = _call(
        dispatcher, "settings.get", {"key": "missing", "default": "light"}
    )
    assert defaulted["value"] == "light"


def test_notifications_and_styles_reach_the_services_they_wrap() -> None:
    services = _services(1)
    dispatcher = _dispatcher(services)
    assert _call(dispatcher, "notifications.info", {"message": "hello"})["ok"] is True
    assert services.notifications.messages == ["hello"]
    applied = _call(
        dispatcher, "styles.apply", {"layer_id": "layer-0", "style": "sites"}
    )
    assert applied["ok"] is True
    assert applied["value"] is None
    assert services.styles.applied == [("layer-0", "sites")]


def test_a_paged_id_list_crosses_as_strings() -> None:
    dispatcher = _dispatcher(_services(3))
    reply = _call(dispatcher, "project.layer_ids", {"limit": 2})
    assert reply["value"] == {
        "items": ["layer-0", "layer-1"],
        "truncated": True,
        "next_cursor": "2",
    }


# -- the refusals ----------------------------------------------------------


def test_a_payload_the_declaration_forbids_is_refused_before_the_handler() -> None:
    dispatcher = _dispatcher(_services(1))
    unknown = _call(dispatcher, "layers.get", {"layer_id": "layer-0", "extra": 1})
    assert unknown["ok"] is False
    assert unknown["error"]["code"] == BridgeErrorCode.INVALID_PAYLOAD.value
    missing = _call(dispatcher, "layers.get", {})
    assert missing["error"]["code"] == BridgeErrorCode.INVALID_PAYLOAD.value
    mistyped = _call(dispatcher, "notifications.info", {"message": 7})
    assert mistyped["error"]["code"] == BridgeErrorCode.INVALID_PAYLOAD.value


def test_an_operation_that_was_not_registered_is_unknown_not_answered() -> None:
    dispatcher = _dispatcher(_services(1), only=["layers.get"])
    assert _call(dispatcher, "layers.get", {"layer_id": "layer-0"})["ok"] is True
    refused = _call(dispatcher, "settings.get", {"key": "theme"})
    assert refused["ok"] is False
    assert refused["error"]["code"] == BridgeErrorCode.UNKNOWN_OPERATION.value


def test_a_view_without_authorization_gets_nothing() -> None:
    dispatcher = Dispatcher(
        description={"schema_version": 1, "id": "demo.plugin", "title": "Demo"},
        authorize=lambda binding, operation: False,
    )
    register_host_operations(dispatcher, _services(1))
    refused = _call(dispatcher, "layers.list")
    assert refused["ok"] is False
    assert refused["error"]["code"] == BridgeErrorCode.NOT_AUTHORIZED.value


# -- the handshake ---------------------------------------------------------


def test_the_handshake_advertises_the_host_version_and_the_registered_ids() -> None:
    services = _services(1)
    dispatcher = _dispatcher(services, only=["layers.get", "settings.get"])
    _, handshake = dispatcher.handshake(view_id="view-1", origin=ORIGIN)
    assert handshake["host_schema_version"] == HOST_SCHEMA_VERSION
    assert [operation["id"] for operation in handshake["operations"]] == [
        "layers.get",
        "settings.get",
    ]


def test_a_registration_returns_the_ids_in_manifest_order() -> None:
    dispatcher = Dispatcher(
        description={"schema_version": 1, "id": "demo.plugin", "title": "Demo"},
        authorize=lambda binding, operation: True,
    )
    registered = register_host_operations(dispatcher, _services(1))
    assert registered == tuple(operation.id for operation in HOST_OPERATIONS)


def test_a_second_registration_is_refused_rather_than_overwriting() -> None:
    dispatcher = _dispatcher(_services(1))
    with pytest.raises(QgisSdkBridgeError, match="duplicate operation id"):
        register_host_operations(dispatcher, _services(1))


@pytest.mark.parametrize("operation", ["layers.list", "project.layer_ids"])
@pytest.mark.parametrize("cursor", ["abc", "-3", "2.7", " 2", "", "\u0663"])
def test_a_cursor_this_host_did_not_issue_is_refused(
    operation: str, cursor: str
) -> None:
    """A malformed cursor must not be read as "start over"."""
    dispatcher = _dispatcher(_services(5))
    reply = _call(dispatcher, operation, {"cursor": cursor})
    assert reply["ok"] is False
    assert reply["error"]["code"] == BridgeErrorCode.INVALID_PAYLOAD.value
    assert "cursor" in reply["error"]["message"]


def test_a_refused_cursor_never_reaches_the_wrapped_method() -> None:
    services = _services(5)
    seen: list[str] = []
    original = services.layers.list_layers

    def record() -> tuple[VectorLayerInfo, ...]:
        seen.append("list_layers")
        return original()

    services.layers.list_layers = record  # type: ignore[method-assign]
    dispatcher = _dispatcher(services)
    refused = _call(dispatcher, "layers.list", {"cursor": "nope"})
    assert refused["error"]["code"] == BridgeErrorCode.INVALID_PAYLOAD.value
    assert seen == []
    assert _call(dispatcher, "layers.list")["ok"] is True
    assert seen == ["list_layers"]


def test_an_only_id_that_is_not_declared_is_refused_and_registers_nothing() -> None:
    dispatcher = _empty()
    with pytest.raises(QgisSdkBridgeError, match="layers.lst"):
        register_host_operations(
            dispatcher, _services(1), only=["layers.get", "layers.lst"]
        )
    assert dispatcher.operations() == ()


def test_a_conflicting_registration_leaves_the_dispatcher_untouched() -> None:
    dispatcher = _empty()
    register_host_operations(dispatcher, _services(1), only=["styles.apply"])
    before = dispatcher.operations()
    with pytest.raises(QgisSdkBridgeError, match="duplicate operation id"):
        register_host_operations(dispatcher, _services(1))
    assert dispatcher.operations() == before
    refused = _call(dispatcher, "settings.get", {"key": "theme"})
    assert refused["error"]["code"] == BridgeErrorCode.UNKNOWN_OPERATION.value
    assert (
        _call(dispatcher, "styles.apply", {"layer_id": "layer-0", "style": "sites"})[
            "ok"
        ]
        is True
    )


# -- scoped authority: file refs and network grants (TASK-20) --------------


def _granted(tmp_path: Path):
    """A dispatcher, its services, the owning binding and a readable ref."""
    dataset = tmp_path / "sites.geojson"
    dataset.write_text("{}", encoding="utf-8")
    services = _services(1)
    dispatcher = _dispatcher(services)
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    ref = services.authority.grant_file(binding, dataset, source="picker")
    return dispatcher, services, binding, ref, dataset


def test_open_vector_takes_a_host_minted_ref_and_opens_its_canonical_path(
    tmp_path: Path,
) -> None:
    dispatcher, services, binding, ref, dataset = _granted(tmp_path)

    opened = _call(
        dispatcher, "layers.open_vector", {"file": ref.to_wire()}, binding=binding
    )

    assert opened["ok"] is True
    assert opened["value"]["id"] == "layer-1"
    assert services.layers.opened == [dataset.resolve()]


def test_open_vector_refuses_a_path_a_foreign_ref_and_a_stale_ref(
    tmp_path: Path,
) -> None:
    dispatcher, services, _binding, ref, dataset = _granted(tmp_path)

    path = _call(dispatcher, "layers.open_vector", {"file": str(dataset)})
    assert path["error"]["code"] == BridgeErrorCode.INVALID_PAYLOAD.value
    forged_kind = _call(
        dispatcher, "layers.open_vector", {"file": {"kind": "layer", "id": ref.id}}
    )
    assert forged_kind["error"]["code"] == BridgeErrorCode.INVALID_PAYLOAD.value

    other = dispatcher.bind(view_id="view-2", origin=ORIGIN)
    foreign = _call(
        dispatcher, "layers.open_vector", {"file": ref.to_wire()}, binding=other
    )
    assert foreign["error"]["code"] == BridgeErrorCode.UNKNOWN_HANDLE.value

    dispatcher.advance_generation()
    later = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    stale = _call(
        dispatcher, "layers.open_vector", {"file": ref.to_wire()}, binding=later
    )
    assert stale["error"]["code"] == BridgeErrorCode.STALE_HANDLE.value
    assert services.layers.opened == []
    for refusal in (path, forged_kind, foreign, stale):
        assert str(dataset) not in refusal["error"]["message"]


def test_a_write_only_ref_cannot_be_opened(tmp_path: Path) -> None:
    services = _services(1)
    dispatcher = _dispatcher(services)
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    ref = services.authority.grant_file(
        binding, tmp_path / "out.csv", operations=("write",)
    )
    refused = _call(
        dispatcher, "layers.open_vector", {"file": ref.to_wire()}, binding=binding
    )
    assert refused["error"]["code"] == BridgeErrorCode.GRANT_REFUSED.value


def test_files_export_writes_through_a_write_ref_and_reports_the_size(
    tmp_path: Path,
) -> None:
    services = _services(1)
    dispatcher = _dispatcher(services)
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    ref = services.authority.grant_file(
        binding, tmp_path / "out.csv", operations=("write",), source="picker"
    )

    written = _call(
        dispatcher,
        "files.export",
        {"file": ref.to_wire(), "content": "a,b\n"},
        binding=binding,
    )

    assert written["ok"] is True
    assert written["value"] == {"bytes_written": 4, "name": "out.csv"}
    assert (tmp_path / "out.csv").read_text(encoding="utf-8") == "a,b\n"

    again = _call(
        dispatcher,
        "files.export",
        {"file": ref.to_wire(), "content": "changed"},
        binding=binding,
    )
    assert again["error"]["code"] == BridgeErrorCode.GRANT_REFUSED.value
    assert (tmp_path / "out.csv").read_text(encoding="utf-8") == "a,b\n"


def test_files_export_through_a_read_ref_is_refused(tmp_path: Path) -> None:
    dispatcher, _, binding, ref, dataset = _granted(tmp_path)
    refused = _call(
        dispatcher,
        "files.export",
        {"file": ref.to_wire(), "content": "x"},
        binding=binding,
    )
    assert refused["error"]["code"] == BridgeErrorCode.GRANT_REFUSED.value
    assert dataset.read_text(encoding="utf-8") == "{}"


def _fetching(hold: bool = True):
    network = FakeNetworkTransport()
    services = _services(1, network=network)
    dispatcher = _dispatcher(services)
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    services.authority.grant_network(
        binding, NetworkGrant(origins=("https://api.example.org",), max_body_bytes=64)
    )
    return dispatcher, services, binding, network


def test_network_fetch_is_a_stream_that_answers_once_through_the_grant() -> None:
    dispatcher, _, binding, network = _fetching()
    network.expect(
        "GET",
        "https://api.example.org/collections",
        reply(json={"collections": []}, headers={"X-Trace": "t1"}),
        hold=True,
    )

    opened = _subscribe(
        dispatcher,
        "network.fetch",
        {
            "url": "https://api.example.org/collections",
            "headers": [{"name": "Accept", "value": "application/json"}],
        },
        binding=binding,
    )

    assert opened["ok"] is True
    (sent,) = network.requests
    assert sent.method == "GET"
    assert sent.headers["accept"] == "application/json"
    assert sent.allowed_origins == frozenset({"https://api.example.org"})
    assert sent.max_body_bytes == 64
    assert dispatcher.pump(binding) == []

    network.pending[0].deliver()
    data, terminal = dispatcher.pump(binding)

    assert data["event"]["kind"] == "data"
    assert data["event"]["payload"] == {
        "url": "https://api.example.org/collections",
        "status_code": 200,
        "reason": "OK",
        "headers": [
            {"name": "Content-Type", "value": "application/json"},
            {"name": "X-Trace", "value": "t1"},
        ],
        "text": '{"collections": []}',
        "base64": None,
    }
    assert terminal["terminal"] == {"kind": "complete"}


def test_network_fetch_without_a_grant_or_outside_it_is_refused_before_sending() -> (
    None
):
    dispatcher, _, binding, network = _fetching()
    other = dispatcher.bind(view_id="view-2", origin=ORIGIN)

    ungranted = _subscribe(
        dispatcher, "network.fetch", {"url": "https://api.example.org/"}, binding=other
    )
    assert ungranted["error"]["code"] == BridgeErrorCode.GRANT_REFUSED.value
    elsewhere = _subscribe(
        dispatcher,
        "network.fetch",
        {"url": "https://evil.example.org/"},
        binding=binding,
    )
    assert elsewhere["error"]["code"] == BridgeErrorCode.GRANT_REFUSED.value
    assert "evil.example.org" in elsewhere["error"]["message"]
    method = _subscribe(
        dispatcher,
        "network.fetch",
        {"url": "https://api.example.org/", "method": "DELETE"},
        binding=binding,
    )
    assert method["error"]["code"] == BridgeErrorCode.GRANT_REFUSED.value
    auth = _subscribe(
        dispatcher,
        "network.fetch",
        {"url": "https://api.example.org/", "auth_config": "cfg1"},
        binding=binding,
    )
    assert auth["error"]["code"] == BridgeErrorCode.GRANT_REFUSED.value
    malformed = _subscribe(
        dispatcher,
        "network.fetch",
        {"url": "https://u:p@api.example.org/"},
        binding=binding,
    )
    assert malformed["error"]["code"] == BridgeErrorCode.OPERATION_FAILED.value
    assert network.requests == []


def test_network_fetch_hands_a_status_over_as_data_and_a_failure_as_terminal() -> None:
    dispatcher, _, binding, network = _fetching()
    network.expect("GET", "https://api.example.org/down", reply(503, body="later"))
    opened = _subscribe(
        dispatcher,
        "network.fetch",
        {"url": "https://api.example.org/down"},
        binding=binding,
    )
    assert opened["ok"] is True
    data, terminal = dispatcher.pump(binding)
    assert data["event"]["payload"]["status_code"] == 503
    assert terminal["terminal"]["kind"] == "complete"

    network.expect(
        "GET",
        "https://api.example.org/big",
        reply(200, body=b"x" * 65),
    )
    opened = _subscribe(
        dispatcher,
        "network.fetch",
        {"url": "https://api.example.org/big"},
        binding=binding,
    )
    assert opened["ok"] is True
    (terminal,) = dispatcher.pump(binding)
    assert terminal["terminal"]["kind"] == "error"
    assert "64" in terminal["terminal"]["message"]


def test_network_fetch_hands_a_binary_body_over_as_base64() -> None:
    dispatcher, _, binding, network = _fetching()
    payload = bytes([0x89, 0x50, 0x4E, 0x47, 0xFF, 0xFE])
    network.expect(
        "GET",
        "https://api.example.org/tile",
        reply(200, body=payload, headers={"Content-Type": "image/png"}),
    )
    _subscribe(
        dispatcher,
        "network.fetch",
        {"url": "https://api.example.org/tile"},
        binding=binding,
    )
    data, _terminal = dispatcher.pump(binding)
    assert data["event"]["payload"]["text"] is None
    assert base64.b64decode(data["event"]["payload"]["base64"]) == payload


def test_disposing_a_fetch_cancels_the_request_and_a_late_reply_is_dropped() -> None:
    dispatcher, _, binding, network = _fetching()
    network.expect(
        "GET", "https://api.example.org/slow", reply(200, body="late"), hold=True
    )
    opened = _subscribe(
        dispatcher,
        "network.fetch",
        {"url": "https://api.example.org/slow"},
        binding=binding,
    )

    dispatcher.dispatch(
        binding,
        {
            "protocol": BRIDGE_PROTOCOL_VERSION,
            "kind": "unsubscribe",
            "call_id": "unsub",
            "subscription_id": opened["value"]["subscription_id"],
        },
    )

    assert len(network.cancelled) == 1
    assert dispatcher.pump(binding) == []


def test_network_fetch_posts_a_body_and_keeps_the_methods_the_grant_allows() -> None:
    dispatcher, services, binding, network = _fetching()
    services.authority.grant_network(
        binding,
        NetworkGrant(origins=("https://api.example.org",), methods=("POST",)),
    )
    network.expect("POST", "https://api.example.org/items", reply(201, body="made"))

    opened = _subscribe(
        dispatcher,
        "network.fetch",
        {
            "url": "https://api.example.org/items",
            "method": "POST",
            "body": '{"a": 1}',
            "headers": [{"name": "Content-Type", "value": "application/json"}],
            "timeout_seconds": 5,
        },
        binding=binding,
    )

    assert opened["ok"] is True
    (sent,) = network.requests
    assert sent.body == b'{"a": 1}'
    assert sent.timeout_seconds == 5
    data, _terminal = dispatcher.pump(binding)
    assert data["event"]["payload"]["status_code"] == 201


def test_network_fetch_without_a_transport_fails_rather_than_pretending() -> None:
    services = _services(1)
    dispatcher = _dispatcher(services)
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    services.authority.grant_network(
        binding, NetworkGrant(origins=("https://api.example.org",))
    )
    opened = _subscribe(
        dispatcher,
        "network.fetch",
        {"url": "https://api.example.org/"},
        binding=binding,
    )
    assert opened["ok"] is False
    assert opened["error"]["code"] == BridgeErrorCode.OPERATION_FAILED.value
    assert "network" in opened["error"]["message"]

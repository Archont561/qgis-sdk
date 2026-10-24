"""The curated host surface: declared, answered, and unable to drift.

Decision-27 makes the inventory the contract. Two things therefore have to be
true at once, and the tests here check both: every curated Protocol method is
either on the wire or recorded as deliberately absent, and the operations that
are on the wire really answer, page, validate and refuse as declared - without
Qt, QGIS or a browser anywhere in the picture.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import pytest
from qgis_sdk.bridge import BridgeErrorCode, Dispatcher
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
from qgis_sdk.services.algorithms import Algorithms
from qgis_sdk.services.contracts import Notifications
from qgis_sdk.services.layers import Layers
from qgis_sdk.services.project import Project
from qgis_sdk.services.settings import Settings
from qgis_sdk.services.styles import Styles

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

    def open_vector(
        self, source: Any
    ) -> VectorLayerInfo:  # pragma: no cover - deferred
        raise AssertionError("open_vector is not on the wire")

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


def _services(count: int = 5) -> HostServices:
    return HostServices(
        layers=FakeLayers(layers=[_info(index) for index in range(count)]),
        project=FakeProject(ids=[f"layer-{index}" for index in range(count)]),
        settings=FakeSettings(values={"theme": "dark"}),
        styles=FakeStyles(),
        notifications=FakeNotifications(),
    )


def _dispatcher(
    services: HostServices, *, only: list[str] | None = None, allow: bool = True
) -> Dispatcher:
    dispatcher = Dispatcher(
        description={"schema_version": 1, "id": "demo.plugin", "title": "Demo"},
        authorize=(lambda binding, operation: True) if allow else None,
    )
    register_host_operations(dispatcher, services, only=only)
    return dispatcher


def _call(
    dispatcher: Dispatcher,
    operation: str,
    payload: Any = None,
    *,
    authorize_with: Callable[[Any, str], bool] | None = None,
) -> dict:
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    request = {
        "protocol": BRIDGE_PROTOCOL_VERSION,
        "call_id": "call",
        "operation": operation,
        "payload": {} if payload is None else payload,
    }
    return dispatcher.dispatch(binding, request)


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


def test_each_operation_wraps_a_method_its_protocol_really_has() -> None:
    for operation in HOST_OPERATIONS:
        protocol_name, _, method = operation.source.partition(".")
        assert protocol_name in PROTOCOLS, operation.source
        assert method in _methods(PROTOCOLS[protocol_name]), operation.source


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
        "project.read",
        "settings.read",
        "notifications.info",
        "styles.apply",
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
        operation.id for operation in HOST_OPERATIONS
    ]
    for action in described["actions"]:
        assert action["request"]["type"] == "object"
        result = action["result"]
        assert (
            result.get("additionalProperties") is False
            or result.get("type") == "null"
            or "anyOf" in result
        )


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

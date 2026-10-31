"""Features, expressions and editing over the curated host surface.

decision-54 point 3 puts four things on the wire: a bounded, deterministic page
stream; one feature by id in a named geometry encoding; an expression that is
either a value or a message; and an editing session that lives as long as the
view that began it. The tests here answer each of them against the fake backend,
so the contract is checked without Qt, QGIS or a browser - and so the same page
shapes the native adapter returns are the ones the fake returns.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from qgis_sdk.bridge import BridgeErrorCode, Dispatcher, ViewBinding
from qgis_sdk.bridge.authority import HostAuthority
from qgis_sdk.bridge.host import (
    DEFAULT_FEATURE_PAGE,
    MAX_FEATURE_PAGE,
    HostServices,
    register_host_operations,
)
from qgis_sdk.bridge.protocol import BRIDGE_PROTOCOL_VERSION
from qgis_sdk.bridge.streams import MAX_FRAMES_PER_PUMP
from qgis_sdk.core import ResourceScope
from qgis_sdk.models import FeatureQuery, Geometry
from qgis_sdk.models.errors import QgisSdkLayerNotFoundError
from qgis_sdk.testing import FakeFeatures, FakeNetworkTransport

ORIGIN = "qgis://desktop"


def _point(x: int, y: int) -> Geometry:
    return Geometry(
        encoding="wkt", value=f"POINT ({x} {y})", geometry_type="point", crs="EPSG:4326"
    )


def _features(scope: ResourceScope) -> FakeFeatures:
    service = FakeFeatures(scope)
    service.declare(
        "parcels",
        fields=("name", "area"),
        rows=[
            (1, {"name": "A", "area": 10}, {"wkt": _point(0, 0)}),
            (2, {"name": "B", "area": 20}, {"wkt": _point(1, 1)}),
            (3, {"name": "C", "area": 30}, {"wkt": _point(2, 2)}),
            (4, {"name": "D", "area": 40}, {"wkt": _point(3, 3)}),
            (5, {"name": "E", "area": 50}, {"wkt": _point(4, 4)}),
        ],
    )
    service.declare("scan", fields=("name",), editable=False)
    return service


@pytest.fixture(name="scope")
def fixture_scope() -> Iterator[ResourceScope]:
    scope = ResourceScope()
    yield scope
    scope.close()


@pytest.fixture(name="features")
def fixture_features(scope: ResourceScope) -> FakeFeatures:
    return _features(scope)


class _Layers:
    def list_layers(self) -> tuple[Any, ...]:
        return ()

    def layer(self, layer_id: str) -> Any:  # pragma: no cover - not called here
        raise AssertionError(layer_id)


class _Project:
    def layer_ids(self) -> tuple[str, ...]:
        return ()


class _Settings:
    def get(self, key: str, default: str | None = None) -> str | None:
        return default


class _Styles:
    def apply_style(self, layer_id: str, style: str) -> None:  # pragma: no cover
        raise AssertionError((layer_id, style))


class _Notifications:
    def info(self, message: str) -> None:  # pragma: no cover - not called here
        raise AssertionError(message)


def _services(features: FakeFeatures) -> HostServices:
    return HostServices(
        layers=_Layers(),
        project=_Project(),
        settings=_Settings(),
        styles=_Styles(),
        notifications=_Notifications(),
        features=features,
        authority=HostAuthority(),
        network=FakeNetworkTransport(),
    )


def _dispatcher_for(
    features: FakeFeatures,
    *,
    authorize: Any = None,
) -> Dispatcher:
    dispatcher = Dispatcher(
        description={"schema_version": 1, "id": "demo.plugin", "title": "Demo"},
        authorize=authorize if authorize is not None else (lambda binding, op: True),
    )
    register_host_operations(dispatcher, _services(features))
    return dispatcher


@pytest.fixture(name="dispatcher")
def fixture_dispatcher(features: FakeFeatures) -> Dispatcher:
    return _dispatcher_for(features)


def _call(dispatcher: Dispatcher, operation: str, payload: Any = None) -> dict:
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


def _subscribe(
    dispatcher: Dispatcher, binding: ViewBinding, payload: Any
) -> dict[str, Any]:
    return dispatcher.dispatch(
        binding,
        {
            "protocol": BRIDGE_PROTOCOL_VERSION,
            "kind": "subscribe",
            "call_id": "sub-1",
            "operation": "features.page",
            "payload": payload,
        },
    )


def _ack(dispatcher: Dispatcher, binding: ViewBinding, subscription_id: str, seq: int):
    return dispatcher.dispatch(
        binding,
        {
            "protocol": BRIDGE_PROTOCOL_VERSION,
            "kind": "ack",
            "call_id": f"ack-{seq}",
            "subscription_id": subscription_id,
            "seq": seq,
        },
    )


def _pages(
    dispatcher: Dispatcher, binding: ViewBinding, payload: dict[str, Any]
) -> list[dict[str, Any]]:
    """Walk a page stream the way a protocol-2 client does: pump, then ack."""
    opened = _subscribe(dispatcher, binding, payload)
    assert opened["ok"] is True, opened
    subscription_id = opened["value"]["subscription_id"]
    pages: list[dict[str, Any]] = []
    for _ in range(64):
        batch = dispatcher.pump(binding, limit=MAX_FRAMES_PER_PUMP)
        if not batch:
            break
        for frame in batch:
            if "terminal" in frame:
                assert frame["terminal"]["kind"] == "complete", frame
                return pages
            pages.append(frame["event"]["payload"])
            _ack(dispatcher, binding, subscription_id, frame["seq"])
    return pages


# -- paging ------------------------------------------------------------------


def test_a_page_stream_walks_the_layer_in_bounded_id_ordered_pages(
    dispatcher: Dispatcher,
) -> None:
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)

    pages = _pages(
        dispatcher, binding, {"layer_id": "parcels", "limit": 2, "encoding": "wkt"}
    )

    assert [[item["id"] for item in page["items"]] for page in pages] == [
        [1, 2],
        [3, 4],
        [5],
    ]
    assert [page["truncated"] for page in pages] == [True, True, False]
    # The cursor is the last id of the page, so a provider that reorders between
    # two calls cannot make a reader skip a row.
    assert [page.get("next_cursor") for page in pages] == ["2", "4", None]
    assert all(len(page["items"]) <= 2 for page in pages)


def test_a_page_stream_filters_on_the_provider_not_in_the_page(
    dispatcher: Dispatcher,
) -> None:
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)

    pages = _pages(
        dispatcher,
        binding,
        {
            "layer_id": "parcels",
            "limit": 2,
            "encoding": "wkt",
            "expression": '"area" > 25',
        },
    )

    assert [item["id"] for page in pages for item in page["items"]] == [3, 4, 5]
    # A page says it is truncated whenever more rows remain, so a caller
    # walking pages never mistakes the end of a page for the end of the layer.
    assert [page["truncated"] for page in pages] == [True, False]


def test_a_page_over_the_ceiling_is_refused_by_name(dispatcher: Dispatcher) -> None:
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)

    reply = _subscribe(
        dispatcher,
        binding,
        {"layer_id": "parcels", "limit": MAX_FEATURE_PAGE + 1, "encoding": "wkt"},
    )

    assert reply["ok"] is False
    assert reply["error"]["code"] == BridgeErrorCode.INVALID_PAYLOAD.value
    assert str(MAX_FEATURE_PAGE) in reply["error"]["message"]


def test_a_page_without_a_size_asks_the_default(dispatcher: Dispatcher) -> None:
    """The default is the query's, so the fake and the native adapter agree."""
    assert DEFAULT_FEATURE_PAGE == FeatureQuery().limit


def test_a_page_with_a_bbox_that_is_not_four_numbers_is_refused(
    dispatcher: Dispatcher,
) -> None:
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)

    reply = _subscribe(
        dispatcher,
        binding,
        {"layer_id": "parcels", "bbox": [0, 0, 1], "encoding": "wkt"},
    )

    assert reply["ok"] is False
    assert reply["error"]["code"] == BridgeErrorCode.INVALID_PAYLOAD.value
    assert "bbox" in reply["error"]["message"]


def test_a_page_for_an_unknown_layer_says_which(dispatcher: Dispatcher) -> None:
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)

    opened = _subscribe(dispatcher, binding, {"layer_id": "nowhere"})
    assert opened["ok"] is True, opened

    frames = dispatcher.pump(binding)
    assert frames[-1]["terminal"]["kind"] == "error"
    assert "nowhere" in frames[-1]["terminal"]["message"]


def test_one_feature_crosses_in_the_encoding_it_was_asked_for(
    dispatcher: Dispatcher,
) -> None:
    reply = _call(
        dispatcher,
        "features.get",
        {"layer_id": "parcels", "feature_id": 3, "encoding": "wkt"},
    )

    assert reply["ok"] is True, reply
    feature = reply["value"]
    assert feature["id"] == 3
    assert feature["attributes"] == {"name": "C", "area": 30}
    assert feature["geometry"]["encoding"] == "wkt"
    assert feature["geometry"]["geometry_type"] == "point"


def test_one_feature_in_an_encoding_the_layer_does_not_hold_is_refused(
    dispatcher: Dispatcher,
) -> None:
    """The fake never converts: a conversion is a geometry engine's job."""
    reply = _call(
        dispatcher,
        "features.get",
        {"layer_id": "parcels", "feature_id": 3, "encoding": "geojson"},
    )

    assert reply["ok"] is False
    assert "geojson" in reply["error"]["message"]


# -- expressions -------------------------------------------------------------


def test_an_expression_returns_a_value_or_a_message(dispatcher: Dispatcher) -> None:
    """An unparseable expression is an answer, not a failed call (decision-54)."""
    value = _call(dispatcher, "expressions.evaluate", {"text": "42"})
    broken = _call(dispatcher, "expressions.evaluate", {"text": "1 +"})
    checked = _call(dispatcher, "expressions.validate", {"text": "1 +"})

    assert value["ok"] is True, value
    assert value["value"] == {"valid": True, "value": 42, "message": None}
    assert broken["ok"] is True, broken
    assert broken["value"]["valid"] is False
    assert broken["value"]["message"]
    assert checked["ok"] is True, checked
    assert checked["value"]["valid"] is False
    assert checked["value"]["message"]


def test_an_expression_over_a_feature_reads_its_columns(
    dispatcher: Dispatcher,
) -> None:
    reply = _call(
        dispatcher,
        "expressions.evaluate",
        {"text": '"area" > 25', "layer_id": "parcels", "feature_id": 4},
    )

    assert reply["ok"] is True, reply
    assert reply["value"] == {
        "valid": True,
        "value": True,
        "message": None,
    }


def test_the_fake_refuses_the_expressions_it_does_not_parse(
    dispatcher: Dispatcher,
) -> None:
    """A function call is outside the documented subset, and named as such."""
    reply = _call(dispatcher, "expressions.evaluate", {"text": "buffer($geometry, 10)"})

    assert reply["ok"] is True, reply
    assert reply["value"]["valid"] is False
    # ``buffer(`` is not in the subset, and the refusal names the construct it
    # could not read rather than pretending to have run it.
    assert "$geometry" in reply["value"]["message"]


def test_validate_names_the_columns_an_expression_reads(dispatcher: Dispatcher) -> None:
    reply = _call(
        dispatcher,
        "expressions.validate",
        {"text": '"area" > 25', "layer_id": "parcels"},
    )

    assert reply["ok"] is True, reply
    assert reply["value"]["valid"] is True
    assert reply["value"]["referenced_columns"] == ["area"]


# -- editing -----------------------------------------------------------------


def _begin(dispatcher: Dispatcher) -> str:
    reply = _call(dispatcher, "editing.begin", {"layer_id": "parcels"})
    assert reply["ok"] is True, reply
    assert reply["value"]["layer_id"] == "parcels"
    return reply["value"]["session_id"]


def test_an_editing_session_adds_updates_and_commits(dispatcher: Dispatcher) -> None:
    session_id = _begin(dispatcher)

    added = _call(
        dispatcher,
        "editing.add",
        {"session_id": session_id, "attributes": {"name": "F", "area": 60}},
    )
    assert added["ok"] is True, added
    feature_id = added["value"]["feature_id"]
    assert added["value"]["pending"] == 1

    updated = _call(
        dispatcher,
        "editing.update",
        {"session_id": session_id, "feature_id": 1, "attributes": {"area": 11}},
    )
    assert updated["ok"] is True, updated
    assert updated["value"]["pending"] == 2

    committed = _call(dispatcher, "editing.commit", {"session_id": session_id})

    assert committed["ok"] is True, committed
    assert committed["value"]["committed"] is True
    assert committed["value"]["applied"] == 2
    assert feature_id in committed["value"]["feature_ids"]

    read_back = _call(
        dispatcher, "features.get", {"layer_id": "parcels", "feature_id": feature_id}
    )
    assert read_back["ok"] is True
    assert read_back["value"]["attributes"] == {"name": "F", "area": 60}


def test_a_rollback_discards_what_the_session_held(dispatcher: Dispatcher) -> None:
    session_id = _begin(dispatcher)
    _call(
        dispatcher,
        "editing.add",
        {"session_id": session_id, "attributes": {"name": "F", "area": 60}},
    )

    rolled = _call(dispatcher, "editing.rollback", {"session_id": session_id})

    assert rolled["ok"] is True, rolled
    assert rolled["value"]["pending"] == 0
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    pages = _pages(dispatcher, binding, {"layer_id": "parcels", "encoding": "wkt"})
    assert len([item for page in pages for item in page["items"]]) == 5


def test_editing_a_layer_that_refuses_edits_is_refused_by_name(
    dispatcher: Dispatcher,
) -> None:
    reply = _call(dispatcher, "editing.begin", {"layer_id": "scan"})

    assert reply["ok"] is False
    assert "read-only" in reply["error"]["message"]


def test_a_session_id_from_another_view_is_refused(dispatcher: Dispatcher) -> None:
    session_id = _begin(dispatcher)
    other = dispatcher.bind(view_id="view-2", origin=ORIGIN)

    reply = dispatcher.dispatch(
        other,
        {
            "protocol": BRIDGE_PROTOCOL_VERSION,
            "call_id": "call",
            "operation": "editing.add",
            "payload": {"session_id": session_id, "attributes": {"name": "X"}},
        },
    )

    assert reply["ok"] is False
    assert session_id in reply["error"]["message"]


def test_disposing_a_view_closes_the_sessions_it_began(
    dispatcher: Dispatcher, features: FakeFeatures
) -> None:
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    session_id = _begin(dispatcher)
    assert features.session(session_id).pending == 0

    dispatcher.dispose(binding)

    with pytest.raises(QgisSdkLayerNotFoundError):
        features.session(session_id)


def test_an_unknown_session_id_is_refused_by_name(dispatcher: Dispatcher) -> None:
    reply = _call(dispatcher, "editing.commit", {"session_id": "session-9"})

    assert reply["ok"] is False
    assert "session-9" in reply["error"]["message"]


def test_a_grant_is_required_for_every_new_operation(
    features: FakeFeatures,
) -> None:
    dispatcher = _dispatcher_for(
        features,
        authorize=lambda binding, operation: not operation.startswith("editing."),
    )
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)

    assert _subscribe(dispatcher, binding, {"layer_id": "parcels"})["ok"] is True
    refused = dispatcher.dispatch(
        binding,
        {
            "protocol": BRIDGE_PROTOCOL_VERSION,
            "call_id": "call",
            "operation": "editing.begin",
            "payload": {"layer_id": "parcels"},
        },
    )

    assert refused["ok"] is False
    assert refused["error"]["code"] == BridgeErrorCode.NOT_AUTHORIZED.value

"""The endpoint's edges, reached through the surface a host actually uses.

``test_bridge_dispatch.py`` covers the decisions a well-formed call goes
through, and ``test_bridge_dispatch_properties.py`` covers what holds for any
message at all. What is left is the object's own edge: the description it is
built from, the binding it mints, and the sources a subscription is handed -
each of which can be wrong in one way, and each of which has to say so by name
rather than by an exception that crosses the transport.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any

import pytest
from qgis_sdk.bridge import BRIDGE_PROTOCOL_VERSION, BridgeOperation, Dispatcher
from qgis_sdk.bridge.dispatch import _ref_inputs as ref_inputs
from qgis_sdk.bridge.endpoint._wire import wire_size
from qgis_sdk.models.errors import QgisSdkBridgeError, QgisSdkLayerNotFoundError

ECHO = BridgeOperation(id="edge.echo", title="Echo")
STREAM = BridgeOperation(id="edge.stream", title="A stream")
VIEW = "view-1"
ORIGIN = "qgis://desktop"


def _call(kind: str, **fields: Any) -> dict[str, Any]:
    """One call of ``kind``, carrying whatever the caller says it carries."""
    return {
        "protocol": BRIDGE_PROTOCOL_VERSION,
        "call_id": f"{kind}-1",
        "kind": kind,
        **fields,
    }


def _allow(binding: Any, operation: str) -> bool:
    """An authorizer that grants everything the allowlist holds."""
    return True


def _dispatcher(authorize: Any = _allow) -> Dispatcher:
    """A dispatcher holding one action, with an authorizer that grants it."""
    dispatcher = Dispatcher(authorize=authorize)
    dispatcher.register(ECHO, lambda payload: {"value": payload.get("value")})
    return dispatcher


class _Pushed:
    """A push source that can fail while starting, and counts its closes."""

    def __init__(self, error: Exception | None = None) -> None:
        self._error = error
        self.closed = False

    def start(self, sink: Any) -> None:
        if self._error is not None:
            raise self._error

    def close(self) -> None:
        self.closed = True


def test_the_generation_is_the_one_the_views_hold() -> None:
    dispatcher = _dispatcher()

    assert dispatcher.generation == 0
    assert dispatcher.advance_generation() == 1
    assert dispatcher.generation == 1


def test_an_unknown_call_kind_is_refused_by_name() -> None:
    dispatcher = _dispatcher()

    reply = dispatcher.dispatch(
        dispatcher.bind(view_id=VIEW, origin=ORIGIN), _call("teleport")
    )

    assert reply["ok"] is False
    assert reply["error"]["code"] == "invalid_bridge_message"
    assert "teleport" in reply["error"]["message"]


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        (42, "must be a PluginDescription or a mapping"),
        ({"actions": "nope"}, "description.actions must be a list"),
        ({"actions": ["nope"]}, "every action in a description must be an object"),
        ({"actions": [{"id": "", "title": "T"}]}, "action id must be a nonempty"),
    ],
)
def test_a_description_the_wiring_cannot_read_is_refused(
    description: Any, expected: str
) -> None:
    with pytest.raises(QgisSdkBridgeError, match=expected):
        Dispatcher.from_description(description, {})


@pytest.mark.parametrize(
    ("handlers", "expected"),
    [
        ({}, "is declared but has no handler"),
        ({"edge.echo": 42}, "handler must be callable"),
    ],
)
def test_a_declared_action_needs_a_callable_handler(
    handlers: Mapping[str, Any], expected: str
) -> None:
    described = {"id": "edge", "actions": [{"id": "edge.echo", "title": "Echo"}]}

    with pytest.raises(QgisSdkBridgeError, match=expected):
        Dispatcher.from_description(described, handlers)


def test_a_declared_stream_needs_a_callable_factory() -> None:
    described = {
        "id": "edge",
        "actions": [],
        "streams": [
            {"id": "edge.stream", "title": "A stream", "events": {"data": {}}},
        ],
    }

    with pytest.raises(QgisSdkBridgeError, match="factory must be callable"):
        Dispatcher.from_description(described, {}, streams={"edge.stream": 42})


def test_a_stream_a_host_pushes_into_answers_a_subscription() -> None:
    dispatcher = _dispatcher()
    dispatcher.register_stream(STREAM, lambda payload: None)
    binding = dispatcher.bind(view_id=VIEW, origin=ORIGIN)

    reply = dispatcher.dispatch(binding, _call("subscribe", operation=STREAM.id))

    assert reply["ok"] is True
    subscription_id = reply["value"]["subscription_id"]
    assert dispatcher.emit(subscription_id, {"index": 1}) is True
    assert len(dispatcher.pump(binding)) == 1


def test_a_factory_that_raises_is_answered_rather_than_raised() -> None:
    dispatcher = _dispatcher()

    def broken(payload: Mapping[str, Any]) -> Iterator[dict[str, Any]]:
        raise RuntimeError("a secret path on disk")

    dispatcher.register_stream(STREAM, broken)
    binding = dispatcher.bind(view_id=VIEW, origin=ORIGIN)

    reply = dispatcher.dispatch(binding, _call("subscribe", operation=STREAM.id))

    assert reply["ok"] is False
    assert reply["error"]["code"] == "operation_failed"
    assert "secret" not in reply["error"]["message"]
    assert dispatcher.subscriptions() == ()


def test_a_source_that_raises_when_started_ends_its_own_subscription() -> None:
    dispatcher = _dispatcher()
    dispatcher.register_stream(
        STREAM, lambda payload: _Pushed(QgisSdkLayerNotFoundError("sites"))
    )
    binding = dispatcher.bind(view_id=VIEW, origin=ORIGIN)

    reply = dispatcher.dispatch(binding, _call("subscribe", operation=STREAM.id))
    (frame,) = dispatcher.pump(binding)

    assert reply["ok"] is True
    assert frame["terminal"]["kind"] == "error"


def test_a_stream_that_returns_neither_events_nor_a_push_is_refused() -> None:
    dispatcher = _dispatcher()
    dispatcher.register_stream(STREAM, lambda payload: "not a stream")
    binding = dispatcher.bind(view_id=VIEW, origin=ORIGIN)

    reply = dispatcher.dispatch(binding, _call("subscribe", operation=STREAM.id))

    assert reply["ok"] is False
    assert reply["error"]["code"] == "operation_failed"
    assert dispatcher.subscriptions() == ()


def test_a_release_payload_that_is_not_an_object_is_refused() -> None:
    dispatcher = _dispatcher()
    binding = dispatcher.bind(view_id=VIEW, origin=ORIGIN)

    reply = dispatcher.dispatch(binding, _call("release", payload=["nope"]))

    assert reply["ok"] is False
    assert reply["error"]["message"] == "payload must be an object"


@pytest.mark.parametrize(
    ("kind", "fields"),
    [
        ("subscribe", {"operation": ""}),
        ("unsubscribe", {"subscription_id": ""}),
        ("ack", {"subscription_id": "s1"}),
    ],
)
def test_a_malformed_streaming_call_is_refused_as_a_message(
    kind: str, fields: dict[str, Any]
) -> None:
    dispatcher = _dispatcher()
    binding = dispatcher.bind(view_id=VIEW, origin=ORIGIN)

    reply = dispatcher.dispatch(binding, _call(kind, **fields))

    assert reply["ok"] is False
    assert reply["error"]["code"] == "invalid_bridge_message"
    assert reply["call_id"] == f"{kind}-1"


@pytest.mark.parametrize(
    ("view_id", "origin", "expected"),
    [
        ("", ORIGIN, "view_id must be a nonempty string"),
        ("   ", ORIGIN, "view_id must be a nonempty string"),
        (VIEW, "", "origin must be a nonempty string"),
        (VIEW, 7, "origin must be a nonempty string"),
    ],
)
def test_a_binding_needs_a_nonempty_view_and_origin(
    view_id: Any, origin: Any, expected: str
) -> None:
    with pytest.raises(QgisSdkBridgeError, match=expected):
        _dispatcher().bind(view_id=view_id, origin=origin)


def test_a_handler_may_answer_with_a_list() -> None:
    dispatcher = Dispatcher(authorize=_allow)
    dispatcher.register(ECHO, lambda payload: [1, "two", None])
    binding = dispatcher.bind(view_id=VIEW, origin=ORIGIN)

    reply = dispatcher.dispatch(binding, _call("invoke", operation=ECHO.id))

    assert reply["ok"] is True
    assert reply["value"] == [1, "two", None]


def test_a_declared_handler_may_answer_with_a_list() -> None:
    described = {"id": "edge", "actions": [{"id": "edge.list", "title": "List"}]}
    dispatcher = Dispatcher.from_description(
        described, {"edge.list": lambda: [1, "two", None]}, authorize=_allow
    )
    binding = dispatcher.bind(view_id=VIEW, origin=ORIGIN)

    reply = dispatcher.dispatch(binding, _call("invoke", operation="edge.list"))

    assert reply["ok"] is True
    assert reply["value"] == [1, "two", None]


def test_a_declared_stream_may_push_into_the_host() -> None:
    described = {
        "id": "edge",
        "actions": [],
        "streams": [
            {
                "id": "edge.stream",
                "title": "A stream",
                "events": {"data": {"type": "object"}},
            },
        ],
    }
    dispatcher = Dispatcher.from_description(
        described, {}, streams={"edge.stream": lambda: None}, authorize=_allow
    )
    binding = dispatcher.bind(view_id=VIEW, origin=ORIGIN)

    reply = dispatcher.dispatch(binding, _call("subscribe", operation="edge.stream"))

    assert reply["ok"] is True
    assert dispatcher.emit(reply["value"]["subscription_id"], {"index": 0}) is True


def test_a_request_property_that_is_not_a_schema_names_no_file_ref() -> None:
    """A malformed property is skipped by the ref scan, not crashed on.

    Only a declared ``FileInput()`` turns a wire object back into a ref; anything
    the scan cannot read is left to the validator, which is the thing that gets
    to refuse it.
    """
    assert ref_inputs({"properties": {"value": "not a schema"}}) == frozenset()


def test_a_value_that_cannot_be_measured_is_zero_bytes() -> None:
    assert wire_size({1, 2, 3}) == 0

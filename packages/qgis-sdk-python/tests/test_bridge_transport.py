"""The adapter's pure half: text in, text out, nothing decided here.

A QWebChannel carries JSON strings, so the transport is tested with JSON
strings. That keeps correlation, refusal and frame delivery testable without a
browser, and leaves the Qt glue with nothing to get wrong except wiring.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from qgis_sdk.bridge import BRIDGE_PROTOCOL_VERSION, BridgeOperation, Dispatcher
from qgis_sdk.bridge.resources import HandleKind
from qgis_sdk.bridge.streams import MAX_QUEUED_EVENTS
from qgis_sdk.bridge.transport import ChannelTransport, envelope_protocol

ORIGIN = "qgis://desktop"
ECHO = BridgeOperation(id="demo.echo", title="Echo the payload")
TICKS = BridgeOperation(id="demo.ticks", title="Emit a tick")
PUSHED = BridgeOperation(id="demo.push", title="A pushed stream")


def _transport(*, allow: bool = True) -> tuple[ChannelTransport, list[dict]]:
    dispatcher = Dispatcher(
        description={"schema_version": 1, "id": "demo.plugin", "title": "Demo"},
        authorize=(lambda binding, operation: True) if allow else None,
    )
    dispatcher.register(ECHO, lambda payload: {"echo": payload})
    dispatcher.register_stream(TICKS, lambda payload: _ticks())
    dispatcher.register_stream(PUSHED, lambda payload: None)
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    sent: list[str] = []
    transport = ChannelTransport(
        dispatcher=dispatcher,
        binding=binding,
        send=sent.append,
    )
    return transport, sent


def _ticks() -> Iterator[dict[str, Any]]:
    for index in range(3):
        yield {"index": index}


def _frames(sent: list[Any]) -> list[dict]:
    return [json.loads(item) for item in sent]


def test_a_call_crosses_as_text_and_comes_back_as_text() -> None:
    transport, sent = _transport()

    assert transport.receive(
        json.dumps(
            {
                "protocol": envelope_protocol(),
                "call_id": "c1",
                "operation": ECHO.id,
                "payload": {"name": "A"},
            }
        )
    )

    (reply,) = _frames(sent)
    assert reply == {
        "call_id": "c1",
        "ok": True,
        "protocol": BRIDGE_PROTOCOL_VERSION,
        "value": {"echo": {"name": "A"}},
    }


def test_text_that_is_not_a_message_is_counted_and_dropped() -> None:
    transport, sent = _transport()

    assert transport.receive("{not json") is False
    assert transport.receive(json.dumps([1, 2, 3])) is False
    assert transport.receive(b"{}") is False  # type: ignore[arg-type]

    assert transport.refused == 3
    assert sent == []


def test_a_refusal_survives_the_round_trip() -> None:
    transport, sent = _transport(allow=False)

    transport.receive(
        json.dumps(
            {
                "protocol": BRIDGE_PROTOCOL_VERSION,
                "call_id": "c1",
                "operation": ECHO.id,
                "payload": {},
            }
        )
    )

    (reply,) = _frames(sent)
    assert reply["ok"] is False
    assert reply["error"]["code"] == "not_authorized"


def test_a_subscription_is_acknowledged_and_its_frames_flushed_in_order() -> None:
    transport, sent = _transport()

    transport.receive(
        json.dumps(
            {
                "protocol": BRIDGE_PROTOCOL_VERSION,
                "kind": "subscribe",
                "call_id": "s1",
                "operation": TICKS.id,
                "payload": {},
            }
        )
    )
    ack = _frames(sent)[0]
    subscription_id = ack["value"]["subscription_id"]
    sent.clear()

    assert transport.flush(limit=2) == 2
    first = _frames(sent)
    sent.clear()
    transport.flush()

    rest = _frames(sent)
    assert [frame["seq"] for frame in first + rest] == [0, 1, 2, 3]
    assert all(frame["subscription_id"] == subscription_id for frame in first)
    assert (first + rest)[-1]["terminal"] == {"kind": "complete"}


def test_flush_reports_nothing_to_do_when_no_stream_is_open() -> None:
    transport, sent = _transport()

    assert transport.flush() == 0
    assert sent == []


def test_a_pushed_stream_reaches_the_channel_through_flush() -> None:
    transport, sent = _transport()
    transport.receive(
        json.dumps(
            {
                "protocol": BRIDGE_PROTOCOL_VERSION,
                "kind": "subscribe",
                "call_id": "s1",
                "operation": PUSHED.id,
                "payload": {},
            }
        )
    )
    subscription_id = _frames(sent)[0]["value"]["subscription_id"]
    sent.clear()
    dispatcher = transport.dispatcher
    for index in range(MAX_QUEUED_EVENTS + 1):
        dispatcher.emit(subscription_id, {"index": index})

    # A protocol-2 reader acks what it delivered; without an ack the host stops
    # after MAX_IN_FLIGHT_FRAMES by design, so this loop is the client's side of
    # the contract, not a workaround.
    frames = []
    for _ in range(MAX_QUEUED_EVENTS):
        sent.clear()
        transport.flush(limit=MAX_QUEUED_EVENTS + 1)
        batch = _frames(sent)
        frames.extend(batch)
        if not batch:
            break
        for frame in batch:
            if "terminal" not in frame:
                transport.acknowledge(frame["subscription_id"], frame["seq"])
        if any("terminal" in frame for frame in batch):
            break

    assert frames[-1]["terminal"]["kind"] == "gap"
    assert frames[-1]["terminal"]["dropped"] == 1


def test_release_crosses_the_channel_like_any_other_call() -> None:
    transport, sent = _transport()
    transport.dispatcher.track(transport.binding, HandleKind.BORROWED, "sites")

    transport.receive(
        json.dumps(
            {
                "protocol": BRIDGE_PROTOCOL_VERSION,
                "kind": "release",
                "call_id": "r1",
                "payload": {"handles": [{"kind": "borrowed", "id": "sites"}]},
            }
        )
    )

    (reply,) = _frames(sent)
    assert reply["value"]["released"] == [
        {"kind": "borrowed", "id": "sites", "outcome": "borrowed_retained"}
    ]


def test_disposal_stops_the_frames_for_that_view() -> None:
    transport, sent = _transport()
    transport.receive(
        json.dumps(
            {
                "protocol": BRIDGE_PROTOCOL_VERSION,
                "kind": "subscribe",
                "call_id": "s1",
                "operation": TICKS.id,
                "payload": {},
            }
        )
    )
    sent.clear()

    assert transport.dispose() == 1

    assert transport.flush() == 0
    assert sent == []


class _Later:
    """A push source whose reply arrives on a later turn, as a network reply does."""

    def __init__(self) -> None:
        self.sink = None

    def start(self, sink) -> None:
        self.sink = sink


def test_a_push_source_reply_reaches_the_channel_without_a_flush_call() -> None:
    """The transport is the view's waker: a pushed event flushes itself."""
    transport, sent = _transport()
    later = _Later()
    transport.dispatcher.register_stream(
        BridgeOperation(id="demo.later", title="Reply later"), lambda payload: later
    )
    transport.receive(
        json.dumps(
            {
                "protocol": envelope_protocol(),
                "kind": "subscribe",
                "call_id": "sub-1",
                "operation": "demo.later",
                "payload": {},
            }
        )
    )
    assert len(sent) == 1

    later.sink.emit({"status": 200})
    later.sink.complete()

    frames = _frames(sent[1:])
    assert [frame.get("event", frame.get("terminal")) for frame in frames] == [
        {"kind": "data", "payload": {"status": 200}},
        {"kind": "complete"},
    ]


def test_a_disposed_transport_no_longer_flushes_late_replies() -> None:
    transport, sent = _transport()
    later = _Later()
    transport.dispatcher.register_stream(
        BridgeOperation(id="demo.later", title="Reply later"), lambda payload: later
    )
    transport.receive(
        json.dumps(
            {
                "protocol": envelope_protocol(),
                "kind": "subscribe",
                "call_id": "sub-1",
                "operation": "demo.later",
                "payload": {},
            }
        )
    )
    transport.dispose()
    before = len(sent)

    assert later.sink.emit({"status": 200}) is False
    assert len(sent) == before


class _Immediate:
    """A push source that answers inside ``start`` - a cached reply, say."""

    def start(self, sink) -> None:
        sink.emit({"cached": True})
        sink.complete()


def test_a_frame_pushed_during_the_call_still_follows_the_acknowledgement() -> None:
    """The view must learn the subscription id before it sees the id's frames."""
    transport, sent = _transport()
    transport.dispatcher.register_stream(
        BridgeOperation(id="demo.now", title="Reply now"), lambda payload: _Immediate()
    )

    transport.receive(
        json.dumps(
            {
                "protocol": envelope_protocol(),
                "kind": "subscribe",
                "call_id": "sub-1",
                "operation": "demo.now",
                "payload": {},
            }
        )
    )

    messages = _frames(sent)
    assert messages[0]["call_id"] == "sub-1"
    assert messages[0]["ok"] is True
    assert [frame.get("event", frame.get("terminal")) for frame in messages[1:]] == [
        {"kind": "data", "payload": {"cached": True}},
        {"kind": "complete"},
    ]

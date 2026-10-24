"""Subscriptions, streams and disposal over the narrow dispatcher.

The tests here are written against the rules decision-23 asks for: ordering is
scoped to one subscription, buffering is bounded and says so when it overflows,
progress may be coalesced and data may not, and every subscription ends exactly
once. None of it needs Qt, a browser or a live QGIS - which is the point of
keeping the dispatcher dictionary-shaped.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from qgis_sdk.bridge import BridgeOperation, Dispatcher, ViewBinding
from qgis_sdk.bridge.streams import (
    MAX_FRAMES_PER_PUMP,
    MAX_QUEUED_EVENTS,
    MAX_SUBSCRIPTIONS_PER_VIEW,
    StreamEventType,
)
from qgis_sdk.models.errors import QgisSdkJobCancelledError

TICKS = BridgeOperation(id="demo.ticks", title="Emit a tick per pump")
BROKEN = BridgeOperation(id="demo.broken", title="Fail halfway through")
PLAIN = BridgeOperation(id="demo.plain", title="An ordinary call")
PUSH = BridgeOperation(id="demo.push", title="A stream the host pushes into")
ORIGIN = "qgis://desktop"


def _host(*, allow: bool = True) -> Dispatcher:
    dispatcher = Dispatcher(
        description={"schema_version": 1, "id": "demo.plugin", "title": "Demo"},
        authorize=(lambda binding, operation: True) if allow else None,
    )
    dispatcher.register(PLAIN, lambda payload: {"echo": payload})
    dispatcher.register_stream(TICKS, lambda payload: _ticks(payload.get("count", 3)))
    dispatcher.register_stream(BROKEN, _broken)
    dispatcher.register_stream(PUSH, lambda payload: None)
    return dispatcher


def _ticks(count: int) -> Iterator[dict[str, Any]]:
    for index in range(count):
        yield {"index": index}


def _broken(payload: Any) -> Iterator[dict[str, Any]]:
    stage = payload.get("stage", "sdk")
    yield {"started": True}
    if stage == "sdk":
        raise QgisSdkJobCancelledError("the user cancelled the job")
    if stage == "unexpected":
        raise RuntimeError("object at 0xdeadbeef")
    if stage == "garbage":
        yield "not a mapping"  # type: ignore[misc]
    raise AssertionError(stage)


def _subscribe(
    dispatcher: Dispatcher, binding: ViewBinding, *, operation: str = TICKS.id, **payload
) -> dict[str, Any]:
    return dispatcher.dispatch(
        binding,
        {
            "protocol": 1,
            "kind": "subscribe",
            "call_id": "sub-1",
            "operation": operation,
            "payload": payload,
        },
    )


def _unsubscribe(
    dispatcher: Dispatcher, binding: ViewBinding, subscription_id: str
) -> dict[str, Any]:
    return dispatcher.dispatch(
        binding,
        {
            "protocol": 1,
            "kind": "unsubscribe",
            "call_id": "unsub-1",
            "subscription_id": subscription_id,
        },
    )


def test_a_subscription_is_a_call_and_a_forbidden_view_cannot_open_one() -> None:
    dispatcher = _host(allow=False)
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)

    reply = _subscribe(dispatcher, binding)

    assert reply["ok"] is False
    assert reply["error"]["code"] == "not_authorized"
    assert dispatcher.subscriptions() == ()


def test_a_plain_operation_is_not_a_stream() -> None:
    dispatcher = _host()
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)

    reply = _subscribe(dispatcher, binding, operation=PLAIN.id)

    assert reply["ok"] is False
    assert reply["error"]["code"] == "unknown_operation"


def test_an_unknown_stream_is_refused_with_the_call_id_it_names() -> None:
    dispatcher = _host()
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)

    reply = _subscribe(dispatcher, binding, operation="demo.missing")

    assert reply["ok"] is False
    assert reply["call_id"] == "sub-1"
    assert reply["error"]["code"] == "unknown_operation"


def test_a_stale_generation_cannot_open_or_close_a_subscription() -> None:
    dispatcher = _host()
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    subscription_id = _subscribe(dispatcher, binding)["value"]["subscription_id"]
    dispatcher.advance_generation()

    assert _subscribe(dispatcher, binding)["error"]["code"] == "stale_generation"
    assert (
        _unsubscribe(dispatcher, binding, subscription_id)["error"]["code"]
        == "stale_generation"
    )


def test_frames_are_ordered_per_subscription_and_carry_the_protocol() -> None:
    dispatcher = _host()
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    subscription_id = _subscribe(dispatcher, binding, count=3)["value"][
        "subscription_id"
    ]

    frames = dispatcher.pump(binding)

    assert [frame["seq"] for frame in frames] == [0, 1, 2, 3]
    assert all(frame["protocol"] == 1 for frame in frames)
    assert all(frame["subscription_id"] == subscription_id for frame in frames)
    assert [frame["event"]["payload"] for frame in frames[:-1]] == [
        {"index": 0},
        {"index": 1},
        {"index": 2},
    ]
    assert frames[-1]["terminal"] == {"kind": "complete"}


def test_a_terminal_frame_is_the_last_frame_a_subscription_ever_sends() -> None:
    dispatcher = _host()
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    subscription_id = _subscribe(dispatcher, binding, count=1)["value"][
        "subscription_id"
    ]

    frames = dispatcher.pump(binding)

    assert frames[-1]["terminal"] == {"kind": "complete"}
    assert dispatcher.emit(subscription_id, {"late": True}) is False
    assert dispatcher.subscriptions() == ()
    assert dispatcher.pump(binding) == []


def test_pulling_never_grows_the_queue_past_its_capacity() -> None:
    dispatcher = _host()
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    _subscribe(dispatcher, binding, count=200)
    (subscription,) = dispatcher.subscriptions()

    frames = dispatcher.pump(binding, limit=4)

    assert len(frames) == 4
    assert subscription.queued <= MAX_QUEUED_EVENTS
    assert [frame["seq"] for frame in frames] == [0, 1, 2, 3]


def test_a_pushed_stream_that_overruns_its_queue_ends_with_a_gap() -> None:
    dispatcher = _host()
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    subscription_id = _subscribe(dispatcher, binding, operation=PUSH.id)["value"][
        "subscription_id"
    ]

    for index in range(MAX_QUEUED_EVENTS):
        assert dispatcher.emit(subscription_id, {"index": index}) is True

    assert dispatcher.emit(subscription_id, {"index": "overflow"}) is False
    frames = dispatcher.pump(binding, limit=MAX_QUEUED_EVENTS + 1)

    assert frames[-1]["terminal"] == {
        "kind": "gap",
        "dropped": 1,
        "message": (
            "The view did not consume this subscription fast enough and "
            "events were dropped"
        ),
    }
    assert len(frames) == MAX_QUEUED_EVENTS + 1


def test_progress_is_coalesced_and_data_is_not() -> None:
    dispatcher = _host()
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    subscription_id = _subscribe(dispatcher, binding, operation=PUSH.id)["value"][
        "subscription_id"
    ]

    dispatcher.emit(subscription_id, {"percent": 10}, kind=StreamEventType.PROGRESS)
    dispatcher.emit(subscription_id, {"percent": 20}, kind=StreamEventType.PROGRESS)
    dispatcher.emit(subscription_id, {"percent": 30}, kind=StreamEventType.PROGRESS)
    dispatcher.emit(subscription_id, {"row": 1})

    frames = dispatcher.pump(binding)

    assert len(frames) == 2
    assert frames[0]["event"] == {"kind": "progress", "payload": {"percent": 30}}
    assert frames[1]["event"] == {"kind": "data", "payload": {"row": 1}}
    assert [frame["seq"] for frame in frames] == [0, 1]


def test_an_sdk_error_ends_the_stream_with_its_own_message() -> None:
    dispatcher = _host()
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    _subscribe(dispatcher, binding, operation=BROKEN.id, stage="sdk")

    frames = dispatcher.pump(binding)

    assert frames[0]["event"] == {"kind": "data", "payload": {"started": True}}
    terminal = frames[-1]["terminal"]
    assert terminal["kind"] == "cancelled"
    assert "user cancelled" in terminal["message"]


def test_an_unexpected_error_is_replaced_before_it_reaches_the_view() -> None:
    dispatcher = _host()
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    _subscribe(dispatcher, binding, operation=BROKEN.id, stage="unexpected")

    terminal = dispatcher.pump(binding)[-1]["terminal"]

    assert terminal == {
        "kind": "error",
        "message": "The stream failed; the host recorded the details",
    }
    assert "0xdeadbeef" not in str(terminal)


def test_a_source_that_yields_something_that_is_not_a_mapping_fails_loudly() -> None:
    dispatcher = _host()
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    _subscribe(dispatcher, binding, operation=BROKEN.id, stage="garbage")

    frames = dispatcher.pump(binding)

    assert frames[-1]["terminal"]["kind"] == "error"
    assert "str" in frames[-1]["terminal"]["message"]


def test_disposal_is_idempotent_and_stops_the_frames() -> None:
    dispatcher = _host()
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    subscription_id = _subscribe(dispatcher, binding, count=50)["value"][
        "subscription_id"
    ]

    first = _unsubscribe(dispatcher, binding, subscription_id)
    second = _unsubscribe(dispatcher, binding, subscription_id)

    assert first["value"] == {"subscription_id": subscription_id, "disposed": True}
    assert second["value"] == {"subscription_id": subscription_id, "disposed": False}
    assert dispatcher.pump(binding) == []
    assert dispatcher.subscriptions() == ()


def test_disposal_closes_the_source_so_its_cleanup_runs() -> None:
    closed: list[str] = []

    def source(payload: Any) -> Iterator[dict[str, Any]]:
        try:
            yield {"first": True}
            yield {"second": True}
        finally:
            closed.append("closed")

    dispatcher = Dispatcher(authorize=lambda binding, operation: True)
    dispatcher.register_stream(TICKS, source)
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    subscription_id = _subscribe(dispatcher, binding)["value"]["subscription_id"]
    dispatcher.pump(binding)  # start the generator, so there is cleanup to run

    _unsubscribe(dispatcher, binding, subscription_id)

    assert closed == ["closed"]


def test_one_view_cannot_dispose_another_views_subscription() -> None:
    dispatcher = _host()
    owner = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    stranger = dispatcher.bind(view_id="view-2", origin=ORIGIN)
    subscription_id = _subscribe(dispatcher, owner, count=5)["value"]["subscription_id"]

    reply = _unsubscribe(dispatcher, stranger, subscription_id)

    assert reply["error"]["code"] == "not_authorized"
    assert [subscription.id for subscription in dispatcher.subscriptions()] == [
        subscription_id
    ]


def test_frames_are_delivered_only_to_the_view_that_opened_them() -> None:
    dispatcher = _host()
    owner = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    other = dispatcher.bind(view_id="view-2", origin=ORIGIN)
    _subscribe(dispatcher, owner, count=2)

    assert dispatcher.pump(other) == []
    assert [frame["seq"] for frame in dispatcher.pump(owner)] == [0, 1, 2]


def test_a_new_generation_closes_every_subscription_source() -> None:
    closed: list[str] = []

    def source(payload: Any) -> Iterator[dict[str, Any]]:
        try:
            yield {"first": True}
        finally:
            closed.append("closed")

    dispatcher = Dispatcher(authorize=lambda binding, operation: True)
    dispatcher.register_stream(TICKS, source)
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    _subscribe(dispatcher, binding)
    dispatcher.pump(binding)

    dispatcher.advance_generation()

    assert closed == ["closed"]
    assert dispatcher.subscriptions() == ()
    assert dispatcher.pump(binding) == []


def test_a_view_holds_a_bounded_number_of_subscriptions() -> None:
    dispatcher = _host()
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    for _ in range(MAX_SUBSCRIPTIONS_PER_VIEW):
        assert _subscribe(dispatcher, binding, count=1)["ok"] is True

    reply = _subscribe(dispatcher, binding, count=1)

    assert reply["error"]["code"] == "limit_exceeded"


def test_a_payload_that_cannot_cross_the_wire_opens_no_subscription() -> None:
    dispatcher = _host()
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    deep: dict[str, Any] = {"value": 1}
    for _ in range(40):
        deep = {"nested": deep}

    reply = _subscribe(dispatcher, binding, **deep)

    assert reply["error"]["code"] == "invalid_payload"
    assert dispatcher.subscriptions() == ()


def test_pump_respects_its_budget_across_many_subscriptions() -> None:
    dispatcher = _host()
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    _subscribe(dispatcher, binding, count=40)
    _subscribe(dispatcher, binding, count=40)

    first = dispatcher.pump(binding, limit=MAX_FRAMES_PER_PUMP)

    assert len(first) == 2 * MAX_FRAMES_PER_PUMP
    assert len(dispatcher.pump(binding, limit=MAX_FRAMES_PER_PUMP)) > 0

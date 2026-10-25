"""Interleavings of subscribe, emit, pump, dispose and generation change (TASK-7 AC 6).

``test_bridge_streams.py`` pins each stream rule in isolation. This state
machine lets Hypothesis interleave them across two views and checks what has to
hold in *every* order, with the scheduling entirely in the test's hands - no
event loop, no thread, no timer:

* frames of one subscription carry contiguous sequence numbers from zero, so a
  client that sees a hole knows the host did not produce one;
* data events arrive in the order they were emitted, none skipped, until the
  subscription ends;
* a terminal frame is the last frame a subscription ever sends, and it is sent
  at most once;
* a subscription a view disposed delivers nothing afterwards - not even a
  terminal that was already queued - and refuses further events;
* a view only ever receives frames of subscriptions it opened in the generation
  it opened them, and a stale binding receives nothing at all;
* another view cannot dispose a subscription it does not hold;
* once a subscription ended for any reason, ``emit`` reports it instead of
  absorbing the event;
* a push source whose subscription ended - completed, disposed, or lost with
  its generation - is closed exactly once, so a Qt task behind it is cancelled
  and never cancelled twice.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from hypothesis import settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, precondition, rule
from qgis_sdk.bridge import BridgeOperation, Dispatcher, ViewBinding
from qgis_sdk.bridge.streams import (
    MAX_SUBSCRIPTIONS_PER_VIEW,
    StreamEventType,
    StreamSink,
)

PUSH = BridgeOperation(id="prop.push", title="A stream the host pushes into")
TICKS = BridgeOperation(id="prop.ticks", title="A pulled stream of ticks")
VIEWS = ("view-1", "view-2")
ORIGIN = "qgis://desktop"


def _ticks(count: int) -> Iterator[dict[str, Any]]:
    for index in range(count):
        yield {"index": index}


class _Pushed:
    """A push source that hands its sink to the test and counts its closes."""

    def __init__(self, sinks: dict[str, StreamSink], closed: dict[str, int]) -> None:
        self.sinks = sinks
        self.closed = closed
        self.subscription_id = ""

    def start(self, sink: StreamSink) -> None:
        self.subscription_id = sink.subscription.id
        self.sinks[self.subscription_id] = sink

    def close(self) -> None:
        self.closed[self.subscription_id] = self.closed.get(self.subscription_id, 0) + 1


@dataclass
class Observed:
    """What the test knows about one subscription, from the view's side."""

    view: str
    generation: int
    pulled: bool
    emitted: int = 0
    seen_seq: int = -1
    seen_data: list[int] = field(default_factory=list)
    terminal: str | None = None
    disposed: bool = False
    completing: bool = False
    """The host accepted a ``complete``; the terminal may still be in the queue."""

    @property
    def ended(self) -> bool:
        return self.terminal is not None or self.disposed


class StreamDelivery(RuleBasedStateMachine):
    def __init__(self) -> None:
        super().__init__()
        self.dispatcher = Dispatcher(
            description={"schema_version": 1, "id": "prop.plugin", "title": "Prop"},
            authorize=lambda binding, operation: True,
        )
        self.sinks: dict[str, StreamSink] = {}
        self.closed: dict[str, int] = {}
        self.dispatcher.register_stream(
            PUSH, lambda payload: _Pushed(self.sinks, self.closed)
        )
        self.dispatcher.register_stream(
            TICKS, lambda payload: _ticks(payload.get("count", 3))
        )
        self.bindings: dict[str, ViewBinding] = {
            view: self.dispatcher.bind(view_id=view, origin=ORIGIN) for view in VIEWS
        }
        self.stale: list[ViewBinding] = []
        self.subscriptions: dict[str, Observed] = {}
        self.calls = 0

    # -- helpers --------------------------------------------------------------

    def _call(self, binding: ViewBinding, message: dict[str, Any]) -> dict[str, Any]:
        self.calls += 1
        return self.dispatcher.dispatch(
            binding, {"protocol": 1, "call_id": f"c{self.calls}", **message}
        )

    def _live(self, view: str) -> list[str]:
        return [
            key
            for key, observed in self.subscriptions.items()
            if observed.view == view
            and observed.generation == self.bindings[view].generation
            and not observed.ended
        ]

    def _ids(self, *, ended: bool | None = None) -> list[str]:
        return [
            key
            for key, observed in self.subscriptions.items()
            if ended is None or observed.ended is ended
        ]

    def _check(self, view: str, frames: list[dict[str, Any]]) -> None:
        """Hold a pumped batch to the delivery guarantees."""
        binding = self.bindings[view]
        for frame in frames:
            observed = self.subscriptions[frame["subscription_id"]]
            assert observed.view == view, "a frame reached a view that did not open it"
            assert observed.generation == binding.generation, (
                "a frame from a dead generation was delivered"
            )
            assert not observed.disposed, "a disposed subscription still delivered"
            assert observed.terminal is None, "a frame followed the terminal"
            assert frame["seq"] == observed.seen_seq + 1, (
                f"sequence hole: saw {observed.seen_seq}, got {frame['seq']}"
            )
            observed.seen_seq = frame["seq"]
            if "terminal" in frame:
                observed.terminal = frame["terminal"]["kind"]
                continue
            event = frame["event"]
            if event["kind"] == StreamEventType.DATA.value and not observed.pulled:
                observed.seen_data.append(event["payload"]["index"])

    # -- rules ----------------------------------------------------------------

    @rule(view=st.sampled_from(VIEWS), pulled=st.booleans())
    def subscribe(self, view: str, pulled: bool) -> None:
        binding = self.bindings[view]
        reply = self._call(
            binding,
            {
                "kind": "subscribe",
                "operation": TICKS.id if pulled else PUSH.id,
                "payload": {"count": 3} if pulled else {},
            },
        )
        if not reply["ok"]:
            assert reply["error"]["code"] == "limit_exceeded"
            held = [
                s
                for s in self.dispatcher.subscriptions()
                if s.view_id == view and s.generation == binding.generation
            ]
            assert len(held) >= MAX_SUBSCRIPTIONS_PER_VIEW
            return
        key = reply["value"]["subscription_id"]
        assert key not in self.subscriptions, "a subscription id was reused"
        self.subscriptions[key] = Observed(
            view=view, generation=binding.generation, pulled=pulled
        )

    @precondition(lambda self: any(not o.pulled for o in self.subscriptions.values()))
    @rule(
        data=st.data(),
        kind=st.sampled_from([StreamEventType.DATA, StreamEventType.PROGRESS]),
    )
    def emit(self, data: st.DataObject, kind: StreamEventType) -> None:
        key = data.draw(
            st.sampled_from([k for k, o in self.subscriptions.items() if not o.pulled])
        )
        observed = self.subscriptions[key]
        payload = (
            {"index": observed.emitted}
            if kind is StreamEventType.DATA
            else {"percent": observed.emitted}
        )
        accepted = self.dispatcher.emit(key, payload, kind=kind)
        if observed.ended or observed.completing:
            assert accepted is False, "an ended subscription absorbed an event"
            return
        if accepted and kind is StreamEventType.DATA:
            observed.emitted += 1

    @precondition(lambda self: any(not o.pulled for o in self.subscriptions.values()))
    @rule(data=st.data())
    def complete(self, data: st.DataObject) -> None:
        key = data.draw(
            st.sampled_from([k for k, o in self.subscriptions.items() if not o.pulled])
        )
        observed = self.subscriptions[key]
        ended = self.sinks[key].complete()
        if observed.ended or observed.completing:
            assert ended is False, "an ended subscription was completed again"
        elif ended:
            observed.completing = True

    @rule(view=st.sampled_from(VIEWS), limit=st.integers(min_value=1, max_value=8))
    def pump(self, view: str, limit: int) -> None:
        frames = self.dispatcher.pump(self.bindings[view], limit=limit)
        self._check(view, frames)

    @precondition(lambda self: self.stale)
    @rule(data=st.data())
    def pump_stale(self, data: st.DataObject) -> None:
        binding = data.draw(st.sampled_from(self.stale))
        assert self.dispatcher.pump(binding) == [], "a stale binding was served"

    @precondition(lambda self: self.subscriptions)
    @rule(data=st.data())
    def unsubscribe(self, data: st.DataObject) -> None:
        key = data.draw(st.sampled_from(sorted(self.subscriptions)))
        observed = self.subscriptions[key]
        reply = self._call(
            self.bindings[observed.view],
            {"kind": "unsubscribe", "subscription_id": key},
        )
        if observed.generation != self.bindings[observed.view].generation:
            # The subscription died with its generation; the view's new binding
            # simply does not hold it any more.
            assert reply["ok"] and reply["value"]["disposed"] is False
            return
        assert reply["ok"], reply
        observed.disposed = True

    @precondition(lambda self: self.subscriptions)
    @rule(data=st.data())
    def unsubscribe_from_the_other_view(self, data: st.DataObject) -> None:
        key = data.draw(st.sampled_from(sorted(self.subscriptions)))
        observed = self.subscriptions[key]
        other = next(view for view in VIEWS if view != observed.view)
        before = {s.id for s in self.dispatcher.subscriptions()}
        reply = self._call(
            self.bindings[other], {"kind": "unsubscribe", "subscription_id": key}
        )
        if key in before:
            assert not reply["ok"] and reply["error"]["code"] == "not_authorized"
            assert key in {s.id for s in self.dispatcher.subscriptions()}
        else:
            assert reply["ok"] and reply["value"]["disposed"] is False

    @rule(view=st.sampled_from(VIEWS))
    def dispose_view(self, view: str) -> None:
        self.dispatcher.dispose(self.bindings[view])
        for observed in self.subscriptions.values():
            if observed.view == view:
                observed.disposed = True

    @rule()
    def advance_generation(self) -> None:
        self.dispatcher.advance_generation()
        self.stale.extend(self.bindings.values())
        for observed in self.subscriptions.values():
            observed.disposed = True
        self.bindings = {
            view: self.dispatcher.bind(view_id=view, origin=ORIGIN) for view in VIEWS
        }

    # -- invariants -----------------------------------------------------------

    @invariant()
    def data_is_delivered_in_order_without_omission(self) -> None:
        for observed in self.subscriptions.values():
            seen = observed.seen_data
            assert seen == list(range(len(seen))), f"out of order or skipped: {seen}"

    @invariant()
    def the_host_forgets_what_ended(self) -> None:
        held = {s.id for s in self.dispatcher.subscriptions()}
        for key, observed in self.subscriptions.items():
            if observed.disposed:
                assert key not in held, "a disposed subscription is still held"

    @invariant()
    def a_terminal_subscription_refuses_events(self) -> None:
        for key, observed in self.subscriptions.items():
            if observed.ended and not observed.pulled:
                assert self.dispatcher.emit(key, {"index": -1}) is False
                assert self.sinks[key].emit({"index": -1}) is False

    @invariant()
    def an_ended_push_source_was_closed_exactly_once(self) -> None:
        for key, observed in self.subscriptions.items():
            if observed.pulled:
                continue
            closes = self.closed.get(key, 0)
            assert closes <= 1, f"{key} was closed {closes} times"
            if observed.ended:
                assert closes == 1, f"{key} ended but its source was not closed"


TestStreamDelivery = StreamDelivery.TestCase
TestStreamDelivery.settings = settings(
    max_examples=120, stateful_step_count=40, deadline=None
)

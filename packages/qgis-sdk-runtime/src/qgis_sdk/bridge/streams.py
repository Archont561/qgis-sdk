"""Subscriptions and streams that ride on the same narrow dispatcher.

A subscription is an operation that answers with more than one message. It is
not a second transport and not a second authorization path: opening one is a
call like any other (protocol, generation, authorization, allowlist, payload),
and the frames it produces afterwards belong to the view that opened it
(decision-23).

The rules below are the ones decision-23 asks to be settled by tests rather than
by prose, and they are deliberately dull:

*Ordering is scoped to a subscription.* Every frame carries a ``seq`` that starts
at zero and increases by exactly one. A client that sees a different number has
missed or reordered a frame and must treat the subscription as broken rather than
assemble a plausible sequence out of what arrived.

*Ordered delivery is not backpressure.* The queue is bounded per subscription
(:data:`MAX_QUEUED_EVENTS`). A pulled stream never overruns it, because a pull
model simply stops pulling. A pushed stream - progress from a Qt task, say - can
overrun it, and then the subscription is terminated with ``gap`` and a count of
what was dropped. Growth without bound is the one outcome that is not allowed.

*Acknowledgements bound what is in flight (protocol 2, decision-59).* Every event
frame a client delivered is acknowledged with ``kind: "ack"``; the host hands
out at most :data:`MAX_IN_FLIGHT_FRAMES` unacknowledged frames and then stops
advancing the source, so a slow consumer slows the producer instead of filling a
queue. A terminal frame is never held back: the stream is over, and making the
end wait for an acknowledgement would let a stalled client keep a subscription -
and whatever it wrote into - alive. An acknowledgement for a frame the host
never handed out is refused rather than clamped, because a client that acks
numbers it did not receive has lost track of the stream.

*Progress may be coalesced; data may not.* Only a ``progress`` event may replace
the previous queued ``progress`` frame, and only while that frame is still
waiting for the transport. A data event is never merged, replaced or dropped
silently.

*Every subscription ends exactly once.* Completion, an error, cancellation, a
gap and disposal all produce one terminal frame or one acknowledgement, and a
closed subscription accepts no further events.

*A declared stream emits what it declared.* When the operation carries an
``events`` map (decision-28), an event of a kind it did not declare, or whose
payload fails that kind's schema, ends the subscription with ``error`` - the
stream analogue of ``invalid_result``. The check is lenient about additive
fields, exactly as a result's is.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from qgis_sdk.bridge.protocol import (
    BRIDGE_PROTOCOL_VERSION,
    peek_call_id,
    to_wire,
)
from qgis_sdk.bridge.schema import validate
from qgis_sdk.models.errors import (
    QgisSdkBridgeError,
    QgisSdkBridgeProtocolError,
    QgisSdkError,
    QgisSdkJobCancelledError,
)

MAX_QUEUED_EVENTS = 64
MAX_FRAMES_PER_PUMP = 16
MAX_SUBSCRIPTIONS_PER_VIEW = 8

#: Unacknowledged event frames one subscription may have in flight. Eight is a
#: comfortable burst for a channel that acks on delivery, and small enough that
#: a consumer which stopped acking stalls the producer long before the queue
#: (four times larger) would have to terminate the stream with ``gap``.
MAX_IN_FLIGHT_FRAMES = 8


class StreamTerminal(str, Enum):
    """Why a subscription stopped, as the client sees it."""

    COMPLETE = "complete"
    ERROR = "error"
    CANCELLED = "cancelled"
    GAP = "gap"
    DISPOSED = "disposed"


class StreamState(str, Enum):
    """Where a subscription is in its life, for the host's own bookkeeping."""

    OPEN = "open"
    TERMINATED = "terminated"
    DRAINED = "drained"


class StreamEventType(str, Enum):
    """The kinds of event a stream may carry: ``STREAM_EVENT_KINDS`` as an enum."""

    DATA = "data"
    PROGRESS = "progress"
    STATE = "state"


_EVENT_KINDS = frozenset(kind.value for kind in StreamEventType)


def event_frame(
    subscription_id: str, seq: int, *, kind: StreamEventType, payload: Any
) -> dict[str, Any]:
    """Build one event frame, with the payload already made JSON-safe."""
    return {
        "protocol": BRIDGE_PROTOCOL_VERSION,
        "subscription_id": subscription_id,
        "seq": seq,
        "event": {"kind": kind.value, "payload": to_wire(payload)},
    }


def terminal_frame(
    subscription_id: str,
    seq: int,
    terminal: StreamTerminal,
    *,
    message: str | None = None,
    dropped: int = 0,
) -> dict[str, Any]:
    """Build the frame that ends a subscription.

    ``dropped`` is only meaningful for ``gap``, and it is carried rather than
    logged so the client can say how much it lost instead of guessing.
    """
    body: dict[str, Any] = {"kind": terminal.value}
    if message is not None:
        body["message"] = message[:200]
    if dropped:
        body["dropped"] = dropped
    return {
        "protocol": BRIDGE_PROTOCOL_VERSION,
        "subscription_id": subscription_id,
        "seq": seq,
        "terminal": body,
    }


@dataclass(frozen=True, slots=True)
class SubscriptionRequest:
    """A parsed ``subscribe`` call: the same shape as an invocation."""

    call_id: str
    operation: str
    payload: Mapping[str, Any]

    @classmethod
    def parse(cls, raw: Any) -> SubscriptionRequest:
        """Validate ``raw`` as a subscription request, refusing anything else."""
        if not isinstance(raw, Mapping):
            raise QgisSdkBridgeProtocolError("A subscription request must be an object")
        if raw.get("protocol") != BRIDGE_PROTOCOL_VERSION:
            raise QgisSdkBridgeProtocolError(
                f"Unsupported bridge protocol: {raw.get('protocol')!r}; "
                f"this host speaks {BRIDGE_PROTOCOL_VERSION}"
            )
        call_id = peek_call_id(raw)
        if call_id is None:
            raise QgisSdkBridgeProtocolError(
                "call_id must be a nonempty string of at most 128 characters"
            )
        operation = raw.get("operation")
        if not isinstance(operation, str) or not operation:
            raise QgisSdkBridgeProtocolError("operation must be a nonempty string")
        payload = raw.get("payload", {})
        if not isinstance(payload, Mapping):
            raise QgisSdkBridgeProtocolError("payload must be an object")
        return cls(call_id=call_id, operation=operation, payload=payload)


@dataclass(frozen=True, slots=True)
class AckRequest:
    """A parsed ``ack`` call: which frame the client has delivered."""

    call_id: str
    subscription_id: str
    seq: int

    @classmethod
    def parse(cls, raw: Any) -> AckRequest:
        """Validate ``raw`` as an acknowledgement, refusing anything else."""
        if not isinstance(raw, Mapping):
            raise QgisSdkBridgeProtocolError("An acknowledgement must be an object")
        if raw.get("protocol") != BRIDGE_PROTOCOL_VERSION:
            raise QgisSdkBridgeProtocolError(
                f"Unsupported bridge protocol: {raw.get('protocol')!r}; "
                f"this host speaks {BRIDGE_PROTOCOL_VERSION}"
            )
        call_id = peek_call_id(raw)
        if call_id is None:
            raise QgisSdkBridgeProtocolError(
                "call_id must be a nonempty string of at most 128 characters"
            )
        subscription_id = raw.get("subscription_id")
        if not isinstance(subscription_id, str) or not subscription_id:
            raise QgisSdkBridgeProtocolError(
                "subscription_id must be a nonempty string"
            )
        seq = raw.get("seq")
        if not isinstance(seq, int) or isinstance(seq, bool) or seq < 0:
            raise QgisSdkBridgeProtocolError("seq must be a non-negative integer")
        return cls(call_id=call_id, subscription_id=subscription_id, seq=seq)


@dataclass(frozen=True, slots=True)
class DisposalRequest:
    """A parsed ``unsubscribe`` call: a call id and the subscription it names."""

    call_id: str
    subscription_id: str

    @classmethod
    def parse(cls, raw: Any) -> DisposalRequest:
        """Validate ``raw`` as a disposal, refusing anything else."""
        if not isinstance(raw, Mapping):
            raise QgisSdkBridgeProtocolError("A disposal must be an object")
        if raw.get("protocol") != BRIDGE_PROTOCOL_VERSION:
            raise QgisSdkBridgeProtocolError(
                f"Unsupported bridge protocol: {raw.get('protocol')!r}; "
                f"this host speaks {BRIDGE_PROTOCOL_VERSION}"
            )
        call_id = peek_call_id(raw)
        if call_id is None:
            raise QgisSdkBridgeProtocolError(
                "call_id must be a nonempty string of at most 128 characters"
            )
        subscription_id = raw.get("subscription_id")
        if not isinstance(subscription_id, str) or not subscription_id:
            raise QgisSdkBridgeProtocolError(
                "subscription_id must be a nonempty string"
            )
        return cls(call_id=call_id, subscription_id=subscription_id)


@runtime_checkable
class PushSource(Protocol):
    """A source the host feeds, for work that finishes on a later event loop turn.

    A network reply, a Qt task's progress: nothing an iterator can wait for
    without blocking the GUI thread. The dispatcher calls :meth:`start` once the
    subscription exists, with a :class:`StreamSink` that knows the subscription
    id so the source never has to. A ``close`` method, when present, runs when
    the subscription ends for any reason - the place to cancel the request.
    """

    def start(self, sink: StreamSink) -> None: ...


StreamSource = Callable[
    [Mapping[str, Any]], Iterator[Mapping[str, Any]] | PushSource | None
]


@dataclass(slots=True)
class Subscription:
    """One open subscription: a bounded queue plus the source behind it."""

    id: str
    view_id: str
    generation: int
    operation: str
    capacity: int = MAX_QUEUED_EVENTS
    events: Mapping[str, Mapping[str, Any]] | None = None
    seq: int = 0
    #: How many frames have been handed to the transport; also the seq the next
    #: acknowledgement may not exceed.
    handed: int = 0
    #: Every frame below this seq is acknowledged by the client.
    acked: int = 0
    dropped: int = 0
    state: StreamState = StreamState.OPEN
    _queue: deque[dict[str, Any]] = field(default_factory=deque)
    _source: Iterator[Mapping[str, Any]] | PushSource | None = None

    @property
    def open(self) -> bool:
        """Whether this subscription still accepts events."""
        return self.state is StreamState.OPEN

    @property
    def queued(self) -> int:
        """How many frames are waiting for the transport."""
        return len(self._queue)

    @property
    def in_flight(self) -> int:
        """Event frames handed out but not yet acknowledged."""
        return max(0, self.handed - self.acked)

    @property
    def acknowledged(self) -> int:
        """The seq the client has confirmed it delivered."""
        return self.acked

    def acknowledge(self, seq: int) -> bool:
        """Record that the client delivered frame ``seq``.

        ``True`` when the seq is one this subscription handed out - a repeat or
        an out-of-order ack is accepted, because frames race the consumer that
        acknowledges them - and ``False`` when it names a frame that was never
        handed out. A client that acks numbers it did not receive has lost track
        of the stream, and clamping would hide exactly the gap this exists to
        surface.
        """
        if seq < 0 or seq >= self.handed:
            return False
        self.acked = max(self.acked, seq + 1)
        return True

    def attach(self, source: Iterator[Mapping[str, Any]] | PushSource | None) -> None:
        """Attach the generator a pull subscription is fed from, or a push source.

        A push source is only held so its ``close`` runs when the subscription
        ends; :meth:`pull` never advances it.
        """
        self._source = source

    def emit(
        self, payload: Any, *, kind: StreamEventType = StreamEventType.DATA
    ) -> bool:
        """Queue one event, coalescing progress and refusing to grow unbounded.

        Returns ``False`` when the subscription is no longer open. A full queue
        terminates the subscription with ``gap``: losing events silently is not
        an option, and neither is an unbounded buffer. An event the operation
        did not declare terminates it with ``error`` for the same reason.
        """
        if not self.open:
            return False
        try:
            payload = to_wire(payload)
        except QgisSdkBridgeError as error:
            self.terminate(StreamTerminal.ERROR, message=str(error))
            return False
        refusal = self._event_refusal(kind, payload)
        if refusal is not None:
            self.terminate(StreamTerminal.ERROR, message=refusal)
            return False
        if kind is StreamEventType.PROGRESS and self._queue:
            tail = self._queue[-1]
            if tail.get("event", {}).get("kind") == StreamEventType.PROGRESS.value:
                frame = event_frame(self.id, tail["seq"], kind=kind, payload=payload)
                self._queue[-1] = frame
                return True
        if len(self._queue) >= self.capacity:
            self.dropped += 1
            self.terminate(
                StreamTerminal.GAP,
                message=(
                    "The view did not consume this subscription fast enough and "
                    "events were dropped"
                ),
                dropped=self.dropped,
            )
            return False
        self._queue.append(event_frame(self.id, self.seq, kind=kind, payload=payload))
        self.seq += 1
        return True

    def _event_refusal(self, kind: StreamEventType, payload: Any) -> str | None:
        """Hold an event to the declaration, naming the path and never the value."""
        if self.events is None:
            return None
        schema = self.events.get(kind.value)
        if schema is None:
            return (
                f"{self.operation}: the stream emitted {kind.value!r}, "
                "which it did not declare"
            )
        try:
            validate(payload, schema, path="event", allow_unknown=True)
        except QgisSdkBridgeError as error:
            return f"{self.operation}: {error}"
        return None

    def terminate(
        self,
        terminal: StreamTerminal,
        *,
        message: str | None = None,
        dropped: int = 0,
    ) -> bool:
        """Queue the terminal frame exactly once."""
        if not self.open:
            return False
        self._queue.append(
            terminal_frame(
                self.id, self.seq, terminal, message=message, dropped=dropped
            )
        )
        self.seq += 1
        self.state = StreamState.TERMINATED
        self.close_source()
        return True

    def dispose(self) -> None:
        """End the subscription without a frame: the view asked, or is gone.

        Nothing queued is delivered and nothing further is accepted, so a push
        source whose reply lands after disposal writes into a closed sink.
        """
        self.state = StreamState.DRAINED
        self._queue.clear()
        self.close_source()

    def close_source(self) -> None:
        """Close the generator, so its ``finally`` blocks run while they can."""
        source, self._source = self._source, None
        if source is None:
            return
        close = getattr(source, "close", None)
        if close is not None:
            close()

    def drain(self, limit: int) -> list[dict[str, Any]]:
        """Hand up to ``limit`` frames to the transport, oldest first.

        At most :data:`MAX_IN_FLIGHT_FRAMES` unacknowledged event frames leave in
        one go; a terminal frame is never held back, because ending the stream is
        not work the client has to acknowledge first.
        """
        frames: list[dict[str, Any]] = []
        while self._queue and len(frames) < limit:
            frame = self._queue[0]
            if "terminal" not in frame and self.in_flight >= MAX_IN_FLIGHT_FRAMES:
                break
            self._queue.popleft()
            if "terminal" not in frame:
                self.handed += 1
            frames.append(frame)
        if not self._queue and self.state is StreamState.TERMINATED:
            self.state = StreamState.DRAINED
        return frames

    def pull(self, limit: int) -> None:
        """Take up to ``limit`` events from the source into the queue.

        A pull model has natural backpressure: when the queue is full the source
        is simply not advanced, so a pulled stream cannot overflow. The source
        ending is a ``complete``; an actor raising is reported as the failure it
        is, with the SDK's own message when it has one.
        """
        source = self._source
        if source is None or not self.open or not hasattr(source, "__next__"):
            return
        produced = 0
        while produced < limit and self.open and len(self._queue) < self.capacity:
            try:
                item = next(source)
            except StopIteration:
                self.terminate(StreamTerminal.COMPLETE)
                return
            except QgisSdkJobCancelledError as error:
                self.terminate(StreamTerminal.CANCELLED, message=str(error))
                return
            except QgisSdkError as error:
                self.terminate(StreamTerminal.ERROR, message=str(error))
                return
            except Exception:  # noqa: BLE001 - a stream failure must be a frame
                self.terminate(
                    StreamTerminal.ERROR,
                    message="The stream failed; the host recorded the details",
                )
                return
            try:
                kind, payload = split_event(item)
            except QgisSdkBridgeError as error:
                self.terminate(StreamTerminal.ERROR, message=str(error))
                return
            self.emit(payload, kind=kind)
            produced += 1


@dataclass(slots=True)
class StreamSink:
    """What a :class:`PushSource` writes into: one subscription plus a wake-up.

    ``wake`` tells the adapter that frames are waiting, so a channel can flush
    them without polling. Once the subscription ended every call is inert and
    returns ``False``: a late reply arriving after disposal is normal, not an
    error path the host has to guard.
    """

    subscription: Subscription
    wake: Callable[[], None] | None = None

    @property
    def open(self) -> bool:
        return self.subscription.open

    def emit(
        self, payload: Any, *, kind: StreamEventType = StreamEventType.DATA
    ) -> bool:
        """Queue one event; ``False`` once the subscription is closed."""
        if not self.subscription.open:
            return False
        accepted = self.subscription.emit(payload, kind=kind)
        self._wake()
        return accepted

    def complete(self) -> bool:
        """End the stream normally."""
        ended = self.subscription.terminate(StreamTerminal.COMPLETE)
        if ended:
            self._wake()
        return ended

    def fail(self, error: BaseException | str) -> bool:
        """End the stream with a failure, keeping an SDK error's own message."""
        if isinstance(error, QgisSdkJobCancelledError):
            terminal, message = StreamTerminal.CANCELLED, str(error)
        elif isinstance(error, (QgisSdkError, str)):
            terminal, message = StreamTerminal.ERROR, str(error)
        else:
            terminal = StreamTerminal.ERROR
            message = "The stream failed; the host recorded the details"
        ended = self.subscription.terminate(terminal, message=message)
        if ended:
            self._wake()
        return ended

    def _wake(self) -> None:
        if self.wake is not None:
            self.wake()


def split_event(item: Any) -> tuple[StreamEventType, Any]:
    """Split one produced item into its event kind and its payload.

    A source yields either a bare payload (a data event) or a mapping carrying
    ``kind`` and ``payload``. Anything that is not a mapping is refused here
    rather than reaching a view as a guessing game; the refusal is a ``pull``
    failure, so the subscription terminates with ``error``.
    """
    if not isinstance(item, Mapping):
        raise QgisSdkBridgeError(
            f"a stream emitted {type(item).__name__}, not a mapping"
        )
    if "kind" in item or "payload" in item:
        kind = item.get("kind", StreamEventType.DATA.value)
        if kind not in _EVENT_KINDS:
            raise QgisSdkBridgeError(f"{kind!r} is not a stream event kind")
        return StreamEventType(kind), item.get("payload")
    return StreamEventType.DATA, item


__all__ = [
    "MAX_FRAMES_PER_PUMP",
    "MAX_IN_FLIGHT_FRAMES",
    "MAX_QUEUED_EVENTS",
    "MAX_SUBSCRIPTIONS_PER_VIEW",
    "AckRequest",
    "DisposalRequest",
    "PushSource",
    "StreamEventType",
    "StreamSink",
    "StreamSource",
    "StreamState",
    "StreamTerminal",
    "Subscription",
    "SubscriptionRequest",
    "event_frame",
    "split_event",
    "terminal_frame",
]

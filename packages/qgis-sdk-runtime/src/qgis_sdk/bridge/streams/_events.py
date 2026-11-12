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

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from qgis_sdk.bridge.protocol import (
    BRIDGE_PROTOCOL_VERSION,
    peek_call_id,
    to_wire,
)
from qgis_sdk.models.errors import (
    QgisSdkBridgeProtocolError,
)

if TYPE_CHECKING:
    from qgis_sdk.bridge.streams._sink import StreamSink

MAX_QUEUED_EVENTS = 64
MAX_FRAMES_PER_PUMP = 16
MAX_SUBSCRIPTIONS_PER_VIEW = 8
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


EVENT_KINDS = frozenset(kind.value for kind in StreamEventType)


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

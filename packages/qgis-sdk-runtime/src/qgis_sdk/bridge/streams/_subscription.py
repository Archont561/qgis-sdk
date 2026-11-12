from __future__ import annotations

from collections import deque
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any

from qgis_sdk.bridge.protocol import (
    to_wire,
)
from qgis_sdk.bridge.schema import validate
from qgis_sdk.models.errors import (
    QgisSdkBridgeError,
    QgisSdkError,
    QgisSdkJobCancelledError,
)

from ._events import (
    MAX_IN_FLIGHT_FRAMES,
    MAX_QUEUED_EVENTS,
    PushSource,
    StreamEventType,
    StreamState,
    StreamTerminal,
    event_frame,
    terminal_frame,
)
from ._sink import split_event


class _SubscriptionMixin1:
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
        accepted, wired = self._wired(payload, kind)
        if not accepted:
            return False
        return self._queue_frame(wired, kind)

    def _wired(self, payload: Any, kind: StreamEventType) -> tuple[bool, Any]:
        """The payload as the wire carries it, and whether the stream survived it.

        Two refusals live here - a payload that cannot cross, and an event the
        operation never declared - and both end the subscription rather than
        dropping the event.
        """
        try:
            wired = to_wire(payload)
        except QgisSdkBridgeError as error:
            self.terminate(StreamTerminal.ERROR, message=str(error))
            return False, None
        refusal = self._event_refusal(kind, wired)
        if refusal is not None:
            self.terminate(StreamTerminal.ERROR, message=refusal)
            return False, None
        return True, wired

    def _queue_frame(self, wired: Any, kind: StreamEventType) -> bool:
        """Queue one event, replacing a progress frame instead of growing the queue.

        A progress report is a position, not a history: the last one still
        describes the stream, so it is overwritten where it sits. Anything else
        is appended, and a queue already at capacity ends the subscription with
        a gap rather than dropping an event silently.
        """
        if kind is StreamEventType.PROGRESS and self._queue:
            tail = self._queue[-1]
            if tail.get("event", {}).get("kind") == StreamEventType.PROGRESS.value:
                self._queue[-1] = event_frame(
                    self.id, tail["seq"], kind=kind, payload=wired
                )
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
        self._queue.append(event_frame(self.id, self.seq, kind=kind, payload=wired))
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


class _SubscriptionMixin2:
    def pull(self, limit: int) -> None:
        """Take up to ``limit`` events from the source into the queue.

        A pull model has natural backpressure: when the queue is full the source
        is simply not advanced, so a pulled stream cannot overflow. The source
        ending is a ``complete``; an actor raising is reported as the failure it
        is, with the SDK's own message when it has one.
        """
        source = self._source
        if not self.open or source is None or not hasattr(source, "__next__"):
            return
        produced = 0
        while produced < limit and self.open and len(self._queue) < self.capacity:
            item = _advance(self, source)
            if item is _EXHAUSTED:
                return
            try:
                kind, payload = split_event(item)
            except QgisSdkBridgeError as error:
                self.terminate(StreamTerminal.ERROR, message=str(error))
                return
            self.emit(payload, kind=kind)
            produced += 1


@dataclass(slots=True)
class Subscription(_SubscriptionMixin1, _SubscriptionMixin2):
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


_EXHAUSTED = object()
"""The answer :func:`_advance` gives when the source stopped producing."""


def _advance(subscription: Subscription, source: Any) -> Any:
    """Take the source's next event, ending the subscription if it has none.

    Every way a source stops - an exhausted iterator, a cancellation, a job
    error, a surprise - is a terminal state, so it is written once here and the
    pull loop only has to know that the answer was ``_EXHAUSTED``.
    """
    try:
        return next(source)
    except StopIteration:
        subscription.terminate(StreamTerminal.COMPLETE)
    except QgisSdkJobCancelledError as error:
        subscription.terminate(StreamTerminal.CANCELLED, message=str(error))
    except QgisSdkError as error:
        subscription.terminate(StreamTerminal.ERROR, message=str(error))
    except Exception:  # noqa: BLE001 - a broken stream still gets a terminal frame
        subscription.terminate(
            StreamTerminal.ERROR,
            message="The stream failed; the host recorded the details",
        )
    return _EXHAUSTED


"""The answer :meth:`Subscription._advance` gives when the source stopped."""

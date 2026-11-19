"""One open subscription of a view to a plugin's ``@stream`` method."""

from __future__ import annotations

import contextlib
import threading
from collections import deque
from collections.abc import Callable, Iterator, Mapping
from typing import Any

from qgis_sdk.bridge.streams import MAX_FRAMES_PER_PUMP, PushSource, split_event
from qgis_sdk.declarations import STREAM_EVENT_KINDS
from qgis_sdk.models import QgisSdkError
from qgis_sdk.ui.actions import CALLING_VIEW

from ._streams import StreamEvent, ViewStreams

__all__ = ["ViewSubscription"]


class ViewSubscription:
    """One open subscription of a view; ``dispose()`` ends it early.

    Args:
        streams: The view's stream service.
        stream: The stream name to subscribe to.
        callback: What each event is handed to.
    """

    __slots__ = (
        "_callback",
        "_pending",
        "_source",
        "_streams",
        "_thread",
        "active",
        "stream",
    )

    def __init__(
        self,
        streams: ViewStreams,
        stream: str,
        callback: Callable[[StreamEvent], None],
    ) -> None:
        """Hold one open subscription of a view.

        Args:
            streams: The view's stream service.
            stream: The stream name the subscription is on.
            callback: What each event is handed to.
        """
        self._streams = streams
        self.stream = stream
        self._callback = callback
        self._source: Iterator[Mapping[str, Any]] | PushSource | None = None
        self._pending: deque[StreamEvent] = deque()
        self._thread = threading.get_ident()
        self.active = True

    @property
    def pulling(self) -> bool:
        """Whether an iterator still feeds this subscription on ``pump``."""
        return self.active and hasattr(self._source, "__next__")

    @property
    def pending(self) -> int:
        """Events pushed from another thread, waiting for the next ``pump``."""
        return len(self._pending)

    # -- the sink a push source writes into -----------------------------------------

    @property
    def open(self) -> bool:
        return self.active

    def emit(self, payload: Any, *, kind: Any = "data") -> bool:
        """Queue or deliver one event; ``False`` once disposed.

        Args:
            payload: The value the event carries.
            kind: What happened: ``data`` by default.
        """
        if not self.active:
            return False
        name = getattr(kind, "value", kind)
        if name not in STREAM_EVENT_KINDS:
            self.fail(f"{name!r} is not a stream event kind")
            return False
        self._deliver(StreamEvent(self.stream, name, payload, echo=self._echo()))
        return True

    def complete(self) -> bool:
        if not self.active:
            return False
        self._deliver(StreamEvent(self.stream, "complete", None))
        self.dispose()
        return True

    def fail(self, error: BaseException | str) -> bool:
        """Deliver an error event and end the subscription.

        Args:
            error: The failure, or its message.
        """
        if not self.active:
            return False
        message = (
            str(error)
            if isinstance(error, (str, QgisSdkError))
            else "The stream failed; the host recorded the details"
        )
        self._deliver(StreamEvent(self.stream, "error", message))
        self.dispose()
        return True

    # -- lifecycle --------------------------------------------------------------------

    def dispose(self) -> None:
        """End the subscription; nothing is delivered after this."""
        if not self.active:
            return
        self.active = False
        source = self._source
        self._source = None
        close = getattr(source, "close", None)
        if callable(close):
            # Disposal never raises into a Qt slot; a failing close is the
            # source's problem, already past the point anyone can act on it.
            with contextlib.suppress(Exception):
                close()
        self._streams._forget(self)

    def pump(self, limit: int = MAX_FRAMES_PER_PUMP) -> int:
        """Deliver queued events and pull up to ``limit`` items from an iterator.

        Args:
            limit: How many events to deliver at most.
        """
        delivered = 0
        while self._pending and delivered < limit:
            self._callback(self._pending.popleft())
            delivered += 1
        source = self._source
        if not self.active or not hasattr(source, "__next__"):
            return delivered
        for _ in range(limit - delivered):
            delivered += self._pull_one(source)
            if not self.active:
                break
        return delivered

    def _pull_one(self, source: Any) -> int:
        """Pull one item from the iterator; ``1`` when an event was delivered."""
        try:
            item = next(source)  # type: ignore[arg-type]
        except StopIteration:
            self.complete()
            return 0
        except Exception as error:  # noqa: BLE001 - the stream must still end
            self.fail(error)
            return 0
        try:
            kind, payload = split_event(item)
        except QgisSdkError as error:
            self.fail(error)
            return 0
        self._callback(StreamEvent(self.stream, kind.value, payload))
        return 1

    def _attach(self, source: Any) -> None:
        self._source = source
        if isinstance(source, PushSource) and not hasattr(source, "__next__"):
            try:
                source.start(self)
            except Exception as error:  # noqa: BLE001 - the stream must still end
                self.fail(error)

    def _deliver(self, event: StreamEvent) -> None:
        # Author code runs on the GUI thread only: an event pushed from another
        # thread waits for the next pump.
        """Deliver an event now, or queue it for the next pump.

        Args:
            event: The event to deliver or queue.
        """
        if threading.get_ident() == self._thread:
            self._callback(event)
        else:
            self._pending.append(event)
            self._streams._wake()

    def _echo(self) -> bool:
        return CALLING_VIEW.get() == self._streams.view_id

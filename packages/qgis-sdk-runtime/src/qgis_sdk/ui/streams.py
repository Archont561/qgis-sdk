"""``ctx.on(stream, callback)``: a native surface subscribes to a plugin's streams.

A page subscribes through the bridge (decision-23); a native surface has no
wire, so :class:`ViewStreams` opens the same ``@stream`` methods directly:
the method's iterator is pulled on :meth:`pump` and a
:class:`~qgis_sdk.bridge.streams.PushSource` is started with a sink that
delivers as it emits. Every event reaches the callback as a
:class:`StreamEvent` on the GUI thread; an event the view's own synchronous
action call produced carries ``echo=True`` (decision-55 point 2), so a
surface that already updated itself can skip its own echo. Subscriptions are
owned by the view's scope: closing the window disposes them.
"""

from __future__ import annotations

import contextlib
import threading
from collections import deque
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from qgis_sdk.bridge.streams import MAX_FRAMES_PER_PUMP, PushSource, split_event
from qgis_sdk.core import ResourceScope
from qgis_sdk.declarations import STREAM_EVENT_KINDS, PluginDescription
from qgis_sdk.models import QgisSdkError, QgisSdkFormError, QgisSdkUiError

from .actions import CALLING_VIEW
from .form_fields import coerce_values

__all__ = ["StreamEvent", "ViewStreams", "ViewSubscription"]

EventKind = Literal["data", "progress", "state", "complete", "error"]


@dataclass(frozen=True, slots=True)
class StreamEvent:
    """One event a subscribed callback receives.

    ``kind`` is ``data``/``progress``/``state`` for the stream's own events,
    ``complete`` or ``error`` when it ended (``payload`` is then ``None`` or
    the message). ``echo`` marks an event produced by this view's own call.
    """

    stream: str
    kind: EventKind
    payload: Any
    echo: bool = False

    @property
    def terminal(self) -> bool:
        return self.kind in ("complete", "error")


class StreamSource(Protocol):
    """What ``ViewStreams`` reads: a started ``PluginRuntime`` fits."""

    @property
    def description(self) -> PluginDescription: ...

    @property
    def streams(self) -> Mapping[str, Callable[..., object]]: ...


class ViewSubscription:
    """One open subscription of a view; ``dispose()`` ends it early."""

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
        """Queue or deliver one event; ``False`` once disposed."""
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
        """Deliver queued events and pull up to ``limit`` items from an iterator."""
        delivered = 0
        while self._pending and delivered < limit:
            self._callback(self._pending.popleft())
            delivered += 1
        source = self._source
        if not self.active or not hasattr(source, "__next__"):
            return delivered
        for _ in range(limit - delivered):
            try:
                item = next(source)  # type: ignore[arg-type]
            except StopIteration:
                self.complete()
                break
            except Exception as error:  # noqa: BLE001 - the stream must still end
                self.fail(error)
                break
            try:
                kind, payload = split_event(item)
            except QgisSdkError as error:
                self.fail(error)
                break
            self._callback(StreamEvent(self.stream, kind.value, payload))
            delivered += 1
            if not self.active:
                break
        return delivered

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
        if threading.get_ident() == self._thread:
            self._callback(event)
        else:
            self._pending.append(event)
            self._streams._wake()

    def _echo(self) -> bool:
        return CALLING_VIEW.get() == self._streams.view_id


class ViewStreams:
    """The view-scoped way into the plugin's ``@stream`` methods.

    ``runtime`` is the started ``PluginRuntime``; ``view_id`` names the
    surface, which is what the echo flag compares against. ``wake`` is what
    a host hooks to learn that events arrived off the GUI thread.
    """

    __slots__ = ("_runtime", "_subscriptions", "_view_id", "_wake_callback")

    def __init__(
        self,
        runtime: StreamSource,
        *,
        view_id: str,
        wake: Callable[[], None] | None = None,
    ) -> None:
        self._runtime = runtime
        self._view_id = view_id
        self._wake_callback = wake
        self._subscriptions: list[ViewSubscription] = []

    @property
    def view_id(self) -> str:
        return self._view_id

    @property
    def ids(self) -> tuple[str, ...]:
        """The stream ids the plugin declares."""
        return tuple(item.id for item in self._runtime.description.streams)

    @property
    def open(self) -> tuple[ViewSubscription, ...]:
        """The subscriptions still active, oldest first."""
        return tuple(self._subscriptions)

    @property
    def busy(self) -> bool:
        """Whether a ``pump`` still has work: an iterator to pull or events waiting."""
        return any(item.pulling or item.pending for item in self._subscriptions)

    def subscribe(
        self,
        stream: str,
        callback: Callable[[StreamEvent], None],
        *,
        owner: ResourceScope | None = None,
        **request: object,
    ) -> ViewSubscription:
        """Open ``stream`` with ``request``; ``callback`` hears every event.

        ``owner`` is the scope that disposes the subscription when it closes,
        the view's. An unknown stream is refused by name; what the method
        raises while opening is refused with its message.
        """
        described = next(
            (item for item in self._runtime.description.streams if item.id == stream),
            None,
        )
        if described is None:
            known = ", ".join(self.ids) or "none"
            raise QgisSdkUiError(
                f"{self._runtime.description.id} declares no stream {stream!r}; "
                f"it has: {known}"
            )
        method = self._runtime.streams.get(stream)
        if method is None:
            raise QgisSdkUiError(f"{stream} is not bound: the plugin is not running")
        if owner is not None:
            owner.ensure_open()
        # The same validated path a page's subscribe request takes: unknown
        # and ill-typed arguments are refused by name before the method runs.
        try:
            coerced = coerce_values(described, request)  # type: ignore[arg-type]
        except QgisSdkFormError as error:
            raise QgisSdkUiError(f"{stream}: {error}") from error
        subscription = ViewSubscription(self, stream, callback)
        try:
            source = method(**coerced)
        except QgisSdkError as error:
            raise QgisSdkUiError(f"{stream}: {error}") from error
        if source is not None and not (
            hasattr(source, "__next__") or isinstance(source, PushSource)
        ):
            raise QgisSdkUiError(
                f"{stream} did not produce an iterator of events or a push source"
            )
        self._subscriptions.append(subscription)
        if owner is not None:
            owner.on_close(subscription.dispose)
        subscription._attach(source)
        if subscription.pulling:
            self._wake()
        return subscription

    def pump(self, limit: int = MAX_FRAMES_PER_PUMP) -> int:
        """Advance every open subscription; returns how many events were delivered."""
        delivered = 0
        for subscription in tuple(self._subscriptions):
            delivered += subscription.pump(limit)
        return delivered

    def dispose(self) -> None:
        """End every subscription of this view."""
        for subscription in tuple(self._subscriptions):
            subscription.dispose()

    def _forget(self, subscription: ViewSubscription) -> None:
        if subscription in self._subscriptions:
            self._subscriptions.remove(subscription)

    def _wake(self) -> None:
        if self._wake_callback is not None:
            self._wake_callback()

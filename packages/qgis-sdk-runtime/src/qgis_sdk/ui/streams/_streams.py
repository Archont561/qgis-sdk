"""View-scoped subscriptions to a plugin's ``@stream`` methods."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, Protocol

from qgis_sdk.bridge.streams import MAX_FRAMES_PER_PUMP, PushSource
from qgis_sdk.core import ResourceScope
from qgis_sdk.declarations import PluginDescription
from qgis_sdk.models import QgisSdkError, QgisSdkFormError, QgisSdkUiError
from qgis_sdk.ui.form_fields import coerce_values

if TYPE_CHECKING:
    from ._subscription import ViewSubscription


class _CcState:
    """A mutable record shared by the phases of one long function."""

    def __init__(_cc_self, **values):
        _cc_self.__dict__.update(values)


class _CcReturn:
    """An early return travelling out of a phase."""

    def __init__(_cc_self, value):
        _cc_self.value = value


def _cc_subscribe_p1(_s):
    _s.described = next(
        (item for item in _s.self._runtime.description.streams if item.id == _s.stream),
        None,
    )
    if _s.described is None:
        _s.known = ", ".join(_s.self.ids) or "none"
        raise QgisSdkUiError(
            f"{_s.self._runtime.description.id} declares no stream {_s.stream!r}; "
            f"it has: {_s.known}"
        )
    _s.method = _s.self._runtime.streams.get(_s.stream)


def _cc_subscribe_p2(_s):
    if _s.method is None:
        raise QgisSdkUiError(f"{_s.stream} is not bound: the plugin is not running")
    if _s.owner is not None:
        _s.owner.ensure_open()
    # The same validated path a page's subscribe request takes: unknown
    # and ill-typed arguments are refused by name before the method runs.
    try:
        _s.coerced = coerce_values(_s.described, _s.request)  # type: ignore[arg-type]
    except QgisSdkFormError as error:
        _s.error = error
        raise QgisSdkUiError(f"{_s.stream}: {_s.error}") from _s.error
    from ._subscription import ViewSubscription

    _s.subscription = ViewSubscription(_s.self, _s.stream, _s.callback)


def _cc_subscribe_p3(_s):
    try:
        _s.source = _s.method(**_s.coerced)
    except QgisSdkError as error:
        _s.error = error
        raise QgisSdkUiError(f"{_s.stream}: {_s.error}") from _s.error
    return _CcReturn(
        _subscribe_facts11(_s.owner, _s.self, _s.source, _s.stream, _s.subscription)
    )


def _subscribe_facts11(owner, self, source, stream, subscription):
    if source is not None and not (
        hasattr(source, "__next__") or isinstance(source, PushSource)
    ):
        raise QgisSdkUiError(
            f"{stream} did not produce an iterator of events or a push source"
        )
    self._subscriptions.append(subscription)
    return _subscribe_facts1(owner, self, source, subscription)


def _subscribe_facts1(owner, self, source, subscription):
    if owner is not None:
        owner.on_close(subscription.dispose)
    subscription._attach(source)
    if subscription.pulling:
        self._wake()
    return subscription


__all__ = ["StreamEvent", "ViewStreams"]

EventKind = Literal["data", "progress", "state", "complete", "error"]


@dataclass(frozen=True, slots=True)
class StreamEvent:
    """One event a subscribed callback receives.

    ``kind`` is ``data``/``progress``/``state`` for the stream's own events,
    ``complete`` or ``error`` when it ended (``payload`` is then ``None`` or
    the message). ``echo`` marks an event produced by this view's own call.

    Attributes:
        stream: The stream name the event belongs to.
        kind: What happened: ``started``, ``data``, ``ended`` or ``failed``.
        payload: The value the event carries, when it carries one.
        echo: The value the handler returned, when the stream echoes it.
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


class ViewStreams:
    """The view-scoped way into the plugin's ``@stream`` methods.

    ``runtime`` is the started ``PluginRuntime``; ``view_id`` names the
    surface, which is what the echo flag compares against. ``wake`` is what
    a host hooks to learn that events arrived off the GUI thread.

    Args:
        runtime: The runtime whose streams are subscribed to.
        view_id: The view the subscriptions belong to.
        wake: How the driver thread is woken to deliver an event.
    """

    __slots__ = ("_runtime", "_subscriptions", "_view_id", "_wake_callback")

    def __init__(
        self,
        runtime: StreamSource,
        *,
        view_id: str,
        wake: Callable[[], None] | None = None,
    ) -> None:
        """Build the stream service for one view over a started runtime.

        Args:
            runtime: The started runtime the streams are read from.
            view_id: The view the subscriptions belong to.
            wake: How the driver thread is woken to deliver an event.
        """
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

        Args:
            stream: The stream name to open.
            callback: What each event is handed to.
            owner: The scope that owns the subscription, or ``None``.
            **request: The arguments the stream is opened with.
        """
        _s = _CcState(
            self=self, stream=stream, callback=callback, owner=owner, request=request
        )
        for _p in (_cc_subscribe_p1, _cc_subscribe_p2, _cc_subscribe_p3):
            _r = _p(_s)
            if isinstance(_r, _CcReturn):
                return _r.value
        return None

    def pump(self, limit: int = MAX_FRAMES_PER_PUMP) -> int:
        """Advance every open subscription; returns how many events were delivered.

        Args:
            limit: How many events to deliver at most.
        """
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

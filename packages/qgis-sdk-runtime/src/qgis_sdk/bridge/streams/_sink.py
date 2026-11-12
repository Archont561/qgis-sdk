from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from qgis_sdk.models.errors import (
    QgisSdkBridgeError,
    QgisSdkError,
    QgisSdkJobCancelledError,
)

from ._events import EVENT_KINDS, StreamEventType, StreamTerminal

if TYPE_CHECKING:
    from qgis_sdk.bridge.streams._subscription import Subscription


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
        if kind not in EVENT_KINDS:
            raise QgisSdkBridgeError(f"{kind!r} is not a stream event kind")
        return StreamEventType(kind), item.get("payload")
    return StreamEventType.DATA, item

"""The catalogue's feedback components: progress, log and result tables."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

from qgis_sdk.models import QgisSdkUiError
from qgis_sdk.services import LogRecord
from qgis_sdk.ui.components import Component

__all__ = ["JobProgress", "LogView"]

ProgressStatus = Literal[
    "idle", "queued", "running", "succeeded", "failed", "cancelled"
]


class _Feedback(Component):
    prefix = "feedback"

    def __init__(self, name: str | None = None, *, label: str | None = None) -> None:
        super().__init__(name, label=label)
        self._listeners: list[Callable[[Any], None]] = []

    def changed(self, listener: Callable[[Any], None]) -> Callable[[], None]:
        """Call ``listener`` after each change; returns the unsubscribe.

        Args:
            listener: What each change is handed to.
        """
        self._listeners.append(listener)

        def unsubscribe() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return unsubscribe

    def dispose(self) -> None:
        super().dispose()
        self._listeners.clear()

    def _sync(self) -> None:
        if self._native is not None and not self._syncing:
            self._syncing = True
            try:
                self._native.apply(self._state())
            finally:
                self._syncing = False

    def _notify(self, value: Any) -> None:
        for listener in tuple(self._listeners):
            listener(value)


class _JobProgressMixin1:
    @property
    def handle(self) -> Any | None:
        """The job handle currently followed, if any."""
        return self._handle

    @property
    def status(self) -> ProgressStatus:
        return self._status

    @property
    def fraction(self) -> float | None:
        """The latest fraction (``0.0``-``1.0``) reported, or ``None``."""
        return self._fraction

    @property
    def message(self) -> str:
        """The failure's text once a job failed; empty otherwise."""
        return self._message

    def bind(self, handle: Any) -> None:
        """Follow ``handle``; a previous handle is left alone from now on.

        Args:
            handle: The job handle to follow.
        """
        if not hasattr(handle, "on_progress") or not hasattr(handle, "status"):
            raise QgisSdkUiError(
                f"{self._describe()}.bind() takes a job handle, "
                f"got {type(handle).__name__}"
            )
        self._unbind()
        self._handle = handle
        self._status = str(handle.status)  # type: ignore[assignment]
        self._fraction = handle.progress
        self._message = ""
        owner = self._ctx.scope if self._ctx is not None else None
        self._subscriptions = [
            handle.on_progress(self._progressed, owner=owner),
            handle.on_success(self._succeeded, owner=owner),
            handle.on_failure(self._failed, owner=owner),
            handle.on_cancelled(self._cancelled, owner=owner),
        ]
        self._sync()
        self._notify(self._status)

    def reset(self) -> None:
        """Forget the handle and show nothing running."""
        self._unbind()
        self._set("idle", None, "")

    def cancel(self) -> bool:
        """Ask the followed job to stop; ``False`` when nothing is running."""
        if self._handle is None or self._handle.status.settled:
            return False
        return bool(self._handle.cancel())

    def _state(self) -> object:
        return (self._status, self._fraction, self._message)

    def _from_widget(self, value: object) -> None:
        if value == "cancel":
            self.cancel()

    def _unbind(self) -> None:
        for subscription in self._subscriptions:
            subscription.dispose()
        self._subscriptions = []
        self._handle = None

    def _progressed(self, fraction: float) -> None:
        status = self._status
        if status in ("idle", "queued"):
            status = "running"
        self._set(status, fraction, self._message)

    def _succeeded(self, _result: object) -> None:
        self._set("succeeded", 1.0, "")

    def _failed(self, error: BaseException) -> None:
        self._set("failed", self._fraction, str(error) or type(error).__name__)


class _JobProgressMixin2:
    def _cancelled(self) -> None:
        self._set("cancelled", self._fraction, "")

    def _set(self, status: str, fraction: float | None, message: str) -> None:
        self._status = status  # type: ignore[assignment]
        self._fraction = fraction
        self._message = message
        self._sync()
        self._notify(status)


class JobProgress(_JobProgressMixin1, _JobProgressMixin2, _Feedback):
    """A progress bar, a message and a Cancel button over one job handle.

    ``bind(handle)`` follows the handle's progress and outcome through its
    own subscriptions, owned by the surface's scope once attached, so a
    closed window hears nothing more. ``status`` is one of ``idle``,
    ``queued``, ``running``, ``succeeded``, ``failed``, ``cancelled``;
    ``fraction`` the latest report; ``message`` the failure text. ``cancel()``
    is what the button does: asks the bound job to stop.

    Args:
        name: The component's name in the surface.
        label: The text shown above it.
        cancellable: Whether it offers a Cancel button.
    """

    def __init__(
        self,
        name: str | None = None,
        *,
        label: str | None = None,
        cancellable: bool = True,
    ) -> None:
        """Build the progress component, with or without a Cancel button.

        Args:
            name: The component's name in the surface.
            label: The text shown above it.
            cancellable: Whether it offers a Cancel button.
        """
        super().__init__(name, label=label)
        self.cancellable = cancellable
        self._handle: Any | None = None
        self._subscriptions: list[Any] = []
        self._status: ProgressStatus = "idle"
        self._fraction: float | None = None
        self._message = ""

    def dispose(self) -> None:
        self._unbind()
        super().dispose()

    def snapshot(self) -> dict[str, Any]:
        node = super().snapshot()
        node["status"] = self._status
        node["fraction"] = self._fraction
        node["message"] = self._message
        node["cancellable"] = self.cancellable
        if self._handle is not None:
            node["job"] = self._handle.id
        return node


class LogView(_Feedback):
    """The plugin's ``ctx.log`` records as they arrive, newest last.

    Subscribes to the context's log on ``attach`` (a host without ``ctx.log``
    is refused by name) and unsubscribes when the scope closes. ``limit``
    bounds how many records are kept; ``records()`` is what the widget shows.

    Args:
        name: The component's name in the surface.
        label: The text shown above it.
        limit: How many records to keep, oldest dropped first.
    """

    def __init__(
        self, name: str | None = None, *, label: str | None = None, limit: int = 500
    ) -> None:
        """Build the log view, keeping at most ``limit`` records.

        Args:
            name: The component's name in the surface.
            label: The text shown above it.
            limit: How many records to keep, oldest dropped first.
        """
        super().__init__(name, label=label)
        if limit < 1:
            raise QgisSdkUiError(f"{self._describe()}: limit must be at least 1")
        self.limit = limit
        self._records: list[LogRecord] = []
        self._unsubscribe: Callable[[], None] | None = None

    def records(self) -> tuple[LogRecord, ...]:
        """The records shown, oldest first."""
        return tuple(self._records)

    def lines(self) -> tuple[str, ...]:
        """One text line per record: ``[level] message key=value``."""
        return tuple(f"[{record.level}] {record.format()}" for record in self._records)

    def clear(self) -> None:
        """Drop every record shown."""
        self._records.clear()
        self._sync()
        self._notify(None)

    def snapshot(self) -> dict[str, Any]:
        node = super().snapshot()
        node["limit"] = self.limit
        node["lines"] = list(self.lines())
        return node

    def _attached(self) -> None:
        log = self._require_ctx("log")
        self._unsubscribe = log.subscribe(self._record)

    def _detached(self) -> None:
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None

    def _state(self) -> object:
        return self.lines()

    def _record(self, record: LogRecord) -> None:
        self._records.append(record)
        del self._records[: -self.limit]
        self._sync()
        self._notify(record)

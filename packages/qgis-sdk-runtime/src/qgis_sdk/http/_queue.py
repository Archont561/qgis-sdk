"""Bounded handoff from HTTP threads to one non-reentrant owner thread."""

from __future__ import annotations

import threading
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from qgis_sdk.models.errors import QgisSdkError


class QgisSdkHostBusyError(QgisSdkError):
    """The host did not start an HTTP request before its deadline."""

    code = "host_busy"


class QgisSdkHostReloadedError(QgisSdkError):
    """The host closed before a queued request could start."""

    code = "host_reloaded"


@dataclass
class _Work:
    fn: Callable[[], Any]
    picked: threading.Event = field(default_factory=threading.Event)
    done: threading.Event = field(default_factory=threading.Event)
    cancelled: bool = False
    value: Any = None
    error: BaseException | None = None


class GuiQueue:
    """Serialize work even when a callback spins a nested Qt event loop.

    The post callable may be called from any thread and must enqueue on the
    runtime owner. Deadlines apply only before pickup: once work has begun its
    outcome must be delivered unless the host closes, in which case the caller
    is told the outcome is unknown; running effects cannot be undone.
    """

    def __init__(self, post: Callable[[Callable[[], None]], None], deadline: float):
        self._post = post
        self._deadline = deadline
        self._lock = threading.Lock()
        self._items: deque[_Work] = deque()
        # At most one cleanup per session; unlike requests, cleanup is not
        # discarded when the request queue fills or a post is rejected.
        self._cleanups: dict[str, _Work] = {}
        self._active = False
        self._current: _Work | None = None
        self._idle_callbacks: list[Callable[[], None]] = []
        self._retry_timer: threading.Timer | None = None
        self._scheduled = False
        self._closed = False

    def close(self) -> None:
        """Withdraw queued work and fail active callers without undoing effects."""
        with self._lock:
            self._closed = True
            if self._retry_timer is not None:
                self._retry_timer.cancel()
                self._retry_timer = None
            if self._current is not None:
                self._current.cancelled = True
                self._current.error = QgisSdkHostReloadedError(
                    "The QGIS host closed; an already-started action may have had effects"
                )
                self._current.done.set()
            self._cleanups.clear()  # The owner disposes every session during close.
            while self._items:
                work = self._items.popleft()
                work.cancelled = True
                work.error = QgisSdkHostReloadedError("The QGIS host closed")
                work.picked.set()
                work.done.set()

    def defer_until_idle(self, fn: Callable[[], None]) -> bool:
        """Defer owner cleanup if an already-started callback is still running."""
        with self._lock:
            if not self._active:
                return False
            self._idle_callbacks.append(fn)
            return True

    def defer(self, key: str, fn: Callable[[], Any]) -> bool:
        """Retain one cleanup per session until the owner can execute it."""
        with self._lock:
            if self._closed:
                return False
            self._cleanups.setdefault(key, _Work(fn))
            schedule = not self._active and not self._scheduled
            if schedule:
                self._scheduled = True
        if schedule:
            self._schedule()
        return True

    def call(self, fn: Callable[[], Any]) -> Any:
        work = _Work(fn)
        with self._lock:
            if self._closed:
                raise QgisSdkHostReloadedError("The QGIS host closed")
            if len(self._items) >= 64:
                raise QgisSdkHostBusyError("The QGIS host request queue is full")
            self._items.append(work)
            schedule = not self._active and not self._scheduled
            if schedule:
                self._scheduled = True
        if schedule:
            self._schedule()
        if not work.picked.wait(self._deadline):
            with self._lock:
                if not work.picked.is_set():
                    work.cancelled = True
                    self._items.remove(work)
                    raise QgisSdkHostBusyError(
                        "The QGIS host did not pick up the request in time"
                    )
        work.done.wait()
        if work.error is not None:
            raise work.error
        return work.value

    def _schedule(self) -> None:
        try:
            self._post(self._drain)
        except Exception:  # noqa: BLE001 - fail queued callers if the host rejects a post
            with self._lock:
                self._scheduled = False
                while self._items:
                    work = self._items.popleft()
                    work.cancelled = True
                    work.error = QgisSdkHostBusyError(
                        "The QGIS host rejected scheduling"
                    )
                    work.picked.set()
                    work.done.set()
                if self._cleanups and not self._closed and self._retry_timer is None:
                    timer = threading.Timer(0.25, self._retry_cleanups)
                    timer.daemon = True
                    self._retry_timer = timer
                    timer.start()

    def _retry_cleanups(self) -> None:
        with self._lock:
            self._retry_timer = None
            schedule = bool(self._cleanups) and not (
                self._closed or self._active or self._scheduled
            )
            if schedule:
                self._scheduled = True
        if schedule:
            self._schedule()

    def _drain(self) -> None:
        with self._lock:
            self._scheduled = False
            if self._active:
                return
            while self._items and self._items[0].cancelled:
                self._items.popleft()
            if self._cleanups:
                key = next(iter(self._cleanups))
                item = self._cleanups.pop(key)
            elif self._items:
                item = self._items.popleft()
            else:
                return
            self._active = True
            self._current = item
            item.picked.set()
        value = None
        error = None
        try:
            value = item.fn()
        except BaseException as caught:  # noqa: BLE001 - always release the waiting caller
            error = caught
        finally:
            with self._lock:
                if not item.cancelled:
                    item.value = value
                    item.error = error
                    item.done.set()
                self._current = None
                self._active = False
                idle_callbacks, self._idle_callbacks = self._idle_callbacks, []
                schedule = bool(self._cleanups or self._items) and not self._scheduled
                if schedule:
                    self._scheduled = True
            for callback in idle_callbacks:
                callback()
            if schedule:
                self._schedule()

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
        self._active_thread: int | None = None
        self._current: _Work | None = None
        self._idle_callbacks: list[Callable[[], None]] = []
        self._retry_timer: threading.Timer | None = None
        self._scheduled = False
        self._closed = False
        # Per thread: whether this thread is inside `_drain`, and whether the
        # post it made at the end of an item ran the callback straight away.
        self._local = threading.local()

    @property
    def pending(self) -> int:
        """Requests waiting for their turn behind the work the owner runs."""
        with self._lock:
            return len(self._items)

    @property
    def busy(self) -> bool:
        """Whether the owner thread is running queued work right now."""
        with self._lock:
            return self._active

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
            if self._active_thread == threading.get_ident():
                # Calling back into the owner from work it is already running
                # would wait for a turn that cannot arrive; refuse at once
                # instead of blocking the owner thread for the whole deadline.
                raise QgisSdkHostBusyError(
                    "The QGIS host is already running work on this thread"
                )
            if len(self._items) >= 64:
                raise QgisSdkHostBusyError("The QGIS host request queue is full")
            self._items.append(work)
            schedule = not self._active and not self._scheduled
            if schedule:
                self._scheduled = True
        if schedule:
            self._schedule()
        if not work.picked.wait(self._deadline) and not self._adopt_late(work):
            raise QgisSdkHostBusyError(
                "The QGIS host did not pick up the request in time"
            )
        work.done.wait()
        if work.error is not None:
            raise work.error
        return work.value

    def _adopt_late(self, work: _Work) -> bool:
        """Settle a request whose pickup deadline has just expired.

        ``True`` means the request has begun - the owner picked it up, or took
        it out of the queue as the deadline expired - so its outcome is owed to
        the caller, because a deadline only covers pickup. ``False`` means it was
        taken back out before it started, and the caller is told the pickup
        failed.
        """
        with self._lock:
            if work.picked.is_set():
                return True
            work.cancelled = True
            try:
                self._items.remove(work)
            except ValueError:
                # Popped between the deadline expiring and this sweep, so the
                # owner is starting it: leave it uncancelled and wait for the
                # pickup to be announced rather than losing the outcome.
                work.cancelled = False
                return work.picked.wait(self._deadline)
            return False

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
        """Deliver queued work, without growing the stack per item.

        The tail of every item posts the next turn. A ``post`` that runs the
        callback immediately - a test's ``lambda callback: callback()``, or a
        host that dispatches inline - would then re-enter this method once per
        queued request, and a hundred waiting requests would be a hundred nested
        frames, close enough to Python's limit to fail as a ``RecursionError``
        raised somewhere unrelated. The re-entry is noticed here and answered by
        the loop of the item that is finishing, so the stack stays flat.
        """
        local = self._local
        if getattr(local, "draining", False):
            local.again = True
            return
        local.draining = True
        local.again = False
        try:
            while True:
                local.again = False
                self._drain_one()
                if not local.again:
                    return
        finally:
            local.draining = False

    def _drain_one(self) -> None:
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
            self._active_thread = threading.get_ident()
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
                self._active_thread = None
                idle_callbacks, self._idle_callbacks = self._idle_callbacks, []
                schedule = bool(self._cleanups or self._items) and not self._scheduled
                if schedule:
                    self._scheduled = True
            for callback in idle_callbacks:
                callback()
            if schedule:
                self._schedule()

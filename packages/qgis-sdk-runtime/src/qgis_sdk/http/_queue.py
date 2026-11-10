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


def _refuse_all(items: deque[_Work], error: QgisSdkError) -> None:
    """Tell every waiting caller its work will never run; the caller holds the lock."""
    while items:
        work = items.popleft()
        work.cancelled = True
        work.error = error
        work.picked.set()
        work.done.set()


def _settle_late(items: deque[_Work], work: _Work, deadline: float) -> bool:
    """Settle a request whose pickup deadline has just expired.

    ``True`` means the request has begun - the owner picked it up, or took it
    out of the queue as the deadline expired - so its outcome is owed to the
    caller, because a deadline only covers pickup. ``False`` means it was taken
    back out before it started, and the caller is told the pickup failed.
    """
    if work.picked.is_set():
        return True
    work.cancelled = True
    try:
        items.remove(work)
    except ValueError:
        # Popped between the deadline expiring and this sweep, so the owner is
        # starting it: leave it uncancelled and wait for the pickup to be
        # announced rather than losing the outcome.
        work.cancelled = False
        return work.picked.wait(deadline)
    return False


class _Cleanups:
    """The one-per-session work a host defers: kept until the owner runs it.

    Unlike requests, a cleanup is not discarded when the request queue fills or
    a post is rejected: the session still has to be disposed of, so it is
    retried until the host accepts it.

    Guarded by the queue's lock rather than its own: what is deferred, whether
    the owner is busy and whether a turn is already scheduled are read together,
    and a second lock would only add an ordering to get wrong.
    """

    def __init__(self) -> None:
        self._items: dict[str, _Work] = {}

    def __bool__(self) -> bool:
        return bool(self._items)

    def add(self, key: str, fn: Callable[[], Any]) -> None:
        """Keep the first cleanup queued for a session; a repeat is a no-op."""
        self._items.setdefault(key, _Work(fn))

    def take(self) -> _Work | None:
        """Take the oldest cleanup, if the host still has one to run."""
        if not self._items:
            return None
        return self._items.pop(next(iter(self._items)))

    def clear(self) -> None:
        """Drop every cleanup, for a host that disposes its sessions itself."""
        self._items.clear()


class _Turn:
    """What the owner thread is running, and the cleanup it owes when it stops.

    One item at a time: `start` hands it over, `finish` records its outcome and
    frees the owner, and anything deferred meanwhile waits in `owed` so it runs
    once the callback returns rather than inside it. Guarded by the queue's
    lock, like `_Cleanups`.
    """

    def __init__(self) -> None:
        self.thread: int | None = None
        self.current: _Work | None = None
        self.owed: list[Callable[[], None]] = []

    @property
    def busy(self) -> bool:
        """Whether the owner is running an item right now."""
        return self.current is not None

    def start(self, item: _Work) -> None:
        """Give the item to the owner thread and announce the pickup."""
        self.thread = threading.get_ident()
        self.current = item
        item.picked.set()

    def finish(
        self, item: _Work, value: Any, error: BaseException | None
    ) -> list[Callable[[], None]]:
        """Record the outcome, free the owner, and hand back what it owes."""
        if not item.cancelled:
            item.value = value
            item.error = error
            item.done.set()
        self.thread = None
        self.current = None
        owed, self.owed = self.owed, []
        return owed

    def owe(self, fn: Callable[[], None]) -> bool:
        """Keep a cleanup for when the running item returns, if one is running."""
        if not self.busy:
            return False
        self.owed.append(fn)
        return True


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
        self._cleanups = _Cleanups()
        self._turn = _Turn()
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
            return self._turn.busy

    def close(self) -> None:
        """Withdraw queued work and fail active callers without undoing effects."""
        with self._lock:
            self._closed = True
            if self._retry_timer is not None:
                self._retry_timer.cancel()
                self._retry_timer = None
            current = self._turn.current
            if current is not None:
                current.cancelled = True
                current.error = QgisSdkHostReloadedError(
                    "The QGIS host closed; an already-started action may have had effects"
                )
                current.done.set()
            self._cleanups.clear()  # The owner disposes every session during close.
            _refuse_all(self._items, QgisSdkHostReloadedError("The QGIS host closed"))

    def defer_until_idle(self, fn: Callable[[], None]) -> bool:
        """Defer owner cleanup if an already-started callback is still running."""
        with self._lock:
            return self._turn.owe(fn)

    def defer(self, key: str, fn: Callable[[], Any]) -> bool:
        """Retain one cleanup per session until the owner can execute it."""
        with self._lock:
            if self._closed:
                return False
            self._cleanups.add(key, fn)
            schedule = not self._turn.busy and not self._scheduled
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
            if self._turn.thread == threading.get_ident():
                # Calling back into the owner from work it is already running
                # would wait for a turn that cannot arrive; refuse at once
                # instead of blocking the owner thread for the whole deadline.
                raise QgisSdkHostBusyError(
                    "The QGIS host is already running work on this thread"
                )
            if len(self._items) >= 64:
                raise QgisSdkHostBusyError("The QGIS host request queue is full")
            self._items.append(work)
            schedule = not self._turn.busy and not self._scheduled
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
        """Settle a request whose pickup deadline has just expired."""
        with self._lock:
            return _settle_late(self._items, work, self._deadline)

    def _schedule(self) -> None:
        try:
            self._post(self._drain)
        except Exception:  # noqa: BLE001 - fail queued callers if the host rejects a post
            with self._lock:
                self._scheduled = False
                _refuse_all(
                    self._items,
                    QgisSdkHostBusyError("The QGIS host rejected scheduling"),
                )
                if (
                    bool(self._cleanups)
                    and not self._closed
                    and self._retry_timer is None
                ):
                    timer = threading.Timer(0.25, self._retry_cleanups)
                    timer.daemon = True
                    self._retry_timer = timer
                    timer.start()

    def _retry_cleanups(self) -> None:
        with self._lock:
            self._retry_timer = None
            schedule = bool(self._cleanups) and not (
                self._closed or self._turn.busy or self._scheduled
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
        item = self._take()
        if item is None:
            return
        value = None
        error = None
        try:
            value = item.fn()
        except BaseException as caught:  # noqa: BLE001 - always release the waiting caller
            error = caught
        with self._lock:
            owed = self._turn.finish(item, value, error)
        for callback in owed:
            callback()
        self._next_turn()

    def _take(self) -> _Work | None:
        """Claim the next item - a cleanup before a request - for the owner."""
        with self._lock:
            self._scheduled = False
            if self._turn.busy:
                return None
            while self._items and self._items[0].cancelled:
                self._items.popleft()
            item = self._cleanups.take()
            if item is None and self._items:
                item = self._items.popleft()
            if item is None:
                return None
            self._turn.start(item)
            return item

    def _next_turn(self) -> None:
        """Post the next turn unless one is already on its way."""
        with self._lock:
            if self._scheduled or not (self._items or bool(self._cleanups)):
                return
            self._scheduled = True
        self._schedule()

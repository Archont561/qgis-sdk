"""The sessions one listener keeps open, and the one way each of them is disposed."""

from __future__ import annotations

import json
import secrets
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from queue import Full, Queue
from typing import TYPE_CHECKING, Any

from qgis_sdk.bridge.transport import ChannelTransport

from ._options import MAX_SESSIONS

if TYPE_CHECKING:  # pragma: no cover - typing only; the dispatcher imports at runtime
    from qgis_sdk.bridge import Dispatcher
    from qgis_sdk.bridge.resources import ReleaseLedger

    from ._queue import GuiQueue


class FrameBuffer:
    """A session's outgoing frames, bounded by count and encoded byte size."""

    _MAX_FRAME_BYTES = 512 * 1024
    _MAX_TOTAL_BYTES = 2 * 1024 * 1024

    def __init__(self) -> None:
        self._queue: Queue[tuple[str, int]] = Queue(maxsize=256)
        self._bytes = 0
        self._lock = threading.Lock()

    def put_nowait(self, text: str) -> None:
        size = len(text.encode("utf-8"))
        with self._lock:
            if (
                size > self._MAX_FRAME_BYTES
                or self._bytes + size > self._MAX_TOTAL_BYTES
            ):
                raise Full
            self._queue.put_nowait((text, size))
            self._bytes += size

    def get(self, timeout: float) -> str:
        text, size = self._queue.get(timeout=timeout)
        with self._lock:
            self._bytes -= size
        return text

    def empty(self) -> bool:
        return self._queue.empty()


@dataclass
class _Session:
    """One page: the transport that answers into it and the frames it has not read."""

    channel: ChannelTransport
    closed: bool = False
    replies: list[str] = field(default_factory=list)
    frames: FrameBuffer = field(default_factory=FrameBuffer)
    on_overflow: Callable[[], None] = lambda: None

    def send(self, text: str) -> None:
        value = json.loads(text)
        if "call_id" in value:
            self.replies.append(text)
        elif not self.closed:
            try:
                self.frames.put_nowait(text)
            except Full:
                # The caller must reconnect rather than receive a silently
                # truncated stream. Cleanup is deferred to the owner queue.
                self.closed = True
                self.on_overflow()


class Sessions:
    """Every session this listener has open, keyed by the id it bound the view to.

    One object owns the book because every path through it is the same three
    steps - the binding, the transport that answers into it, and the ledger
    entries a dispose has to release - and a session that outlives its page is
    the leak this class exists to prevent (decision-20).
    """

    def __init__(
        self,
        dispatcher: Dispatcher,
        ledger: ReleaseLedger,
        *,
        queue: GuiQueue,
        on_error: Callable[[Exception], None],
    ) -> None:
        self._dispatcher = dispatcher
        self._ledger = ledger
        self._queue = queue
        self._on_error = on_error
        self._lock = threading.Lock()
        self._items: dict[str, _Session] = {}
        self.failed = False

    def open(self, *, defer_on_overflow: bool = False) -> tuple[str, _Session]:
        """Mint one session: a fresh binding, a transport that answers into it, a slot."""
        session_id = secrets.token_urlsafe(24)
        binding = self._dispatcher.bind(view_id=session_id, origin="http://loopback")
        channel = ChannelTransport(self._dispatcher, binding, lambda _: None)
        session = _Session(channel)
        if defer_on_overflow:
            session.on_overflow = lambda: self.dispose_later(session_id)
        channel.send = session.send
        with self._lock:
            self._items[session_id] = session
        return session_id, session

    def capacity_error(self) -> dict[str, Any] | None:
        """Refuse a new session once the per-plugin budget is spent."""
        with self._lock:
            if len(self._items) < MAX_SESSIONS:
                return None
        return {"error": {"code": "capacity", "message": "Too many sessions"}}

    def dispose(self, session_id: str) -> bool:
        """Close one session and release every handle it took; report every failure."""
        with self._lock:
            session = self._items.pop(session_id, None)
        if session is None:
            return False
        session.closed = True
        failures: list[Exception] = []
        try:
            session.channel.dispose()
        except Exception as error:  # noqa: BLE001 - release siblings even if a source fails
            failures.append(error)
        for handle in self._ledger.handles(session_id):
            try:
                self._ledger.release(session_id, handle)
            except Exception as error:  # noqa: BLE001 - release remaining handles
                failures.append(error)
        if failures:
            self.failed = True
            raise ExceptionGroup("HTTP session cleanup failed", failures)
        return True

    def dispose_later(self, session_id: str) -> None:
        """Ask the owner thread to dispose one session, reporting what it fails with."""

        def dispose() -> None:
            try:
                self.dispose(session_id)
            except Exception as error:  # noqa: BLE001 - report deferred failures
                self._on_error(error)

        self._queue.defer(session_id, dispose)

    def dispose_all(self) -> list[Exception]:
        """Dispose every session still open, collecting what each one failed with."""
        with self._lock:
            session_ids = tuple(self._items)
        failures: list[Exception] = []
        for session_id in session_ids:
            try:
                self.dispose(session_id)
            except Exception as error:  # noqa: BLE001 - continue disposing siblings
                failures.append(error)
        return failures

    def mark_closed(self) -> None:
        """Tell every open session to stop emitting; nothing reads it after a close."""
        with self._lock:
            for session in self._items.values():
                session.closed = True

    def stop_waking(self) -> None:
        """Stop the transports from waking the owner thread of a listener that is gone."""
        with self._lock:
            for session in self._items.values():
                session.channel.stop_waking()

"""Explicitly owned loopback HTTP listener; no third-party runtime dependency."""

from __future__ import annotations

import logging
import os
import secrets
import threading
import weakref
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self, TypedDict, Unpack

from qgis_sdk.bridge import Dispatcher
from qgis_sdk.bridge.resources import ReleaseLedger

from ._endpoint import Endpoint
from ._errors import QgisSdkHttpError, error_status
from ._listener import Listener
from ._options import DEFAULT_CLOSE_GRACE, capacity, positive, timing
from ._queue import GuiQueue
from ._sessions import FrameBuffer, Sessions

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ._options import _Capacity, _Timing

__all__ = ["FrameBuffer", "PluginHttpServer", "QgisSdkHttpError"]

_RUNTIME_LOCK = threading.Lock()
_ACTIVE_RUNTIMES: weakref.WeakSet[Any] = weakref.WeakSet()


class _Owner:
    """The thread that owns the runtime, and the cleanup a close has to finish there."""

    def __init__(
        self,
        post: Callable[[Callable[[], None]], None],
        on_cleanup_error: Callable[[Exception], None] | None,
    ) -> None:
        self.thread = threading.get_ident()
        self.lock = threading.RLock()
        self.post = post
        self.error: Exception | None = None
        self.reserved = False
        self.requested = False
        self.done = threading.Event()
        self._on_cleanup_error = on_cleanup_error

    @property
    def here(self) -> bool:
        """Whether the calling thread is the one the runtime is owned by."""
        return threading.get_ident() == self.thread

    def schedule(self, fn: Callable[[], None]) -> None:
        """Run ``fn`` on the owner thread now, or post it there."""
        if self.here:
            fn()
        else:
            self.post(fn)

    def report(self, error: Exception) -> None:
        """Record a deferred cleanup failure and hand it to the observer, if any."""
        self.error = error
        if self._on_cleanup_error is None:
            return
        try:
            self._on_cleanup_error(error)
        except Exception:
            logging.getLogger(__name__).exception("HTTP cleanup error observer failed")


def _sessions_of(server: PluginHttpServer) -> Sessions:
    """Build the session book over the dispatcher and ledger this server mints."""
    ledger = ReleaseLedger()
    dispatcher = Dispatcher.from_runtime(
        server._runtime,
        authorize=lambda binding, operation: operation in server._allowed,
        ledger=ledger,
    )
    return Sessions(
        dispatcher, ledger, queue=server._queue, on_error=server._owner.report
    )


def _endpoint_of(
    server: PluginHttpServer, limits: _Timing, budgets: _Capacity
) -> Endpoint:
    """Assemble the frozen view one request handler works from."""
    return Endpoint(
        runtime=server._runtime,
        allowed=server._allowed,
        queue=server._queue,
        sessions=server._sessions,
        token=secrets.token_urlsafe(32),
        read_timeout=limits.request_read_timeout,
        write_timeout=limits.stream_write_timeout,
        grace=limits.close_grace,
        event_slots=threading.BoundedSemaphore(budgets.max_event_streams),
        closed=server._closed,
    )


def _refuse_unusable(
    host: str, post: Callable[[Callable[[], None]], None], cleanup_error: Any
) -> None:
    """Refuse what cannot work before anything is created: a bind address, a callback."""
    if host != "127.0.0.1":
        raise QgisSdkHttpError("HTTP listeners may bind only to 127.0.0.1")
    if not callable(post):
        raise QgisSdkHttpError("a GUI-thread post callback is required")
    if cleanup_error is not None and not callable(cleanup_error):
        raise QgisSdkHttpError("on_cleanup_error must be callable")


def _refuse_unknown(actions: Sequence[str], runtime: Any) -> None:
    """Refuse an action the runtime does not declare, before a listener could offer it."""
    unknown = set(actions) - (set(runtime.actions) | set(runtime.streams))
    if unknown:
        raise QgisSdkHttpError(f"unknown HTTP actions: {', '.join(sorted(unknown))}")


class PluginHttpServer:
    """Own one explicitly opted-in listener for a started plugin runtime.

    Construct on the runtime's owning GUI thread. ``post`` must enqueue its
    callable on that thread, not execute it on the caller. No operations are
    exposed unless named in ``actions``. Call :meth:`close` before unloading
    the runtime; off-owner cleanup is posted and may finish after close returns.
    """

    def __init__(self, runtime: Any, **options: Unpack[_InitOptions1]) -> None:
        values = _InitValues1(**options)
        _refuse_unusable(values.host, values.post, values.on_cleanup_error)
        limits = timing(
            values.request_read_timeout, values.stream_write_timeout, values.close_grace
        )
        budgets = capacity(values.max_connections, values.max_event_streams)
        _refuse_unknown(values.actions, runtime)
        self._runtime = runtime
        self._owner = _Owner(values.post, values.on_cleanup_error)
        self._allowed = frozenset(values.actions)
        self._closed = threading.Event()
        self._queue = GuiQueue(values.post, positive("deadline", values.deadline))
        self._sessions = _sessions_of(self)
        self._endpoint = _endpoint_of(self, limits, budgets)
        self._listener = Listener(
            self._endpoint, values.token_file, values.port, budgets
        )
        runtime.instance.ctx.scope.on_close(self.close)

    @property
    def port(self) -> int:
        """The assigned loopback port; valid while the server is running."""
        if self._closed.is_set():
            raise QgisSdkHttpError("the HTTP server is not running")
        return self._listener.port

    @property
    def pending_requests(self) -> int:
        """Requests waiting for their turn on the QGIS owner thread."""
        return self._queue.pending

    @property
    def busy(self) -> bool:
        """Whether the owner thread is running a request right now."""
        return self._queue.busy

    def __enter__(self) -> Self:
        self.start()
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def start(self) -> None:
        """Create a private token file and start the listener once.

        Every refusal lands before a socket exists: a closed server, a second
        start, a platform without private file permissions, or a runtime that
        already has an endpoint. A failure after the reservation releases it
        again, so the same server can be started once the cause is fixed.
        """
        with self._owner.lock:
            if self._closed.is_set():
                raise QgisSdkHttpError("HTTP server is closed")
            if self._listener.started:
                raise QgisSdkHttpError("HTTP server is already started")
            if os.name != "posix":
                raise QgisSdkHttpError(
                    "private token permissions require POSIX; "
                    "Windows ACL handling is not implemented"
                )
            with _RUNTIME_LOCK:
                if self._runtime in _ACTIVE_RUNTIMES:
                    raise QgisSdkHttpError("this runtime already has an HTTP endpoint")
                _ACTIVE_RUNTIMES.add(self._runtime)
                self._owner.reserved = True
            try:
                self._listener.start()
            except BaseException:
                self.close()
                raise

    def close(self) -> None:
        """Stop the listener and remove its token; off-owner cleanup is posted."""
        with self._owner.lock:
            self._close()

    def wait_cleanup(self, timeout: float | None = None) -> bool:
        """Wait for cleanup to finish, including error reporting, off the owner.

        Completion does not imply success: failed cleanup is reported through
        ``on_cleanup_error`` and keeps the runtime quarantined.
        """
        if self._owner.here and not self._owner.done.is_set():
            raise QgisSdkHttpError("the owner thread must not wait for queued cleanup")
        return self._owner.done.wait(timeout)

    @staticmethod
    def _error_status(payload: dict[str, Any]) -> int:
        """The status an error reply answers: 503 when retrying could help, else 400."""
        return error_status(payload)

    def _close(self) -> None:
        """Withdraw what the listener owes, then finish the cleanup it cannot skip."""
        failures: list[Exception] = []
        if not self._closed.is_set():
            self._closed.set()
            self._sessions.mark_closed()
            self._queue.close()
            failures += self._stop_waking()
        failures += self._listener.stop(self._endpoint.grace)
        failures += self._finish_later()
        if failures:
            raise ExceptionGroup("HTTP listener shutdown failed", failures)

    def _stop_waking(self) -> list[Exception]:
        """Stop sessions waking an owner that has closed, keeping a scheduling failure."""
        try:
            self._owner.schedule(self._sessions.stop_waking)
        except Exception as error:  # noqa: BLE001 - keep the reservation if scheduling fails
            return [error]
        return []

    def _finish_later(self) -> list[Exception]:
        """Schedule the last cleanup once the socket is gone, and report why it could not."""
        if self._listener.alive or self._owner.requested:
            return []
        self._owner.requested = True
        if self._queue.defer_until_idle(self._finish_close_async):
            return []
        try:
            if self._owner.here:
                try:
                    self._finish_close()
                finally:
                    self._owner.done.set()
            else:
                self._owner.post(self._finish_close_async)
        except Exception as error:  # noqa: BLE001 - allow a retry off the owner
            if not self._owner.here:
                self._owner.requested = False
            return [error]
        return []

    def _finish_close_async(self) -> None:
        """Finish the cleanup off the owner thread, reporting what it failed with."""
        try:
            self._finish_close()
        except Exception as error:  # noqa: BLE001 - reported after the close caller returned
            self._owner.report(error)
        finally:
            self._owner.done.set()

    def _finish_close(self) -> None:
        """Dispose every session, then let the runtime have another endpoint."""
        failures = self._sessions.dispose_all()
        # A source that raised during disposal may still own native resources:
        # keep this runtime quarantined rather than permit a second listener.
        with _RUNTIME_LOCK:
            if self._owner.reserved and not self._sessions.failed:
                _ACTIVE_RUNTIMES.discard(self._runtime)
                self._owner.reserved = False
        if failures:
            raise ExceptionGroup("HTTP listener cleanup failed", failures)


class _InitOptions1(TypedDict, total=False):
    post: Callable[[Callable[[], None]], None]
    token_file: Path
    actions: Sequence[str]
    host: str
    port: int
    deadline: float
    max_connections: int
    max_event_streams: int | None
    request_read_timeout: float
    stream_write_timeout: float
    close_grace: float
    on_cleanup_error: Callable[[Exception], None] | None


@dataclass(frozen=True, slots=True)
class _InitValues1:
    post: Callable[[Callable[[], None]], None]
    token_file: Path
    actions: Sequence[str] = ()
    host: str = "127.0.0.1"
    port: int = 0
    deadline: float = 10
    max_connections: int = 128
    max_event_streams: int | None = None
    request_read_timeout: float = 5
    stream_write_timeout: float = 10
    close_grace: float = DEFAULT_CLOSE_GRACE
    on_cleanup_error: Callable[[Exception], None] | None = None

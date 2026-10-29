"""Explicitly owned loopback HTTP listener; no third-party runtime dependency."""

from __future__ import annotations

import hmac
import json
import logging
import math
import os
import secrets
import socket
import threading
import weakref
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from queue import Empty, Full, Queue
from typing import Any, Self

from qgis_sdk.bridge import Dispatcher
from qgis_sdk.bridge.resources import ReleaseLedger
from qgis_sdk.bridge.transport import ChannelTransport
from qgis_sdk.models.errors import QgisSdkError

from ._queue import GuiQueue, QgisSdkHostBusyError, QgisSdkHostReloadedError

_RUNTIME_LOCK = threading.Lock()
_ACTIVE_RUNTIMES: weakref.WeakSet[Any] = weakref.WeakSet()


class _FrameBuffer:
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
    channel: ChannelTransport
    closed: bool = False
    reader: bool = False
    replies: list[str] = field(default_factory=list)
    frames: _FrameBuffer = field(default_factory=_FrameBuffer)
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


class _BoundedHTTPServer(ThreadingHTTPServer):
    """Limit concurrently accepted HTTP handlers without blocking the accept loop."""

    def __init__(self, address: tuple[str, int], handler: type, limit: int) -> None:
        self._slots = threading.BoundedSemaphore(limit)
        self._connections: set[socket.socket] = set()
        self._connections_lock = threading.Lock()
        self._closing = False
        super().__init__(address, handler)

    def process_request(self, request: Any, client_address: Any) -> None:
        if not self._slots.acquire(blocking=False):
            try:
                request.setblocking(False)
                request.send(
                    b"HTTP/1.0 503 Service Unavailable\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
                )
            except OSError:
                pass
            finally:
                self.shutdown_request(request)
            return
        with self._connections_lock:
            if self._closing:
                self._slots.release()
                self.shutdown_request(request)
                return
            self._connections.add(request)
        try:
            super().process_request(request, client_address)
        except BaseException:
            with self._connections_lock:
                self._connections.discard(request)
            self._slots.release()
            raise

    def process_request_thread(self, request: Any, client_address: Any) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            with self._connections_lock:
                self._connections.discard(request)
            self._slots.release()

    def server_close(self) -> None:
        with self._connections_lock:
            self._closing = True
            connections = tuple(self._connections)
        for connection in connections:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        super().server_close()


class QgisSdkHttpError(QgisSdkError):
    """An HTTP listener could not be started safely."""

    code = "http_error"


class PluginHttpServer:
    """Own one explicitly opted-in listener for a started plugin runtime.

    Construct on the runtime's owning GUI thread. ``post`` must enqueue its
    callable on that thread, not execute it on the caller. No operations are
    exposed unless named in ``actions``. Call :meth:`close` before unloading
    the runtime; off-owner cleanup is posted and may finish after close returns.
    """

    def __init__(
        self,
        runtime: Any,
        *,
        post: Callable[[Callable[[], None]], None],
        token_file: Path,
        actions: Sequence[str] = (),
        host: str = "127.0.0.1",
        port: int = 0,
        deadline: float = 10,
        max_connections: int = 128,
        max_event_streams: int | None = None,
        request_read_timeout: float = 5,
        stream_write_timeout: float = 10,
        on_cleanup_error: Callable[[Exception], None] | None = None,
    ) -> None:
        if host != "127.0.0.1":
            raise QgisSdkHttpError("HTTP listeners may bind only to 127.0.0.1")
        if not callable(post):
            raise QgisSdkHttpError("a GUI-thread post callback is required")
        if on_cleanup_error is not None and not callable(on_cleanup_error):
            raise QgisSdkHttpError("on_cleanup_error must be callable")
        if (
            isinstance(deadline, bool)
            or not isinstance(deadline, (int, float))
            or not math.isfinite(deadline)
            or deadline <= 0
        ):
            raise QgisSdkHttpError("deadline must be a positive finite number")
        if (
            isinstance(max_connections, bool)
            or not isinstance(max_connections, int)
            or max_connections < 1
        ):
            raise QgisSdkHttpError("max_connections must be a positive integer")
        if max_event_streams is None:
            max_event_streams = min(16, max_connections - 1)
        if (
            isinstance(max_event_streams, bool)
            or not isinstance(max_event_streams, int)
            or not 0 <= max_event_streams < max_connections
        ):
            raise QgisSdkHttpError(
                "max_event_streams must leave at least one connection for calls"
            )
        if (
            isinstance(request_read_timeout, bool)
            or not isinstance(request_read_timeout, (int, float))
            or not math.isfinite(request_read_timeout)
            or request_read_timeout <= 0
        ):
            raise QgisSdkHttpError("request_read_timeout must be positive and finite")
        if (
            isinstance(stream_write_timeout, bool)
            or not isinstance(stream_write_timeout, (int, float))
            or not math.isfinite(stream_write_timeout)
            or stream_write_timeout <= 0
        ):
            raise QgisSdkHttpError("stream_write_timeout must be positive and finite")
        unknown = set(actions) - (set(runtime.actions) | set(runtime.streams))
        if unknown:
            raise QgisSdkHttpError(
                f"unknown HTTP actions: {', '.join(sorted(unknown))}"
            )
        self._runtime = runtime
        # The listener must be constructed on the runtime's owning thread.
        self._owner_thread = threading.get_ident()
        self._post = post
        self._lifecycle_lock = threading.RLock()
        self._registered = False
        self._closed = False
        self._close_error: Exception | None = None
        self._on_cleanup_error = on_cleanup_error
        self._cleanup_requested = False
        self._cleanup_failed = False
        self._cleanup_done = threading.Event()
        self._allowed = frozenset(actions)
        self._queue = GuiQueue(post, float(deadline))
        self._ledger = ReleaseLedger()
        self._dispatcher = Dispatcher.from_runtime(
            runtime,
            authorize=lambda binding, operation: operation in self._allowed,
            ledger=self._ledger,
        )
        self._path = Path(token_file)
        self._token = secrets.token_urlsafe(32)
        self._sessions: dict[str, _Session] = {}
        self._lock = threading.Lock()
        # Dispatch is serialized by the queue: a handler that spins a nested
        # event loop cannot let a second call or subscription dispatch inside
        # it, mirroring ChannelTransport's receiving guard.
        self._http: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._identity: tuple[int, int] | None = None
        self._port = port
        self._max_connections = max_connections
        self._event_slots = threading.BoundedSemaphore(max_event_streams)
        self._request_read_timeout = float(request_read_timeout)
        self._stream_write_timeout = float(stream_write_timeout)
        # Closing the runtime's scope revokes the endpoint as a safety net.
        # The host must still coordinate asynchronous cleanup before unload.
        runtime.instance.ctx.scope.on_close(self.close)

    @property
    def port(self) -> int:
        """The assigned loopback port; valid while the server is running."""
        if self._closed or self._http is None:
            raise QgisSdkHttpError("the HTTP server is not running")
        return self._http.server_port

    def __enter__(self) -> Self:
        self.start()
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def start(self) -> None:
        """Create a private token file and start the listener once."""
        with self._lifecycle_lock:
            self._start()

    def _start(self) -> None:
        if self._closed:
            raise QgisSdkHttpError("HTTP server is closed")
        if self._http is not None or self._identity is not None:
            raise QgisSdkHttpError("HTTP server is already started")
        if os.name != "posix":
            raise QgisSdkHttpError(
                "private token permissions require POSIX; Windows ACL handling is not implemented"
            )
        with _RUNTIME_LOCK:
            if self._runtime in _ACTIVE_RUNTIMES:
                raise QgisSdkHttpError("this runtime already has an HTTP endpoint")
            _ACTIVE_RUNTIMES.add(self._runtime)
            self._registered = True
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            fd = os.open(self._path, flags, 0o600)
            with os.fdopen(fd, "w", encoding="ascii") as handle:
                info = os.fstat(handle.fileno())
                self._identity = (info.st_dev, info.st_ino)
                os.fchmod(handle.fileno(), 0o600)
                handle.write(self._token + "\n")
            owner = self

            class Handler(BaseHTTPRequestHandler):
                def setup(self) -> None:
                    super().setup()
                    self._read_lock = threading.Lock()
                    self._reading = True
                    self._timed_out = False
                    self._read_timer = threading.Timer(
                        owner._request_read_timeout, self._expire_read
                    )
                    self._read_timer.daemon = True
                    self._read_timer.start()

                def _expire_read(self) -> None:
                    with self._read_lock:
                        if not self._reading:
                            return
                        self._reading = False
                        self._timed_out = True
                        try:
                            self.connection.shutdown(socket.SHUT_RDWR)
                        except OSError:
                            pass

                def _finish_reading(self) -> bool:
                    with self._read_lock:
                        was_reading = self._reading
                        self._reading = False
                        self._read_timer.cancel()
                        if was_reading and not self._timed_out:
                            # Bound ordinary response writes as well as SSE writes.
                            self.connection.settimeout(owner._stream_write_timeout)
                        return not self._timed_out

                def handle(self) -> None:
                    try:
                        super().handle()
                    except (ConnectionError, TimeoutError):
                        pass  # A client may disconnect or exceed the read deadline.

                def finish(self) -> None:
                    self._finish_reading()
                    super().finish()

                def log_message(self, format: str, *args: object) -> None:
                    pass

                def do_POST(self) -> None:
                    if not self._authorized():
                        return
                    if self.path.startswith("/actions/"):
                        self._rest_action()
                        return
                    if self.path.startswith("/streams/"):
                        self._rest_stream()
                        return
                    self.send_error(404)

                def _rest_action(self) -> None:
                    parts = self.path.split("/")
                    action = parts[2] if len(parts) == 3 else ""
                    if (
                        action not in owner._runtime.actions
                        or action not in owner._allowed
                    ):
                        self.send_error(404)
                        return
                    lengths = self.headers.get_all("Content-Length") or []
                    if (
                        len(lengths) != 1
                        or not lengths[0].isdigit()
                        or self.headers.get("Transfer-Encoding")
                    ):
                        self.send_error(400)
                        return
                    size = int(lengths[0])
                    if size > 1024 * 1024:
                        self.send_error(413)
                        return
                    raw = self.rfile.read(size)
                    if not self._finish_reading():
                        return
                    try:
                        payload = json.loads(raw)
                    except (ValueError, UnicodeDecodeError):
                        self.send_error(400)
                        return
                    if len(raw) != size or not isinstance(payload, dict):
                        self.send_error(400)
                        return

                    def call() -> dict[str, Any]:
                        session_id = secrets.token_urlsafe(24)
                        with owner._lock:
                            if len(owner._sessions) >= 64:
                                return {
                                    "error": {
                                        "code": "capacity",
                                        "message": "Too many sessions",
                                    }
                                }
                        binding = owner._dispatcher.bind(
                            view_id=session_id, origin="http://loopback"
                        )
                        channel = ChannelTransport(
                            owner._dispatcher, binding, lambda _: None
                        )
                        session = _Session(channel)
                        channel.send = session.send
                        with owner._lock:
                            owner._sessions[session_id] = session
                        try:
                            text = json.dumps(
                                {
                                    "protocol": 1,
                                    "call_id": secrets.token_hex(8),
                                    "operation": action,
                                    "payload": payload,
                                }
                            )
                            if not channel.receive(text) or not session.replies:
                                return {
                                    "error": {
                                        "code": "invalid_request",
                                        "message": "Invalid request",
                                    }
                                }
                            reply = json.loads(session.replies.pop(0))
                            return (
                                {"value": reply["value"]}
                                if reply.get("ok")
                                else {"error": reply["error"]}
                            )
                        finally:
                            owner._dispose_session(session_id)

                    try:
                        result = owner._queue.call(call)
                    except (QgisSdkHostBusyError, QgisSdkHostReloadedError) as error:
                        self._json(
                            503, {"error": {"code": error.code, "message": str(error)}}
                        )
                        return
                    self._json(
                        200 if "value" in result else owner._error_status(result),
                        result,
                    )

                def _rest_stream(self) -> None:
                    parts = self.path.split("/")
                    stream_id = parts[2] if len(parts) == 3 else ""
                    if (
                        stream_id not in owner._runtime.streams
                        or stream_id not in owner._allowed
                    ):
                        self.send_error(404)
                        return
                    lengths = self.headers.get_all("Content-Length") or []
                    if (
                        len(lengths) != 1
                        or not lengths[0].isdigit()
                        or self.headers.get("Transfer-Encoding")
                    ):
                        self.send_error(400)
                        return
                    size = int(lengths[0])
                    if size > 1024 * 1024:
                        self.send_error(413)
                        return
                    raw = self.rfile.read(size)
                    if not self._finish_reading():
                        return
                    try:
                        payload = json.loads(raw)
                    except (ValueError, UnicodeDecodeError):
                        self.send_error(400)
                        return
                    if len(raw) != size or not isinstance(payload, dict):
                        self.send_error(400)
                        return
                    if not owner._event_slots.acquire(blocking=False):
                        self.send_error(503)
                        return
                    session_id = secrets.token_urlsafe(24)
                    session = None
                    try:

                        def subscribe():
                            with owner._lock:
                                if len(owner._sessions) >= 64:
                                    return None, {
                                        "error": {
                                            "code": "capacity",
                                            "message": "Too many sessions",
                                        }
                                    }
                            binding = owner._dispatcher.bind(
                                view_id=session_id, origin="http://loopback"
                            )
                            channel = ChannelTransport(
                                owner._dispatcher, binding, lambda _: None
                            )
                            session = _Session(
                                channel,
                                on_overflow=lambda: owner._defer_dispose(session_id),
                            )
                            channel.send = session.send
                            with owner._lock:
                                owner._sessions[session_id] = session
                            text = json.dumps(
                                {
                                    "protocol": 1,
                                    "kind": "subscribe",
                                    "call_id": secrets.token_hex(8),
                                    "operation": stream_id,
                                    "payload": payload,
                                }
                            )
                            if not channel.receive(text) or not session.replies:
                                owner._dispose_session(session_id)
                                return None, {
                                    "error": {
                                        "code": "invalid_request",
                                        "message": "Invalid request",
                                    }
                                }
                            reply = json.loads(session.replies.pop(0))
                            if not reply.get("ok"):
                                owner._dispose_session(session_id)
                                return None, {"error": reply["error"]}
                            return session, None

                        try:
                            session, error = owner._queue.call(subscribe)
                        except (
                            QgisSdkHostBusyError,
                            QgisSdkHostReloadedError,
                        ) as error:
                            self._json(
                                503,
                                {"error": {"code": error.code, "message": str(error)}},
                            )
                            return
                        if error is not None:
                            self._json(owner._error_status(error), error)
                            return
                        self.connection.settimeout(owner._stream_write_timeout)
                        self.send_response(200)
                        self.send_header("Content-Type", "text/event-stream")
                        self.send_header("Cache-Control", "no-store")
                        self.send_header("Connection", "close")
                        self.end_headers()
                        while not session.closed:
                            if session.frames.empty():
                                try:
                                    owner._queue.call(
                                        lambda: session.channel.flush(limit=1)
                                    )
                                except (QgisSdkHostBusyError, QgisSdkHostReloadedError):
                                    break
                            try:
                                frame = session.frames.get(timeout=0.5)
                                outgoing = b"data: " + frame.encode("utf-8") + b"\n\n"
                                terminal = "terminal" in json.loads(frame)
                            except Empty:
                                outgoing = b": keepalive\n\n"
                                terminal = False
                            self.wfile.write(outgoing)
                            self.wfile.flush()
                            if terminal:
                                break
                    except (ConnectionError, OSError):
                        pass
                    finally:
                        owner._event_slots.release()
                        if session is not None:
                            session.closed = True
                            owner._defer_dispose(session_id)

                def do_GET(self) -> None:
                    if not self._authorized():
                        return
                    if not self._finish_reading():
                        return
                    if self.path == "/plugin":
                        description = owner._runtime.description.to_dict()
                        description["actions"] = [
                            a
                            for a in description["actions"]
                            if a["id"] in owner._allowed
                        ]
                        description["streams"] = [
                            s
                            for s in description["streams"]
                            if s["id"] in owner._allowed
                        ]
                        self._json(200, description)
                        return
                    self.send_error(404)

                def _authorized(self) -> bool:
                    if owner._closed:
                        self._json(
                            503,
                            {
                                "error": {
                                    "code": "host_reloaded",
                                    "message": "Host closed",
                                }
                            },
                        )
                        return False
                    hosts = self.headers.get_all("Host") or []
                    if hosts != [f"127.0.0.1:{self.server.server_port}"]:
                        self.send_error(403)
                        return False
                    if self.headers.get_all("Origin"):
                        self.send_error(403)
                        return False
                    headers = self.headers.get_all("Authorization") or []
                    expected = ("Bearer " + owner._token).encode("ascii")
                    if len(headers) != 1 or not hmac.compare_digest(
                        headers[0].encode("latin-1"), expected
                    ):
                        self.send_error(401)
                        return False
                    return True

                def _json(self, status: int, data: dict[str, Any]) -> None:
                    payload = json.dumps(data, separators=(",", ":")).encode("utf-8")
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(payload)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(payload)

            self._http = _BoundedHTTPServer(
                ("127.0.0.1", self._port), Handler, self._max_connections
            )
            self._thread = threading.Thread(
                target=self._http.serve_forever, daemon=True, name="qgis-sdk-http"
            )
            self._thread.start()
        except BaseException:
            self.close()
            raise

    @staticmethod
    def _error_status(payload: dict[str, Any]) -> int:
        code = payload.get("error", {}).get("code")
        return 503 if code == "host_busy" else 400

    def _report_cleanup_error(self, error: Exception) -> None:
        self._close_error = error
        if self._on_cleanup_error is not None:
            try:
                self._on_cleanup_error(error)
            except Exception:
                logging.getLogger(__name__).exception(
                    "HTTP cleanup error observer failed"
                )

    def _defer_dispose(self, session_id: str) -> None:
        def dispose() -> None:
            try:
                self._dispose_session(session_id)
            except Exception as error:  # noqa: BLE001 - report deferred owner failures
                self._report_cleanup_error(error)

        self._queue.defer(session_id, dispose)

    def _dispose_session(self, session_id: str) -> bool:
        with self._lock:
            session = self._sessions.pop(session_id, None)
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
            self._cleanup_failed = True
            raise ExceptionGroup("HTTP session cleanup failed", failures)
        return True

    def close(self) -> None:
        """Stop the listener and remove its token; off-owner cleanup is posted."""
        with self._lifecycle_lock:
            self._close()

    def wait_cleanup(self, timeout: float | None = None) -> bool:
        """Wait for cleanup to finish, including error reporting, off the owner.

        Completion does not imply success: failed cleanup is reported through
        ``on_cleanup_error`` and keeps the runtime quarantined.
        """
        if (
            threading.get_ident() == self._owner_thread
            and not self._cleanup_done.is_set()
        ):
            raise QgisSdkHttpError("the owner thread must not wait for queued cleanup")
        return self._cleanup_done.wait(timeout)

    def _close(self) -> None:
        failures: list[Exception] = []
        on_owner = threading.get_ident() == self._owner_thread
        if not self._closed:
            self._closed = True
            with self._lock:
                for session in self._sessions.values():
                    session.closed = True
            self._queue.close()
            try:
                if on_owner:
                    self._stop_waking()
                else:
                    self._post(self._stop_waking)
            except Exception as error:  # noqa: BLE001 - keep reservation if scheduling fails
                failures.append(error)

        server = self._http
        if server is not None:
            try:
                if self._thread is not None and self._thread.is_alive():
                    server.shutdown()
                server.server_close()
                if self._thread is not None and self._thread.is_alive():
                    self._thread.join(timeout=5)
                    if self._thread.is_alive():
                        raise QgisSdkHttpError("HTTP listener thread did not stop")
                self._http = None
                self._thread = None
            except Exception as error:  # noqa: BLE001 - retain ownership and retry
                failures.append(error)
        try:
            self._remove_token()
        except OSError as error:
            failures.append(error)
        # Never release the runtime while the listener might still be alive.
        if self._http is None and not self._cleanup_requested:
            self._cleanup_requested = True
            if not self._queue.defer_until_idle(self._finish_close_async):
                try:
                    if on_owner:
                        try:
                            self._finish_close()
                        finally:
                            self._cleanup_done.set()
                    else:
                        self._post(self._finish_close_async)
                except Exception as error:  # noqa: BLE001 - retain reservation and allow retry
                    if not on_owner:
                        self._cleanup_requested = False
                    failures.append(error)
        if failures:
            raise ExceptionGroup("HTTP listener shutdown failed", failures)

    def _stop_waking(self) -> None:
        with self._lock:
            for session in self._sessions.values():
                session.channel.stop_waking()

    def _remove_token(self) -> None:
        if self._identity is None:
            return
        try:
            info = self._path.lstat()
            if (info.st_dev, info.st_ino) == self._identity:
                self._path.unlink()
        except FileNotFoundError:
            pass
        self._identity = None

    def _finish_close_async(self) -> None:
        try:
            self._finish_close()
        except Exception as error:  # noqa: BLE001 - report failures after the close caller returned
            self._report_cleanup_error(error)
        finally:
            self._cleanup_done.set()

    def _finish_close(self) -> None:
        with self._lock:
            session_ids = tuple(self._sessions)
        failures: list[Exception] = []
        for session_id in session_ids:
            try:
                self._dispose_session(session_id)
            except Exception as error:  # noqa: BLE001 - continue disposing sibling sessions
                failures.append(error)
        # A source that raised during disposal may still own native resources.
        # Keep this runtime quarantined rather than permit a second listener.
        with _RUNTIME_LOCK:
            if self._registered and not self._cleanup_failed:
                _ACTIVE_RUNTIMES.discard(self._runtime)
                self._registered = False
        if failures:
            raise ExceptionGroup("HTTP listener cleanup failed", failures)

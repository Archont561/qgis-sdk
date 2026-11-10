"""The socket itself: a bounded accept loop, the token file that names it, and its stop."""

from __future__ import annotations

import os
import socket
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ._errors import QgisSdkHttpError
from ._handler import _RequestHandler

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ._endpoint import _Endpoint
    from ._options import _Capacity


class _BoundedHTTPServer(ThreadingHTTPServer):
    """Limit concurrently accepted HTTP handlers without blocking the accept loop."""

    def __init__(
        self, address: tuple[str, int], limit: int, endpoint: _Endpoint
    ) -> None:
        self.endpoint = endpoint
        self._slots = threading.BoundedSemaphore(limit)
        self._connections: set[socket.socket] = set()
        self._connections_lock = threading.Lock()
        self._idle = threading.Condition(self._connections_lock)
        self._handlers = 0
        self._closing = False
        super().__init__(address, _RequestHandler)

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
        with self._connections_lock:
            self._handlers += 1
        try:
            super().process_request_thread(request, client_address)
        finally:
            with self._connections_lock:
                self._connections.discard(request)
                self._handlers -= 1
                if self._handlers == 0:
                    self._idle.notify_all()
            self._slots.release()

    def wait_idle(self, timeout: float) -> bool:
        """Wait for the handlers already running to finish, or ``timeout``.

        A close withdraws queued work, which wakes the waiting caller so it can
        answer ``host_reloaded``. That reply still has to leave over a socket
        this object is about to shut down, so the caller of a close waits here
        first. It is a grace, not a guarantee: a handler still running when the
        time is up is cut off, exactly as before.
        """
        with self._connections_lock:
            return self._idle.wait_for(lambda: self._handlers == 0, timeout)

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


class _Listener:
    """One bound socket, its accept thread, and the private file that carries the token."""

    def __init__(
        self, endpoint: _Endpoint, token_file: Path, port: int, capacity: _Capacity
    ) -> None:
        self._endpoint = endpoint
        self._path = Path(token_file)
        self._port = port
        self._limit = capacity.max_connections
        self._http: _BoundedHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._identity: tuple[int, int] | None = None

    @property
    def started(self) -> bool:
        """Whether a token file exists or a socket is bound, i.e. start was attempted."""
        return self._http is not None or self._identity is not None

    @property
    def alive(self) -> bool:
        """Whether the socket is still bound, i.e. requests may still arrive."""
        return self._http is not None

    @property
    def port(self) -> int:
        """The assigned loopback port; valid while the listener is running."""
        if self._http is None:
            raise QgisSdkHttpError("the HTTP server is not running")
        return self._http.server_port

    def start(self) -> None:
        """Write the token file, bind the socket and start the accept thread."""
        self._write_token()
        self._http = _BoundedHTTPServer(
            ("127.0.0.1", self._port), self._limit, self._endpoint
        )
        self._thread = threading.Thread(
            target=self._http.serve_forever, daemon=True, name="qgis-sdk-http"
        )
        self._thread.start()

    def stop(self, grace: float) -> list[Exception]:
        """Wait out the reply grace, shut the socket down, and forget the token."""
        failures: list[Exception] = []
        if self._http is not None:
            try:
                self._http.wait_idle(grace)
                self._shutdown()
                self._http = None
                self._thread = None
            except Exception as error:  # noqa: BLE001 - retain ownership and retry
                failures.append(error)
        try:
            self.remove_token()
        except OSError as error:
            failures.append(error)
        return failures

    def remove_token(self) -> None:
        """Unlink the token file this listener wrote, and never another file at that path."""
        if self._identity is None:
            return
        try:
            info = self._path.lstat()
            if (info.st_dev, info.st_ino) == self._identity:
                self._path.unlink()
        except FileNotFoundError:
            pass
        self._identity = None

    def _write_token(self) -> None:
        """Create the token file exclusively, readable by its owner alone."""
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(self._path, flags, 0o600)
        with os.fdopen(fd, "w", encoding="ascii") as handle:
            info = os.fstat(handle.fileno())
            self._identity = (info.st_dev, info.st_ino)
            os.fchmod(handle.fileno(), 0o600)
            handle.write(self._endpoint.token + "\n")

    def _shutdown(self) -> None:
        """Stop accepting, close every connection, and wait for the accept thread."""
        server = self._http
        if server is None:
            return
        if self._thread is not None and self._thread.is_alive():
            server.shutdown()
        server.server_close()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=5)
            if self._thread.is_alive():
                raise QgisSdkHttpError("HTTP listener thread did not stop")

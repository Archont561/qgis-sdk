"""The HTTP request handler: framing, authorization, and the routes it answers."""

from __future__ import annotations

import hmac
import json
import socket
import threading
from http.server import BaseHTTPRequestHandler
from typing import TYPE_CHECKING, Any

from ._options import MAX_BODY_BYTES
from ._rest import call_action, open_stream

if TYPE_CHECKING:  # pragma: no cover - typing only; the listener constructs this class
    from ._endpoint import _Endpoint
    from ._listener import _BoundedHTTPServer


def _decoded(raw: bytes, size: int) -> dict[str, Any] | None:
    """Decode a body read under one framing, insisting it is one whole JSON object."""
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return None
    if len(raw) != size or not isinstance(payload, dict):
        return None
    return payload


class _RequestHandler(BaseHTTPRequestHandler):
    """One request, read under a deadline and answered as JSON or an event stream.

    The handler owns framing and authorization only: what an ``/actions/`` or
    ``/streams/`` request does once it is authorized is a route in ``_rest``,
    so one handler serves both without knowing either of them.
    """

    server: _BoundedHTTPServer

    @property
    def endpoint(self) -> _Endpoint:
        """What this request may reach: the listener's queue, sessions and limits."""
        return self.server.endpoint

    def setup(self) -> None:
        super().setup()
        self._read_lock = threading.Lock()
        self._reading = True
        self._timed_out = False
        self._read_timer = threading.Timer(
            self.endpoint.read_timeout, self._expire_read
        )
        self._read_timer.daemon = True
        self._read_timer.start()

    def _expire_read(self) -> None:
        """Cut the connection when a client has not finished sending its request."""
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
        """Stop the read deadline; ``False`` when it already fired."""
        with self._read_lock:
            was_reading = self._reading
            self._reading = False
            self._read_timer.cancel()
            if was_reading and not self._timed_out:
                # Bound ordinary response writes as well as SSE writes.
                self.connection.settimeout(self.endpoint.write_timeout)
            return not self._timed_out

    def _content_length(self) -> int | None:
        """The one unambiguous Content-Length framing, or the refusal already sent."""
        lengths = self.headers.get_all("Content-Length") or []
        if (
            len(lengths) != 1
            or not lengths[0].isdigit()
            or self.headers.get("Transfer-Encoding")
        ):
            self.send_error(400)
            return None
        size = int(lengths[0])
        if size > MAX_BODY_BYTES:
            self.send_error(413)
            return None
        return size

    def json_object_body(self) -> dict[str, Any] | None:
        """Read one bounded JSON-object body, or answer and return None."""
        size = self._content_length()
        if size is None:
            return None
        raw = self.rfile.read(size)
        if not self._finish_reading():
            return None
        payload = _decoded(raw, size)
        if payload is None:
            self.send_error(400)
        return payload

    def answer(self, status: int, data: dict[str, Any]) -> None:
        """Write one JSON reply, with the framing that makes it unambiguous."""
        payload = json.dumps(data, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

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
            call_action(self)
            return
        if self.path.startswith("/streams/"):
            open_stream(self)
            return
        self.send_error(404)

    def do_GET(self) -> None:
        if not self._authorized() or not self._finish_reading():
            return
        if self.path != "/plugin":
            self.send_error(404)
            return
        description = self.endpoint.runtime.description.to_dict()
        description["actions"] = [
            action
            for action in description["actions"]
            if action["id"] in self.endpoint.allowed
        ]
        description["streams"] = [
            stream
            for stream in description["streams"]
            if stream["id"] in self.endpoint.allowed
        ]
        self.answer(200, description)

    def _authorized(self) -> bool:
        """Whether this request may proceed: loopback host, no origin, the one token."""
        endpoint = self.endpoint
        if endpoint.closed.is_set():
            self.answer(
                503,
                {"error": {"code": "host_reloaded", "message": "Host closed"}},
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
        expected = ("Bearer " + endpoint.token).encode("ascii")
        if len(headers) != 1 or not hmac.compare_digest(
            headers[0].encode("latin-1"), expected
        ):
            self.send_error(401)
            return False
        return True

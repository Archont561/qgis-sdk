"""Helpers the native layers share: driving the event loop and loopback origins.

Nothing here imports Qt. ``pump`` and ``settle`` only call ``processEvents`` on
whatever application they are handed, so a native test spins the loop the way
a host would - from the GUI thread, between its own checks - without a timer or
a thread of its own. The loopback origin is a real HTTP server bound to
``127.0.0.1:0``: a browser or a network transport talks to it like any other
origin, and nothing here ever contacts the internet.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

DEADLINE_SECONDS = 20.0
"""How long ``pump`` waits before it calls a condition unmet.

Generous because a cold Chromium takes seconds to first paint on a shared CI
runner; a test that needs longer is waiting for something that will not come.
"""


def pump(
    app: Any, until: Callable[[], bool], *, deadline: float = DEADLINE_SECONDS
) -> None:
    """Spin the event loop until ``until`` holds, failing after ``deadline``."""
    end = time.monotonic() + deadline
    while not until():
        if time.monotonic() > end:
            raise AssertionError("condition not met within the deadline")
        app.processEvents()
        time.sleep(0.005)


def settle(app: Any, seconds: float) -> None:
    """Spin the loop for a while: the absence of an event needs time to show."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.005)


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args: object) -> None:
        """Quiet; the test reads ``server.seen`` instead."""

    def do_GET(self) -> None:
        server = self.server
        assert isinstance(server, LoopbackOrigin)
        server.seen.append(self.path)
        body, content_type = server.pages.get(
            self.path.split("?")[0], (b"hello", "text/plain")
        )
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)


class LoopbackOrigin(ThreadingHTTPServer):
    """One HTTP origin on the loopback interface, serving the pages it is given."""

    allow_reuse_address = True

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _Handler)
        self.seen: list[str] = []
        self.pages: dict[str, tuple[bytes, str]] = {}

    @property
    def origin(self) -> str:
        return f"http://127.0.0.1:{self.server_port}"

    def url(self, path: str) -> str:
        return self.origin + path

    def page(self, path: str, html: str) -> None:
        self.pages[path] = (html.encode("utf-8"), "text/html; charset=utf-8")


def serve() -> Iterator[LoopbackOrigin]:
    """Run a :class:`LoopbackOrigin` on a daemon thread for the duration of a fixture."""
    server = LoopbackOrigin()
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
    )
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()

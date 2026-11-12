from __future__ import annotations

import importlib
import importlib.util
import sys
import time
import traceback
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, TypedDict, Unpack
from urllib.parse import parse_qsl, urlsplit

from qgis_sdk_tools.devtools.reloader import (
    WATCH_INTERVAL_MS,
    ReloadCoordinator,
    SourceWatcher,
)

from ._serve import (
    DISABLED_BODY,
    DISABLED_STATUS,
    LOOPBACK,
    Answer,
    QueryOptions,
    ServerReloadHost,
    announce_server,
    handler_for,
    init_loop,
    query_server,
)


class ServerLoop:
    """A loopback HTTP listener in front of one ``QgsServer``, plus the reload tick.

    Single-threaded on purpose: ``QgsServer`` is not thread-safe and the request
    is the clock for a request-scoped job (decision-52), so one request is
    answered at a time and the watcher is polled between them.
    """

    def __init__(self, **options: Unpack[_InitOptions1]) -> None:
        values = _InitValues1(**options)
        self._bindings = values.bindings
        self._server = values.server
        self._host = values.host
        self._plugin = values.plugin
        self._port = values.port
        self._say = values.say
        self._watcher = values.watcher
        self._coordinator = values.coordinator
        self._clock = values.clock
        init_loop(values.poll_seconds, values.process_events, values.project, self)

    @property
    def origin(self) -> str:
        return f"http://{LOOPBACK}:{self._port}"

    # -- one request ---------------------------------------------------------------

    def _disabled_answer(self) -> Answer:
        """The 503 a disabled plugin answers, with the refusal reason."""
        reason = f"reason: {self._host.reason}\n".encode() if self._host.reason else b""
        return Answer(
            DISABLED_STATUS,
            {"Content-Type": "text/plain; charset=utf-8"},
            DISABLED_BODY + reason,
        )

    def answer_request(
        self,
        method: str,
        path: str,
        headers: Mapping[str, str] | None = None,
        body: bytes = b"",
    ) -> Answer:
        """Answer one request, or say the plugin is disabled."""
        if not self._host.running(self._plugin):
            return self._disabled_answer()
        options = QueryOptions(
            headers=headers,
            body=body,
            project=None if _names_a_map(path) else self.empty_project(),
        )
        return query_server(
            self._bindings,
            self._server,
            method,
            f"{self.origin}{path}",
            options=options,
        )

    def empty_project(self) -> Any:
        """The project a request that names no ``MAP`` is served with.

        ``QgsServer`` dispatches a ``SERVICE`` only when it has a project, and a
        plugin answering its own service has no file to name, so the loop hands
        it an empty one - built once, because ``handleRequest`` installs it as
        the current project on every request.
        """
        if self._project is None and self._project_factory is not None:
            self._project = self._project_factory()
        return self._project

    def respond(self, handler: BaseHTTPRequestHandler, method: str) -> None:
        """Serve one ``http.server`` request from the buffered answer."""
        length = int(handler.headers.get("Content-Length") or 0)
        body = handler.rfile.read(length) if length else b""
        try:
            answer = self.answer_request(
                method, handler.path, dict(handler.headers), body
            )
        except Exception:  # noqa: BLE001 - the request answers 500 with the traceback
            answer = self.failed(traceback.format_exc())
        self.write(handler, answer)

    def failed(self, detail: str) -> Answer:
        """The answer to a request the server could not complete.

        Left to itself, ``http.server`` turns a raised exception into a bare
        ``500`` and keeps the reason to itself - the one thing a dev loop must
        not do. The terminal gets the notice and the body gets the traceback, so
        ``curl`` alone explains the failure.
        """
        self.say("the request failed; the traceback is in the response body")
        return Answer(
            500,
            {"Content-Type": "text/plain; charset=utf-8"},
            f"qgis-sdk dev: the request failed\n\n{detail}".encode(),
        )

    def write(self, handler: BaseHTTPRequestHandler, answer: Answer) -> None:
        """Hand one buffered answer to ``http.server``."""
        handler.send_response(answer.status)
        for name, value in answer.headers.items():
            if name.casefold() == "content-length":
                continue  # http.server writes the one it knows
            handler.send_header(name, value)
        handler.send_header("Content-Length", str(len(answer.body)))
        handler.end_headers()
        handler.wfile.write(answer.body)

    # -- the loop ------------------------------------------------------------------

    def bind(self) -> str:
        """Start listening; returns the origin it answers on.

        The port is read back from the socket, so asking for port 0 - the way a
        test or a caller that does not care gets a free one - still reports the
        address the loop really answers on.
        """
        self._httpd = HTTPServer((LOOPBACK, self._port), handler_for(self))
        self._httpd.timeout = self._poll_seconds
        self._port = int(self._httpd.server_address[1])
        return self.origin

    def tick(self) -> None:
        """Give the event loop, the watcher and a pending reload a turn."""
        if self._process_events is not None:
            self._process_events()
        if self._watcher is not None:
            self._watcher.poll()

    def serve_forever(self, *, max_requests: int | None = None) -> None:
        """Answer requests until interrupted, ticking between them."""
        if self._httpd is None:
            self.bind()
        assert self._httpd is not None
        served = 0
        try:
            while not self._stopping:
                self._httpd.handle_request()
                self.tick()
                served += 1
                if max_requests is not None and served >= max_requests:
                    return
        except KeyboardInterrupt:  # pragma: no cover - a person pressed Ctrl+C
            self._say("stopping")
        finally:
            self.close()

    def stop(self) -> None:
        self._stopping = True

    def close(self) -> None:
        if self._httpd is not None:
            self._httpd.server_close()
            self._httpd = None

    def say(self, message: str) -> None:
        self._say(f"server: {message}")


@dataclass(frozen=True, slots=True)
class _ServerFacts:
    """The request's root, plugin, host path, port and reload policy."""

    root: Path
    plugin: str
    host_root: Path
    port: int
    watch: bool


@dataclass(frozen=True, slots=True)
class _ServerWiring:
    """Everything the running loop is assembled from."""

    facts: _ServerFacts
    application: Any
    bindings: Any
    server: Any
    host: Any
    coordinator: Any
    watcher: Any
    say: Any


def _server_facts(request: Mapping[str, object]) -> _ServerFacts:
    """Read the four fields the probe wrote, plus the optional watch flag."""
    return _ServerFacts(
        root=Path(str(request["root"])),
        plugin=str(request["plugin"]),
        host_root=Path(str(request["host"])),
        port=int(str(request["port"])),
        watch=bool(request.get("watch", True)),
    )


def _qgis_application():
    """Start a headless QgsApplication with the prefix the probe declared."""
    import os

    from qgis.core import QgsApplication

    prefix = os.environ.get("QGIS_PREFIX_PATH")
    if prefix:
        QgsApplication.setPrefixPath(prefix, True)
    application = QgsApplication([b"qgis-sdk-dev"], False)
    application.initQgis()
    return application


def _server_coordinator(facts: _ServerFacts, host, say, application):
    """The reload coordinator; one change, one reload, no editor bursts."""
    return ReloadCoordinator(
        root=facts.root,
        plugin=facts.plugin,
        host=host,
        say=say,
        notify=lambda _level, text: say(text),
        schedule=None,
        pump=application.processEvents,
    )


def _start_server(request: Mapping[str, object], say) -> _ServerWiring:
    """Build the application, server, reload host, coordinator and watcher."""
    facts = _server_facts(request)
    sys.path.insert(0, str(facts.host_root))
    application = _qgis_application()
    bindings = importlib.import_module("qgis.server")
    server = bindings.QgsServer()
    host = ServerReloadHost(server.serverInterface(), say=say)
    coordinator = _server_coordinator(facts, host, say, application)
    started = coordinator.start()
    watcher = (
        SourceWatcher(facts.root, facts.plugin, on_change=coordinator.request)
        if started and facts.watch
        else None
    )
    return _ServerWiring(
        facts, application, bindings, server, host, coordinator, watcher, say
    )


def _server_loop(wiring: _ServerWiring) -> ServerLoop:
    """Assemble the HTTP loop over a real QgsServer."""
    from qgis.core import QgsProject

    say = wiring.say
    return ServerLoop(
        bindings=wiring.bindings,
        server=wiring.server,
        host=wiring.host,
        plugin=wiring.facts.plugin,
        port=wiring.facts.port,
        project=QgsProject,
        say=lambda message: say(f"server: {message}"),
        watcher=wiring.watcher,
        coordinator=wiring.coordinator,
        process_events=wiring.application.processEvents,
    )


def bootstrap_server(request: Mapping[str, object]) -> ServerLoop:
    """Start a real QGIS Server in this process and serve the source plugin.

    Called by the probe ``plan_dev`` writes, with the request it wrote: a
    headless ``QgsApplication``, one ``QgsServer``, the plugin loaded through
    its generated package, and the reload watcher armed unless ``watch`` is off.
    """
    from ..bootstrap import say

    wiring = _start_server(request, say)
    loop = _server_loop(wiring)
    origin = loop.bind()
    return announce_server(wiring.application, loop, origin, wiring.facts.plugin, say)


def _names_a_map(path: str) -> bool:
    """Whether a request path names the ``MAP`` project QGIS should load.

    The query string of a server request is case-insensitive, so ``map=`` counts.
    """
    return any(
        key.casefold() == "map" and value
        for key, value in parse_qsl(urlsplit(path).query, keep_blank_values=True)
    )


class _InitOptions1(TypedDict, total=False):
    bindings: Any
    server: Any
    host: ServerReloadHost
    plugin: str
    port: int
    say: Callable[[str], None]
    watcher: SourceWatcher | None
    coordinator: ReloadCoordinator | None
    clock: Callable[[], float]
    poll_seconds: float
    process_events: Callable[[], None] | None
    project: Callable[[], Any] | None


@dataclass(frozen=True, slots=True)
class _InitValues1:
    bindings: Any
    server: Any
    host: ServerReloadHost
    plugin: str
    port: int
    say: Callable[[str], None]
    watcher: SourceWatcher | None = None
    coordinator: ReloadCoordinator | None = None
    clock: Callable[[], float] = time.monotonic
    poll_seconds: float = WATCH_INTERVAL_MS / 1000
    process_events: Callable[[], None] | None = None
    project: Callable[[], Any] | None = None

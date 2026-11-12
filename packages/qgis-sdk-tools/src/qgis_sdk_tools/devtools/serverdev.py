"""The QGIS side of ``qgis-sdk dev --host server``: a local QGIS Server loop.

A server plugin has no Desktop, no iface and no GUI, so its fast loop is a real
``QgsServer`` in this process answering real HTTP on loopback: ``curl`` the
``SERVICE`` the plugin declares, save a file, curl it again and see the new
answer. Nothing here fakes a request - :func:`query_server` hands a
``QgsBufferServerRequest`` to ``QgsServer.handleRequest``, which is the same C++
request path ``qgis_mapserv.fcgi`` drives - and nothing here starts FCGI.

Everything that touches ``qgis.server``, ``QgsApplication`` or ``qgis.PyQt`` is
imported inside the functions that need it, so the reload policy
(:class:`ServerReloadHost`) and the request/response translation
(:func:`query_server`, with the classes handed in) are testable on a machine with
no QGIS at all. :func:`.bootstrap_server` is what the probe calls inside a QGIS
process.

Reload is why :meth:`QgsServerHost.rebind` exists. QGIS Server registers a
filter, a service and an access-control object and offers no way to withdraw
any of them, so this loop registers once - on the first load, through the
plugin's own ``serverClassFactory`` - and every reload after that re-imports the
sources and hands the objects QGIS holds the new hook set. Two consequences are
stated rather than hidden: the entry module must export ``HOOKS`` (the name
`qgis-sdk new --host server` writes) for a reload to find the new hooks, and a
change to a filter priority or a service name/version cannot be applied to a
live registration, so it needs a new ``qgis-sdk dev``.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
import time
import traceback
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Final, TypedDict, Unpack
from urllib.parse import parse_qsl, urlsplit

from qgis_sdk.core import QuiesceOutcome
from qgis_sdk.server import ServerHooks

from .reloader import WATCH_INTERVAL_MS, ReloadCoordinator, SourceWatcher


def _buffer_answer(project, request, response, server):
    server.handleRequest(request, response, project)
    return Answer(
        status=int(response.statusCode()),
        headers={str(name): str(value) for name, value in response.headers().items()},
        body=bytes(response.body()),
    )


def _init_loop(poll_seconds, process_events, project, self):
    self._poll_seconds = poll_seconds
    self._process_events = process_events
    self._project_factory = project
    self._project: Any = None
    self._httpd: HTTPServer | None = None
    self._stopping = False


def _announce_server(application, loop, origin, plugin, say):
    say(f"server: {plugin} answering on {origin}")
    say(
        "server: add MAP=/path/to/project.qgs to the query string for a project, "
        "or a @server.service hook that answers its own SERVICE"
    )
    return _serve(application, loop, say)


def _serve(application, loop, say):
    say("server: Ctrl+C stops it; a saved Python change reloads the plugin")
    try:
        loop.serve_forever()
    finally:
        application.exitQgis()
    return loop


LOOPBACK: Final = "127.0.0.1"
#: What a request gets while the plugin is disabled after a failed reload.
DISABLED_STATUS: Final = 503
DISABLED_BODY: Final = (
    b"qgis-sdk dev: the plugin is disabled; fix the error and save, or run "
    b"`qgis-sdk dev` again\n"
)


@dataclass(frozen=True, slots=True)
class Answer:
    """One response, ready to write to the socket."""

    status: int
    headers: Mapping[str, str] = field(default_factory=dict)
    body: bytes = b""


def hooks_of(module: Any) -> ServerHooks:
    """The hook set a plugin's entry module exports as ``HOOKS``.

    ``serverClassFactory`` is what QGIS Server calls and it registers as it
    builds, which is exactly what a reload cannot do twice; ``HOOKS`` is the same
    set before registration, and it is the name the scaffold writes.
    """
    hooks = getattr(module, "HOOKS", None)
    if not isinstance(hooks, ServerHooks):
        raise _Refused(
            f"`{getattr(module, '__name__', module)}` exports no `HOOKS = "
            "ServerHooks((...))`, so a reload cannot find the new hooks; "
            "`qgis-sdk new --host server` writes one beside serverClassFactory"
        )
    return hooks


class _Refused(Exception):
    """A reload could not be applied; the message is what the terminal shows."""


class ServerReloadHost:
    """The reload coordinator's host over imports and ``QgsServerHost.rebind``.

    The first load is the plugin's own ``serverClassFactory``, called with the
    live interface - the same call QGIS Server makes. Every load after that
    re-imports the package and rebinds, because the registration it built the
    first time is the only one QGIS will accept.

    ``running`` is what the request loop asks before it dispatches: a plugin
    whose reload failed answers 503 until a reload succeeds, which is the
    server's version of the Desktop rule "a failure after teardown leaves the
    plugin visibly disabled".
    """

    def __init__(
        self,
        server_interface: Any,
        *,
        load_module: Callable[[str], Any] = importlib.import_module,
        find_spec: Callable[[str], Any] = importlib.util.find_spec,
        say: Callable[[str], None] | None = None,
    ) -> None:
        self._interface = server_interface
        self._load_module = load_module
        self._find_spec = find_spec
        self._say = say if say is not None else (lambda _message: None)
        self._host: Any = None
        self._registered = False
        self._enabled = False
        self._reason = ""

    # -- what the loop reads ------------------------------------------------------

    @property
    def host(self) -> Any:
        """The ``QgsServerHost`` serving the current revision, once loaded."""
        return self._host

    @property
    def reason(self) -> str:
        """Why the plugin is disabled, for the 503 body and the terminal."""
        return self._reason

    # -- PluginHost ---------------------------------------------------------------

    def available(self, name: str) -> bool:
        try:
            return self._find_spec(name) is not None
        except (ImportError, ValueError):
            return False

    def load(self, name: str) -> bool:
        """Import the package; register the first time, rebind every time after."""
        try:
            module = self._load_module(name)
            if not self._registered:
                factory = getattr(module, "serverClassFactory", None)
                if factory is None:
                    raise _Refused(
                        f"`{name}` exports no `serverClassFactory`; a server "
                        "plugin's entry module has to define one"
                    )
                self._host = factory(self._interface)
                self._registered = True
            else:
                self._host.rebind(hooks_of(module))
        except _Refused as error:
            self.disable(str(error))
            return False
        except Exception as error:  # noqa: BLE001 - a reload reports, never raises
            self.disable(f"{type(error).__name__}: {error}")
            return False
        self._enabled = True
        self._reason = ""
        return True

    def start(self, name: str) -> bool:
        """Registering *is* starting on a server; the first load already did it."""
        if not self._registered:
            self.disable("the plugin was never registered")
            return False
        self._enabled = True
        return True

    def unload(self, name: str) -> bool:
        """Stop serving the current hook set without touching the registration."""
        self._enabled = False
        self.forget(name)
        return True

    def forget(self, name: str) -> None:
        """Drop the package's modules so the next import reads the edited sources."""
        for module in [m for m in sys.modules if m == name or m.startswith(f"{name}.")]:
            del sys.modules[module]

    def running(self, name: str) -> bool:
        return self._enabled

    def quiesce(self, name: str) -> QuiesceOutcome:
        """Nothing to wait for: requests are served one at a time, and a request
        job is abandoned when its response is sent (decision-52)."""
        return QuiesceOutcome(refused=False, blockers=())

    def resume(self, name: str) -> None:
        """A quiesce that never refuses has nothing to undo."""

    # -- refusal -----------------------------------------------------------------

    def disable(self, reason: str) -> None:
        """Stop serving and remember why; the loop answers 503 until a reload works."""
        self._enabled = False
        self._reason = reason
        self._say(f"{reason}")


@dataclass(frozen=True, slots=True)
class _QueryOptions:
    """The optional parts of one buffered server request."""

    headers: Mapping[str, str] | None = None
    body: bytes = b""
    project: Any = None


def query_server(
    bindings: Any,
    server: Any,
    method: str,
    url: str,
    *,
    options: _QueryOptions | None = None,
) -> Answer:
    """One request through ``QgsServer.handleRequest``: buffer in, buffer out.

    ``bindings`` is the ``qgis.server`` module and ``server`` a ``QgsServer``
    instance; both are parameters so the translation can be checked with the
    stand-ins ``tests/qgis_server_support.py`` provides. ``options.project`` is
    QGIS's own split: ``None`` loads the file the request names in ``MAP``, and
    a project object is served as it stands. The dispatcher refuses every
    ``SERVICE`` without one, a plugin's own service included.
    """
    values = options or _QueryOptions()
    verb = (
        bindings.QgsServerRequest.PostMethod
        if method.upper() == "POST"
        else bindings.QgsServerRequest.GetMethod
    )
    request = bindings.QgsBufferServerRequest(
        url, verb, dict(values.headers or {}), values.body
    )
    response = bindings.QgsBufferServerResponse()
    return _buffer_answer(values.project, request, response, server)


def _handler_for(loop: ServerLoop) -> type[BaseHTTPRequestHandler]:
    """The ``http.server`` handler: every verb becomes one buffered request."""

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:
            loop.respond(self, "GET")

        def do_POST(self) -> None:
            loop.respond(self, "POST")

        def log_message(self, format: str, *args: Any) -> None:
            loop.say(f"{self.address_string()} {format % args}")

    return Handler


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
        _init_loop(values.poll_seconds, values.process_events, values.project, self)

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
        options = _QueryOptions(
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
        except Exception:  # noqa: BLE001 - a plugin bug is reported, never swallowed
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
        self._httpd = HTTPServer((LOOPBACK, self._port), _handler_for(self))
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
    from .bootstrap import say

    wiring = _start_server(request, say)
    loop = _server_loop(wiring)
    return _serve(wiring.application, loop, wiring.facts.plugin, say)


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

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
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import TYPE_CHECKING, Any, Final

from qgis_sdk.core import QuiesceOutcome
from qgis_sdk.server import ServerHooks

if TYPE_CHECKING:
    from qgis_sdk_tools.devtools.serverdev._loop import ServerLoop


def _buffer_answer(project, request, response, server):
    server.handleRequest(request, response, project)
    return Answer(
        status=int(response.statusCode()),
        headers={str(name): str(value) for name, value in response.headers().items()},
        body=bytes(response.body()),
    )


def init_loop(poll_seconds, process_events, project, self):
    self._poll_seconds = poll_seconds
    self._process_events = process_events
    self._project_factory = project
    self._project: Any = None
    self._httpd: HTTPServer | None = None
    self._stopping = False


def announce_server(application, loop, origin, plugin, say):
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
        except Exception as error:  # noqa: BLE001 - the request answers 500
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
class QueryOptions:
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
    options: QueryOptions | None = None,
) -> Answer:
    """One request through ``QgsServer.handleRequest``: buffer in, buffer out.

    ``bindings`` is the ``qgis.server`` module and ``server`` a ``QgsServer``
    instance; both are parameters so the translation can be checked with the
    stand-ins ``tests/qgis_server_support.py`` provides. ``options.project`` is
    QGIS's own split: ``None`` loads the file the request names in ``MAP``, and
    a project object is served as it stands. The dispatcher refuses every
    ``SERVICE`` without one, a plugin's own service included.
    """
    values = options or QueryOptions()
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


def handler_for(loop: ServerLoop) -> type[BaseHTTPRequestHandler]:
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

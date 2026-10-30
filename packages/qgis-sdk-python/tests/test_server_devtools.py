"""The server half of ``qgis-sdk dev``: the reload policy and the wire, without QGIS.

``devtools.serverdev`` is what the probe runs inside a QGIS process, but only
two of its parts touch ``qgis.server``: building the ``QgsApplication`` and the
``QgsServer`` (``bootstrap_server``, which needs the bindings) and the classes
:func:`query_server` is handed. Everything else is checked here against the
stand-ins in ``qgis_server_support`` - the same cast the adapter's own tests use -
so the reload rule is provable on a machine whose QGIS has no server support,
which is every environment this workspace can reach.

The rule under test is TASK-80 AC 4's "dev --host server reloads a filter edit":
QGIS Server cannot withdraw a registration, so a reload re-imports the sources
and hands the objects QGIS holds the new hook set.
"""

from __future__ import annotations

import types
from pathlib import Path
from typing import Any

import pytest
import qgis_server_support as support
from qgis_sdk.adapters._server import QgsServerHost
from qgis_sdk.server import (
    ServerContext,
    ServerHooks,
    ServerRequest,
    ServerResponse,
    access_control,
    filter,
    service,
)
from qgis_sdk_tools.devtools.serverdev import (
    DISABLED_BODY,
    DISABLED_STATUS,
    Answer,
    ServerLoop,
    ServerReloadHost,
    hooks_of,
    query_server,
)


@pytest.fixture(autouse=True)
def wired(monkeypatch: pytest.MonkeyPatch) -> types.ModuleType:
    """``from qgis import server`` resolves to the stand-ins."""
    return support.install(monkeypatch)


def chain(marker: str) -> ServerHooks:
    """One filter, one service and one access hook that answer with ``marker``."""

    @filter(priority=10)
    def rewrite(ctx: ServerContext, request, response):
        if request.param("SDK_DEMO") is None:
            return None
        return request.with_params(ROUTED=marker)

    @service(name="SDKDEMO", version="1.0.0")
    def answer(ctx: ServerContext, request) -> ServerResponse:
        return ServerResponse.text(f"{marker}:{request.param('ROUTED')}")

    @access_control(priority=10)
    def only_public(ctx: ServerContext, request, layer) -> bool:
        return layer != marker

    return ServerHooks((rewrite, answer, only_public))


def plugin_module(hooks: ServerHooks) -> types.ModuleType:
    """A plugin entry module: the factory QGIS calls, and the ``HOOKS`` a reload reads."""
    module = types.ModuleType("demo")
    module.HOOKS = hooks
    module.serverClassFactory = lambda iface: QgsServerHost(hooks, iface).register()
    return module


class Modules:
    """The import side: ``<plugin>`` resolves to whatever this holds."""

    def __init__(self, module: types.ModuleType | None) -> None:
        self.module = module
        self.forgotten: list[str] = []

    def load(self, name: str) -> Any:
        if self.module is None:
            raise ImportError(f"No module named {name!r}")
        return self.module

    def find_spec(self, name: str) -> Any:
        return object() if self.module is not None else None


def host_over(
    module: types.ModuleType,
) -> tuple[ServerReloadHost, support.ServerInterface]:
    interface = support.ServerInterface()
    modules = Modules(module)
    return ServerReloadHost(interface, load_module=modules.load), interface


# -- what a plugin's entry module has to export ---------------------------------------


def test_a_module_without_hooks_is_refused_with_the_name_it_needs() -> None:
    with pytest.raises(Exception) as excinfo:
        hooks_of(types.ModuleType("demo"))

    assert "HOOKS" in str(excinfo.value)


def test_the_hooks_of_a_module_are_the_set_it_exported() -> None:
    exported = chain("first")

    assert hooks_of(plugin_module(exported)) is exported


# -- the first load and every reload after it ------------------------------------------


def test_the_first_load_calls_the_plugins_own_factory() -> None:
    host, interface = host_over(plugin_module(chain("first")))

    assert host.load("demo") is True
    assert host.running("demo") is True
    assert isinstance(host.host, QgsServerHost)
    # One registration, exactly as a deployed server would see.
    assert list(interface.filters) == [10]
    assert [item.name() for item in interface.services] == ["SDKDEMO"]


def test_a_reload_serves_the_new_hooks_through_the_old_registration() -> None:
    module = plugin_module(chain("first"))
    host, interface = host_over(module)
    host.load("demo")
    filter_object = interface.filters[10][0]
    service_object = interface.services[0]

    module.HOOKS = chain("second")
    assert host.unload("demo") is True
    assert host.load("demo") is True

    # The objects QGIS holds are the same ones - nothing was registered twice.
    assert interface.filters[10] == [filter_object]
    assert interface.services == [service_object]
    handler = support.Handler({"SERVICE": "SDKDEMO", "SDK_DEMO": "1"})
    interface.handler = handler
    filter_object.onRequestReady()
    assert handler.params["ROUTED"] == "second"
    response = support.Response()
    service_object.executeRequest(support.Request({"SERVICE": "SDKDEMO"}), response)
    assert response.body == b"second:None"


def test_unloading_stops_serving_but_keeps_the_registration() -> None:
    host, interface = host_over(plugin_module(chain("first")))
    host.load("demo")

    host.unload("demo")

    assert host.running("demo") is False
    assert list(interface.filters) == [10]  # still registered, just disabled


def test_a_reload_that_moves_a_service_identity_is_disabled_and_says_why() -> None:
    @service(name="OTHER", version="2.0.0")
    def other(ctx: ServerContext, request) -> ServerResponse:
        return ServerResponse.text("other")

    module = plugin_module(chain("first"))
    host, _interface = host_over(module)
    host.load("demo")

    module.HOOKS = ServerHooks((other,))
    host.unload("demo")
    assert host.load("demo") is False

    assert host.running("demo") is False
    assert "services" in host.reason


def test_an_import_that_raises_leaves_the_plugin_disabled_with_the_reason() -> None:
    modules = Modules(None)
    host = ServerReloadHost(support.ServerInterface(), load_module=modules.load)

    assert host.available("demo") is False
    assert host.load("demo") is False
    assert "No module named" in host.reason


def test_forgetting_drops_the_package_modules(monkeypatch: pytest.MonkeyPatch) -> None:
    host, _interface = host_over(plugin_module(chain("first")))
    import sys

    monkeypatch.setitem(sys.modules, "demo", types.ModuleType("demo"))
    monkeypatch.setitem(sys.modules, "demo.plugin", types.ModuleType("demo.plugin"))

    host.forget("demo")

    assert "demo" not in sys.modules
    assert "demo.plugin" not in sys.modules


def test_a_server_has_nothing_to_quiesce() -> None:
    host, _interface = host_over(plugin_module(chain("first")))

    outcome = host.quiesce("demo")

    assert outcome.refused is False
    assert outcome.blockers == ()


# -- the request path ------------------------------------------------------------------


class BufferRequest:
    """``QgsBufferServerRequest``: URL, verb, headers, body."""

    GetMethod = "GET"
    PostMethod = "POST"

    def __init__(self, url: str, method: str = "GET", headers=None, body=b"") -> None:
        self.url = url
        self.method = method
        self.headers = dict(headers or {})
        self.body = bytes(body)


class BufferResponse:
    """``QgsBufferServerResponse``: what ``handleRequest`` wrote."""

    def __init__(self) -> None:
        self._status = 200
        self._headers = {"Content-Type": "text/plain"}
        self._body = b""

    def statusCode(self) -> int:
        return self._status

    def headers(self) -> dict[str, str]:
        return dict(self._headers)

    def body(self) -> bytes:
        return self._body

    def answer(self, status: int, body: bytes) -> None:
        self._status = status
        self._body = body


def bindings() -> types.SimpleNamespace:
    """The names ``query_server`` reaches for in ``qgis.server``."""
    return types.SimpleNamespace(
        QgsServerRequest=BufferRequest,
        QgsBufferServerRequest=BufferRequest,
        QgsBufferServerResponse=BufferResponse,
    )


class FakeServer:
    """``QgsServer``: the one call the loop makes."""

    def __init__(self) -> None:
        self.seen: list[BufferRequest] = []
        self.projects: list[Any] = []

    def handleRequest(self, request: Any, response: Any, project: Any = None) -> None:
        self.seen.append(request)
        self.projects.append(project)
        response.answer(200, f"served {request.method} {request.url}".encode())


def test_a_request_is_buffered_in_and_out() -> None:
    server = FakeServer()

    answer = query_server(
        bindings(), server, "POST", "http://127.0.0.1:8080/?SERVICE=WMS", None, b"x=1"
    )

    assert answer.status == 200
    assert answer.body == b"served POST http://127.0.0.1:8080/?SERVICE=WMS"
    assert server.seen[0].method == BufferRequest.PostMethod
    assert server.seen[0].body == b"x=1"


def loop_over(host: ServerReloadHost, server: FakeServer | None = None) -> ServerLoop:
    said: list[str] = []
    loop = ServerLoop(
        bindings=bindings(),
        server=server if server is not None else FakeServer(),
        host=host,
        plugin="demo",
        port=8080,
        say=said.append,
    )
    loop.said = said  # type: ignore[attr-defined]
    return loop


def test_a_disabled_plugin_answers_503_and_names_the_reason() -> None:
    host, _interface = host_over(plugin_module(chain("first")))
    host.load("demo")
    host.disable("the reload moved a service")

    answer = loop_over(host).answer_request("GET", "/?SERVICE=SDKDEMO")

    assert isinstance(answer, Answer)
    assert answer.status == DISABLED_STATUS
    assert answer.body.startswith(DISABLED_BODY)
    assert b"the reload moved a service" in answer.body


def test_a_running_plugin_answers_through_the_server() -> None:
    host, _interface = host_over(plugin_module(chain("first")))
    host.load("demo")

    answer = loop_over(host).answer_request("GET", "/?SERVICE=SDKDEMO")

    assert answer.status == 200
    assert answer.body == b"served GET http://127.0.0.1:8080/?SERVICE=SDKDEMO"


def test_the_tick_gives_the_event_loop_and_the_watcher_a_turn() -> None:
    host, _interface = host_over(plugin_module(chain("first")))
    host.load("demo")
    polled: list[int] = []
    events: list[str] = []

    loop = ServerLoop(
        bindings=bindings(),
        server=FakeServer(),
        host=host,
        plugin="demo",
        port=8080,
        say=lambda _message: None,
        watcher=types.SimpleNamespace(poll=lambda: polled.append(1) or False),
        process_events=lambda: events.append("qt"),
    )

    loop.tick()

    assert events == ["qt"]
    assert polled == [1]


def test_the_origin_is_the_loopback_address_it_bound() -> None:
    host, _interface = host_over(plugin_module(chain("first")))

    assert loop_over(host).origin == "http://127.0.0.1:8080"


def test_a_bound_loop_answers_one_real_http_request() -> None:
    """The `http.server` wrapper: a real socket, the buffered answer written out."""
    import http.client
    import threading

    host, _interface = host_over(plugin_module(chain("first")))
    host.load("demo")
    loop = loop_over(host)
    origin = loop.bind()
    port = int(origin.rsplit(":", 1)[1])
    serving = threading.Thread(
        target=loop.serve_forever, kwargs={"max_requests": 1}, daemon=True
    )
    serving.start()
    try:
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        connection.request("GET", "/?SERVICE=SDKDEMO")
        response = connection.getresponse()
        body = response.read()
        connection.close()
    finally:
        serving.join(timeout=10)
        loop.close()

    assert response.status == 200
    assert body == b"served GET http://127.0.0.1:8080/?SERVICE=SDKDEMO"


class RaisingServer(FakeServer):
    """``QgsServer`` whose one call raises, as a plugin bug reaches the loop."""

    def handleRequest(self, request: Any, response: Any, project: Any = None) -> None:
        raise RuntimeError("the filter raised instead of answering")


def test_a_request_that_raises_answers_500_with_the_traceback() -> None:
    """A plugin bug is reported, not turned into a bare ``500`` by ``http.server``."""
    import http.client
    import threading

    host, _interface = host_over(plugin_module(chain("first")))
    host.load("demo")
    said: list[str] = []
    loop = ServerLoop(
        bindings=bindings(),
        server=RaisingServer(),
        host=host,
        plugin="demo",
        port=0,
        say=said.append,
    )
    origin = loop.bind()
    port = int(origin.rsplit(":", 1)[1])
    serving = threading.Thread(
        target=loop.serve_forever, kwargs={"max_requests": 1}, daemon=True
    )
    serving.start()
    try:
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        connection.request("GET", "/?SERVICE=SDKDEMO")
        response = connection.getresponse()
        body = response.read()
        connection.close()
    finally:
        serving.join(timeout=10)
        loop.close()

    assert response.status == 500
    assert body.startswith(b"qgis-sdk dev: the request failed")
    assert b"RuntimeError: the filter raised instead of answering" in body
    # The notice, then `http.server`'s own access line for the 500 it sent.
    assert (
        said[0] == "server: the request failed; the traceback is in the response body"
    )
    assert said[-1].endswith('"GET /?SERVICE=SDKDEMO HTTP/1.1" 500 -')


class Project:
    """Stand-in for ``QgsProject``: only its identity matters here."""


def test_a_request_without_map_is_served_with_an_empty_project() -> None:
    """QGIS dispatches a SERVICE only when it has a project (qgsserver.cpp).

    A plugin answering its own service has no file to name, so the loop hands
    the dispatcher an empty project instead of letting the request fail with
    ``Project file error``.
    """
    host, _interface = host_over(plugin_module(chain("first")))
    host.load("demo")
    server = FakeServer()
    built: list[Project] = []

    loop = ServerLoop(
        bindings=bindings(),
        server=server,
        host=host,
        plugin="demo",
        port=8080,
        say=lambda _message: None,
        project=lambda: built.append(Project()) or built[-1],
    )
    loop.answer_request("GET", "/?SERVICE=SDKDEMO")
    loop.answer_request("GET", "/?SERVICE=SDKDEMO")

    assert len(built) == 1  # one project for the loop, not one per request
    assert server.projects == [built[0], built[0]]


def test_a_request_that_names_map_lets_the_server_load_the_project() -> None:
    """``MAP`` in the query string is QGIS's to load, so the loop passes ``None``."""
    host, _interface = host_over(plugin_module(chain("first")))
    host.load("demo")
    server = FakeServer()
    loop = ServerLoop(
        bindings=bindings(),
        server=server,
        host=host,
        plugin="demo",
        port=8080,
        say=lambda _message: None,
        project=Project,
    )

    loop.answer_request("GET", "/?SERVICE=WMS&map=/tmp/project.qgs")
    loop.answer_request("GET", "/?SERVICE=SDKDEMO")

    assert server.projects[0] is None
    assert isinstance(server.projects[1], Project)


def test_a_missing_project_is_not_a_loop_error(tmp_path: Path) -> None:
    """The loop never loads a project itself: the request's MAP decides (QGIS's rule)."""
    host, _interface = host_over(plugin_module(chain("first")))
    host.load("demo")

    answer = loop_over(host).answer_request(
        "GET", "/?MAP=%s&SERVICE=WMS" % (tmp_path / "project.qgs")
    )

    assert answer.status == 200


def test_a_request_model_survives_the_translation() -> None:
    """What the loop hands the server is the request the C++ side would build."""
    request = ServerRequest(method="GET", url="http://127.0.0.1:8080/", params={})

    assert request.method == "GET"

"""The one QGIS the SDK cannot assume: a build with QGIS Server in it.

``qgis.server`` - ``QgsServer``, ``QgsServerInterface``, ``QgsServerFilter`` -
exists only when QGIS was configured with ``WITH_SERVER=ON`` and its Python
bindings. conda-forge passes ``-D WITH_SERVER=FALSE`` on every platform, so the
Pixi environment every other job uses has no such module and the whole server
host is proven there against ``qgis_sdk.testing.FakeServerInterface`` instead
(decision-52 implementation note).

This file is the other half: it runs only where the module exists, and it is
one of the two modules the ``QGIS 3.44 LTS`` CI row runs. Everywhere else
``pytest.importorskip`` skips it, so a build without server bindings costs a
skip and never a failure.

One thing about this file: ``QgsServer`` holds one static server interface, so
every hook a test registers is still registered when the next test runs. Each
test therefore declares hooks that recognise their own request - a marker
parameter, a layer name - instead of assuming it is the only plugin loaded.

TASK-80 AC 2 lives here: the same plugin class served in-process under a headless
``QgsApplication`` through the objects a deployed server calls - a
``QgsServerFilter``, a ``QgsService`` and a ``QgsAccessControlFilter`` built by
:mod:`qgis_sdk.adapters.qgis.server` - and driven by ``QgsServer.handleRequest``
with a real ``QgsBufferServerRequest``. No FCGI, no network, no browser.
"""

from __future__ import annotations

import pytest

# One layer per module: `server` already means the QGIS bindings are there,
# and the application comes from the shared `qgis_app` fixture.
pytestmark = pytest.mark.server

server = pytest.importorskip(
    "qgis.server", reason="this QGIS was built without WITH_SERVER (no qgis.server)"
)


def test_the_bindings_the_host_needs_are_importable() -> None:
    from qgis.server import (
        QgsServer,
        QgsServerFilter,
        QgsServerInterface,
        QgsService,
    )

    assert all(
        item is not None
        for item in (QgsServer, QgsServerFilter, QgsServerInterface, QgsService)
    )


def test_a_server_can_be_created_in_process(qgis_app) -> None:
    from qgis.server import QgsServer

    created = QgsServer()

    assert created is not None
    # The in-process route TASK-80 AC 2 takes instead of FCGI: build a request,
    # hand it to this server, read the response. Only the classes are asserted
    # here, so the test keeps working on a build that renames either one.
    assert hasattr(created, "handleRequest")


def test_the_sdk_serves_a_request_inside_a_qgis_process(qgis_app) -> None:
    from qgis_sdk.server import (
        ServerContext,
        ServerHooks,
        ServerRequest,
        ServerResponse,
        filter,
        service,
    )
    from qgis_sdk.testing import FakeServerInterface

    @filter(priority=10)
    def default_version(ctx: ServerContext, request, response):
        if request.param("VERSION") is None:
            return request.with_params(VERSION="1.3.0")
        return None

    @service(name="WMS")
    def capabilities(ctx: ServerContext, request) -> ServerResponse:
        return ServerResponse.xml(f"<v>{request.param('VERSION')}</v>")

    answer = FakeServerInterface().serve(
        ServerHooks((default_version, capabilities)),
        ServerRequest(
            method="GET",
            url="http://localhost/qgis/qgis_mapserv.fcgi",
            params={"SERVICE": "WMS", "REQUEST": "GetCapabilities"},
        ),
    )

    # The pure layer answers the same way with QGIS loaded as it does without:
    # nothing in the dispatcher reaches a Qt object behind the author's back.
    assert answer.status == 200
    assert answer.body == b"<v>1.3.0</v>"


# -- AC 2: the adapter, driven by a real QgsServer ----------------------------------


def _demo_hooks():
    """One filter that rewrites and one service that answers, as a plugin declares them."""
    from qgis_sdk.server import ServerContext, ServerResponse, filter, service

    @filter(priority=10)
    def route_to_demo(ctx: ServerContext, request, response):
        # Only a request that carries the marker becomes ours: `QgsServer` is one
        # per process, so every hook this module registers stays registered for
        # the tests after it, and a filter that claimed every request would be
        # rewriting theirs too (it was, until this test found it).
        if request.param("SDK_DEMO") is None:
            return None
        return request.with_params(SERVICE="SDKDEMO", VERSION="1.0.0", ROUTED="yes")

    @service(name="SDKDEMO")
    def demo(ctx: ServerContext, request) -> ServerResponse:
        routed = request.param("ROUTED")
        return ServerResponse.text(
            f"marker={request.param('MARKER')} routed={routed}", status=200
        )

    return route_to_demo, demo


def test_a_plugin_answers_a_request_through_a_real_qgis_server(qgis_app) -> None:
    """AC 2, first claim: the filter runs and its rewrite reaches the service.

    ``QgsServer.handleRequest`` is the whole C++ request path: filters, service
    dispatch, response. The request names ``WMS``; the filter rewrites it to the
    plugin's own service, and the body proves the service read the rewritten
    parameters - not the ones on the wire.
    """
    from qgis.core import QgsProject
    from qgis.server import QgsBufferServerRequest, QgsBufferServerResponse, QgsServer
    from qgis_sdk.adapters.qgis.server import QgsServerHost
    from qgis_sdk.server import ServerHooks

    route_to_demo, demo = _demo_hooks()
    server = QgsServer()
    QgsServerHost(
        ServerHooks((route_to_demo, demo)), server.serverInterface()
    ).register()

    request = QgsBufferServerRequest(
        "http://localhost/qgis/qgis_mapserv.fcgi?SERVICE=WMS&MARKER=seen&SDK_DEMO=1"
    )
    response = QgsBufferServerResponse()
    server.handleRequest(request, response, QgsProject())

    assert response.statusCode() == 200
    # `MARKER` came in on the wire; `routed` is what the filter put in the
    # request QGIS dispatched, so both halves of the adapter ran.
    assert bytes(response.body()) == b"marker=seen routed=yes"


def test_an_access_hook_restricts_a_layer_inside_the_qgis_server(qgis_app) -> None:
    """AC 2, second claim: the access hook answers QGIS's per-layer question."""
    from qgis.core import QgsVectorLayer
    from qgis.server import QgsServer
    from qgis_sdk.adapters.qgis.server import QgsServerHost
    from qgis_sdk.server import ServerContext, ServerHooks, access_control

    @access_control(priority=10)
    def only_public(ctx: ServerContext, request, layer) -> bool:
        return layer != "secret"

    server = QgsServer()
    host = QgsServerHost(
        ServerHooks((only_public,)), server.serverInterface()
    ).register()
    public = QgsVectorLayer("Point?crs=EPSG:4326&field=id:integer", "public", "memory")
    secret = QgsVectorLayer("Point?crs=EPSG:4326&field=id:integer", "secret", "memory")

    allowed = host.access_control.layerPermissions(public)
    refused = host.access_control.layerPermissions(secret)

    # QGIS's own answer is "everything allowed"; a refusal is every permission
    # cleared, which is what QgsAccessControl consults while it renders.
    assert allowed.canRead is True
    assert refused.canRead is False
    assert (refused.canInsert, refused.canUpdate, refused.canDelete) == (
        False,
        False,
        False,
    )


def test_the_hooks_become_the_three_objects_qgis_calls(qgis_app) -> None:
    """AC 2, third claim: registration, in the shape QGIS Server expects.

    One filter carries the whole SDK filter chain, one ``QgsService`` answers the
    ``SERVICE`` it declares, and one access-control object runs the access hooks -
    three objects, in the interface QGIS reads when a request arrives.
    """
    from qgis.server import QgsServer
    from qgis_sdk.adapters.qgis.server import QgsServerHost
    from qgis_sdk.server import (
        ServerContext,
        ServerHooks,
        ServerResponse,
        access_control,
        filter,
        service,
    )

    @filter(priority=10)
    def first(ctx: ServerContext, request, response):
        return None

    @filter(priority=20)
    def second(ctx: ServerContext, request, response):
        return None

    @service(name="SDKDEMO")
    def demo(ctx: ServerContext, request) -> ServerResponse:
        return ServerResponse.text("demo")

    @access_control(priority=30)
    def only_public(ctx: ServerContext, request, layer) -> bool:
        return True

    server = QgsServer()
    iface = server.serverInterface()
    host = QgsServerHost(
        ServerHooks((first, second, demo, only_public)), iface
    ).register()

    registered = [item for group in iface.filters().values() for item in group]
    assert host.filter is not None
    assert registered.count(host.filter) == 1
    assert [item.name() for item in host.services] == ["SDKDEMO"]
    assert host.access_control is not None


def test_a_refused_layer_never_reaches_the_capabilities(qgis_app) -> None:
    """AC 2, second claim driven by a whole request: WMS GetCapabilities.

    The permission question above is one QGIS call. This one is the request an
    operator actually sees: the layer list of a WMS capabilities document, once
    with the hook allowing everything and once with it refusing one layer.

    It only works because the adapter answers ``cacheKey()`` with a non-empty
    string: without it QGIS serves the *first* document to the second request,
    which is the leak the pure layer pins.
    """
    from qgis.core import QgsProject, QgsVectorLayer
    from qgis.server import QgsBufferServerRequest, QgsBufferServerResponse, QgsServer
    from qgis_sdk.adapters.qgis.server import QgsServerHost
    from qgis_sdk.server import ServerContext, ServerHooks, access_control

    refused: set[str] = set()

    @access_control(priority=10)
    def only_public(ctx: ServerContext, request, layer) -> bool:
        return layer not in refused

    project = QgsProject()
    for name in ("public_layer", "secret_layer"):
        layer = QgsVectorLayer("Point?crs=EPSG:4326&field=id:integer", name, "memory")
        project.addMapLayer(layer)

    server = QgsServer()
    QgsServerHost(ServerHooks((only_public,)), server.serverInterface()).register()

    def capabilities() -> bytes:
        request = QgsBufferServerRequest(
            "http://localhost/qgis/qgis_mapserv.fcgi"
            "?SERVICE=WMS&REQUEST=GetCapabilities&VERSION=1.3.0"
        )
        response = QgsBufferServerResponse()
        server.handleRequest(request, response, project)
        assert response.statusCode() == 200, response.statusCode()
        return bytes(response.body())

    allowed = capabilities()
    # The control: unless both layers are listed when nothing is refused, the
    # absence below would prove nothing.
    assert b"public_layer" in allowed, allowed[:400]
    assert b"secret_layer" in allowed, allowed[:400]

    refused.add("secret_layer")
    denied = capabilities()

    assert b"public_layer" in denied, denied[:400]
    assert b"secret_layer" not in denied, denied[:400]

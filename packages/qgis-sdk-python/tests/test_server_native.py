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
from qgis_sdk.server import (
    ServerContext,
    ServerHooks,
    ServerRequest,
    ServerResponse,
    access_control,
    filter,
    service,
)

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


# -- one plugin's hooks, served two ways ------------------------------------------
#
# AC 2 asks for *the same plugin class, unchanged* in both places, so the hooks
# below are declared once and used by a pure `FakeServerInterface` and by a real
# `QgsServer`. They recognise their own request - the `SDK_DEMO` marker, the layer
# name - because `QgsServer` holds one static server interface per process and
# anything registered here stays registered.

REFUSED: set[str] = set()


@filter(priority=10)
def demo_route(ctx: ServerContext, request, response):
    """Take a marked request to the plugin's own service, and rewrite it there."""
    if request.param("SDK_DEMO") is None:
        return None
    return request.with_params(SERVICE="SDKDEMO", VERSION="1.0.0", ROUTED="yes")


@service(name="SDKDEMO", version="1.0.0")
def demo_answer(ctx: ServerContext, request) -> ServerResponse:
    return ServerResponse.text(
        f"marker={request.param('MARKER')} routed={request.param('ROUTED')}"
    )


@access_control(priority=10)
def demo_permission(ctx: ServerContext, request, layer) -> bool:
    return layer not in REFUSED


HOOKS = ServerHooks((demo_route, demo_answer, demo_permission))


@pytest.fixture(scope="module")
def served(qgis_app):
    """The real server, with this plugin registered on it once."""
    from qgis.server import QgsServer
    from qgis_sdk.adapters.qgis.server import QgsServerHost

    protocol_server = QgsServer()
    host = QgsServerHost(HOOKS, protocol_server.serverInterface()).register()
    return protocol_server, host


def demo_project():
    """Two memory layers, one of which the access hook will refuse."""
    from qgis.core import QgsProject, QgsVectorLayer

    project = QgsProject()
    for name in ("public_layer", "secret_layer"):
        project.addMapLayer(
            QgsVectorLayer("Point?crs=EPSG:4326&field=id:integer", name, "memory")
        )
    return project


def capabilities(protocol_server, project) -> bytes:
    """One WMS GetCapabilities through the whole C++ request path."""
    from qgis.server import QgsBufferServerRequest, QgsBufferServerResponse

    request = QgsBufferServerRequest(
        "http://localhost/qgis/qgis_mapserv.fcgi"
        "?SERVICE=WMS&REQUEST=GetCapabilities&VERSION=1.3.0"
    )
    response = QgsBufferServerResponse()
    protocol_server.handleRequest(request, response, project)
    assert response.statusCode() == 200, response.statusCode()
    return bytes(response.body())


def test_the_same_hooks_answer_without_qgis(qgis_app) -> None:
    """The pure half: the dispatcher answers with QGIS loaded but unused.

    `FakeServerInterface` records the registrations and serves a request through
    the same `ServerHost` a deployed server drives, so the three claims are
    checked here with no Qt object in the path at all.
    """
    from qgis_sdk.testing import FakeServerInterface

    interface = FakeServerInterface()
    answered = interface.serve(
        HOOKS,
        ServerRequest(
            method="GET",
            url="http://localhost/qgis/qgis_mapserv.fcgi",
            params={"SERVICE": "WMS", "SDK_DEMO": "1", "MARKER": "pure"},
        ),
    )

    assert answered.status == 200
    assert answered.body == b"marker=pure routed=yes"

    REFUSED.add("secret_layer")
    try:
        refused = FakeServerInterface().serve(
            HOOKS,
            ServerRequest(
                method="GET",
                url="http://localhost/qgis/qgis_mapserv.fcgi",
                params={"SERVICE": "WMS", "LAYERS": "secret_layer"},
            ),
        )
    finally:
        REFUSED.discard("secret_layer")

    assert refused.status == 403


def test_a_plugin_answers_a_request_through_a_real_qgis_server(served) -> None:
    """AC 2, first claim: the filter runs and its rewrite reaches the service.

    ``QgsServer.handleRequest`` is the whole C++ request path: filters, service
    dispatch, response. The request names ``WMS``; the filter rewrites it to the
    plugin's own service, and the body proves the service read the rewritten
    parameters - not the ones on the wire.
    """
    from qgis.core import QgsProject
    from qgis.server import QgsBufferServerRequest, QgsBufferServerResponse

    protocol_server, host = served
    assert host.filter is not None

    request = QgsBufferServerRequest(
        "http://localhost/qgis/qgis_mapserv.fcgi?SERVICE=WMS&MARKER=seen&SDK_DEMO=1"
    )
    response = QgsBufferServerResponse()
    protocol_server.handleRequest(request, response, QgsProject())

    assert response.statusCode() == 200
    # `MARKER` came in on the wire; `routed` is what the filter put in the
    # request QGIS dispatched, so both halves of the adapter ran.
    assert bytes(response.body()) == b"marker=seen routed=yes"


def test_the_hooks_become_the_three_objects_qgis_calls(served) -> None:
    """AC 2, second claim: registration, in the shape QGIS Server expects.

    One filter carries the whole SDK filter chain, one ``QgsService`` answers the
    ``SERVICE`` it declares, and one access-control object runs the access hooks.
    """
    protocol_server, host = served
    interface = protocol_server.serverInterface()

    registered = [item for group in interface.filters().values() for item in group]
    assert registered.count(host.filter) == 1
    assert [item.name() for item in host.services] == ["SDKDEMO"]
    assert host.access_control is not None


def test_an_access_hook_restricts_a_layer_inside_the_qgis_server(served) -> None:
    """AC 2, third claim at the object level: QGIS's per-layer question."""
    from qgis.core import QgsVectorLayer

    _, host = served
    public = QgsVectorLayer("Point?crs=EPSG:4326&field=id:integer", "public", "memory")
    secret = QgsVectorLayer(
        "Point?crs=EPSG:4326&field=id:integer", "secret_layer", "memory"
    )

    allowed = host.access_control.layerPermissions(public)
    REFUSED.add("secret_layer")
    try:
        refused = host.access_control.layerPermissions(secret)
    finally:
        REFUSED.discard("secret_layer")

    # QGIS's own answer is "everything allowed"; a refusal is every permission
    # cleared, which is what QgsAccessControl consults while it renders.
    assert allowed.canRead is True
    assert refused.canRead is False
    assert (refused.canInsert, refused.canUpdate, refused.canDelete) == (
        False,
        False,
        False,
    )


def test_a_refused_layer_never_reaches_the_capabilities(served) -> None:
    """AC 2, third claim driven by a whole request: WMS GetCapabilities.

    The permission question above is one QGIS call. This one is the request an
    operator actually sees: the layer list of a WMS capabilities document, once
    with the hook allowing everything and once with it refusing one layer.

    It only works because the adapter answers ``cacheKey()`` with a non-empty
    string: without it QGIS serves the *first* document to the second request,
    which is the leak the pure layer pins.
    """
    protocol_server, _ = served
    project = demo_project()

    allowed = capabilities(protocol_server, project)
    # The control: unless both layers are listed when nothing is refused, the
    # absence below would prove nothing.
    assert b"public_layer" in allowed, allowed[:400]
    assert b"secret_layer" in allowed, allowed[:400]

    REFUSED.add("secret_layer")
    try:
        denied = capabilities(protocol_server, project)
    finally:
        REFUSED.discard("secret_layer")

    assert b"public_layer" in denied, denied[:400]
    assert b"secret_layer" not in denied, denied[:400]

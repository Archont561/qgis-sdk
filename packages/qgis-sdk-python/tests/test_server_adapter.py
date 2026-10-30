"""The server adapter wired against a stand-in for ``qgis.server``.

`qgis_sdk.adapters._server.QgsServerHost` turns a plugin's hooks into the three
objects QGIS Server calls: one `QgsServerFilter`, one `QgsService` per declared
service, and one `QgsAccessControlFilter`. Here those three are stand-ins with
QGIS's constructor signatures, so the wiring - which slot runs which hook, what
a rewrite does to the request QGIS's services read, what an answer leaves in the
handler - is checked on every machine, before the `QGIS 3.44 LTS` row proves the
same objects against the real C++ classes (TASK-80 AC 2).

The stand-ins are deliberately dumb. If a test passes here and fails there, the
difference is QGIS's behaviour, not this file's copy of it.
"""

from __future__ import annotations

import types
from typing import Any

import pytest
import qgis_server_support as support
from qgis_sdk.adapters._server import (
    NO_CAPABILITIES_CACHE,
    QgsServerHost,
    qgis_server,
)
from qgis_sdk.core.host import Host
from qgis_sdk.models import QgisSdkUnsupportedCapabilityError
from qgis_sdk.server import (
    ServerContext,
    ServerHooks,
    ServerRequest,
    ServerResponse,
    access_control,
    filter,
    service,
)


@pytest.fixture
def wired(monkeypatch: pytest.MonkeyPatch) -> types.ModuleType:
    """Make ``from qgis import server`` resolve to the stand-ins."""
    return support.install(monkeypatch)


def only(registered: dict[int, list[Any]], priority: int | None = None) -> Any:
    """The one object in a registration map, or the one at ``priority``."""
    if priority is not None:
        (item,) = registered[priority]
        return item
    (group,) = registered.values()
    (item,) = group
    return item


# -- the module's own contract --------------------------------------------------------


def test_the_adapter_is_importable_without_qgis() -> None:
    # This module was imported at the top of the file with no qgis package
    # installed at all; asking for the bindings is what raises.
    assert QgsServerHost is not None
    with pytest.raises(QgisSdkUnsupportedCapabilityError) as excinfo:
        qgis_server()
    assert "qgis-server" in str(excinfo.value)


def test_a_build_without_the_bindings_refuses_a_host_by_name() -> None:
    with pytest.raises(QgisSdkUnsupportedCapabilityError):
        QgsServerHost(ServerHooks(()), support.ServerInterface())


# -- registration -------------------------------------------------------------------


def test_a_plugin_becomes_one_filter_one_service_and_one_access_object(
    wired: types.ModuleType,
) -> None:
    @filter(priority=10)
    def first(ctx: ServerContext, request, response):
        return None

    @filter(priority=20)
    def second(ctx: ServerContext, request, response):
        return None

    @service(name="SDKDEMO", version="1.0.0")
    def demo(ctx: ServerContext, request) -> ServerResponse:
        return ServerResponse.text("demo")

    @access_control(priority=30)
    def only_public(ctx: ServerContext, request, layer) -> bool:
        return True

    iface = support.ServerInterface()
    host = QgsServerHost(
        ServerHooks((first, second, demo, only_public)), iface
    ).register()

    # One chain for two filters, at the earliest priority either declares.
    assert list(iface.filters) == [10]
    assert len(iface.filters[10]) == 1
    assert host.filter is iface.filters[10][0]
    # One service, answering the SERVICE and VERSION it declares.
    assert [item.name() for item in iface.services] == ["SDKDEMO"]
    assert [item.version() for item in iface.services] == ["1.0.0"]
    assert host.services == tuple(iface.services)
    # One access-control object for the whole hook set.
    assert len(iface.access_controls[30]) == 1
    assert host.access_control is iface.access_controls[30][0]


def test_registering_twice_does_not_duplicate_the_objects(
    wired: types.ModuleType,
) -> None:
    @filter(priority=10)
    def first(ctx: ServerContext, request, response):
        return None

    iface = support.ServerInterface()
    host = QgsServerHost(ServerHooks((first,)), iface).register()
    host.register()

    assert len(iface.filters[10]) == 1


# -- the filter chain ----------------------------------------------------------------


def test_a_rewrite_reaches_the_request_the_qgis_services_read(
    wired: types.ModuleType,
) -> None:
    @filter(priority=10)
    def reroute(ctx: ServerContext, request, response):
        # A request built by hand rather than `with_params`: the model's helper
        # only ever merges values, while a filter that wants a parameter gone
        # returns a request without it.
        return ServerRequest(
            method=request.method,
            url=request.url,
            params={"SERVICE": "SDKDEMO", "KEEP": "1", "ADDED": "yes"},
        )

    iface = support.ServerInterface(
        support.Handler({"SERVICE": "WMS", "KEEP": "1", "GONE": "bye"})
    )
    host = QgsServerHost(ServerHooks((reroute,)), iface).register()

    assert host.filter.onRequestReady() is True
    assert iface.handler is not None
    assert iface.handler.params == {"SERVICE": "SDKDEMO", "KEEP": "1", "ADDED": "yes"}


def test_a_hook_that_passes_leaves_the_request_alone(wired: types.ModuleType) -> None:
    @filter(priority=10)
    def nothing(ctx: ServerContext, request, response):
        return None

    iface = support.ServerInterface(support.Handler({"SERVICE": "WMS"}))
    host = QgsServerHost(ServerHooks((nothing,)), iface).register()

    assert host.filter.onRequestReady() is True
    assert iface.handler is not None
    assert iface.handler.params == {"SERVICE": "WMS"}


def test_an_answer_is_written_over_the_error_that_stops_the_dispatch(
    wired: types.ModuleType,
) -> None:
    @filter(priority=10)
    def answer(ctx: ServerContext, request, response):
        return ServerResponse.text("answered", status=418)

    iface = support.ServerInterface(support.Handler({"SERVICE": "WMS"}))
    host = QgsServerHost(ServerHooks((answer,)), iface).register()

    host.filter.onRequestReady()

    assert iface.handler.exception is not None
    # Cleared after the exception wrote its OGC error, then the hook's body.
    assert iface.handler.cleared == 1
    assert iface.handler.status == 418
    assert iface.handler.body == b"answered"
    assert iface.handler.response_headers["Content-Type"].startswith("text/plain")


def test_the_hooks_are_handed_a_context_that_is_not_written_to_the_response_yet(
    wired: types.ModuleType,
) -> None:
    seen: list[Any] = []

    @filter(priority=10)
    def record(ctx: ServerContext, request, response):
        seen.append((ctx.host, ctx.request.param("SERVICE"), ctx.response.status))

    iface = support.ServerInterface(support.Handler({"SERVICE": "WMS"}))
    QgsServerHost(ServerHooks((record,)), iface).register()
    iface.filters[10][0].onRequestReady()

    assert seen == [(Host.SERVER, "WMS", 200)]


# -- the service ---------------------------------------------------------------------


def test_a_service_answers_into_the_qgis_response(wired: types.ModuleType) -> None:
    @service(name="SDKDEMO", version="1.0.0")
    def demo(ctx: ServerContext, request) -> ServerResponse:
        return ServerResponse.json({"service": request.param("SERVICE")}, status=201)

    iface = support.ServerInterface()
    host = QgsServerHost(ServerHooks((demo,)), iface).register()
    response = support.Response()

    host.services[0].executeRequest(support.Request({"SERVICE": "SDKDEMO"}), response)

    assert response.status == 201
    assert response.headers()["Content-Type"].startswith("application/json")
    assert response.body == b'{"service": "SDKDEMO"}'


def test_a_service_that_does_not_answer_is_refused_by_name(
    wired: types.ModuleType,
) -> None:
    @service(name="SDKDEMO", version="1.0.0")
    def demo(ctx: ServerContext, request) -> ServerResponse:
        return None  # type: ignore[return-value]

    iface = support.ServerInterface()
    host = QgsServerHost(ServerHooks((demo,)), iface).register()

    with pytest.raises(QgisSdkUnsupportedCapabilityError) as excinfo:
        host.services[0].executeRequest(
            support.Request({"SERVICE": "SDKDEMO"}), support.Response()
        )

    assert "ServerResponse" in str(excinfo.value)


# -- the access-control object --------------------------------------------------------


def test_an_access_hook_denies_by_clearing_every_permission(
    wired: types.ModuleType,
) -> None:
    @access_control(priority=10)
    def only_public(ctx: ServerContext, request, layer) -> bool:
        return layer != "secret"

    iface = support.ServerInterface(support.Handler({"LAYERS": "secret"}))
    host = QgsServerHost(ServerHooks((only_public,)), iface).register()

    allowed = host.access_control.layerPermissions(support.Layer("public"))
    refused = host.access_control.layerPermissions(support.Layer("secret"))

    assert allowed.canRead is True
    assert (refused.canRead, refused.canInsert, refused.canUpdate) == (
        False,
        False,
        False,
    )
    assert refused.canDelete is False


def test_an_access_hook_asked_outside_a_request_still_answers(
    wired: types.ModuleType,
) -> None:
    @access_control(priority=10)
    def only_public(ctx: ServerContext, request, layer) -> bool:
        return request.param("SERVICE") is None and layer == "public"

    iface = support.ServerInterface()  # no request in flight
    host = QgsServerHost(ServerHooks((only_public,)), iface).register()

    assert host.access_control.layerPermissions(support.Layer("public")).canRead is True
    assert (
        host.access_control.layerPermissions(support.Layer("secret")).canRead is False
    )


def test_every_access_hook_has_to_agree(wired: types.ModuleType) -> None:
    @access_control(priority=10)
    def allow(ctx: ServerContext, request, layer) -> bool:
        return True

    @access_control(priority=20)
    def deny(ctx: ServerContext, request, layer) -> bool:
        return False

    iface = support.ServerInterface(support.Handler({}))
    host = QgsServerHost(ServerHooks((allow, deny)), iface).register()

    assert host.access_control.layerPermissions(support.Layer("roads")).canRead is False


def test_the_access_object_keeps_qgis_from_caching_a_shaped_document(
    wired: types.ModuleType,
) -> None:
    """A layer decision must not be served from another request's cache.

    `QgsAccessControl::fillCacheKey` reads a non-empty `cacheKey()` as "this
    plugin's answer varies, do not reuse a capabilities document" - so the
    adapter answers with a key whenever an access hook exists. The cost is one
    capabilities render per request; the alternative is a document built for one
    caller answering another, which is a leak rather than a slow response.
    """

    @access_control(priority=10)
    def only_public(ctx: ServerContext, request, layer) -> bool:
        return True

    iface = support.ServerInterface(support.Handler({}))
    host = QgsServerHost(ServerHooks((only_public,)), iface).register()

    assert host.access_control.cacheKey() == NO_CAPABILITIES_CACHE
    assert NO_CAPABILITIES_CACHE

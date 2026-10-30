"""The QGIS Server host: hooks over one request, and the plain models they see.

A plugin that declares ``hosts = ["server"]`` is one plugin class loaded through
a generated ``serverClassFactory`` instead of ``classFactory``; the hooks below
are what it declares, and they run once per request on the server's thread
(decision-52).

Three hooks, each a plain function with the context injected first::

    from qgis_sdk.server import ServerContext, ServerRequest, ServerResponse
    from qgis_sdk.server import access_control, filter, service

    @filter(priority=20)
    def default_wms_version(ctx: ServerContext, request: ServerRequest,
                            response: ServerResponse):
        if request.param("VERSION") is None:
            return request.with_params(VERSION="1.3.0")
        return None

    @service(name="WMS")
    def capabilities(ctx: ServerContext, request: ServerRequest) -> ServerResponse:
        if request.param("REQUEST") != "GetCapabilities":
            return ServerResponse.denied("only GetCapabilities is served", status=400)
        return ServerResponse.xml(render(ctx))

    @access_control
    def parcels_are_internal(ctx: ServerContext, request: ServerRequest,
                             layer: str) -> bool:
        return layer != "parcels"

Nothing here imports QGIS or Qt: the adapter
(``qgis_sdk.adapters.qgis.server``) turns a hook into a ``QgsServerFilter``,
``QgsService`` or ``QgsAccessControlFilter`` and hands the same context to it, so
a test drives the same functions with ``qgis_sdk.testing.FakeServerInterface``
and no QGIS at all.
"""

from ._context import ServerContext
from ._hooks import (
    DEFAULT_PRIORITY,
    HOOK_SIGNATURES,
    HookDeclaration,
    HookKind,
    ServerHooks,
    access_control,
    filter,
    service,
)
from ._host import ServerHost, ServerInterface
from ._request import CaseInsensitiveMapping, ServerRequest
from ._response import ServerResponse

__all__ = [
    "DEFAULT_PRIORITY",
    "HOOK_SIGNATURES",
    "CaseInsensitiveMapping",
    "HookDeclaration",
    "HookKind",
    "ServerContext",
    "ServerHooks",
    "ServerHost",
    "ServerInterface",
    "ServerRequest",
    "ServerResponse",
    "access_control",
    "filter",
    "service",
]

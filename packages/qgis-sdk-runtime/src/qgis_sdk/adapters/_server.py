"""The QGIS Server half, as plain Python: read, write, register, serve.

Nothing in this module imports Qt at import time.

``QgsServerRequest``, ``QgsServerResponse`` and ``QgsRequestHandler`` exist only
inside a running server, but everything an adapter does with them is plain
attribute access: read the parameters, the headers and the body, write a status,
a header and a body, carry a filter's rewrite into the request the services will
read. Keeping that here rather than in
:mod:`qgis_sdk.adapters.qgis.server` makes the mapping testable on a machine with
no QGIS at all, against four lines of stand-in object - which is the part of an
adapter that goes wrong quietly.

Nothing here imports Qt: the objects are passed in, and this module only asks
them for the calls QGIS's own ``handleRequest`` makes.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from qgis_sdk.core.scope import ResourceScope
from qgis_sdk.models import QgisSdkUnsupportedCapabilityError
from qgis_sdk.server import (
    ServerContext,
    ServerHooks,
    ServerHost,
    ServerRequest,
    ServerResponse,
)

__all__ = [
    "UNKNOWN_METHOD",
    "QgsServerHost",
    "qgis_server",
    "request_from_handler",
    "rewrite_parameters",
    "sdk_request",
    "sdk_response",
    "stop_dispatch",
    "write",
]

#: What ``ServerRequest.method`` is when the host cannot know it: see
#: :func:`request_from_handler`. Empty rather than ``"GET"``, because a hook that
#: reads it and finds nothing can ask for the service path instead of trusting a
#: guess.
UNKNOWN_METHOD = ""


def sdk_request(qgs_request: Any) -> ServerRequest:
    """Read a ``QgsServerRequest`` as the immutable model a hook is handed."""
    return ServerRequest(
        method=str(qgs_request.__class__.methodToString(qgs_request.method())),
        url=str(qgs_request.url().toString()),
        params=dict(qgs_request.serverParameters().toMap()),
        headers=dict(qgs_request.headers()),
        body=bytes(qgs_request.data() or b""),
    )


def request_from_handler(handler: Any) -> ServerRequest:
    """Read the request behind a ``QgsRequestHandler``, which is the filter path.

    QGIS fills the handler's parameter map from the query string and from a
    ``POST`` body before any plugin runs, so this is the request its services
    will see. The verb is not available here; :data:`UNKNOWN_METHOD` says so
    rather than a plausible guess.
    """
    return ServerRequest(
        method=UNKNOWN_METHOD,
        url=str(handler.url()),
        params=dict(handler.parameterMap()),
        headers=dict(handler.requestHeaders()),
    )


def sdk_response(qgs_response: Any) -> ServerResponse:
    """Read a ``QgsServerResponse`` as the model a hook writes."""
    response = ServerResponse(status=int(qgs_response.statusCode()))
    headers = {str(name): str(value) for name, value in qgs_response.headers().items()}
    if headers:
        response.headers = type(response.headers)(headers)
    body = bytes(qgs_response.data() or b"")
    if body:
        response.body = body
    return response


def write(target: Any, response: ServerResponse) -> None:
    """Write an SDK response into whatever the host holds.

    A ``QgsServerResponse`` (the service path) carries status, headers and a body
    the same way a ``QgsRequestHandler`` (the filter path) does, under two sets of
    names, so one writer serves both call sites.
    """
    target.setStatusCode(int(response.status))
    set_header = getattr(target, "setHeader", None) or target.setResponseHeader
    for name, value in response.headers.items():
        set_header(name, value)
    if response.body:
        append = getattr(target, "write", None) or target.appendBody
        append(response.body)


def rewrite_parameters(
    handler: Any, before: ServerRequest, after: ServerRequest
) -> None:
    """Carry a filter's rewrite into the request QGIS's own services will read.

    A filter returns a *new* :class:`~qgis_sdk.server.ServerRequest`; the object
    QGIS's services read is the handler's parameter map, so the difference between
    the two is what has to be written back: an entry whose value changed, an entry
    a filter added, and an entry a filter dropped.
    """
    for name in before.params:
        if after.params.get(name) is None:
            handler.removeParameter(name)
    for name, value in after.params.items():
        if before.params.get(name) != value:
            handler.setParameter(name, value)


def stop_dispatch(server: Any, handler: Any) -> bool:
    """Tell QGIS to skip its own services for a request a filter answered.

    ``setServiceException`` is the switch the C++ dispatcher checks, and it
    writes an OGC error as it sets it, so the caller clears the response right
    afterwards and writes the hook's answer over it.
    """
    exception = getattr(server, "QgsMapServiceException", None)
    if exception is None:  # pragma: no cover - depends on the build
        return False
    try:
        handler.setServiceException(
            exception("SdkAnswer", "answered by a @server.filter hook")
        )
    except (TypeError, ValueError):  # pragma: no cover - depends on the build
        return False
    return True


def qgis_server() -> Any:
    """``qgis.server``, imported when a server host is actually built.

    A QGIS built without server bindings has no such module, and the error the
    author gets has to name the build they need and how to get it, because the
    environment is the problem - not their plugin (decision-52).
    """
    try:
        from qgis import server
    except ImportError as error:
        raise QgisSdkUnsupportedCapabilityError(
            "the server host needs a QGIS built with server bindings "
            f"(`import qgis.server` failed: {error}). Install `qgis-server` and "
            "`python3-qgis` from the qgis.org or Debian repositories, or build "
            "QGIS with -DWITH_SERVER=ON -DWITH_BINDINGS=ON; conda-forge builds "
            "QGIS without server support (decision-52)."
        ) from error
    return server


# -- the host --------------------------------------------------------------------


# -- the host --------------------------------------------------------------------


class QgsServerHost:
    """One plugin's hooks, registered on a live ``QgsServerInterface``.

    The object is both the SDK-side :class:`~qgis_sdk.server.ServerInterface`
    (``register_filter`` and the two beside it) and the owner of the QGIS objects
    those calls create: one filter that runs the whole filter chain, one
    ``QgsService`` per declared service, and one access-control object that
    answers QGIS's per-layer questions with the plugin's access hooks.
    """

    __slots__ = ("_access", "_filter", "_host", "_iface", "_server", "_services")

    def __init__(
        self,
        hooks: ServerHooks,
        server_interface: Any,
        *,
        context_factory: (
            Callable[[ResourceScope, ServerRequest, ServerResponse], ServerContext]
            | None
        ) = None,
    ) -> None:
        self._server = qgis_server()
        self._iface = server_interface
        self._filter: Any = None
        self._access: Any = None
        self._services: list[Any] = []
        self._host = ServerHost(hooks, self, context_factory=context_factory)

    # -- what a plugin loader calls ----------------------------------------------

    def register(self) -> QgsServerHost:
        """Register every hook with QGIS once; returns this host for chaining."""
        self._host.register()
        return self

    @property
    def host(self) -> ServerHost:
        """The dispatcher these QGIS objects call into."""
        return self._host

    @property
    def hooks(self) -> ServerHooks:
        """The hooks this host serves."""
        return self._host.hooks

    @property
    def server(self) -> Any:
        """The ``qgis.server`` module this host was built from."""
        return self._server

    @property
    def filter(self) -> Any:
        """The ``QgsServerFilter`` that runs the filter chain, once registered."""
        return self._filter

    @property
    def access_control(self) -> Any:
        """The ``QgsAccessControlFilter`` that runs the access hooks, once registered."""
        return self._access

    @property
    def services(self) -> tuple[Any, ...]:
        """The ``QgsService`` objects this host registered, in declaration order."""
        return tuple(self._services)

    # -- ServerInterface, as ServerHost calls it ----------------------------------

    def register_filter(
        self, name: str, hook: Callable[..., Any], priority: int
    ) -> None:
        """Register the chain filter, once, at the lowest declared priority.

        The SDK fixes the order of its own filters - priority, then declaration
        order, then include order - so QGIS needs one position for the whole
        chain: the earliest priority any of those filters declares. Filters from
        other plugins still interleave at their own priorities.
        """
        if self._filter is not None:
            return
        self._filter = _object(
            self._server.QgsServerFilter,
            f"{name}FilterChain",
            ("onRequestReady", "onResponseComplete"),
            {
                "onRequestReady": _on_request_ready,
                "onResponseComplete": _on_complete,
            },
            (self._iface,),
            _qgis_sdk_host=self,
        )
        self._iface.registerFilter(self._filter, int(priority))

    def register_service(
        self, name: str, version: str, handler: Callable[..., Any]
    ) -> None:
        """Register one ``QgsService`` for the ``SERVICE`` it answers."""
        service = _object(
            self._server.QgsService,
            f"{name}Service",
            ("name", "version", "executeRequest"),
            {
                "name": _service_name,
                "version": _service_version,
                "executeRequest": _execute_request,
            },
            (),
            _qgis_sdk_host=self,
            _qgis_sdk_hook=handler,
            _qgis_sdk_service_name=str(name),
            _qgis_sdk_service_version=str(version),
        )
        self._services.append(service)
        self._iface.serviceRegistry().registerService(service)

    def register_access_control(
        self, name: str, hook: Callable[..., Any], priority: int
    ) -> None:
        """Register the access-control object, once, running every access hook."""
        if self._access is not None:
            return
        self._access = _object(
            self._server.QgsAccessControlFilter,
            f"{name}AccessControl",
            ("cacheKey", "layerPermissions"),
            {"cacheKey": _cache_key, "layerPermissions": _layer_permissions},
            (self._iface,),
            _qgis_sdk_host=self,
        )
        self._iface.registerAccessControl(self._access, int(priority))

    # -- what the QGIS objects call ------------------------------------------------

    def serve_filter(self, qgs_filter: Any) -> bool:
        """Run the filter chain for one request; ``False`` stops the SDK chain."""
        handler = qgs_filter.serverInterface().requestHandler()
        if handler is None:  # pragma: no cover - QGIS always sets it first
            return True
        request = request_from_handler(handler)
        response = ServerResponse()
        scope = ResourceScope()
        try:
            context = self._host.context(scope, request, response)
            outcome = self._host.rewrite(context, request, response)
        finally:
            scope.close()
        if isinstance(outcome, ServerResponse):
            # `setServiceException` is what makes the C++ dispatcher skip its own
            # services; it writes an OGC error as it does, so the handler is
            # cleared and the hook's answer written over it. The return value
            # stays True: stopping the *other* plugins' filters is not this
            # plugin's decision.
            stop_dispatch(self._server, handler)
            handler.clear()
            write(handler, outcome)
            return True
        rewrite_parameters(handler, request, outcome)
        return True

    def serve_service(
        self, hook: Callable[..., Any], qgs_request: Any, qgs_response: Any
    ) -> None:
        """Answer one request with the service hook QGIS dispatched to."""
        request = sdk_request(qgs_request)
        response = ServerResponse()
        scope = ResourceScope()
        try:
            context = self._host.context(scope, request, response)
            answer = hook(context, request)
        finally:
            scope.close()
        if not isinstance(answer, ServerResponse):
            raise QgisSdkUnsupportedCapabilityError(
                f"@server.service `{getattr(hook, '__name__', hook)}` returned "
                f"{type(answer).__name__}; a service answers with a "
                "ServerResponse"
            )
        qgs_response.clear()
        write(qgs_response, answer)

    def permits(self, qgs_filter: Any, layer: Any) -> bool:
        """Ask the access hooks about one layer, in the middle of a request.

        QGIS asks per layer while a service renders, and another plugin may ask
        at any time - including outside a request, where the interface holds no
        request handler. Then the hooks see an empty request rather than a
        traceback, because a permission question is still answerable.
        """
        handler = qgs_filter.serverInterface().requestHandler()
        request = (
            request_from_handler(handler) if handler is not None else _no_request()
        )
        scope = ResourceScope()
        try:
            context = self._host.context(scope, request, ServerResponse())
            return self._host.permits(context, request, str(layer.name()))
        finally:
            scope.close()

    def __repr__(self) -> str:
        return f"QgsServerHost({self._host!r})"


def _object(
    base: type,
    name: str,
    slots: tuple[str, ...],
    methods: dict[str, Callable[..., Any]],
    arguments: tuple[Any, ...],
    **state: Any,
) -> Any:
    """Build one QGIS plugin object and give it the state its slots need.

    The subclass is made with :func:`type` so the constructor stays QGIS's own -
    a ``QgsServerFilter`` and an access-control object take the
    ``QgsServerInterface``, a ``QgsService`` takes nothing - and the plugin state
    is attached afterwards. ``slots`` are the C++ virtuals this subclass overrides; naming
    them keeps a typo in a method name from silently doing nothing.
    """
    missing = set(slots) - set(methods)
    if missing:  # pragma: no cover - a programming error, not a runtime state
        raise TypeError(f"{name} declares no override for {sorted(missing)}")
    instance = type(name, (base,), methods)(*arguments)
    for attribute, value in state.items():
        setattr(instance, attribute, value)
    return instance


def _no_request() -> ServerRequest:
    """The request an access hook sees when QGIS asks outside one."""
    return ServerRequest(method="", url="")


def _on_request_ready(self: Any) -> bool:
    """The chain's slot: rewrites reach QGIS's services, answers stop them."""
    return self._qgis_sdk_host.serve_filter(self)


def _on_complete(self: Any) -> bool:
    """Nothing to add once the services ran: the response is already written."""
    return True


def _service_name(self: Any) -> str:
    return self._qgis_sdk_service_name


def _service_version(self: Any) -> str:
    return self._qgis_sdk_service_version


def _execute_request(
    self: Any, request: Any, response: Any, project: Any = None
) -> None:
    """The service's slot: one hook answers the ``SERVICE`` this object names."""
    self._qgis_sdk_host.serve_service(self._qgis_sdk_hook, request, response)


#: What the access-control object answers ``cacheKey()`` with. Non-empty on
#: purpose: `QgsAccessControl::fillCacheKey` reads a non-empty key as "this
#: plugin's answer varies, do not reuse a capabilities document", and a
#: per-request layer decision served from a cache built for another request is a
#: leak, not a performance win.
NO_CAPABILITIES_CACHE = "qgis-sdk:access-control"


def _cache_key(self: Any) -> str:
    """Keep QGIS from caching a capabilities document an access hook shaped."""
    return NO_CAPABILITIES_CACHE


def _layer_permissions(self: Any, layer: Any) -> Any:
    """The access hook's slot: a refusal is every permission, a pass is QGIS's."""
    access = self._qgis_sdk_host.server.QgsAccessControlFilter
    if self._qgis_sdk_host.permits(self, layer):
        return access.layerPermissions(self, layer)
    permissions = access.LayerPermissions()
    permissions.canRead = False
    permissions.canInsert = False
    permissions.canUpdate = False
    permissions.canDelete = False
    return permissions

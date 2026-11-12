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
from typing import TYPE_CHECKING, Any

from qgis_sdk.core.scope import ResourceScope
from qgis_sdk.models import QgisSdkUnsupportedCapabilityError
from qgis_sdk.server import (
    ServerHooks,
    ServerHost,
    ServerRequest,
    ServerResponse,
)

if TYPE_CHECKING:
    from qgis_sdk.adapters._server._host import QgsServerHost

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


class QgsServerHostMixin1:
    # -- what a plugin loader calls ----------------------------------------------

    def register(self) -> QgsServerHost:
        """Register every hook with QGIS once; returns this host for chaining."""
        self._host.register()
        return self

    def rebind(self, hooks: ServerHooks) -> QgsServerHost:
        """Serve ``hooks`` through the registration QGIS already holds.

        QGIS Server hands out ``registerFilter``, ``registerService`` and
        ``registerAccessControl`` and no way to withdraw any of them, so a
        development loop that reloads a plugin cannot register twice: it hands
        the objects QGIS holds a new hook set instead. What it *cannot* do is
        change their identity, because that is what the registration froze - the
        filter's position among the other plugins' filters and the
        ``SERVICE``/version each ``QgsService`` answers. A hook set that moves
        either is refused, and the caller starts a new host instead.
        """
        from ._host import shape, shape_difference

        before = shape(self._host.hooks)
        after = shape(hooks)
        if after != before:
            raise QgisSdkUnsupportedCapabilityError(
                "server registration",
                f"the reloaded hooks do not fit what QGIS registered "
                f"({shape_difference(before, after)}); a filter priority and a "
                "service name or version are fixed at registration, so start a "
                "new host for this revision",
            )
        self._host = ServerHost(
            hooks, self, context_factory=self._context_factory, jobs=self._jobs
        )
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
        from ._host import object, on_complete, on_request_ready

        if self._filter is not None:
            return
        self._filter = object(
            self._server.QgsServerFilter,
            f"{name}FilterChain",
            ("onRequestReady", "onResponseComplete"),
            {
                "onRequestReady": on_request_ready,
                "onResponseComplete": on_complete,
            },
            (self._iface,),
            _qgis_sdk_host=self,
        )
        self._iface.registerFilter(self._filter, int(priority))

    def register_service(
        self, name: str, version: str, handler: Callable[..., Any]
    ) -> None:
        """Register one ``QgsService`` for the ``SERVICE`` it answers."""
        from ._host import execute_request, object, service_name, service_version

        service = object(
            self._server.QgsService,
            f"{name}Service",
            ("name", "version", "executeRequest"),
            {
                "name": service_name,
                "version": service_version,
                "executeRequest": execute_request,
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
        from ._host import cache_key, layer_permissions, object

        self._access = object(
            self._server.QgsAccessControlFilter,
            f"{name}AccessControl",
            ("cacheKey", "layerPermissions"),
            {"cacheKey": cache_key, "layerPermissions": layer_permissions},
            (self._iface,),
            _qgis_sdk_host=self,
        )
        self._iface.registerAccessControl(self._access, int(priority))

    def current_service(self, name: str, version: str) -> Callable[..., Any]:
        """The service hook ``name``/``version`` names, as the host holds it now."""
        for declaration, hook in self._host.hooks.services:
            if (declaration.name or "").casefold() != str(name).casefold():
                continue
            if (declaration.version or "") == str(version):
                return hook
        raise QgisSdkUnsupportedCapabilityError(
            "server registration",
            f"no @server.service answers SERVICE={name!r} version {version!r}; "
            "the registration QGIS holds cannot be given a new one",
        )

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
            self._host.tick()
            context = self._host.context(scope, request, response)
            outcome = self._host.rewrite(context, request, response)
        finally:
            # The response exists once the chain returned, so this is the moment
            # decision-52 abandons the request's jobs: closing the scope is the
            # zero-deadline quiesce - nothing here waits for a worker.
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

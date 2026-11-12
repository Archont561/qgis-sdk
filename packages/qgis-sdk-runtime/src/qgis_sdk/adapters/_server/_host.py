from __future__ import annotations

from collections.abc import Callable
from typing import Any

from qgis_sdk._published import REQUIRED, published
from qgis_sdk.core.scope import ResourceScope
from qgis_sdk.jobs import JobService
from qgis_sdk.models import QgisSdkUnsupportedCapabilityError
from qgis_sdk.server import (
    ServerContext,
    ServerHooks,
    ServerHost,
    ServerRequest,
    ServerResponse,
)

from ._requests import (
    QgsServerHostMixin1,
    qgis_server,
    request_from_handler,
    sdk_request,
    write,
)


class _QgsServerHostMixin2:
    def serve_service(
        self, hook: Callable[..., Any], qgs_request: Any, qgs_response: Any
    ) -> None:
        """Answer one request with the service hook QGIS dispatched to."""
        request = sdk_request(qgs_request)
        response = ServerResponse()
        scope = ResourceScope()
        try:
            self._host.tick()
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


class QgsServerHost(QgsServerHostMixin1, _QgsServerHostMixin2):
    """One plugin's hooks, registered on a live ``QgsServerInterface``.

    The object is both the SDK-side :class:`~qgis_sdk.server.ServerInterface`
    (``register_filter`` and the two beside it) and the owner of the QGIS objects
    those calls create: one filter that runs the whole filter chain, one
    ``QgsService`` per declared service, and one access-control object that
    answers QGIS's per-layer questions with the plugin's access hooks.
    """

    __slots__ = (
        "_access",
        "_context_factory",
        "_filter",
        "_host",
        "_iface",
        "_jobs",
        "_server",
        "_services",
    )

    def __init__(
        self,
        hooks: ServerHooks,
        server_interface: Any,
        *,
        context_factory: (
            Callable[[ResourceScope, ServerRequest, ServerResponse], ServerContext]
            | None
        ) = None,
        jobs: JobService | None = None,
    ) -> None:
        self._server = qgis_server()
        self._iface = server_interface
        self._filter: Any = None
        self._access: Any = None
        self._services: list[Any] = []
        self._context_factory = context_factory
        self._jobs = jobs
        self._host = ServerHost(hooks, self, context_factory=context_factory, jobs=jobs)

    def __repr__(self) -> str:
        return f"QgsServerHost({self._host!r})"


def shape(
    hooks: ServerHooks,
) -> tuple[tuple[tuple[str, str], ...], int | None, int | None]:
    """What a registration froze: one service per identity, two chain positions."""
    services = tuple(
        (declaration.name or "", declaration.version or "")
        for declaration, _ in hooks.services
    )
    filters = [hooks.declaration(hook).priority for hook in hooks.filters]
    access = [hooks.declaration(hook).priority for hook in hooks.access_control]
    return services, min(filters, default=None), min(access, default=None)


def shape_difference(before: tuple[Any, ...], after: tuple[Any, ...]) -> str:
    """Name the part of the registration that moved, rather than both shapes."""
    names = ("services", "filter priority", "access-control priority")
    moved = [
        name for name, old, new in zip(names, before, after, strict=True) if old != new
    ]
    return ", ".join(moved) if moved else "nothing"


_CC_SPECS_object_1 = (
    ("base", type, REQUIRED, "positional"),
    ("name", str, REQUIRED, "positional"),
    ("slots", tuple[str, ...], REQUIRED, "positional"),
    ("methods", dict[str, Callable[..., Any]], REQUIRED, "positional"),
    ("arguments", tuple[Any, ...], REQUIRED, "positional"),
    ("state", Any, REQUIRED, "var_keyword"),
)


@published(_CC_SPECS_object_1, returns=Any)
def object(_published_values):
    """Build one QGIS plugin object and give it the state its slots need.

    The subclass is made with :func:`type` so the constructor stays QGIS's own -
    a ``QgsServerFilter`` and an access-control object take the
    ``QgsServerInterface``, a ``QgsService`` takes nothing - and the plugin state
    is attached afterwards. ``slots`` are the C++ virtuals this subclass overrides; naming
    them keeps a typo in a method name from silently doing nothing.
    """
    missing = set(_published_values.slots) - set(_published_values.methods)
    if missing:  # pragma: no cover - a programming error, not a runtime state
        raise TypeError(
            f"{_published_values.name} declares no override for {sorted(missing)}"
        )
    instance = type(
        _published_values.name, (_published_values.base,), _published_values.methods
    )(*_published_values.arguments)
    for attribute, value in _published_values.state.items():
        setattr(instance, attribute, value)
    return instance


def _no_request() -> ServerRequest:
    """The request an access hook sees when QGIS asks outside one."""
    return ServerRequest(method="", url="")


def on_request_ready(self: Any) -> bool:
    """The chain's slot: rewrites reach QGIS's services, answers stop them."""
    return self._qgis_sdk_host.serve_filter(self)


def on_complete(self: Any) -> bool:
    """Nothing to add once the services ran: the response is already written."""
    return True


def service_name(self: Any) -> str:
    return self._qgis_sdk_service_name


def service_version(self: Any) -> str:
    return self._qgis_sdk_service_version


def execute_request(
    self: Any, request: Any, response: Any, project: Any = None
) -> None:
    """The service's slot: the hook this object names, as the host holds it now.

    The lookup is by identity rather than by the function captured at
    registration, because :meth:`QgsServerHost.rebind` swaps the hook set under a
    registration that QGIS keeps - a service whose body was edited has to answer
    with the edited body on the next request.
    """
    host = self._qgis_sdk_host
    hook = host.current_service(
        self._qgis_sdk_service_name, self._qgis_sdk_service_version
    )
    host.serve_service(hook, request, response)


NO_CAPABILITIES_CACHE = "qgis-sdk:access-control"


def cache_key(self: Any) -> str:
    """Keep QGIS from caching a capabilities document an access hook shaped."""
    return NO_CAPABILITIES_CACHE


def layer_permissions(self: Any, layer: Any) -> Any:
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

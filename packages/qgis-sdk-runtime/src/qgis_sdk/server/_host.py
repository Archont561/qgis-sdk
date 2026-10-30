"""``ServerHost``: register the hooks, then serve one request at a time.

This is the half of the server host that can be tested without QGIS: it takes
the declared hooks, registers them with whatever object plays
``QgsServerInterface`` (the real one in ``qgis_sdk.adapters.qgis.server``, the
scripted one in ``qgis_sdk.testing``), and serves a request through them in the
order decision-69 fixes.

Serving is deliberately linear. A filter returns ``None`` to pass the request
on, a :class:`~qgis_sdk.server.ServerRequest` to rewrite what the hooks after it
see, or a :class:`~qgis_sdk.server.ServerResponse` to answer it and stop; the
service whose name matches the ``SERVICE`` parameter answers next; the access
hooks then rule on each requested layer, and a refusal is a 403 naming the layer
rather than a silently filtered map. No step of that is allowed to wait for a
thread: the scope closes when the response exists, and a job a hook submitted is
request-scoped and abandoned with it (decision-52).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from qgis_sdk.core.scope import ResourceScope
from qgis_sdk.models import QgisSdkUnsupportedCapabilityError
from qgis_sdk.services import Layers, Log, Project

from ._context import ServerContext
from ._hooks import HookDeclaration, ServerHooks
from ._request import ServerRequest
from ._response import ServerResponse

__all__ = ["ServerHost", "ServerInterface"]


class ServerInterface(Protocol):
    """What the host needs of a ``QgsServerInterface``, and all it needs.

    The real object lives in the adapter and the scripted one in
    ``qgis_sdk.testing``; both are registered with the same three calls, so the
    dispatcher below is the same code in a test and in a deployed server.
    """

    def register_filter(
        self,
        name: str,
        hook: Callable[..., Any],
        priority: int,
    ) -> None:
        """Register a request hook under ``name`` at ``priority``."""

    def register_service(
        self,
        name: str,
        version: str,
        handler: Callable[..., Any],
    ) -> None:
        """Register the handler of the OGC service ``name`` at ``version``."""

    def register_access_control(
        self,
        name: str,
        hook: Callable[..., Any],
        priority: int,
    ) -> None:
        """Register a layer permission hook under ``name`` at ``priority``."""


class ServerHost:
    """The hooks of one plugin, registered once and served request by request.

    ``context_factory`` is how a host adds the services a request's project
    makes possible: it is called with the scope, the request and the response
    and returns the :class:`ServerContext` the hooks receive. Without one the
    context carries the request and the response and refuses ``project``,
    ``layers`` and ``log`` by name, which is what a capabilities-only
    deployment needs.
    """

    __slots__ = ("_context_factory", "_hooks", "_interface", "_registered")

    def __init__(
        self,
        hooks: ServerHooks,
        interface: ServerInterface,
        *,
        context_factory: (
            Callable[[ResourceScope, ServerRequest, ServerResponse], ServerContext]
            | None
        ) = None,
    ) -> None:
        self._hooks = hooks
        self._interface = interface
        self._context_factory = context_factory
        self._registered = False

    @property
    def hooks(self) -> ServerHooks:
        """The hooks this host serves, in the order it serves them."""
        return self._hooks

    def register(self) -> None:
        """Register every hook with the interface once; a second call is a no-op."""
        if self._registered:
            return
        for hook in self._hooks.filters:
            declaration = _declaration_of(hook, "filter")
            self._interface.register_filter(hook.__name__, hook, declaration.priority)
        for declaration, hook in self._hooks.services:
            self._interface.register_service(
                declaration.name or hook.__name__,
                declaration.version or "1.0.0",
                hook,
            )
        for hook in self._hooks.access_control:
            declaration = _declaration_of(hook, "access_control")
            self._interface.register_access_control(
                hook.__name__, hook, declaration.priority
            )
        self._registered = True

    def handle(
        self,
        request: ServerRequest,
        *,
        scope: ResourceScope | None = None,
        project: Project | None = None,
        layers: Layers | None = None,
        log: Log | None = None,
    ) -> ServerResponse:
        """Serve one request and return the response the host will send.

        ``scope`` is the request scope; the caller owns it and closes it when the
        response is sent, because a request-scoped job must be abandoned at the
        same moment (decision-52). A host that passes none gets a scope opened
        and closed inside this call.
        """
        owned = scope is None
        if scope is None:
            scope = ResourceScope()
        try:
            response = ServerResponse()
            context = self._context(
                scope, request, response, project=project, layers=layers, log=log
            )
            return self._serve(context, request, response)
        finally:
            if owned:
                scope.close()

    # -- serving -----------------------------------------------------------------

    def _serve(
        self,
        context: ServerContext,
        request: ServerRequest,
        response: ServerResponse,
    ) -> ServerResponse:
        current = request
        for hook in self._hooks.filters:
            outcome = hook(context, current, response)
            if isinstance(outcome, ServerResponse):
                return outcome
            if isinstance(outcome, ServerRequest):
                current = outcome
            elif outcome is not None:
                raise QgisSdkUnsupportedCapabilityError(
                    f"@server.filter `{hook.__name__}` returned "
                    f"{type(outcome).__name__}; return None to pass, a "
                    "ServerRequest to rewrite or a ServerResponse to answer"
                )
        # A refusal beats the answer: an access hook that denies a layer stops
        # the request before any service renders it (decision-52).
        denied = self._denied_layer(context, current)
        if denied is not None:
            return denied
        service = self._service_for(current)
        if service is not None:
            answer = service(context, current)
            if not isinstance(answer, ServerResponse):
                raise QgisSdkUnsupportedCapabilityError(
                    f"@server.service `{service.__name__}` returned "
                    f"{type(answer).__name__}; a service answers with a "
                    "ServerResponse"
                )
            return answer
        return context.response.write_text(
            f"SERVICE {current.param('SERVICE') or '(missing)'!r} is not served "
            "by this plugin",
            status=400,
        )

    def _service_for(self, request: ServerRequest) -> Callable[..., Any] | None:
        requested = (request.param("SERVICE") or "").replace("_", "").upper()
        if not requested:
            return None
        for declaration, hook in self._hooks.services:
            if (declaration.name or "").replace("_", "").upper() == requested:
                return hook
        return None

    def _denied_layer(
        self, context: ServerContext, request: ServerRequest
    ) -> ServerResponse | None:
        """Ask every access-control hook about every requested layer."""
        if not self._hooks.access_control:
            return None
        requested = request.param("LAYERS") or request.param("LAYER") or ""
        for layer in (name.strip() for name in requested.split(",")):
            if not layer:
                continue
            for hook in self._hooks.access_control:
                if hook(context, request, layer):
                    continue
                # A hook that wants its own refusal writes it to ctx.response;
                # otherwise the host builds the plain 403 that names the layer.
                if context.response.body or context.response.status != 200:
                    return context.response
                return ServerResponse.denied(
                    f"layer {layer!r} is not available to this request"
                )
        return None

    def _context(
        self,
        scope: ResourceScope,
        request: ServerRequest,
        response: ServerResponse,
        *,
        project: Project | None,
        layers: Layers | None,
        log: Log | None,
    ) -> ServerContext:
        if self._context_factory is not None:
            return self._context_factory(scope, request, response)
        if project is None and layers is None and log is None:
            return ServerContext(scope, request, response)
        return ServerContext(
            scope, request, response, project=project, layers=layers, log=log
        )

    def __repr__(self) -> str:
        state = "registered" if self._registered else "unregistered"
        return f"ServerHost({self._hooks!r}, {state})"


def _declaration_of(hook: Callable[..., Any], kind: str) -> HookDeclaration:
    declaration = getattr(hook, "__qgis_sdk_server_hook__", None)
    if not isinstance(declaration, HookDeclaration) or declaration.kind != kind:
        raise QgisSdkUnsupportedCapabilityError(
            f"{getattr(hook, '__name__', hook)!r} is not a @server.{kind} hook"
        )
    return declaration

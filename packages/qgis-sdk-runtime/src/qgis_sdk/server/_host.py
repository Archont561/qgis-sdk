"""``ServerHost``: register the hooks, then serve one request at a time.

This is the half of the server host that can be tested without QGIS: it takes
the declared hooks, registers them with whatever object plays
``QgsServerInterface``, and serves a request through them in the order
decision-69 fixes. Serving is deliberately linear - a filter passes, rewrites
or answers, the matching service answers next, and the access hooks then rule
on each requested layer - and no step of it waits for a thread: the scope
closes when the response exists, so a job a hook submitted is request-scoped
and abandoned with it (decision-52).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypedDict, Unpack

from qgis_sdk._published import REQUIRED, published
from qgis_sdk.core.scope import ResourceScope
from qgis_sdk.jobs import Jobs, JobService
from qgis_sdk.models import QgisSdkUnsupportedCapabilityError
from qgis_sdk.services import Layers, Log, Project

from ._context import ServerContext, ServerServices
from ._hooks import ServerHooks, declaration_of
from ._interface import ServerInterface
from ._phases import (
    EarlyAnswer,
    ServeState,
    requested_layers,
    serve_filters,
    serve_service,
    serve_unserved,
)
from ._request import ServerRequest
from ._response import ServerResponse

__all__ = ["ServerHost"]


class _ServerHostRegistration:
    """Registering the declared hooks, and the one call a host makes per request."""

    @property
    def hooks(self) -> ServerHooks:
        """The hooks this host serves, in the order it serves them."""
        return self._hooks

    @property
    def jobs(self) -> JobService | None:
        """The plugin-lifetime job service this host derives request work from."""
        return self._jobs

    def tick(self) -> int:
        """Advance the job service one step; the host does this at request start.

        A server has no event loop and no job pump, so the request is the clock:
        one tick here lets a job submitted by an earlier request start, and a
        job submitted now is abandoned rather than kept waiting for a next tick
        that may never come (decision-52). Without a job service this is a
        no-op, so a deployment that has none pays nothing.
        """
        return 0 if self._jobs is None else self._jobs.tick()

    def register(self) -> None:
        """Register every hook with the interface once; a second call is a no-op."""
        if self._registered:
            return
        for hook in self._hooks.filters:
            declaration = declaration_of(hook, "filter")
            self._interface.register_filter(hook.__name__, hook, declaration.priority)
        for declaration, hook in self._hooks.services:
            self._interface.register_service(
                declaration.name or hook.__name__,
                declaration.version or "1.0.0",
                hook,
            )
        for hook in self._hooks.access_control:
            declaration = declaration_of(hook, "access_control")
            self._interface.register_access_control(
                hook.__name__, hook, declaration.priority
            )
        self._registered = True

    _CC_SPECS_handle_1 = (
        ("self", REQUIRED, REQUIRED, "positional"),
        ("request", ServerRequest, REQUIRED, "positional"),
        ("scope", ResourceScope | None, None, "keyword"),
        ("project", Project | None, None, "keyword"),
        ("layers", Layers | None, None, "keyword"),
        ("log", Log | None, None, "keyword"),
    )

    @published(_CC_SPECS_handle_1, returns=ServerResponse)
    def handle(_published_values):
        """Serve one request and return the response the host will send.

        ``scope`` is the request scope; the caller owns it and closes it when the
        response is sent, because a request-scoped job must be abandoned at the
        same moment (decision-52). A host that passes none gets a scope opened
        and closed inside this call.

        Args:
            request: The request, as the host received it.
            scope: The request scope, or ``None`` to open one here.
            project: The project the request loaded, if the host has one.
            layers: The layers service for it.
            log: The log the request writes to.
        """
        values = _published_values
        owned = values.scope is None
        if values.scope is None:
            values.scope = ResourceScope()
        try:
            values.self.tick()
            response = ServerResponse()
            context = _request_context(values.self, values, response)
            return values.self.serve(context, values.request, response)
        finally:
            if owned:
                values.scope.close()


class _ServerHostDispatch:
    """The steps one request is served in, in the order the host runs them."""

    # -- serving -----------------------------------------------------------------

    def serve(
        self,
        context: ServerContext,
        request: ServerRequest,
        response: ServerResponse,
    ) -> ServerResponse:
        """Serve one request through every declared hook, in the fixed order.

        The pieces below are public because a host that is not this dispatcher
        - QGIS Server calls a filter, a service and an access-control object at
        three different moments of one request - has to run the same steps one
        at a time and in this order, not a second implementation of them.

        Args:
            context: The context the hooks receive.
            request: The request being served.
            response: The response being built.

        Returns:
            The answer, whether a hook wrote it or the service did.
        """
        _s = ServeState(self=self, context=context, request=request, response=response)
        for _p in (serve_filters, serve_service, serve_unserved):
            _r = _p(_s)
            if isinstance(_r, EarlyAnswer):
                return _r.value
        return None

    def rewrite(
        self,
        context: ServerContext,
        request: ServerRequest,
        response: ServerResponse,
    ) -> ServerRequest | ServerResponse:
        """Run the filters; return the rewritten request or a hook's answer.

        ``None`` from a filter means "pass this request on unchanged", a
        ``ServerRequest`` means "the hooks after me see this one", and a
        ``ServerResponse`` means "answer the request, run nothing else".

        Args:
            context: The context the hooks receive.
            request: The request being served.
            response: The response being built.

        Raises:
            QgisSdkUnsupportedCapabilityError: A filter returned something else.
        """
        current = request
        for hook in self._hooks.filters:
            outcome = hook(context, current, response)
            if isinstance(outcome, ServerResponse):
                return outcome
            if isinstance(outcome, ServerRequest):
                current = outcome
            elif outcome is not None:
                raise _filter_return_refused(hook, outcome)
        return current

    def denied_layer(
        self, context: ServerContext, request: ServerRequest
    ) -> ServerResponse | None:
        """Ask every access-control hook about every requested layer.

        A refusal beats the answer: a hook that denies a layer stops the request
        before any service renders it (decision-52), and the response names the
        layer instead of passing a silently filtered map.

        Args:
            context: The context the hooks receive.
            request: The request, whose ``LAYERS`` name what to rule on.

        Returns:
            The refusal, or ``None`` when every layer is allowed.
        """
        if not self._hooks.access_control:
            return None
        for layer in requested_layers(request):
            if self.permits(context, request, layer):
                continue
            # A hook that wants its own refusal writes it to ctx.response;
            # otherwise the host builds the plain 403 that names the layer.
            if context.response.body or context.response.status != 200:
                return context.response
            return ServerResponse.denied(
                f"layer {layer!r} is not available to this request"
            )
        return None

    def permits(
        self, context: ServerContext, request: ServerRequest, layer: str
    ) -> bool:
        """Whether every access-control hook allows ``layer`` for this request.

        QGIS Server asks this one layer at a time, while it renders a map or
        resolves a filter, so the question is public and the answer is a bool -
        not the 403 :meth:`denied_layer` builds for a host that dispatches whole
        requests.

        Args:
            context: The context the hooks receive.
            request: The request being served.
            layer: The layer name to rule on.

        Returns:
            Whether every hook allows it.
        """
        for hook in self._hooks.access_control:
            if not hook(context, request, layer):
                return False
        return True

    def service_for(self, request: ServerRequest) -> Callable[..., Any] | None:
        """The declared handler of the OGC service this request names, if any.

        Args:
            request: The request whose ``SERVICE`` parameter to look up.

        Returns:
            The handler, or ``None`` when the plugin serves no such service.
        """
        requested = (request.param("SERVICE") or "").replace("_", "").upper()
        if not requested:
            return None
        for declaration, hook in self._hooks.services:
            if (declaration.name or "").replace("_", "").upper() == requested:
                return hook
        return None


class _ServerHostContext:
    def _request_jobs(self, scope: ResourceScope) -> Jobs | None:
        """The jobs facade over ``scope``, which ends with the response."""
        return None if self._jobs is None else Jobs(self._jobs.request_scoped(scope))

    def context(
        self,
        scope: ResourceScope,
        request: ServerRequest,
        response: ServerResponse,
        **options: Unpack[_ContextOptions1],
    ) -> ServerContext:
        """Build the context one request's hooks receive.

        ``jobs`` is derived from the plugin's service over *this* request's
        scope, because that derivation is the request scope itself; a host with
        its own ``context_factory`` decides the same question in its factory.

        Args:
            scope: The request scope, closed when the response is sent.
            request: The request being served.
            response: The response the hooks are building.
            options: ``project``, ``layers`` and ``log``, when the host has them.
        """
        if self._context_factory is not None:
            return self._context_factory(scope, request, response)
        return self._default_context(scope, request, response, **options)

    def _default_context(
        self,
        scope: ResourceScope,
        request: ServerRequest,
        response: ServerResponse,
        **options: Unpack[_ContextOptions1],
    ) -> ServerContext:
        """The context a host without a factory gets: no project unless given."""
        return ServerContext(
            scope,
            request,
            response,
            ServerServices(
                project=options.get("project"),
                layers=options.get("layers"),
                log=options.get("log"),
                jobs=self._request_jobs(scope),
            ),
        )


class ServerHost(_ServerHostRegistration, _ServerHostDispatch, _ServerHostContext):
    """The hooks of one plugin, registered once and served request by request.

    ``context_factory`` is how a host adds the services a request's project
    makes possible: it is called with the scope, the request and the response
    and returns the :class:`ServerContext` the hooks receive. Without one the
    context carries the request and the response and refuses ``project``,
    ``layers`` and ``log`` by name, which is what a capabilities-only
    deployment needs.

    ``jobs`` is the plugin's job service, if the host has one. Each request gets
    a service derived over the *request* scope, so a job a hook submits is
    request-scoped: it is ticked at request start and abandoned when the
    response is sent, which here means when the request scope closes
    (decision-52). Work submitted through ``ctx.jobs.plugin`` keeps the plugin's
    lifetime. A host without a job service leaves ``ctx.jobs`` out, and the
    context refuses it by name like any other capability it never had.

    Args:
        hooks: The plugin's declared hooks, already validated.
        interface: The object that plays ``QgsServerInterface``.
        context_factory: How a request's services are built, or ``None`` for the
            default context, which has no project.
        jobs: The plugin's job service, or ``None`` when the host has none.
    """

    __slots__ = ("_context_factory", "_hooks", "_interface", "_jobs", "_registered")

    def __init__(
        self,
        hooks: ServerHooks,
        interface: ServerInterface,
        *,
        context_factory: (
            Callable[[ResourceScope, ServerRequest, ServerResponse], ServerContext]
            | None
        ) = None,
        jobs: JobService | None = None,
    ) -> None:
        self._hooks = hooks
        self._interface = interface
        self._context_factory = context_factory
        self._jobs = jobs
        self._registered = False

    def __repr__(self) -> str:
        state = "registered" if self._registered else "unregistered"
        return f"ServerHost({self._hooks!r}, {state})"


def _request_context(
    host: ServerHost, values: Any, response: ServerResponse
) -> ServerContext:
    """Build the context one request's hooks receive, from the published args."""
    return host.context(
        values.scope,
        values.request,
        response,
        project=values.project,
        layers=values.layers,
        log=values.log,
    )


def _filter_return_refused(hook: Callable[..., Any], outcome: object) -> Exception:
    """The error a filter that returned something unusable is refused with."""
    return QgisSdkUnsupportedCapabilityError(
        f"@server.filter `{hook.__name__}` returned {type(outcome).__name__}; "
        "return None to pass, a ServerRequest to rewrite or a "
        "ServerResponse to answer"
    )


class _ContextOptions1(TypedDict, total=False):
    """The services a request's project makes possible, each optional."""

    project: Project | None
    layers: Layers | None
    log: Log | None

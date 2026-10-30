"""``@server.filter``, ``@server.service`` and ``@server.access_control``.

A server hook is a plain function with the context injected first, the way a job
is (decision-52, decision-38). The decorators attach metadata and do not wrap
anything, so a test calls the function directly with a fake context and the
adapter calls the same object inside QGIS.

Which hook runs first is a stated rule rather than an accident of sorting
(decision-69 point 1): ``priority`` ascending, and among equal priorities the
order the plugin declares them in, then the declarations of each plugin it
``include()``s, in include order. ``ServerHooks`` fixes that order once, when the
host starts, and keeps it.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from typing import Any, Literal, TypeVar

from qgis_sdk.declarations import QgisSdkDeclarationError, refuse_bindings

from ._context import ServerContext

__all__ = [
    "DEFAULT_PRIORITY",
    "HOOK_SIGNATURES",
    "HookDeclaration",
    "HookKind",
    "ServerHooks",
    "access_control",
    "filter",
    "service",
]

HookKind = Literal["filter", "service", "access_control"]
"""The three hooks the server host knows."""

_HOOK_ATTRIBUTE = "__qgis_sdk_server_hook__"
_DECORATOR_OF: dict[str, str] = {
    "filter": "@server.filter",
    "service": "@server.service",
    "access_control": "@server.access_control",
}

#: QGIS' own default filter priority (``QgsServerFiltersMap`` uses 30).
DEFAULT_PRIORITY = 30

#: The parameters each kind takes after the injected ``ServerContext``, in order.
HOOK_SIGNATURES: dict[str, tuple[str, ...]] = {
    "filter": ("request", "response"),
    "service": ("request",),
    "access_control": ("request", "layer"),
}

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class HookDeclaration:
    """What a decorator recorded: the kind, the order and the OGC service id."""

    kind: HookKind
    priority: int = DEFAULT_PRIORITY
    #: ``@server.service`` only: the OGC service name the host registers it under.
    name: str | None = None
    #: ``@server.service`` only: the version string QGIS advertises.
    version: str | None = None


# -- authoring --------------------------------------------------------------------


def filter(function: T | None = None, /, *, priority: int = DEFAULT_PRIORITY) -> Any:
    """Declare a request/response filter; ``@server.filter`` or ``@server.filter()``.

    The signature is ``def f(ctx: ServerContext, request: ServerRequest,
    response: ServerResponse)``. Returning ``None`` passes the request on,
    returning a :class:`~qgis_sdk.server.ServerResponse` answers it and stops
    the chain, and returning a :class:`~qgis_sdk.server.ServerRequest` rewrites
    the request the hooks after it see:::

        @server.filter(priority=20)
        def force_crs(ctx, request, response):
            if request.param("SERVICE") == "WMS" and request.param("VERSION") is None:
                return request.with_params(VERSION="1.3.0")
            return None
    """
    return _declare("filter", function, priority=priority)


def service(
    function: T | None = None,
    /,
    *,
    name: str | None = None,
    version: str = "1.0.0",
) -> Any:
    """Declare a custom OGC-style service; ``@server.service`` or called.

    The signature is ``def f(ctx: ServerContext, request: ServerRequest)`` and
    it returns the :class:`~qgis_sdk.server.ServerResponse` it wants sent. The
    service answers requests whose ``SERVICE`` parameter matches ``name`` -
    derived from the function name when it is not given - and QGIS advertises
    it at ``version`` in its service registry.
    """
    return _declare(
        "service",
        function,
        priority=DEFAULT_PRIORITY,
        name=name,
        version=version,
    )


def access_control(
    function: T | None = None, /, *, priority: int = DEFAULT_PRIORITY
) -> Any:
    """Declare a layer permission hook; ``@server.access_control`` or called.

    The signature is ``def f(ctx: ServerContext, request: ServerRequest, layer:
    str) -> bool``: ``True`` lets the request read ``layer``, ``False`` refuses
    it and the host answers with
    :meth:`~qgis_sdk.server.ServerResponse.denied` - a 403 naming the layer -
    instead of passing a filtered map to the client. A hook that wants a
    different refusal returns ``False`` and sets it on
    ``ctx.response`` (an XML ``ServiceException``, a different status).
    """
    return _declare("access_control", function, priority=priority)


def _declare(
    kind: HookKind,
    function: Any,
    *,
    priority: int,
    name: str | None = None,
    version: str | None = None,
) -> Any:
    if isinstance(priority, bool) or not isinstance(priority, int):
        raise QgisSdkDeclarationError(
            f"{_DECORATOR_OF[kind]}: priority must be an int, not "
            f"{type(priority).__name__}; lower runs first"
        )

    def decorate(target: T) -> T:
        refuse_bindings(target, _DECORATOR_OF[kind])
        declaration = HookDeclaration(
            kind=kind,
            priority=priority,
            name=name if kind != "service" else (name or _service_name(target)),
            version=version if kind == "service" else None,
        )
        _validate_signature(target, declaration)
        setattr(target, _HOOK_ATTRIBUTE, declaration)
        return target

    if function is None:
        return decorate
    return decorate(function)


def _service_name(function: Any) -> str:
    """The OGC service name a ``@server.service`` function answers to."""
    name = getattr(function, "__name__", "")
    return name.replace("_", "").upper() or "SERVICE"


def _validate_signature(function: Any, declaration: HookDeclaration) -> None:
    """Refuse a hook the host could not call, naming the signature it wants."""
    where = _DECORATOR_OF[declaration.kind]
    if inspect.iscoroutinefunction(function):
        raise QgisSdkDeclarationError(
            f"{where}: `{function.__name__}` is an `async def`; a server request "
            "is served with no event loop, so a hook is a plain `def`"
        )
    parameters = list(inspect.signature(function).parameters.values())
    expected = ("ctx", *HOOK_SIGNATURES[declaration.kind])
    if tuple(parameter.name for parameter in parameters) != expected:
        shown = f"({', '.join(expected)})"
        raise QgisSdkDeclarationError(
            f"{where}: `{function.__name__}` must take {shown} in that order; "
            f"it takes ({', '.join(p.name for p in parameters)})"
        )
    annotation = parameters[0].annotation
    if not _is_server_context(annotation):
        raise QgisSdkDeclarationError(
            f"{where}: `{function.__name__}` must annotate its first parameter "
            f"as `ServerContext`, not {getattr(annotation, '__name__', annotation)!r}"
        )


def _is_server_context(annotation: object) -> bool:
    return annotation is ServerContext or annotation == "ServerContext"


# -- the collection the host registers ---------------------------------------------


class ServerHooks:
    """The hooks a plugin declares, in the order the host runs them.

    Built once from the declared functions; a function that carries no hook
    metadata, two services claiming one name, or a service the plugin declares
    twice are all refused here rather than at the first request, when the server
    has already accepted traffic.
    """

    __slots__ = ("_access_control", "_filters", "_services")

    def __init__(self, hooks: Iterable[Callable[..., Any]] = ()) -> None:
        declared: list[tuple[HookDeclaration, Callable[..., Any]]] = []
        for hook in hooks:
            declaration = getattr(hook, _HOOK_ATTRIBUTE, None)
            if not isinstance(declaration, HookDeclaration):
                raise QgisSdkDeclarationError(
                    f"{getattr(hook, '__name__', hook)!r} is not a server hook; "
                    "decorate it with @server.filter, @server.service or "
                    "@server.access_control"
                )
            declared.append((declaration, hook))
        # ``sorted`` is stable, so equal priorities keep declaration order, and
        # the caller hands the included plugins' hooks after its own.
        ordered = sorted(declared, key=lambda item: item[0].priority)
        seen: set[tuple[str, str]] = set()
        for declaration, hook in ordered:
            if declaration.kind != "service":
                continue
            key = (declaration.name or "", declaration.version or "")
            key = (key[0].casefold(), key[1])
            if key in seen:
                raise QgisSdkDeclarationError(
                    f"two @server.service hooks answer SERVICE="
                    f"{declaration.name!r} version {declaration.version!r}; "
                    f"the second is `{hook.__name__}`"
                )
            seen.add(key)
        self._filters = tuple(
            hook for declaration, hook in ordered if declaration.kind == "filter"
        )
        self._services = tuple(
            (declaration, hook)
            for declaration, hook in ordered
            if declaration.kind == "service"
        )
        self._access_control = tuple(
            hook
            for declaration, hook in ordered
            if declaration.kind == "access_control"
        )

    @property
    def filters(self) -> tuple[Callable[..., Any], ...]:
        """The request/response filters, lowest priority first."""
        return self._filters

    @property
    def services(self) -> tuple[tuple[HookDeclaration, Callable[..., Any]], ...]:
        """The custom services with the declaration each was registered under."""
        return self._services

    @property
    def access_control(self) -> tuple[Callable[..., Any], ...]:
        """The layer permission hooks, lowest priority first."""
        return self._access_control

    def declaration(self, hook: Callable[..., Any]) -> HookDeclaration:
        """The declaration ``hook`` was registered under.

        The kind, the priority and - for a service - the name and version, which
        is what a host that has to *re-register* compares before it does: QGIS
        Server holds one object per identity, so a hook set whose identities
        moved cannot take the place of the one it registered.
        """
        declaration = getattr(hook, _HOOK_ATTRIBUTE, None)
        if not isinstance(declaration, HookDeclaration):
            raise QgisSdkDeclarationError(
                f"{getattr(hook, '__name__', hook)!r} is not a server hook"
            )
        return declaration

    def __iter__(self) -> Iterator[Callable[..., Any]]:
        """Iterate the filters, then the services, then the access hooks."""
        yield from self._filters
        yield from (hook for _, hook in self._services)
        yield from self._access_control

    def __len__(self) -> int:
        return len(self._filters) + len(self._services) + len(self._access_control)

    def __repr__(self) -> str:
        return (
            f"ServerHooks({len(self._filters)} filters, "
            f"{len(self._services)} services, "
            f"{len(self._access_control)} access-control hooks)"
        )

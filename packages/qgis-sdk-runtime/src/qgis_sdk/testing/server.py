"""A scripted ``QgsServerInterface``: everything a server hook needs, no QGIS.

``QgsServerInterface`` is a Qt object created by the server, so a test cannot
build one and ``qgis-sdk test --target server`` cannot either (decision-52
implementation note). This fake records what the host registers and lets a test
serve a request through the same :class:`~qgis_sdk.server.ServerHost` the
adapter uses, so the ordering rule and the refusal contracts are proven without
a QGIS that has server bindings.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from qgis_sdk.core.scope import ResourceScope
from qgis_sdk.server import ServerHooks, ServerHost, ServerRequest, ServerResponse

__all__ = ["FakeServerInterface", "RegisteredFilter"]


@dataclass(frozen=True, slots=True)
class RegisteredFilter:
    """One registration: the name the host used, the callable and its priority."""

    name: str
    hook: Callable[..., Any]
    priority: int


class FakeServerInterface:
    """A ``QgsServerInterface`` that records registrations instead of running them.

    ``serve`` builds a :class:`~qgis_sdk.server.ServerHost` over these records
    and the hooks the plugin declared, which is the same object the real adapter
    feeds a ``QgsServerInterface``, so a test exercises the dispatcher rather
    than a mock of it.
    """

    __slots__ = ("_access_control", "_filters", "_services")

    def __init__(self) -> None:
        self._filters: list[RegisteredFilter] = []
        self._services: list[tuple[str, str, Callable[..., Any]]] = []
        self._access_control: list[RegisteredFilter] = []

    # -- what the host calls -----------------------------------------------------

    def register_filter(
        self, name: str, hook: Callable[..., Any], priority: int
    ) -> None:
        """Record a request hook."""
        self._filters.append(RegisteredFilter(name, hook, priority))

    def register_service(
        self, name: str, version: str, handler: Callable[..., Any]
    ) -> None:
        """Record an OGC service handler."""
        self._services.append((name, version, handler))

    def register_access_control(
        self, name: str, hook: Callable[..., Any], priority: int
    ) -> None:
        """Record a layer permission hook."""
        self._access_control.append(RegisteredFilter(name, hook, priority))

    # -- what a test reads -------------------------------------------------------

    @property
    def filters(self) -> tuple[RegisteredFilter, ...]:
        """The filters in registration order, with their priorities."""
        return tuple(self._filters)

    @property
    def services(self) -> tuple[tuple[str, str, Callable[..., Any]], ...]:
        """``(name, version, handler)`` for every registered service."""
        return tuple(self._services)

    @property
    def access_control(self) -> tuple[RegisteredFilter, ...]:
        """The access-control hooks in registration order."""
        return tuple(self._access_control)

    @property
    def registrations(self) -> Mapping[str, int]:
        """How many of each kind were registered, for a coarse assertion."""
        return MappingProxyType(
            {
                "filters": len(self._filters),
                "services": len(self._services),
                "access_control": len(self._access_control),
            }
        )

    # -- serving -----------------------------------------------------------------

    def serve(
        self,
        hooks: ServerHooks,
        request: ServerRequest,
        *,
        scope: ResourceScope | None = None,
        **services: Any,
    ) -> ServerResponse:
        """Register ``hooks`` here and serve one request through them."""
        host = ServerHost(hooks, self)
        host.register()
        return host.handle(request, scope=scope, **services)

    def __repr__(self) -> str:
        return (
            f"FakeServerInterface({len(self._filters)} filters, "
            f"{len(self._services)} services, "
            f"{len(self._access_control)} access hooks)"
        )

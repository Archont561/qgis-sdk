"""Typed contexts assembled explicitly by an owner, never a global registry."""

from dataclasses import dataclass

from qgis_sdk.models import QgisSdkUnsupportedCapabilityError
from qgis_sdk.services import (
    Algorithms,
    Cancellation,
    DesktopAccess,
    Notifications,
    Progress,
    ViewControl,
)

from .scope import ResourceScope


@dataclass(frozen=True, slots=True)
class PluginContext:
    """Capabilities owned by one plugin runtime, not an invocation."""

    notifications: Notifications
    scope: ResourceScope
    desktop: DesktopAccess | None = None

    def require_native(self) -> DesktopAccess:
        """Request Desktop access; pure/standalone runtimes fail explicitly."""
        self.scope.ensure_open()
        if self.desktop is None:
            raise QgisSdkUnsupportedCapabilityError("desktop")
        return self.desktop


@dataclass(frozen=True, slots=True)
class UiContext:
    """Capabilities for one view; a close request is not synchronous disposal."""

    notifications: Notifications
    view: ViewControl
    scope: ResourceScope


@dataclass(frozen=True, slots=True)
class AlgorithmContext:
    """Execution-only capabilities for one Processing invocation.

    Built fresh for each invocation and thrown away afterwards (decision-11), so
    an author class can hold it as ``self.ctx`` without carrying state from one
    run into the next. It is not a ``PluginContext``: no ``iface``, no dialogs,
    no GUI notifications - only what one execution legitimately needs.
    """

    progress: Progress
    cancellation: Cancellation
    scope: ResourceScope
    algorithms: Algorithms


@dataclass(frozen=True, slots=True)
class JobContext:
    """One job attempt, owned by a view unless plugin ownership is explicit."""

    progress: Progress
    cancellation: Cancellation
    scope: ResourceScope

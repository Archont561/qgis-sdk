"""Typed contexts assembled explicitly by an owner, never a global registry."""

from dataclasses import dataclass
from typing import TypeVar

from qgis_sdk.models import QgisSdkUnsupportedCapabilityError
from qgis_sdk.services import (
    Algorithms,
    Cancellation,
    DesktopAccess,
    Layers,
    Network,
    Notifications,
    Progress,
    Project,
    Settings,
    Styles,
    ViewControl,
    Workers,
)

from .scope import ResourceScope

T = TypeVar("T")


def _require(scope: ResourceScope, service: T | None, capability: str) -> T:
    """Hand back an optional capability, or refuse it by name on this scope."""
    scope.ensure_open()
    if service is None:
        raise QgisSdkUnsupportedCapabilityError(capability)
    return service


def _require_network(scope: ResourceScope, network: Network | None) -> Network:
    return _require(scope, network, "network")


@dataclass(frozen=True, slots=True)
class PluginContext:
    """Capabilities owned by one plugin runtime, not an invocation.

    Beside notifications and the owned scope it carries the curated services
    (``layers``, ``project``, ``settings``, ``styles``, ``algorithms``,
    ``workers``) as optional fields, exactly the Protocols the web-view host
    surface wraps (decision-27). A host that builds the bridge from this
    context (``HostServices.from_context``) hands both sides the same
    instances, so a Python handler and a page read one project. Every
    optional capability has a ``require_<name>()`` that fails by name instead
    of returning ``None``.
    """

    notifications: Notifications
    scope: ResourceScope
    desktop: DesktopAccess | None = None
    network: Network | None = None
    layers: Layers | None = None
    project: Project | None = None
    settings: Settings | None = None
    styles: Styles | None = None
    algorithms: Algorithms | None = None
    workers: Workers | None = None

    def require_native(self) -> DesktopAccess:
        """Request Desktop access; pure/standalone runtimes fail explicitly."""
        return _require(self.scope, self.desktop, "desktop")

    def require_network(self) -> Network:
        """Request the network client; a host without one fails explicitly."""
        return _require_network(self.scope, self.network)

    def require_layers(self) -> Layers:
        """Request the layer service; a host without one fails explicitly."""
        return _require(self.scope, self.layers, "layers")

    def require_project(self) -> Project:
        """Request the project service; a host without one fails explicitly."""
        return _require(self.scope, self.project, "project")

    def require_settings(self) -> Settings:
        """Request the settings service; a host without one fails explicitly."""
        return _require(self.scope, self.settings, "settings")

    def require_styles(self) -> Styles:
        """Request the style service; a host without one fails explicitly."""
        return _require(self.scope, self.styles, "styles")

    def require_algorithms(self) -> Algorithms:
        """Request Processing execution; a host without it fails explicitly."""
        return _require(self.scope, self.algorithms, "algorithms")

    def require_workers(self) -> Workers:
        """Request the worker pool; a host without one fails explicitly."""
        return _require(self.scope, self.workers, "workers")


@dataclass(frozen=True, slots=True)
class UiContext:
    """Capabilities for one view; a close request is not synchronous disposal."""

    notifications: Notifications
    view: ViewControl
    scope: ResourceScope
    network: Network | None = None

    def require_network(self) -> Network:
        """Request the network client; a host without one fails explicitly."""
        return _require_network(self.scope, self.network)


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
    network: Network | None = None

    def require_network(self) -> Network:
        """Request the network client; a host without one fails explicitly."""
        return _require_network(self.scope, self.network)


@dataclass(frozen=True, slots=True)
class JobContext:
    """One job attempt, owned by a view unless plugin ownership is explicit.

    Built fresh for every attempt by :class:`qgis_sdk.jobs.JobService` and
    passed to the ``@job`` function as its first argument (decision-38); the
    function never builds one itself, and a test hands it a fake. The scope
    is the attempt's own: it closes when the attempt settles or the plugin
    unloads, not when the owning view is disposed, because closing it under a
    worker that has not acknowledged cancellation would be exactly the
    teardown decision-21 forbids.
    """

    progress: Progress
    cancellation: Cancellation
    scope: ResourceScope
    workers: Workers | None = None
    network: Network | None = None

    def require_workers(self) -> Workers:
        """Request the worker pool; a host without one fails explicitly."""
        self.scope.ensure_open()
        if self.workers is None:
            raise QgisSdkUnsupportedCapabilityError("workers")
        return self.workers

    def require_network(self) -> Network:
        """Request the network client; a host without one fails explicitly."""
        return _require_network(self.scope, self.network)

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from qgis_sdk.core.host import Host
from qgis_sdk.core.scope import ResourceScope
from qgis_sdk.services import (
    Algorithms,
    Canvas,
    Connections,
    DesktopAccess,
    Features,
    Files,
    Layers,
    Layouts,
    Log,
    Network,
    Notifications,
    Processing,
    Project,
    Rasters,
    Settings,
    Styles,
    Ui,
    ViewControl,
    Workers,
)

from ._base import Capability, Context, PluginServices

if TYPE_CHECKING:
    from qgis_sdk.jobs._jobs import Jobs
    from qgis_sdk.ui.actions import ViewActions
    from qgis_sdk.ui.streams import ViewStreams


class PluginContext(Context):
    """Capabilities owned by one plugin runtime, not an invocation.

    Beside notifications and the owned scope it carries the curated services
    (``desktop``, ``network``, ``layers``, ``project``, ``settings``,
    ``styles``, ``algorithms``, ``workers``), exactly the Protocols the
    web-view host surface wraps (decision-27), plus ``processing``, the
    host-side registry ``PluginRuntime`` advertises the plugin's providers
    with (decision-42). A host that builds the bridge from this context
    (``HostServices.from_context``) hands both sides the same instances, so a
    Python handler and a page read one project. Each service is a
    :class:`Capability`: reading one the host did not provide fails by name
    (decision-39).
    """

    __slots__ = (
        "_algorithms",
        "_canvas",
        "_connections",
        "_desktop",
        "_features",
        "_files",
        "_jobs",
        "_layers",
        "_layouts",
        "_log",
        "_network",
        "_processing",
        "_project",
        "_rasters",
        "_settings",
        "_styles",
        "_ui",
        "_workers",
        "host",
        "notifications",
        "scope",
    )

    _capability_names = (
        "desktop",
        "network",
        "layers",
        "rasters",
        "features",
        "canvas",
        "layouts",
        "connections",
        "project",
        "settings",
        "styles",
        "algorithms",
        "workers",
        "processing",
        "ui",
        "files",
        "log",
        "jobs",
    )

    notifications: Notifications
    scope: ResourceScope
    #: The host that built this context (``desktop``, ``server`` or ``app``),
    #: stated by the host rather than inferred (decision-52 point 4).
    host: Host
    desktop: Capability[DesktopAccess] = Capability()
    network: Capability[Network] = Capability()
    layers: Capability[Layers] = Capability()
    #: Raster bands, statistics, point samples and an explicit export (TASK-87):
    #: the half of a layer a page reads cell by cell rather than feature by
    #: feature. A host with no ``QgsRasterLayer`` refuses it by name.
    rasters: Capability[Rasters] = Capability()
    #: Layer data and the expressions that select it (decision-54 point 3): a
    #: layer is a description, a feature is data, and editing is an explicitly
    #: opened session rather than another method here.
    features: Capability[Features] = Capability()
    #: Print layouts and atlases (TASK-89): list them, load a template, export
    #: one as a job, iterate an atlas. The job forms submit the render to the
    #: host's worker backend, so an export is a task in the task bar; a host
    #: that cannot render layouts refuses the capability by name.
    layouts: Capability[Layouts] = Capability()
    #: Registered data-source connections and authentication configuration ids
    #: (TASK-92): browse the provider registry and open one of its tables. A
    #: host with no ``QgsProviderRegistry`` refuses the capability by name.
    connections: Capability[Connections] = Capability()
    project: Capability[Project] = Capability()
    settings: Capability[Settings] = Capability()
    styles: Capability[Styles] = Capability()
    algorithms: Capability[Algorithms] = Capability()
    #: The map the user is looking at (decision-54 point 3): read it, move it,
    #: theme it, capture from it. A host with no canvas - a QGIS Server, a bare
    #: ``QgsApplication`` - refuses this capability by name.
    canvas: Capability[Canvas] = Capability()
    workers: Capability[Workers] = Capability()
    #: The plugin's declared jobs (``jobs = {...}``), submitted with the
    #: plugin's lifetime; a view's context carries a view-scoped copy
    #: (decision-65 §3).
    jobs: Capability[Jobs] = Capability()
    processing: Capability[Processing] = Capability()
    ui: Capability[Ui] = Capability()
    files: Capability[Files] = Capability()
    #: Structured records under the plugin's tag (decision-63); the
    #: ``LogView`` component watches it.
    log: Capability[Log] = Capability()

    def __init__(
        self,
        notifications: Notifications,
        scope: ResourceScope,
        services: PluginServices | None = None,
    ) -> None:
        services = services if services is not None else PluginServices()
        self._assemble(
            notifications=notifications,
            scope=scope,
            host=services.host,
            **{f"_{name}": getattr(services, name) for name in self._capability_names},
        )

    def with_services(self, **services: Any) -> PluginContext:
        """A new context over the same scope with ``services`` added, never swapped.

        The Desktop host uses it to add what only it can build once the
        runtime exists (``ui``); a capability the factory already provided
        is a ``ValueError``, so a host cannot quietly replace an author's
        choice.
        """
        for name in services:
            if name not in self._capability_names:
                raise ValueError(f"PluginContext has no capability named {name!r}")
            if self.has(name):
                raise ValueError(f"PluginContext already provides {name!r}")
        current = {name: getattr(self, f"_{name}") for name in self._capability_names}
        current.update(services)
        return PluginContext(
            self.notifications,
            self.scope,
            PluginServices(host=self.host, **current),
        )


@dataclass(frozen=True, slots=True)
class UiServices:
    """What a host shares with one view's context, and which host it is.

    The plugin's own service objects, not view-owned copies: a surface handler
    reads the same project, layers and canvas a page does (decision-55).
    """

    host: Host = Host.DESKTOP
    network: Network | None = None
    actions: ViewActions | None = None
    algorithms: Algorithms | None = None
    desktop: DesktopAccess | None = None
    settings: Settings | None = None
    layers: Layers | None = None
    rasters: Rasters | None = None
    features: Features | None = None
    project: Project | None = None
    canvas: Canvas | None = None
    files: Files | None = None
    log: Log | None = None
    streams: ViewStreams | None = None
    styles: Styles | None = None
    ui: Ui | None = None
    jobs: Jobs | None = None


class UiContext(Context):
    """Capabilities for one view; a close request is not synchronous disposal.

    ``actions`` is the view-scoped way into the plugin's own actions
    (:class:`qgis_sdk.ui.actions.ViewActions`): ``ctx.actions.buffer(...)``
    validates, coerces and dispatches to the runtime's bound handler and
    refuses a second call while the first still runs from this view
    (decision-55). The host may also share plugin services such as
    ``algorithms``, ``styles``, ``desktop`` and ``ui`` directly, so surface
    handlers need not declare actions. ``desktop`` is a native escape hatch.
    These are the plugin's service objects, not view-owned copies: capability
    access checks the view scope, but a previously retained service still has
    its own plugin lifetime. Direct calls are synchronous; the context does
    not move work to a worker.
    """

    __slots__ = (
        "_actions",
        "_algorithms",
        "_canvas",
        "_desktop",
        "_features",
        "_files",
        "_jobs",
        "_layers",
        "_log",
        "_network",
        "_project",
        "_rasters",
        "_settings",
        "_streams",
        "_styles",
        "_ui",
        "host",
        "notifications",
        "scope",
        "view",
    )

    _capability_names = (
        "network",
        "actions",
        "algorithms",
        "desktop",
        "settings",
        "layers",
        "rasters",
        "features",
        "canvas",
        "project",
        "files",
        "log",
        "streams",
        "styles",
        "ui",
        "jobs",
    )

    notifications: Notifications
    view: ViewControl
    scope: ResourceScope
    #: The host this view belongs to, handed down from the plugin context.
    host: Host
    network: Capability[Network] = Capability()
    actions: Capability[ViewActions] = Capability()
    algorithms: Capability[Algorithms] = Capability()
    desktop: Capability[DesktopAccess] = Capability()
    settings: Capability[Settings] = Capability()
    #: What the catalogue's pickers list and the ``FileInput`` mints through
    #: the plugin's own services, handed to its surfaces.
    layers: Capability[Layers] = Capability()
    #: The plugin's raster service, shared like ``layers`` so a surface handler
    #: reads the same cells a page does.
    rasters: Capability[Rasters] = Capability()
    #: The plugin's feature and expression service, shared like ``layers`` so a
    #: surface handler reads the same data a page does.
    features: Capability[Features] = Capability()
    project: Capability[Project] = Capability()
    #: The same canvas the plugin context carries: a surface handler that moves
    #: the map moves the map the page is looking at.
    canvas: Capability[Canvas] = Capability()
    files: Capability[Files] = Capability()
    log: Capability[Log] = Capability()
    #: The plugin's ``@stream`` methods, subscribed from this view
    #: (:class:`qgis_sdk.ui.streams.ViewStreams`); ``ctx.on`` is the short form.
    streams: Capability[ViewStreams] = Capability()
    styles: Capability[Styles] = Capability()
    ui: Capability[Ui] = Capability()
    #: The plugin's named jobs, owned by *this view*: work submitted here is
    #: cancelled with the window unless it goes through ``ctx.jobs.plugin``
    #: (decision-65 §3).
    jobs: Capability[Jobs] = Capability()

    def __init__(
        self,
        notifications: Notifications,
        view: ViewControl,
        scope: ResourceScope,
        services: UiServices | None = None,
    ) -> None:
        services = services if services is not None else UiServices()
        self._assemble(
            notifications=notifications,
            view=view,
            scope=scope,
            host=services.host,
            **{f"_{name}": getattr(services, name) for name in self._capability_names},
        )

    def on(
        self, stream: str, callback: Callable[[Any], None], /, **request: object
    ) -> Any:
        """Subscribe ``callback`` to the plugin's ``stream`` for this view's lifetime.

        The imperative form of ``@subscribe`` (decision-55): the subscription
        is owned by the view's scope and ends with the window. Returns the
        :class:`~qgis_sdk.ui.streams.ViewSubscription`.
        """
        return self.streams.subscribe(stream, callback, owner=self.scope, **request)


@dataclass(frozen=True, slots=True)
class AlgorithmServices:
    """Everything one invocation is handed that is not the runner's own state.

    ``algorithms`` is always supplied; ``project`` and ``network`` are the two
    capabilities a host may not have, so they default to ``None`` - absent, not
    empty - and the context refuses them by name rather than handing a body a
    service that could not work (decision-39).
    """

    algorithms: Algorithms
    project: Project | None = None
    network: Network | None = None

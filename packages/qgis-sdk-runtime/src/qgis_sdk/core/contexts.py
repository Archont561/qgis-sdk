"""Typed contexts assembled explicitly by an owner, never a global registry.

A context carries what its owner always provides (``scope``, ``notifications``,
``progress`` ...) as plain attributes and what a host *may* provide (``workers``,
``network``, ``layers`` ...) as :class:`Capability` attributes. Reading a
capability the host left out raises
:class:`~qgis_sdk.models.QgisSdkUnsupportedCapabilityError` naming it, so author
code spells ``ctx.workers.offload(...)`` and a pure or standalone host still
fails on the first touch rather than with an ``AttributeError`` on ``None``
(decision-39, replacing the ``require_<name>()`` accessors of decision-32).
``has(name)`` and ``capabilities`` are the probes for the few places that need
to ask instead of use.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, ClassVar, Generic, TypeVar, overload

from qgis_sdk.models import QgisSdkUnsupportedCapabilityError
from qgis_sdk.services import (
    Algorithms,
    Cancellation,
    DesktopAccess,
    Files,
    Layers,
    Log,
    Network,
    Notifications,
    Processing,
    Progress,
    Project,
    Settings,
    Styles,
    Ui,
    ViewControl,
    Workers,
)

from .scope import ResourceScope

if TYPE_CHECKING:
    from qgis_sdk.ui.actions import ViewActions
    from qgis_sdk.ui.streams import ViewStreams

T = TypeVar("T")


class Capability(Generic[T]):
    """One optional service on a context, refused by name when it is absent.

    The host's instance (or ``None``) lives in a private slot; reading the
    public attribute checks the scope is open and hands the instance back, or
    raises ``QgisSdkUnsupportedCapabilityError(name)``. Nothing is wrapped, so
    ``ctx.layers is services.layers`` holds for the very object the host passed.
    """

    __slots__ = ("name", "slot")

    def __set_name__(self, owner: type, name: str) -> None:
        self.name = name
        self.slot = f"_{name}"

    @overload
    def __get__(self, instance: None, owner: type) -> Capability[T]: ...

    @overload
    def __get__(self, instance: object, owner: type) -> T: ...

    def __get__(self, instance: object | None, owner: type | None = None) -> Any:
        if instance is None:
            return self
        instance.scope.ensure_open()  # type: ignore[attr-defined]
        service = getattr(instance, self.slot)
        if service is None:
            raise QgisSdkUnsupportedCapabilityError(self.name)
        return service


class _Context:
    """What the four contexts share: immutability and the capability probes."""

    __slots__ = ()

    _capability_names: ClassVar[tuple[str, ...]] = ()

    def _assemble(self, **values: Any) -> None:
        for name, value in values.items():
            object.__setattr__(self, name, value)

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError(
            f"{type(self).__name__} is assembled once; {name!r} is read-only"
        )

    def __delattr__(self, name: str) -> None:
        raise AttributeError(
            f"{type(self).__name__} is assembled once; {name!r} is read-only"
        )

    def has(self, capability: str) -> bool:
        """Whether the host provided ``capability`` (``"workers"``, ``"network"`` ...).

        A probe, not a use: it does not touch the scope. Asking about a name
        this context never carries is a ``ValueError``, so a typo cannot read
        as "not provided".
        """
        if capability not in self._capability_names:
            raise ValueError(
                f"{type(self).__name__} has no capability named {capability!r}; "
                f"it carries {', '.join(self._capability_names) or 'none'}"
            )
        return getattr(self, f"_{capability}") is not None

    @property
    def capabilities(self) -> frozenset[str]:
        """The names of the optional services this host provided."""
        return frozenset(name for name in self._capability_names if self.has(name))

    def __repr__(self) -> str:
        provided = ", ".join(sorted(self.capabilities)) or "none"
        return f"{type(self).__name__}(scope={self.scope!r}, capabilities={provided})"  # type: ignore[attr-defined]


class PluginContext(_Context):
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
        "_desktop",
        "_files",
        "_layers",
        "_log",
        "_network",
        "_processing",
        "_project",
        "_settings",
        "_styles",
        "_ui",
        "_workers",
        "notifications",
        "scope",
    )

    _capability_names = (
        "desktop",
        "network",
        "layers",
        "project",
        "settings",
        "styles",
        "algorithms",
        "workers",
        "processing",
        "ui",
        "files",
        "log",
    )

    notifications: Notifications
    scope: ResourceScope
    desktop: Capability[DesktopAccess] = Capability()
    network: Capability[Network] = Capability()
    layers: Capability[Layers] = Capability()
    project: Capability[Project] = Capability()
    settings: Capability[Settings] = Capability()
    styles: Capability[Styles] = Capability()
    algorithms: Capability[Algorithms] = Capability()
    workers: Capability[Workers] = Capability()
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
        desktop: DesktopAccess | None = None,
        network: Network | None = None,
        layers: Layers | None = None,
        project: Project | None = None,
        settings: Settings | None = None,
        styles: Styles | None = None,
        algorithms: Algorithms | None = None,
        workers: Workers | None = None,
        processing: Processing | None = None,
        ui: Ui | None = None,
        files: Files | None = None,
        log: Log | None = None,
    ) -> None:
        self._assemble(
            notifications=notifications,
            scope=scope,
            _desktop=desktop,
            _network=network,
            _layers=layers,
            _project=project,
            _settings=settings,
            _styles=styles,
            _algorithms=algorithms,
            _workers=workers,
            _processing=processing,
            _ui=ui,
            _files=files,
            _log=log,
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
        return PluginContext(self.notifications, self.scope, **current)


class UiContext(_Context):
    """Capabilities for one view; a close request is not synchronous disposal.

    ``actions`` is the view-scoped way into the plugin's own actions
    (:class:`qgis_sdk.ui.actions.ViewActions`): ``ctx.actions.buffer(...)``
    validates, coerces and dispatches to the runtime's bound handler and
    refuses a second call while the first still runs from this view
    (decision-55). ``settings`` is the plugin's settings when the host
    shares them with its surfaces.
    """

    __slots__ = (
        "_actions",
        "_files",
        "_layers",
        "_log",
        "_network",
        "_project",
        "_settings",
        "_streams",
        "notifications",
        "scope",
        "view",
    )

    _capability_names = (
        "network",
        "actions",
        "settings",
        "layers",
        "project",
        "files",
        "log",
        "streams",
    )

    notifications: Notifications
    view: ViewControl
    scope: ResourceScope
    network: Capability[Network] = Capability()
    actions: Capability[ViewActions] = Capability()
    settings: Capability[Settings] = Capability()
    #: What the catalogue's pickers list and the ``FileInput`` mints through
    #: (TASK-68): the plugin's own services, handed to its surfaces.
    layers: Capability[Layers] = Capability()
    project: Capability[Project] = Capability()
    files: Capability[Files] = Capability()
    log: Capability[Log] = Capability()
    #: The plugin's ``@stream`` methods, subscribed from this view
    #: (:class:`qgis_sdk.ui.streams.ViewStreams`); ``ctx.on`` is the short form.
    streams: Capability[ViewStreams] = Capability()

    def __init__(
        self,
        notifications: Notifications,
        view: ViewControl,
        scope: ResourceScope,
        network: Network | None = None,
        actions: ViewActions | None = None,
        settings: Settings | None = None,
        layers: Layers | None = None,
        project: Project | None = None,
        files: Files | None = None,
        log: Log | None = None,
        streams: ViewStreams | None = None,
    ) -> None:
        self._assemble(
            notifications=notifications,
            view=view,
            scope=scope,
            _network=network,
            _actions=actions,
            _settings=settings,
            _layers=layers,
            _project=project,
            _files=files,
            _log=log,
            _streams=streams,
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


class AlgorithmContext(_Context):
    """Execution-only capabilities for one Processing invocation.

    Built fresh for each invocation by :func:`qgis_sdk.algorithms.invoke` and
    thrown away afterwards (decision-11), and passed to the
    ``@provider.algorithm`` function as its first argument (decision-42), so
    no state carries from one run into the next. It is not a
    ``PluginContext``: no ``iface``, no dialogs, no GUI notifications - only
    what one execution legitimately needs. ``project`` is a capability so an
    algorithm that composes another through ``invoke`` can still add the
    result to the project when its host has one; ``network`` likewise.
    """

    __slots__ = (
        "_network",
        "_project",
        "algorithms",
        "cancellation",
        "progress",
        "scope",
    )

    _capability_names = ("project", "network")

    progress: Progress
    cancellation: Cancellation
    scope: ResourceScope
    algorithms: Algorithms
    project: Capability[Project] = Capability()
    network: Capability[Network] = Capability()

    def __init__(
        self,
        progress: Progress,
        cancellation: Cancellation,
        scope: ResourceScope,
        algorithms: Algorithms,
        project: Project | None = None,
        network: Network | None = None,
    ) -> None:
        self._assemble(
            progress=progress,
            cancellation=cancellation,
            scope=scope,
            algorithms=algorithms,
            _project=project,
            _network=network,
        )


class JobContext(_Context):
    """One job attempt, owned by a view unless plugin ownership is explicit.

    Built fresh for every attempt by :class:`qgis_sdk.jobs.JobService` and
    passed to the ``@job`` function as its first argument (decision-38); the
    function never builds one itself, and a test hands it a fake. The scope
    is the attempt's own: it closes when the attempt settles or the plugin
    unloads, not when the owning view is disposed, because closing it under a
    worker that has not acknowledged cancellation would be exactly the
    teardown decision-21 forbids. ``workers``, ``network``, ``algorithms`` and
    ``project`` are capabilities: ``await ctx.workers.offload(work)`` on a host
    without a pool fails by name, and so does ``invoke(buffer, ctx, ...)`` on
    a host without Processing (decision-42).
    """

    __slots__ = (
        "_algorithms",
        "_network",
        "_project",
        "_workers",
        "cancellation",
        "progress",
        "scope",
    )

    _capability_names = ("workers", "network", "algorithms", "project")

    progress: Progress
    cancellation: Cancellation
    scope: ResourceScope
    workers: Capability[Workers] = Capability()
    network: Capability[Network] = Capability()
    algorithms: Capability[Algorithms] = Capability()
    project: Capability[Project] = Capability()

    def __init__(
        self,
        progress: Progress,
        cancellation: Cancellation,
        scope: ResourceScope,
        workers: Workers | None = None,
        network: Network | None = None,
        algorithms: Algorithms | None = None,
        project: Project | None = None,
    ) -> None:
        self._assemble(
            progress=progress,
            cancellation=cancellation,
            scope=scope,
            _workers=workers,
            _network=network,
            _algorithms=algorithms,
            _project=project,
        )

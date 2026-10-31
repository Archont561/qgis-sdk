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

import threading
import warnings
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, ClassVar, Final, Generic, TypeVar, overload

from qgis_sdk.environment import dev_request
from qgis_sdk.models import (
    QgisSdkThreadSafetyWarning,
    QgisSdkUnsupportedCapabilityError,
)
from qgis_sdk.services import (
    Algorithms,
    Cancellation,
    DesktopAccess,
    Features,
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

from .host import Host
from .scope import ResourceScope

if TYPE_CHECKING:
    from qgis_sdk.jobs import Jobs
    from qgis_sdk.ui.actions import ViewActions
    from qgis_sdk.ui.streams import ViewStreams

T = TypeVar("T")

#: Capabilities whose service belongs to the thread that assembled the context:
#: they reach Qt widgets, the interface or the live project, where a call from
#: another thread crashes QGIS instead of merely being slow (decision-69).
GUI_BOUND_CAPABILITIES: Final = frozenset(
    {"actions", "desktop", "files", "layers", "project", "streams", "ui"}
)

#: ``(context type, capability, thread)`` triples already reported, so one
#: mistaken read does not fill a log with the same line. The thread object is
#: the key rather than its identifier, which the interpreter recycles once a
#: thread has finished.
_reported_cross_thread: set[tuple[str, str, threading.Thread]] = set()


def _report_cross_thread(context: object, name: str) -> None:
    """Report a GUI-bound capability read off the thread that assembled it.

    This is the half of the worker contract a source check cannot see
    (TASK-117): a capability captured on the driving thread and used inside a
    job. The default is one warning per capability and thread, because turning
    working code into a failing one is not this guard's job; a development
    session, which ``QGIS_SDK_DEV_REQUEST`` marks, raises at the call site
    instead. A context with no recorded thread - a pure test double, a
    hand-built context - is left alone.
    """
    owner = getattr(context, "_assembled_on", None)
    current = threading.current_thread()
    if owner is None or owner is current:
        return
    message = (
        f"{type(context).__name__}.{name} is GUI-bound and was read from "
        f"{current.name!r} rather than from the thread that "
        "assembled the context; prepare GUI state on that thread and hand plain "
        "values to a job (decision-69)"
    )
    if dev_request() is not None:
        raise QgisSdkUnsupportedCapabilityError(name, message)
    key = (type(context).__name__, name, current)
    if key in _reported_cross_thread:
        return
    _reported_cross_thread.add(key)
    warnings.warn(message, QgisSdkThreadSafetyWarning, stacklevel=3)


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
        if self.name in GUI_BOUND_CAPABILITIES:
            _report_cross_thread(instance, self.name)
        service = getattr(instance, self.slot)
        if service is None:
            raise QgisSdkUnsupportedCapabilityError(self.name)
        return service


class _Context:
    """What the four contexts share: immutability and the capability probes."""

    __slots__ = ("_assembled_on",)

    _capability_names: ClassVar[tuple[str, ...]] = ()

    def _assemble(self, **values: Any) -> None:
        # Which thread owns the GUI-bound capabilities of this context, read
        # back by the capability guard; recorded before anything else so a
        # context is never briefly thread-less.
        object.__setattr__(self, "_assembled_on", threading.current_thread())
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
        host = getattr(self, "host", None)
        prefix = f"host={host}, " if host is not None else ""
        return (
            f"{type(self).__name__}({prefix}scope={self.scope!r}, "  # type: ignore[attr-defined]
            f"capabilities={provided})"
        )


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
        "_features",
        "_files",
        "_jobs",
        "_layers",
        "_log",
        "_network",
        "_processing",
        "_project",
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
        "features",
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
    #: Layer data and the expressions that select it (decision-54 point 3): a
    #: layer is a description, a feature is data, and editing is an explicitly
    #: opened session rather than another method here.
    features: Capability[Features] = Capability()
    project: Capability[Project] = Capability()
    settings: Capability[Settings] = Capability()
    styles: Capability[Styles] = Capability()
    algorithms: Capability[Algorithms] = Capability()
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
        desktop: DesktopAccess | None = None,
        network: Network | None = None,
        layers: Layers | None = None,
        features: Features | None = None,
        project: Project | None = None,
        settings: Settings | None = None,
        styles: Styles | None = None,
        algorithms: Algorithms | None = None,
        workers: Workers | None = None,
        processing: Processing | None = None,
        ui: Ui | None = None,
        files: Files | None = None,
        log: Log | None = None,
        jobs: Jobs | None = None,
        host: Host = Host.DESKTOP,
    ) -> None:
        self._assemble(
            notifications=notifications,
            scope=scope,
            host=host,
            _jobs=jobs,
            _desktop=desktop,
            _network=network,
            _layers=layers,
            _features=features,
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
        return PluginContext(self.notifications, self.scope, host=self.host, **current)


class UiContext(_Context):
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
        "_desktop",
        "_features",
        "_files",
        "_jobs",
        "_layers",
        "_log",
        "_network",
        "_project",
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
        "features",
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
    #: The plugin's feature and expression service, shared like ``layers`` so a
    #: surface handler reads the same data a page does.
    features: Capability[Features] = Capability()
    project: Capability[Project] = Capability()
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
        network: Network | None = None,
        actions: ViewActions | None = None,
        settings: Settings | None = None,
        layers: Layers | None = None,
        features: Features | None = None,
        project: Project | None = None,
        files: Files | None = None,
        log: Log | None = None,
        streams: ViewStreams | None = None,
        algorithms: Algorithms | None = None,
        ui: Ui | None = None,
        styles: Styles | None = None,
        desktop: DesktopAccess | None = None,
        jobs: Jobs | None = None,
        host: Host = Host.DESKTOP,
    ) -> None:
        self._assemble(
            notifications=notifications,
            view=view,
            scope=scope,
            host=host,
            _jobs=jobs,
            _network=network,
            _actions=actions,
            _algorithms=algorithms,
            _desktop=desktop,
            _settings=settings,
            _layers=layers,
            _features=features,
            _project=project,
            _files=files,
            _log=log,
            _streams=streams,
            _styles=styles,
            _ui=ui,
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


class WorkerContext:
    """The restricted context a ``@job`` body receives on its worker (decision-65).

    A job body runs in its entirety off the driving thread, so it is handed
    only what a worker may safely touch: ``progress`` and a cooperative
    ``cancellation``, both thread-safe by contract. Everything the driving
    thread owns - the project and its layers, the Processing algorithms, the
    interface, the surfaces, another worker pool - is absent, and reading it
    fails by name with the reason instead of returning ``None`` or a live
    object that would crash QGIS from a worker thread.

    This is a guard, not a sandbox. A body can still reach a module-level
    ``iface`` it imported itself, pass a live layer in as an argument, or call
    a helper that does either; ``qgis-sdk check`` names the imports it can see
    (TASK-117) and the runtime refuses what reaches the context, but neither
    proves thread safety. Prepare GUI state before submission and apply GUI
    updates in a callback, which is delivered on the driving thread.
    """

    __slots__ = ("cancellation", "progress")

    progress: Progress
    cancellation: Cancellation

    #: Names a driving-thread context carries and a worker does not, with the
    #: sentence the refusal shows.
    _REFUSED: ClassVar[dict[str, str]] = {
        "algorithms": (
            "Processing runs on the thread that owns the application; return a "
            "result and invoke it from the subscriber instead"
        ),
        "files": "file dialogs are GUI state; resolve a path before submitting",
        "iface": "the QGIS interface belongs to the driving thread",
        "layers": "layers are GUI-affine; pass plain values and re-read them on delivery",
        "network": "the network client suspends on the driving thread, not on a worker",
        "notifications": "the message bar is GUI state; report through the job outcome",
        "project": "the project service is owned by the driving thread",
        "scope": "the job's scope closes on delivery, on the driving thread",
        "ui": "surfaces are GUI state; open one from the driving thread",
        "view": "a view outlives no job and is not thread-safe",
        "workers": "the job body is already on a worker",
    }

    def __init__(self, progress: Progress, cancellation: Cancellation) -> None:
        object.__setattr__(self, "progress", progress)
        object.__setattr__(self, "cancellation", cancellation)

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError(f"WorkerContext is assembled once; {name!r} is read-only")

    def __delattr__(self, name: str) -> None:
        raise AttributeError(f"WorkerContext is assembled once; {name!r} is read-only")

    def __getattr__(self, name: str) -> Any:
        """Refuse a driving-thread capability by name, never with a bare AttributeError.

        Only reached for names the context does not carry, so ``progress`` and
        ``cancellation`` keep working. Dunders raise ``AttributeError`` so
        copying, pickling and ``repr`` still behave like a plain object.
        """
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        reason = self._REFUSED.get(name)
        if reason is None:
            reason = (
                "a job body runs on a worker and only progress and cancellation "
                "are available there"
            )
        raise QgisSdkUnsupportedCapabilityError(name, reason)

    def __repr__(self) -> str:
        return "WorkerContext(progress=..., cancellation=...)"


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

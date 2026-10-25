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

from typing import Any, ClassVar, Generic, TypeVar, overload

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
    web-view host surface wraps (decision-27). A host that builds the bridge
    from this context (``HostServices.from_context``) hands both sides the same
    instances, so a Python handler and a page read one project. Each service
    is a :class:`Capability`: reading one the host did not provide fails by
    name (decision-39).
    """

    __slots__ = (
        "_algorithms",
        "_desktop",
        "_layers",
        "_network",
        "_project",
        "_settings",
        "_styles",
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
        )


class UiContext(_Context):
    """Capabilities for one view; a close request is not synchronous disposal."""

    __slots__ = ("_network", "notifications", "scope", "view")

    _capability_names = ("network",)

    notifications: Notifications
    view: ViewControl
    scope: ResourceScope
    network: Capability[Network] = Capability()

    def __init__(
        self,
        notifications: Notifications,
        view: ViewControl,
        scope: ResourceScope,
        network: Network | None = None,
    ) -> None:
        self._assemble(
            notifications=notifications, view=view, scope=scope, _network=network
        )


class AlgorithmContext(_Context):
    """Execution-only capabilities for one Processing invocation.

    Built fresh for each invocation and thrown away afterwards (decision-11), so
    an author class can hold it as ``self.ctx`` without carrying state from one
    run into the next. It is not a ``PluginContext``: no ``iface``, no dialogs,
    no GUI notifications - only what one execution legitimately needs.
    """

    __slots__ = ("_network", "algorithms", "cancellation", "progress", "scope")

    _capability_names = ("network",)

    progress: Progress
    cancellation: Cancellation
    scope: ResourceScope
    algorithms: Algorithms
    network: Capability[Network] = Capability()

    def __init__(
        self,
        progress: Progress,
        cancellation: Cancellation,
        scope: ResourceScope,
        algorithms: Algorithms,
        network: Network | None = None,
    ) -> None:
        self._assemble(
            progress=progress,
            cancellation=cancellation,
            scope=scope,
            algorithms=algorithms,
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
    teardown decision-21 forbids. ``workers`` and ``network`` are capabilities:
    ``await ctx.workers.offload(work)`` on a host without a pool fails by name.
    """

    __slots__ = ("_network", "_workers", "cancellation", "progress", "scope")

    _capability_names = ("workers", "network")

    progress: Progress
    cancellation: Cancellation
    scope: ResourceScope
    workers: Capability[Workers] = Capability()
    network: Capability[Network] = Capability()

    def __init__(
        self,
        progress: Progress,
        cancellation: Cancellation,
        scope: ResourceScope,
        workers: Workers | None = None,
        network: Network | None = None,
    ) -> None:
        self._assemble(
            progress=progress,
            cancellation=cancellation,
            scope=scope,
            _workers=workers,
            _network=network,
        )

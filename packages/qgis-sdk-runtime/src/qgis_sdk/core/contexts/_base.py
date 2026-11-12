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
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Final, Generic, TypeVar, overload

from qgis_sdk.core.host import Host
from qgis_sdk.environment import dev_request
from qgis_sdk.models import (
    QgisSdkThreadSafetyWarning,
    QgisSdkUnsupportedCapabilityError,
)
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
    Processing,
    Project,
    Rasters,
    Settings,
    Styles,
    Ui,
    Workers,
)

if TYPE_CHECKING:
    from qgis_sdk.jobs import Jobs
T = TypeVar("T")
GUI_BOUND_CAPABILITIES: Final = frozenset(
    {
        "actions",
        "canvas",
        "connections",
        "desktop",
        "files",
        "layers",
        "layouts",
        "project",
        "rasters",
        "streams",
        "ui",
    }
)
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


class Context:
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


@dataclass(frozen=True, slots=True)
class PluginServices:
    """What a host provides to a plugin context, and which host it is.

    One record instead of twenty keyword parameters (decision-81). Every field
    is optional because every one of them is a :class:`Capability` on the
    context: `PluginContext` reads this once and sets one slot per capability
    name, so a service added to the context is still two lines - the field here
    and the slot the class declares.

    ``host`` travels with the services rather than beside them: it is what the
    host says about itself (decision-52 point 4), and a host that builds a
    context to hand its services over is stating both at once.
    """

    host: Host = Host.DESKTOP
    desktop: DesktopAccess | None = None
    network: Network | None = None
    layers: Layers | None = None
    rasters: Rasters | None = None
    features: Features | None = None
    layouts: Layouts | None = None
    connections: Connections | None = None
    canvas: Canvas | None = None
    project: Project | None = None
    settings: Settings | None = None
    styles: Styles | None = None
    algorithms: Algorithms | None = None
    workers: Workers | None = None
    processing: Processing | None = None
    ui: Ui | None = None
    files: Files | None = None
    log: Log | None = None
    jobs: Jobs | None = None

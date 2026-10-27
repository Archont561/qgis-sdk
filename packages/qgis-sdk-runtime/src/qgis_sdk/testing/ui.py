"""Fakes for the UI contracts, and a way to build a surface without Qt.

``FakeUi`` is what a pure test hands a ``PluginContext`` as ``ui``: an action
that calls ``self.ctx.ui.open(BufferDialog, initial={...})`` is observed as
one :class:`OpenedSurface` record, and nothing is built - ``build()`` is the
author's Qt code and runs only under a host. Given the plugin class, the fake
also refuses a surface the class does not list, exactly as the Desktop does.

:func:`fake_ui_context` assembles the ``UiContext`` a surface sees, over
recording fakes; :func:`build_surface` runs a surface's ``build()`` under it
the way the host does, so a catalogue tree can be driven and snapshotted in
a pure test (TASK-96).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from qgis_sdk.core import ResourceScope, UiContext
from qgis_sdk.models import QgisSdkUiError
from qgis_sdk.ui.components import Component
from qgis_sdk.ui.surfaces import Surface, describe_surface, is_surface_class

__all__ = [
    "BuiltSurface",
    "FakeUi",
    "FakeViewControl",
    "OpenedSurface",
    "build_surface",
    "fake_ui_context",
]


@dataclass(frozen=True, slots=True)
class OpenedSurface:
    """One ``ctx.ui.open`` call the fake recorded."""

    surface: type
    initial: Mapping[str, object]

    @property
    def id(self) -> str:
        return describe_surface(self.surface).id


class FakeUi:
    """Record ``open`` calls; refuse unregistered surfaces when a plugin is known."""

    def __init__(
        self, scope: ResourceScope, *, plugin_class: type | None = None
    ) -> None:
        self._scope = scope
        self._plugin_class = plugin_class
        self._opened: list[OpenedSurface] = []

    @property
    def opened(self) -> tuple[OpenedSurface, ...]:
        """Every recorded opening, oldest first."""
        return tuple(self._opened)

    def open(
        self, surface: type, *, initial: Mapping[str, object] | None = None
    ) -> OpenedSurface:
        self._scope.ensure_open()
        if not is_surface_class(surface):
            name = getattr(surface, "__name__", repr(surface))
            raise QgisSdkUiError(f"{name} is not a Dialog/Dock subclass")
        if self._plugin_class is not None:
            from qgis_sdk.bindings import describe_bindings

            if all(
                bound.cls is not surface
                for bound in describe_bindings(self._plugin_class).surfaces
            ):
                raise QgisSdkUiError(
                    f"{surface.__name__} is not registered: list it in "
                    f"{self._plugin_class.__name__}.surfaces"
                )
        record = OpenedSurface(surface, MappingProxyType(dict(initial or {})))
        self._opened.append(record)
        return record


@dataclass(slots=True)
class FakeViewControl:
    """Count close requests; the owning test decides what closing means."""

    close_requests: int = field(default=0)

    def request_close(self) -> None:
        self.close_requests += 1


def fake_ui_context(
    scope: ResourceScope | None = None,
    *,
    runtime: Any | None = None,
    view_id: str = "test",
    **services: Any,
) -> UiContext:
    """The ``UiContext`` a surface sees, over recording fakes.

    ``notifications`` (a ``RecordingNotifications``), ``view`` (a
    ``FakeViewControl``) and ``log`` (a ``RecordingLog``) are provided
    unless passed; ``layers``, ``project``, ``files``, ``settings``,
    ``network`` and ``actions`` are carried when given. ``runtime`` - a
    started ``PluginRuntime`` - builds ``actions`` as the host would.
    """
    from qgis_sdk.ui.actions import ViewActions

    from .fakes import RecordingLog, RecordingNotifications

    if scope is None:
        scope = ResourceScope()
    notifications = services.pop("notifications", None) or RecordingNotifications(scope)
    view = services.pop("view", None) or FakeViewControl()
    if "log" not in services:
        services["log"] = RecordingLog(scope)
    if runtime is not None:
        if "actions" in services:
            raise QgisSdkUiError("fake_ui_context: pass runtime or actions, not both")
        services["actions"] = ViewActions(runtime, view_id=view_id)
    return UiContext(notifications, view, scope, **services)


@dataclass(slots=True)
class BuiltSurface:
    """A surface built under the fake: the instance, its root and its context."""

    surface: Any
    root: Any
    ctx: UiContext

    def find(self, name: str) -> Component:
        """The component called ``name`` anywhere in the tree."""
        root = self.root
        if not isinstance(root, Component):
            raise QgisSdkUiError("build() returned no catalogue component")
        if root.name == name:
            return root
        finder = getattr(root, "find", None)
        if finder is None:
            raise QgisSdkUiError(f"{root.name!r} has no children to search")
        return finder(name)

    def close(self) -> None:
        """What closing the window does: ``on_close()``, then the scope."""
        on_close = getattr(self.surface, "on_close", None)
        try:
            if callable(on_close):
                on_close()
        finally:
            if not self.ctx.scope.closed:
                self.ctx.scope.close()


def build_surface(
    surface: type, ctx: UiContext, *, initial: Mapping[str, object] | None = None
) -> BuiltSurface:
    """Run ``surface.build()`` under ``ctx`` exactly as the host would, minus Qt.

    The instance gets ``ctx`` and ``initial`` first; a catalogue component
    ``build()`` returns is attached to the context, never mounted. A surface
    in the widget form is refused: it *is* a Qt widget and opens only under
    a host.
    """
    if not is_surface_class(surface):
        name = getattr(surface, "__name__", repr(surface))
        raise QgisSdkUiError(f"{name} is not a Dialog/Dock subclass")
    if not issubclass(surface, Surface):
        raise QgisSdkUiError(
            f"{surface.__name__} is a widget surface; it needs Qt and a host to open"
        )
    instance = surface()
    instance.ctx = ctx
    instance.initial = MappingProxyType(dict(initial or {}))
    root = instance.build()
    if isinstance(root, Component) and not root.attached:
        root.attach(ctx)
    return BuiltSurface(instance, root, ctx)

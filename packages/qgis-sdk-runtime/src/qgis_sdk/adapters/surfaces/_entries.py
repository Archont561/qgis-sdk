"""Place a plugin's surfaces and bindings on the QGIS Desktop (decision-55).

The host-owned half of the surfaces API. :class:`SurfaceHost` is what ``ctx.ui`` is
under ``host()``: it opens a ``Dialog`` (a fresh instance, its own
``UiContext`` bound before ``build()``, disposed with its scope when the
window closes) and shows or hides a ``Dock`` (one instance per runtime, its
visibility remembered in the plugin's settings). :class:`DesktopBindings`
turns ``describe_bindings`` into ``QAction``\\ s on the toolbar, under the
menus and behind shortcuts, in declaration order, and takes them down again
on unload. The trigger rule lives in :meth:`DesktopBindings.trigger`.

Qt is imported inside the methods: the module loads without QGIS, so the pure
host tests import it, and ``adapters.desktop`` stays Qt-free at module level.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Final

from qgis_sdk.adapters._qt import qt_enum
from qgis_sdk.bindings import (
    BoundAction,
    BoundSurface,
    MenuBinding,
    ShortcutBinding,
    ToolbarBinding,
)
from qgis_sdk.models import QgisSdkUiError
from qgis_sdk.resources import icon_path
from qgis_sdk.ui.streams import ViewStreams
from qgis_sdk.ui.surfaces import Surface


def report_job_phase1(Qgis, done, entry, handle):
    handle.on_failure(
        lambda error: done(f"{entry.title} failed: {error}", Qgis.MessageLevel.Warning)
    )
    handle.on_cancelled(
        lambda: done(f"{entry.title} cancelled", Qgis.MessageLevel.Warning)
    )


MENU_HOOKS: Final[Mapping[str, tuple[str, str]]] = MappingProxyType(
    {
        "plugins": ("addPluginToMenu", "removePluginMenu"),
        "vector": ("addPluginToVectorMenu", "removePluginVectorMenu"),
        "raster": ("addPluginToRasterMenu", "removePluginRasterMenu"),
        "database": ("addPluginToDatabaseMenu", "removePluginDatabaseMenu"),
        "web": ("addPluginToWebMenu", "removePluginWebMenu"),
        "mesh": ("addPluginToMeshMenu", "removePluginMeshMenu"),
    }
)
DOCK_VISIBLE_SETTING: Final = "ui.{surface}.visible"


def dock_visible_setting(surface_id: str) -> str:
    return DOCK_VISIBLE_SETTING.format(surface=surface_id)


def qt_area(name: str) -> Any:
    from qgis.PyQt.QtCore import Qt

    return qt_enum(Qt, "DockWidgetArea", f"{name.capitalize()}DockWidgetArea")


@dataclass(frozen=True, slots=True)
class EntryRig:
    """The Qt classes and parent window one action is placed against."""

    parent: Any
    action_class: Any
    icon_class: Any
    keys_class: Any


@dataclass(slots=True)
class Placement:
    """Everything placing one toolbar/menu/shortcut binding needs."""

    host: Any
    binding: Any
    action: Any
    parent: Any
    placed: Placed
    icon_class: Any
    keys_class: Any


def action_text(entry) -> str:
    """The toolbar label when one is declared, else the entry's title."""
    return next(
        (
            binding.text
            for binding in entry.bindings
            if isinstance(binding, ToolbarBinding) and binding.text
        ),
        entry.title,
    )


def _place_toolbar(p: Placement) -> None:
    """Put the action on a toolbar, with its declared icon if it has one."""
    if p.binding.icon is not None:
        p.action.setIcon(
            p.icon_class(str(icon_path(p.host._package_directory, p.binding.icon)))
        )
    if not p.placed.toolbar:
        p.host._iface.addToolBarIcon(p.action)
        p.placed.toolbar = True


def _place_menu(p: Placement) -> None:
    """Add the action to the menu its path names (Plugins by default)."""
    top, _, rest = p.binding.path.partition("/")
    hooks = MENU_HOOKS.get(top.strip().lower())
    if hooks is None:
        hooks, rest = MENU_HOOKS["plugins"], p.binding.path
    name = rest.strip() or p.host._title
    getattr(p.host._iface, hooks[0])(name, p.action)
    p.placed.menus.append((hooks[1], name))


def _place_shortcut(p: Placement) -> None:
    """Register the shortcut once, so unload can undo exactly one."""
    p.action.setShortcut(p.keys_class(p.binding.keys))
    if not p.placed.shortcut:
        p.host._iface.registerMainWindowAction(p.action, p.binding.keys)
        p.parent.addAction(p.action)
        p.placed.shortcut = True


_BINDING_HANDLERS: Final[tuple[tuple[type, Any], ...]] = (
    (ToolbarBinding, _place_toolbar),
    (MenuBinding, _place_menu),
    (ShortcutBinding, _place_shortcut),
)


def placement_handler(binding) -> Any | None:
    """The first handler whose binding type matches, or nothing."""
    for kind, handler in _BINDING_HANDLERS:
        if isinstance(binding, kind):
            return handler
    return None


def chosen_surfaces(opened, surface_id):
    """One named surface, or all of them; refuse a name nothing opened."""
    if surface_id is None:
        return opened
    chosen = [entry for entry in opened if entry[0] == surface_id]
    if not chosen:
        known = ", ".join(entry[0] for entry in opened) or "none"
        raise QgisSdkUiError(f"no open surface named {surface_id!r} (open: {known})")
    return chosen


class WidgetControl:
    """``ctx.view`` for a surface: closing is a request the host honours."""

    def __init__(self, close: Callable[[], None]) -> None:
        self._close = close

    def request_close(self) -> None:
        self._close()


class StreamPump:
    """Drive one view's ``ViewStreams`` from the Qt event loop.

    A pushed event from another thread or an opened iterator wakes the pump;
    it then delivers on the GUI thread and keeps polling while a pull
    subscription is open. Nothing runs after the view's scope closed.
    """

    INTERVAL_MS = 50

    def __init__(self, scope: Any) -> None:
        from qgis.PyQt.QtCore import QMetaObject, Qt, QThread, QTimer

        self._scope = scope
        self.streams: ViewStreams | None = None
        # Created on the GUI thread, where the host opens views, so the timer
        # belongs to it; another thread may only ask it to start.
        timer = QTimer()
        timer.setInterval(self.INTERVAL_MS)
        timer.timeout.connect(self.pump)
        self._timer = timer
        self._current_thread = QThread.currentThread
        self._queued = qt_enum(Qt, "ConnectionType", "QueuedConnection")
        self._invoke = QMetaObject.invokeMethod
        scope.on_close(self._stop)

    def wake(self) -> None:
        if self._scope.closed or self.streams is None:
            return
        if self._current_thread() is not self._timer.thread():
            self._invoke(self._timer, "start", self._queued)
        elif not self._timer.isActive():
            self._timer.start()

    def pump(self) -> None:
        streams = self.streams
        if self._scope.closed or streams is None:
            self._stop()
            return
        streams.pump()
        if not streams.busy:
            self._stop()

    def _stop(self) -> None:
        if self._timer is not None:
            self._timer.stop()


@dataclass(slots=True)
class OpenDialog:
    """One shown dialog: the author's instance, the window, the view's scope."""

    surface: Surface
    widget: Any
    view_id: str
    scope: Any
    closed: bool = False


@dataclass(slots=True)
class OpenDock:
    """The one dock instance of a ``Dock`` surface while the plugin runs."""

    surface: Surface
    widget: Any
    view_id: str
    scope: Any


@dataclass(slots=True)
class Placed:
    """One ``QAction`` and the places it was put, so unload can undo each."""

    action: Any
    entry: BoundAction | BoundSurface
    toolbar: bool = False
    menus: list[tuple[str, str]] = field(default_factory=list)
    shortcut: bool = False

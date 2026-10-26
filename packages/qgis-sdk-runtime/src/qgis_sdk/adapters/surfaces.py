"""Place a plugin's surfaces and bindings on the QGIS Desktop (decision-55).

The host-owned half of TASK-67. :class:`SurfaceHost` is what ``ctx.ui`` is
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
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final

from qgis_sdk.bindings import (
    BindingsDescription,
    BoundAction,
    BoundSurface,
    MenuBinding,
    ShortcutBinding,
    ToolbarBinding,
)
from qgis_sdk.core import PluginContext, PluginRuntime, UiContext
from qgis_sdk.models import QgisSdkError, QgisSdkUiError
from qgis_sdk.resources import icon_path
from qgis_sdk.ui.actions import ViewActions
from qgis_sdk.ui.surfaces import Dock, Surface, describe_surface

__all__ = [
    "DOCK_VISIBLE_SETTING",
    "MENU_HOOKS",
    "DesktopBindings",
    "OpenDialog",
    "OpenDock",
    "SurfaceHost",
    "dock_visible_setting",
]

#: ``@menu("Vector/...")`` -> the ``iface`` pair that adds and removes it.
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
#: The settings key pattern a dock's visibility is remembered under.
DOCK_VISIBLE_SETTING: Final = "ui.{surface}.visible"


def dock_visible_setting(surface_id: str) -> str:
    return DOCK_VISIBLE_SETTING.format(surface=surface_id)


def _qt_area(name: str) -> Any:
    from qgis.PyQt.QtCore import Qt

    return {
        "left": Qt.DockWidgetArea.LeftDockWidgetArea,
        "right": Qt.DockWidgetArea.RightDockWidgetArea,
        "top": Qt.DockWidgetArea.TopDockWidgetArea,
        "bottom": Qt.DockWidgetArea.BottomDockWidgetArea,
    }[name]


class _WidgetControl:
    """``ctx.view`` for a surface: closing is a request the host honours."""

    def __init__(self, close: Callable[[], None]) -> None:
        self._close = close

    def request_close(self) -> None:
        self._close()


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
class _Placed:
    """One ``QAction`` and the places it was put, so unload can undo each."""

    action: Any
    entry: BoundAction | BoundSurface
    toolbar: bool = False
    menus: list[tuple[str, str]] = field(default_factory=list)
    shortcut: bool = False


class SurfaceHost:
    """``ctx.ui`` under the Desktop host; also what the bindings open and toggle."""

    def __init__(
        self,
        iface: Any,
        *,
        plugin_id: str,
        title: str,
        bindings: BindingsDescription,
    ) -> None:
        self._iface = iface
        self._plugin_id = plugin_id
        self._title = title
        self._bindings = bindings
        self._runtime: PluginRuntime | None = None
        self._context: PluginContext | None = None
        self._dialogs: list[OpenDialog] = []
        self._docks: dict[type, OpenDock] = {}
        self._openings = 0
        self._closing = False
        self._toggles: dict[type, Any] = {}

    def attach(self, runtime: PluginRuntime, context: PluginContext) -> None:
        """Bind the started runtime and its context; ``host()`` does this once."""
        self._runtime = runtime
        self._context = context

    @property
    def dialogs(self) -> tuple[OpenDialog, ...]:
        """The dialogs currently open, oldest first."""
        return tuple(dialog for dialog in self._dialogs if not dialog.closed)

    @property
    def docks(self) -> Mapping[type, OpenDock]:
        """The dock instances built so far, by surface class."""
        return MappingProxyType(self._docks)

    # -- ctx.ui --------------------------------------------------------------------

    def open(
        self, surface: type, *, initial: Mapping[str, object] | None = None
    ) -> Surface:
        """Show ``surface``: a new dialog, or the one dock made visible."""
        _runtime, context = self._require_attached()
        context.scope.ensure_open()
        bound = self._registered(surface)
        if issubclass(surface, Dock):
            dock = self._ensure_dock(bound, initial)
            dock.widget.show()
            dock.widget.raise_()
            return dock.surface
        return self._open_dialog(bound, initial).surface

    def toggle(self, surface: type, visible: bool) -> None:
        """Show or hide a dock from its checkable binding."""
        bound = self._registered(surface)
        if visible:
            self._ensure_dock(bound, None).widget.show()
        elif surface in self._docks:
            self._docks[surface].widget.hide()

    def restore_docks(self) -> None:
        """Open the docks the last session left visible (``ctx.settings``)."""
        settings = self._settings()
        if settings is None:
            return
        for bound in self._bindings.surfaces:
            if not issubclass(bound.cls, Dock):
                continue
            if settings.get(dock_visible_setting(bound.id)) == "true":
                self._ensure_dock(bound, None).widget.show()

    def close_all(self) -> None:
        """Close every dialog and remove every dock; safe to repeat.

        Unload is not the user hiding a panel, so a dock's remembered
        visibility is left as it was while the plugin ran.
        """
        self._closing = True
        for dialog in list(self._dialogs):
            if not dialog.closed:
                dialog.widget.close()
            self._dispose_dialog(dialog)
        self._dialogs.clear()
        for surface, dock in list(self._docks.items()):
            if self._iface is not None:
                self._iface.removeDockWidget(dock.widget)
            self._dispose(dock.surface, dock.scope)
            dock.widget.deleteLater()
            del self._docks[surface]
        self._runtime = None
        self._context = None
        self._closing = False

    # -- the pieces ------------------------------------------------------------------

    def _require_attached(self) -> tuple[PluginRuntime, PluginContext]:
        if self._runtime is None or self._context is None:
            raise QgisSdkUiError(
                f"{self._title}: surfaces open only while the plugin runs"
            )
        return self._runtime, self._context

    def _registered(self, surface: type) -> BoundSurface:
        try:
            return self._bindings.surface(surface)
        except QgisSdkError as error:
            raise QgisSdkUiError(str(error)) from error

    def _settings(self) -> Any | None:
        context = self._context
        if context is None or not context.has("settings"):
            return None
        return context.settings

    def _ui_context(
        self, view_id: str, close: Callable[[], None]
    ) -> tuple[UiContext, Any]:
        runtime, context = self._require_attached()
        scope = context.scope.child()
        ui = UiContext(
            context.notifications,
            _WidgetControl(close),
            scope,
            network=context.network if context.has("network") else None,
            actions=ViewActions(runtime, view_id=view_id),
            settings=self._settings(),
        )
        return ui, scope

    def _build(
        self,
        bound: BoundSurface,
        initial: Mapping[str, object] | None,
        close: Callable[[], None],
    ) -> tuple[Surface, Any, Any, str]:
        self._openings += 1
        view_id = f"{self._plugin_id}.{bound.id}#{self._openings}"
        ui, scope = self._ui_context(view_id, close)
        instance = bound.cls()
        instance.ctx = ui
        instance.initial = MappingProxyType(dict(initial or {}))
        try:
            widget = instance.build()
        except BaseException:
            scope.close()
            raise
        if widget is None:
            scope.close()
            raise QgisSdkUiError(f"{bound.cls.__name__}.build() returned no widget")
        return instance, widget, scope, view_id

    def _open_dialog(
        self, bound: BoundSurface, initial: Mapping[str, object] | None
    ) -> OpenDialog:
        from qgis.PyQt.QtWidgets import QDialog, QVBoxLayout

        parent = self._iface.mainWindow() if self._iface is not None else None
        dialog = QDialog(parent)
        instance, widget, scope, view_id = self._build(bound, initial, dialog.close)
        dialog.setWindowTitle(bound.title)
        dialog.setObjectName(f"{self._plugin_id}.{bound.id}")
        dialog.setModal(bound.surface.modal)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(widget)
        record = OpenDialog(instance, dialog, view_id, scope)
        self._dialogs.append(record)
        dialog.finished.connect(lambda _result: self._dispose_dialog(record))
        dialog.show()
        dialog.raise_()
        return record

    def _dispose_dialog(self, record: OpenDialog) -> None:
        if record.closed:
            return
        record.closed = True
        self._dispose(record.surface, record.scope)
        if record in self._dialogs:
            self._dialogs.remove(record)
        record.widget.deleteLater()

    def _ensure_dock(
        self, bound: BoundSurface, initial: Mapping[str, object] | None
    ) -> OpenDock:
        existing = self._docks.get(bound.cls)
        if existing is not None:
            return existing
        from qgis.PyQt.QtWidgets import QDockWidget

        parent = self._iface.mainWindow() if self._iface is not None else None
        dock = QDockWidget(bound.title, parent)
        dock.setObjectName(f"{self._plugin_id}.{bound.id}")
        instance, widget, scope, view_id = self._build(bound, initial, dock.hide)
        dock.setWidget(widget)
        record = OpenDock(instance, dock, view_id, scope)
        self._docks[bound.cls] = record
        area = bound.surface.area or "right"
        dock.visibilityChanged.connect(
            lambda visible: self._dock_visibility(bound, record, bool(visible))
        )
        if self._iface is not None:
            self._iface.addDockWidget(_qt_area(area), dock)
        elif parent is not None:  # pragma: no cover - a host without iface
            parent.addDockWidget(_qt_area(area), dock)
        return record

    def _dock_visibility(
        self, bound: BoundSurface, record: OpenDock, visible: bool
    ) -> None:
        if self._closing:
            return
        settings = self._settings()
        if (
            settings is not None
            and self._context is not None
            and not self._context.scope.closed
        ):
            settings.set(dock_visible_setting(bound.id), "true" if visible else "false")
        toggle = self._toggles.get(bound.cls)
        if toggle is not None and toggle.isChecked() != visible:
            toggle.blockSignals(True)
            toggle.setChecked(visible)
            toggle.blockSignals(False)

    def _dispose(self, surface: Surface, scope: Any) -> None:
        try:
            surface.on_close()
        finally:
            if not scope.closed:
                scope.close()

    def bind_toggle(self, surface: type, toggle: Any) -> None:
        """Remember the checkable ``QAction`` a dock surface answers to."""
        self._toggles[surface] = toggle

    def unbind_toggles(self) -> None:
        self._toggles.clear()


class DesktopBindings:
    """Toolbar buttons, menu entries and shortcuts for one plugin, and their removal."""

    def __init__(
        self,
        iface: Any,
        *,
        plugin_id: str,
        title: str,
        bindings: BindingsDescription,
        surfaces: SurfaceHost,
        package_directory: Path,
    ) -> None:
        self._iface = iface
        self._plugin_id = plugin_id
        self._title = title
        self._bindings = bindings
        self._surfaces = surfaces
        self._package_directory = package_directory
        self._placed: list[_Placed] = []
        self._runtime: PluginRuntime | None = None
        self._toggles: dict[type, Any] = {}

    @property
    def placed(self) -> tuple[Any, ...]:
        """The ``QAction`` objects currently placed, in declaration order."""
        return tuple(item.action for item in self._placed)

    def toggle_for(self, surface: type) -> Any | None:
        """The checkable action of a bound ``Dock``, if it has one."""
        return self._toggles.get(surface)

    def install(self, runtime: PluginRuntime) -> None:
        """Create and place every binding; a host without ``iface`` places none."""
        self._runtime = runtime
        if self._iface is None:
            return
        from qgis.PyQt.QtGui import QIcon, QKeySequence
        from qgis.PyQt.QtWidgets import QAction

        parent = self._iface.mainWindow()
        for entry in self._bindings.entries:
            text = next(
                (
                    binding.text
                    for binding in entry.bindings
                    if isinstance(binding, ToolbarBinding) and binding.text
                ),
                entry.title,
            )
            action = QAction(text, parent)
            action.setObjectName(f"{self._plugin_id}.{entry.id}")
            placed = _Placed(action, entry)
            is_dock = isinstance(entry, BoundSurface) and issubclass(entry.cls, Dock)
            if is_dock:
                action.setCheckable(True)
                action.toggled.connect(
                    lambda checked, cls=entry.cls: self._surfaces.toggle(
                        cls, bool(checked)
                    )
                )
                self._toggles[entry.cls] = action
            else:
                action.triggered.connect(
                    lambda _checked=False, item=entry: self.trigger(item)
                )
            for binding in entry.bindings:
                if isinstance(binding, ToolbarBinding):
                    if binding.icon is not None:
                        action.setIcon(
                            QIcon(str(icon_path(self._package_directory, binding.icon)))
                        )
                    if not placed.toolbar:
                        self._iface.addToolBarIcon(action)
                        placed.toolbar = True
                elif isinstance(binding, MenuBinding):
                    top, _, rest = binding.path.partition("/")
                    hooks = MENU_HOOKS.get(top.strip().lower())
                    if hooks is None:
                        hooks, rest = MENU_HOOKS["plugins"], binding.path
                    name = rest.strip() or self._title
                    getattr(self._iface, hooks[0])(name, action)
                    placed.menus.append((hooks[1], name))
                elif isinstance(binding, ShortcutBinding):
                    action.setShortcut(QKeySequence(binding.keys))
                    if not placed.shortcut:
                        self._iface.registerMainWindowAction(action, binding.keys)
                        parent.addAction(action)
                        placed.shortcut = True
            self._placed.append(placed)
        for cls, toggle in self._toggles.items():
            self._surfaces.bind_toggle(cls, toggle)

    def sync_toggles(self) -> None:
        """After ``restore_docks``: check the toggles of the docks now visible."""
        for cls, toggle in self._toggles.items():
            dock = self._surfaces.docks.get(cls)
            visible = dock is not None and dock.widget.isVisible()
            if toggle.isChecked() != visible:
                toggle.blockSignals(True)
                toggle.setChecked(visible)
                toggle.blockSignals(False)

    def remove(self) -> None:
        """Take every placed action down again; safe to repeat."""
        if self._iface is not None:
            for placed in self._placed:
                if placed.toolbar:
                    self._iface.removeToolBarIcon(placed.action)
                for remover, name in placed.menus:
                    getattr(self._iface, remover)(name, placed.action)
                if placed.shortcut:
                    self._iface.unregisterMainWindowAction(placed.action)
                    self._iface.mainWindow().removeAction(placed.action)
                placed.action.deleteLater()
        self._placed.clear()
        self._toggles.clear()
        self._surfaces.unbind_toggles()
        self._runtime = None

    # -- the trigger rule ------------------------------------------------------------

    def trigger(self, entry: BoundAction | BoundSurface) -> Any:
        """What a click does (decision-55): run, open, report, or refuse by name."""
        runtime = self._runtime
        if runtime is None:
            raise QgisSdkUiError(f"{self._title}: the plugin is not running")
        if isinstance(entry, BoundSurface):
            return self._surfaces.open(entry.cls)
        if entry.takes_inputs:
            message = (
                f"{entry.id} takes inputs; open a surface that collects them "
                "(UI003: a bound typed action has no surface)"
            )
            self._warn(message)
            raise QgisSdkUiError(message)
        try:
            result = runtime.actions[entry.id]()
        except QgisSdkError as error:
            self._warn(str(error))
            raise
        if _is_job_handle(result):
            self._report_job(entry, result)
        return result

    def _warn(self, message: str) -> None:
        if self._iface is None:
            return
        self._iface.messageBar().pushWarning(self._title, message)

    def _report_job(self, entry: BoundAction, handle: Any) -> None:
        """Follow a submitted job on the message bar: progress, then the outcome."""
        if self._iface is None:
            return
        from qgis.core import Qgis
        from qgis.PyQt.QtWidgets import QProgressBar

        bar = self._iface.messageBar()
        item = bar.createMessage(self._title, f"{entry.title} running")
        progress = QProgressBar()
        progress.setRange(0, 100)
        progress.setObjectName(f"{self._plugin_id}.{entry.id}.progress")
        item.layout().addWidget(progress)
        bar.pushWidget(item, Qgis.MessageLevel.Info)

        def done(message: str, level: Any) -> None:
            bar.popWidget(item)
            bar.pushMessage(self._title, message, level=level)

        handle.on_progress(lambda fraction: progress.setValue(int(fraction * 100)))
        handle.on_success(
            lambda _result: done(f"{entry.title} finished", Qgis.MessageLevel.Success)
        )
        handle.on_failure(
            lambda error: done(
                f"{entry.title} failed: {error}", Qgis.MessageLevel.Warning
            )
        )
        handle.on_cancelled(
            lambda: done(f"{entry.title} cancelled", Qgis.MessageLevel.Warning)
        )


def _is_job_handle(value: object) -> bool:
    status = getattr(value, "status", None)
    return (
        status is not None
        and hasattr(status, "settled")
        and hasattr(value, "on_progress")
    )


def surface_id_of(surface: type) -> str:
    """The id a surface class gets, for tests that look widgets up by name."""
    return describe_surface(surface).id

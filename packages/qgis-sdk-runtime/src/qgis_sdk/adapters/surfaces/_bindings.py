from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypedDict, Unpack

from qgis_sdk.adapters._qt import action_class
from qgis_sdk.bindings import (
    BindingsDescription,
    BoundAction,
    BoundSurface,
)
from qgis_sdk.core import PluginRuntime
from qgis_sdk.models import QgisSdkError, QgisSdkUiError
from qgis_sdk.ui.surfaces import describe_surface

from ._entries import (
    EntryRig,
    Placed,
    Placement,
    action_text,
    placement_handler,
    report_job_phase1,
)
from ._host import SurfaceHost


class DesktopBindings:
    """Toolbar buttons, menu entries and shortcuts for one plugin, and their removal."""

    def __init__(self, iface: Any, **options: Unpack[_InitOptions1]) -> None:
        values = _InitValues1(**options)
        self._iface = iface
        self._plugin_id = values.plugin_id
        self._title = values.title
        self._bindings = values.bindings
        self._surfaces = values.surfaces
        self._package_directory = values.package_directory
        self._placed: list[Placed] = []
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

        rig = EntryRig(self._iface.mainWindow(), action_class(), QIcon, QKeySequence)
        for entry in self._bindings.entries:
            self._install_entry(entry, rig)
        for cls, toggle in self._toggles.items():
            self._surfaces.bind_toggle(cls, toggle)

    def _install_entry(self, entry, rig: EntryRig) -> None:
        """One action: its label, dock/trigger connection and every placement."""
        action = rig.action_class(action_text(entry), rig.parent)
        action.setObjectName(f"{self._plugin_id}.{entry.id}")
        placed = Placed(action, entry)
        if isinstance(entry, BoundSurface) and entry.surface.kind == "dock":
            action.setCheckable(True)
            action.toggled.connect(
                lambda checked, cls=entry.cls: self._surfaces.toggle(cls, bool(checked))
            )
            self._toggles[entry.cls] = action
        else:
            action.triggered.connect(
                lambda _checked=False, item=entry: self.trigger(item)
            )
        for binding in entry.bindings:
            handler = placement_handler(binding)
            if handler is not None:
                handler(
                    Placement(
                        self,
                        binding,
                        action,
                        rig.parent,
                        placed,
                        rig.icon_class,
                        rig.keys_class,
                    )
                )
        self._placed.append(placed)

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
        report_job_phase1(Qgis, done, entry, handle)


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


class _InitOptions1(TypedDict, total=False):
    plugin_id: str
    title: str
    bindings: BindingsDescription
    surfaces: SurfaceHost
    package_directory: Path


@dataclass(frozen=True, slots=True)
class _InitValues1:
    plugin_id: str
    title: str
    bindings: BindingsDescription
    surfaces: SurfaceHost
    package_directory: Path

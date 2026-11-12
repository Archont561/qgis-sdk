from __future__ import annotations

from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Any

from qgis_sdk.bindings import (
    BindingsDescription,
    BoundSurface,
)
from qgis_sdk.core import PluginContext, PluginRuntime, UiContext
from qgis_sdk.models import QgisSdkUiError
from qgis_sdk.ui.actions import ViewActions
from qgis_sdk.ui.components import Component
from qgis_sdk.ui.declarative import materialise
from qgis_sdk.ui.streams import ViewStreams
from qgis_sdk.ui.surfaces import Surface
from qgis_sdk.ui.wiring import wire_surface

from ._entries import (
    OpenDialog,
    OpenDock,
    StreamPump,
    WidgetControl,
    dock_visible_setting,
    qt_area,
)
from ._host_mixin import SurfaceHostMixin1


class _SurfaceHostMixin2:
    def _ui_context(
        self, view_id: str, close: Callable[[], None]
    ) -> tuple[UiContext, Any]:
        runtime, context = self._require_attached()
        scope = context.scope.child()
        pump = StreamPump(scope)
        streams = ViewStreams(runtime, view_id=view_id, wake=pump.wake)
        pump.streams = streams
        actions = ViewActions(runtime, view_id=view_id, scope=scope)
        ui = UiContext(
            context.notifications,
            WidgetControl(close),
            scope,
            self._view_services(context, scope, actions, streams),
        )
        scope.on_close(streams.dispose)
        return ui, scope

    def _build(
        self,
        bound: BoundSurface,
        initial: Mapping[str, object] | None,
        close: Callable[[], None],
    ) -> tuple[Surface, Any, Any, str]:
        """Construct one surface, wire its tree, and hand back its child scope."""
        self._openings += 1
        view_id = f"{self._plugin_id}.{bound.id}#{self._openings}"
        ui, scope = self._ui_context(view_id, close)
        values = MappingProxyType(dict(initial or {}))
        try:
            instance, widget = self._build_instance(bound, ui, values)
            widget = self._mount_surface(instance, widget, ui, bound)
        except BaseException:
            scope.close()
            raise
        return instance, widget, scope, view_id

    def _build_instance(self, bound, ui, values):
        """Build a declarative Surface, or instantiate the widget form."""
        if issubclass(bound.cls, Surface):
            instance = bound.cls()
            # Components declared on the class become this window's own
            # copies before ``build()`` can read them (declarative form).
            materialise(instance)
            instance.ctx = ui
            instance.initial = values
            return instance, instance.build()
        # The widget form (decision-55): the class is the widget and takes the
        # context; ``initial`` is set when it can be.
        instance = bound.cls(ui)
        try:
            instance.initial = values
        except AttributeError:  # pragma: no cover - a slotted widget
            pass
        return instance, instance

    def _mount_surface(self, instance, widget, ui, bound):
        """Mount a catalogue component, then wire the finished tree."""
        root = widget
        if isinstance(widget, Component):
            # A catalogue component is state until mounted: bind it to this
            # opening's context (unless build() already did) and let it build
            # the widget that mirrors it.
            if not widget.attached:
                widget.attach(ui)
            widget = widget.mount()
        if widget is None:
            raise QgisSdkUiError(f"{bound.cls.__name__}.build() returned no widget")
        # ``@on``/``@subscribe`` and the behaviour mixins connect once the
        # tree exists; the scope undoes it all.
        wire_surface(instance, root, ui)
        return widget

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
            self._iface.addDockWidget(qt_area(area), dock)
        elif parent is not None:  # pragma: no cover - a host without iface
            parent.addDockWidget(qt_area(area), dock)
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

    def _dispose(self, surface: Any, scope: Any) -> None:
        try:
            on_close = getattr(surface, "on_close", None)
            if callable(on_close):
                on_close()
        finally:
            if not scope.closed:
                scope.close()

    def bind_toggle(self, surface: type, toggle: Any) -> None:
        """Remember the checkable ``QAction`` a dock surface answers to."""
        self._toggles[surface] = toggle

    def unbind_toggles(self) -> None:
        self._toggles.clear()


class SurfaceHost(SurfaceHostMixin1, _SurfaceHostMixin2):
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

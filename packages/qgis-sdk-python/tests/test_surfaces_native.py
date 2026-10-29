"""``host()`` placing bindings and surfaces inside a ``QgsApplication`` (TASK-67 AC 2, 3).

A fake ``iface`` over a real ``QMainWindow`` records what the host asks QGIS
to place - toolbar buttons, menu entries, shortcuts, docks - and a real
``QgsMessageBar`` receives the refusals and the job progress. The fixture
plugin is written to a temporary package so ``host()`` resolves it the way
``qgis-sdk build`` binds one, icons included.
"""

from __future__ import annotations

import sys
import textwrap
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from qgis_sdk.core import UiContext
from qgis_sdk.models import QgisSdkUiError

pytestmark = pytest.mark.qgis

try:
    from qgis.core import QgsApplication  # noqa: F401
    from qgis.gui import QgsMessageBar
    from qgis.PyQt.QtWidgets import (
        QDialog,
        QDockWidget,
        QMainWindow,
        QProgressBar,
    )
    from qgis_sdk.adapters.desktop import host
    from qgis_sdk.adapters.surfaces import dock_visible_setting
except ImportError as error:  # pragma: no cover - depends on the host
    pytest.skip(f"the surface host needs QGIS: {error}", allow_module_level=True)

PACKAGE = "surface_tools"
SPEC = f"{PACKAGE}.plugin:app"

PLUGIN = """
from __future__ import annotations

from dataclasses import dataclass

from qgis_sdk import QgisSdkPlugin, menu, shortcut, toolbar
from qgis_sdk.core import JobContext, PluginContext, ResourceScope
from qgis_sdk.jobs import JobHandle, JobService, job
from qgis_sdk.testing import FakeFiles, FakeWorkers, RecordingNotifications

from .ui import BufferDialog, LayerPanel, NoteDialog

SETTINGS: dict[str, str] = {}
CALLS: list[str] = []


class SharedSettings:
    # A settings backend over the module dict, shared by every host in the test.

    def get(self, key: str, default: str | None = None) -> str | None:
        return SETTINGS.get(key, default)

    def set(self, key: str, value: str) -> None:
        SETTINGS[key] = value


@dataclass(frozen=True)
class Total:
    total: int


@job(id="slow_sum", title="Slow sum")
def slow_sum(ctx: JobContext, a: int, b: int) -> Total:
    ctx.progress.report(0.5)
    return Total(total=a + b)


def build_context(iface: object) -> PluginContext:
    global JOBS
    scope = ResourceScope()
    JOBS = JobService(scope, workers=FakeWorkers(), gui_thread=lambda: False)
    return PluginContext(
        notifications=RecordingNotifications(scope),
        scope=scope,
        settings=SharedSettings(),
        files=FakeFiles(scope),
    )


app = QgisSdkPlugin(id="surface_tools", title="Surface tools")
app.context_factory = build_context
for surface in (BufferDialog, LayerPanel, NoteDialog):
    app.add_surface(surface)

@toolbar(icon="count.svg")
@shortcut("Ctrl+Alt+K")
@app.action(id="count", title="Count")
def count(ctx: PluginContext) -> int:
    CALLS.append("count")
    return len(CALLS)

@menu("Vector/Surface tools")
@app.action(id="typed", title="Typed")
def typed(ctx: PluginContext, distance: float) -> float:
    CALLS.append("typed")
    return distance

@toolbar(text="Sum")
@app.action(id="start_sum", title="Start sum")
def start_sum(ctx: PluginContext) -> JobHandle:
    return JOBS.delay(slow_sum, a=1, b=2)

@app.action(id="buffer", title="Buffer")
def buffer_selection(ctx: PluginContext, distance: float) -> str:
    CALLS.append(f"buffer:{distance}")
    return f"buffered {distance}"

@app.action(id="open_buffer", title="Open buffer")
def open_buffer(ctx: PluginContext) -> None:
    ctx.ui.open(BufferDialog, initial={"distance": 5})

@app.action(id="notify", title="Notify")
def notify(ctx: PluginContext) -> None:
    ctx.notifications.with_action("Count", "count").success("Done")

"""

UI = """
from __future__ import annotations

from qgis_sdk import menu, shortcut, toolbar
from qgis_sdk.ui import Dialog, Dock, Text

BUILT: list[object] = []
CLOSED: list[str] = []


@menu("Plugins/Surface tools")
class BufferDialog(Dialog):
    title = "Buffer a layer"

    def build(self):
        from qgis.PyQt.QtWidgets import QLabel

        BUILT.append(self.ctx)
        self.label = QLabel(f"distance={self.initial.get('distance', 'unset')}")
        return self.label

    def on_close(self) -> None:
        CLOSED.append("buffer_dialog")


@toolbar
@shortcut("Ctrl+Alt+L")
class LayerPanel(Dock, area="left"):
    def build(self):
        from qgis.PyQt.QtWidgets import QLabel

        BUILT.append(self.ctx)
        return QLabel("layers")

    def on_close(self) -> None:
        CLOSED.append("layer_panel")


class NoteDialog(Dialog):
    title = "A note"

    def build(self):
        # A catalogue component: the host attaches and mounts it.
        self.note = Text("note", value=self.initial.get("note", ""))
        return self.note
"""


class FakeIface:
    """Record what a plugin asks QGIS to place; back it with a real main window."""

    def __init__(self) -> None:
        self.window = QMainWindow()
        self.window.show()
        self.bar = QgsMessageBar(self.window)
        self.toolbar: list[Any] = []
        self.menus: dict[str, list[Any]] = {}
        self.docks: list[Any] = []
        self.shortcuts: list[Any] = []

    def mainWindow(self) -> QMainWindow:
        return self.window

    def messageBar(self) -> QgsMessageBar:
        return self.bar

    def addToolBarIcon(self, action: Any) -> None:
        self.toolbar.append(action)

    def removeToolBarIcon(self, action: Any) -> None:
        self.toolbar.remove(action)

    def _add(self, menu: str, name: str, action: Any) -> None:
        self.menus.setdefault(f"{menu}/{name}", []).append(action)

    def _remove(self, menu: str, name: str, action: Any) -> None:
        self.menus[f"{menu}/{name}"].remove(action)
        if not self.menus[f"{menu}/{name}"]:
            del self.menus[f"{menu}/{name}"]

    def addPluginToMenu(self, name: str, action: Any) -> None:
        self._add("Plugins", name, action)

    def removePluginMenu(self, name: str, action: Any) -> None:
        self._remove("Plugins", name, action)

    def addPluginToVectorMenu(self, name: str, action: Any) -> None:
        self._add("Vector", name, action)

    def removePluginVectorMenu(self, name: str, action: Any) -> None:
        self._remove("Vector", name, action)

    def addDockWidget(self, area: Any, dock: Any) -> None:
        self.docks.append(dock)
        self.window.addDockWidget(area, dock)

    def removeDockWidget(self, dock: Any) -> None:
        self.docks.remove(dock)
        self.window.removeDockWidget(dock)

    def registerMainWindowAction(self, action: Any, shortcut: str) -> bool:
        self.shortcuts.append(action)
        return True

    def unregisterMainWindowAction(self, action: Any) -> bool:
        self.shortcuts.remove(action)
        return True


@pytest.fixture(scope="module")
def package(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    root = tmp_path_factory.mktemp("surfaces")
    directory = root / PACKAGE
    (directory / "icons").mkdir(parents=True)
    (directory / "__init__.py").write_text("", encoding="utf-8")
    (directory / "plugin.py").write_text(textwrap.dedent(PLUGIN), encoding="utf-8")
    (directory / "ui.py").write_text(textwrap.dedent(UI), encoding="utf-8")
    (directory / "icons" / "count.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"/>',
        encoding="utf-8",
    )
    sys.path.insert(0, str(root))
    try:
        yield directory
    finally:
        sys.path.remove(str(root))
        for name in [name for name in sys.modules if name.startswith(PACKAGE)]:
            del sys.modules[name]


@pytest.fixture
def modules(package: Path) -> tuple[Any, Any]:
    import importlib

    plugin_module = importlib.import_module(f"{PACKAGE}.plugin")
    ui_module = importlib.import_module(f"{PACKAGE}.ui")
    plugin_module.CALLS.clear()
    plugin_module.SETTINGS.clear()
    ui_module.BUILT.clear()
    ui_module.CLOSED.clear()
    return plugin_module, ui_module


@pytest.fixture
def iface(qgis_app: Any) -> FakeIface:
    return FakeIface()


@pytest.fixture
def desktop(qgis_app: Any, iface: FakeIface, modules: tuple[Any, Any]) -> Iterator[Any]:
    desktop = host(SPEC)(iface)
    desktop.initGui()
    yield desktop
    desktop.unload()


def pump(qgis_app: Any) -> None:
    for _ in range(3):
        qgis_app.processEvents()


# -- bindings -------------------------------------------------------------------------


def test_init_gui_places_every_binding_in_declaration_order_and_unload_removes_them(
    qgis_app: Any, iface: FakeIface, modules: tuple[Any, Any]
) -> None:
    desktop = host(SPEC)(iface)
    desktop.initGui()

    placed = desktop.desktop_bindings.placed
    assert [action.objectName() for action in placed] == [
        "surface_tools.buffer_dialog",
        "surface_tools.layer_panel",
        "surface_tools.count",
        "surface_tools.typed",
        "surface_tools.start_sum",
    ]
    assert [action.text() for action in iface.toolbar] == [
        "Layer Panel",
        "Count",
        "Sum",
    ]
    assert not iface.toolbar[1].icon().isNull()
    assert {key: [a.text() for a in v] for key, v in iface.menus.items()} == {
        "Plugins/Surface tools": ["Buffer a layer"],
        "Vector/Surface tools": ["Typed"],
    }
    assert [action.shortcut().toString() for action in iface.shortcuts] == [
        "Ctrl+Alt+L",
        "Ctrl+Alt+K",
    ]
    assert iface.toolbar[0].isCheckable() and not iface.toolbar[1].isCheckable()

    desktop.unload()
    desktop.unload()

    assert iface.toolbar == []
    assert iface.menus == {}
    assert iface.shortcuts == []
    assert iface.docks == []
    assert desktop.desktop_bindings.placed == ()


def test_triggering_a_no_input_action_runs_it_on_the_gui_thread(
    desktop: Any, iface: FakeIface, modules: tuple[Any, Any]
) -> None:
    plugin_module, _ = modules
    count = next(a for a in iface.toolbar if a.objectName() == "surface_tools.count")

    count.trigger()

    assert plugin_module.CALLS == ["count"]


def test_triggering_a_typed_action_without_a_surface_is_refused_by_name(
    qgis_app: Any, desktop: Any, iface: FakeIface, modules: tuple[Any, Any]
) -> None:
    plugin_module, _ = modules
    typed = iface.menus["Vector/Surface tools"][0]
    entry = next(e for e in desktop.bindings.entries if e.id == "typed")

    with pytest.raises(QgisSdkUiError, match="typed takes inputs.*UI003"):
        desktop.desktop_bindings.trigger(entry)
    assert plugin_module.CALLS == []
    pump(qgis_app)
    assert any("UI003" in item.text() for item in iface.bar.items())
    assert typed.isEnabled()


def test_a_job_submitting_action_reports_on_the_message_bar(
    qgis_app: Any, desktop: Any, iface: FakeIface, modules: tuple[Any, Any]
) -> None:
    start = next(
        a for a in iface.toolbar if a.objectName() == "surface_tools.start_sum"
    )

    start.trigger()
    pump(qgis_app)

    def progress_bars() -> list[str]:
        return [
            bar.objectName()
            for bar in iface.bar.findChildren(QProgressBar)
            if bar.objectName().startswith("surface_tools.")
        ]

    assert progress_bars() == ["surface_tools.start_sum.progress"]
    jobs = modules[0].JOBS
    texts: list[str] = []
    for _ in range(20):
        jobs.tick()
        pump(qgis_app)
        texts = [item.text() for item in iface.bar.items()]
        if any("Start sum finished" in text for text in texts):
            break
    assert any("Start sum finished" in text for text in texts), texts


def test_a_notification_button_runs_the_plugin_action_through_the_host(
    desktop: Any, modules: tuple[Any, Any]
) -> None:
    plugin_module, _ = modules
    notifications = desktop.context.notifications

    desktop.runtime.actions["notify"]()
    record = notifications.records[-1]

    assert (record.level, record.message, record.action.label) == (
        "success",
        "Done",
        "Count",
    )
    assert notifications.press() == 1
    assert plugin_module.CALLS == ["count"]


def test_the_message_bar_shows_each_level_and_a_pressable_button(
    qgis_app: Any, iface: FakeIface
) -> None:
    from qgis.core import Qgis
    from qgis.PyQt.QtWidgets import QPushButton
    from qgis_sdk.adapters.desktop import MessageBarNotifications

    pressed: list[tuple[str, dict[str, Any]]] = []
    notifications = MessageBarNotifications(iface, "Surface tools")
    notifications.bind_actions(lambda action_id, **kw: pressed.append((action_id, kw)))

    notifications.warning("Careful")
    notifications.with_action("Undo", "undo", layer_id="L1").critical("Broken")
    pump(qgis_app)

    items = {item.text(): item for item in iface.bar.items()}
    assert items["Careful"].level() == Qgis.MessageLevel.Warning
    assert items["Broken"].level() == Qgis.MessageLevel.Critical
    button = items["Broken"].findChild(QPushButton, "notifications/undo")
    button.click()
    assert pressed == [("undo", {"layer_id": "L1"})]

    notifications.bind_actions(None)
    button.click()
    assert len(pressed) == 1
    MessageBarNotifications(None, "x").with_action("A", "b").info("dropped")


# -- surfaces -------------------------------------------------------------------------


def test_a_dialog_is_built_with_its_context_bound_shown_and_disposed_on_close(
    qgis_app: Any, desktop: Any, iface: FakeIface, modules: tuple[Any, Any]
) -> None:
    plugin_module, ui_module = modules
    entry = iface.menus["Plugins/Surface tools"][0]

    entry.trigger()

    (opened,) = desktop.surfaces.dialogs
    assert isinstance(opened.widget, QDialog)
    assert opened.widget.windowTitle() == "Buffer a layer"
    assert opened.widget.isVisible()
    assert isinstance(ui_module.BUILT[0], UiContext)
    assert ui_module.BUILT[0] is opened.surface.ctx
    assert opened.surface.label.text() == "distance=unset"
    assert opened.view_id.startswith("surface_tools.buffer_dialog#")

    # UiContext.actions from inside the surface: the same handler, coerced.
    assert opened.surface.ctx.actions.buffer(distance="2") == "buffered 2.0"
    # The custom context supplies only settings/files; it gains UI navigation,
    # but no absent plugin capability is silently invented for a surface.
    assert opened.surface.ctx.has("ui")
    for capability in ("algorithms", "styles", "desktop"):
        assert not opened.surface.ctx.has(capability)
    assert plugin_module.CALLS == ["buffer:2.0"]
    with pytest.raises(QgisSdkUiError, match="no action 'explode'"):
        opened.surface.ctx.actions.explode()

    opened.surface.ctx.view.request_close()
    pump(qgis_app)

    assert desktop.surfaces.dialogs == ()
    assert opened.scope.closed
    assert ui_module.CLOSED == ["buffer_dialog"]

    entry.trigger()
    (again,) = desktop.surfaces.dialogs
    assert again.surface is not opened.surface
    assert again.view_id != opened.view_id


def test_ctx_ui_open_from_an_action_opens_the_dialog_with_initial_values(
    desktop: Any, modules: tuple[Any, Any]
) -> None:
    desktop.runtime.actions["open_buffer"]()

    (opened,) = desktop.surfaces.dialogs
    assert opened.surface.label.text() == "distance=5"
    assert dict(opened.surface.initial) == {"distance": 5}


def test_build_may_return_a_catalogue_component_which_the_host_mounts(
    qgis_app: Any, desktop: Any, modules: tuple[Any, Any]
) -> None:
    from qgis.PyQt.QtWidgets import QLineEdit

    _plugin_module, ui_module = modules
    desktop.context.ui.open(ui_module.NoteDialog, initial={"note": "hello"})

    (opened,) = desktop.surfaces.dialogs
    note = opened.surface.note
    assert note.attached and note.mounted
    assert note.ctx is opened.surface.ctx
    assert note.ctx.files is desktop.context.files
    line = opened.widget.findChild(QLineEdit, "form/note")
    assert line is note.widget
    assert line.text() == "hello"

    line.setText("edited")
    assert note.value() == "edited"

    opened.surface.ctx.view.request_close()
    pump(qgis_app)
    assert opened.scope.closed
    assert note.attached is False


def test_ctx_ui_refuses_a_surface_the_plugin_does_not_list(desktop: Any) -> None:
    from qgis_sdk.ui import Dialog

    class Stray(Dialog):
        def build(self) -> object:
            return object()

    with pytest.raises(QgisSdkUiError, match="Stray is not registered"):
        desktop.context.ui.open(Stray)


def test_a_dock_is_one_instance_behind_a_checkable_toggle_with_remembered_visibility(
    qgis_app: Any, desktop: Any, iface: FakeIface, modules: tuple[Any, Any]
) -> None:
    plugin_module, ui_module = modules
    toggle = next(
        a for a in iface.toolbar if a.objectName() == "surface_tools.layer_panel"
    )
    assert toggle.isCheckable() and not toggle.isChecked()
    assert desktop.surfaces.docks == {}

    toggle.trigger()
    pump(qgis_app)

    dock = desktop.surfaces.docks[ui_module.LayerPanel]
    assert isinstance(dock.widget, QDockWidget)
    assert dock.widget in iface.docks
    assert len(ui_module.BUILT) == 1
    assert plugin_module.SETTINGS[dock_visible_setting("layer_panel")] == "true"

    toggle.trigger()
    pump(qgis_app)
    assert not dock.widget.isVisible()
    assert plugin_module.SETTINGS[dock_visible_setting("layer_panel")] == "false"

    toggle.trigger()
    pump(qgis_app)
    assert dock.widget.isVisible()
    assert desktop.surfaces.docks[ui_module.LayerPanel] is dock
    assert len(ui_module.BUILT) == 1

    dock.widget.close()
    pump(qgis_app)
    assert not toggle.isChecked()
    assert plugin_module.SETTINGS[dock_visible_setting("layer_panel")] == "false"


def test_a_visible_dock_is_restored_on_the_next_start(
    qgis_app: Any, iface: FakeIface, modules: tuple[Any, Any]
) -> None:
    plugin_module, ui_module = modules
    plugin_module.SETTINGS[dock_visible_setting("layer_panel")] = "true"

    desktop = host(SPEC)(iface)
    desktop.initGui()
    pump(qgis_app)

    dock = desktop.surfaces.docks[ui_module.LayerPanel]
    assert dock.widget.isVisible()
    assert desktop.desktop_bindings.toggle_for(ui_module.LayerPanel).isChecked()

    desktop.unload()
    pump(qgis_app)

    assert iface.docks == []
    assert dock.scope.closed
    assert ui_module.CLOSED == ["layer_panel"]
    # Unload is not the user hiding the panel: the preference survives it.
    assert plugin_module.SETTINGS[dock_visible_setting("layer_panel")] == "true"


def test_unload_closes_open_dialogs_with_their_scopes(
    qgis_app: Any, iface: FakeIface, modules: tuple[Any, Any]
) -> None:
    _, ui_module = modules
    desktop = host(SPEC)(iface)
    desktop.initGui()
    desktop.runtime.actions["open_buffer"]()
    desktop.runtime.actions["open_buffer"]()
    opened = desktop.surfaces.dialogs
    assert len(opened) == 2

    desktop.unload()
    pump(qgis_app)

    assert desktop.surfaces.dialogs == ()
    assert all(record.scope.closed for record in opened)
    assert ui_module.CLOSED == ["buffer_dialog", "buffer_dialog"]
    assert desktop.context.scope.closed
    assert isinstance(opened[0].surface.ctx, UiContext)
    with pytest.raises(QgisSdkUiError, match="only while the plugin runs"):
        desktop.surfaces.open(ui_module.BufferDialog)

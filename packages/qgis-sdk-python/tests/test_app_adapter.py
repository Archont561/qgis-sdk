"""The app adapter's Qt-free half: the ``iface`` subset and the notifications.

``qgis_sdk.adapters.app`` imports no Qt at module import: every name is reached
for inside the call that needs it. Two of its classes need nothing more than the
objects they are handed - :class:`AppWindowInterface`, which is the ``iface`` a
stand-in window provides so the SDK's existing bindings and surface host place
themselves unchanged, and :class:`AppNotifications`, which writes to the QGIS
message log and the window's status bar.

The window, the toolbar and the menus are therefore plain records here: what the
adapter promises is *which* calls it makes, and that is what these tests read.
The real widgets are ``test_app_native.py``'s business on a row that has QGIS.
"""

from __future__ import annotations

import types
from pathlib import Path
from typing import Any, ClassVar

import pytest
from qgis_sdk.adapters.app import JOB_PUMP_LOOP, AppNotifications, AppWindowInterface


class FakeMenu:
    """A menu that records its title, its children and what was added to it."""

    def __init__(self, title: str, parent: Any) -> None:
        self.title = title
        self.parent = parent
        self.object_name = ""
        self.actions: list[Any] = []
        self.menus: list[FakeMenu] = []

    def setObjectName(self, name: str) -> None:
        self.object_name = name

    def addMenu(self, title: str) -> FakeMenu:
        created = FakeMenu(title, self)
        self.menus.append(created)
        return created

    def addAction(self, action: Any) -> None:
        self.actions.append(action)

    def removeAction(self, action: Any) -> None:
        if action in self.actions:
            self.actions.remove(action)
        elif action in self.menus:
            self.menus.remove(action)

    def isEmpty(self) -> bool:
        return not self.actions and not self.menus

    def menuAction(self) -> FakeMenu:
        return self

    def parentWidget(self) -> Any:
        return self.parent


class FakeMenuBar(FakeMenu):
    def __init__(self) -> None:
        super().__init__("", None)


class FakeToolBar:
    def __init__(self) -> None:
        self.actions: list[Any] = []
        self.visible = False

    def addAction(self, action: Any) -> None:
        self.actions.append(action)

    def removeAction(self, action: Any) -> None:
        if action in self.actions:
            self.actions.remove(action)

    def setVisible(self, visible: bool) -> None:
        self.visible = visible


class FakeStatusBar:
    def __init__(self) -> None:
        self.messages: list[tuple[str, int]] = []

    def showMessage(self, text: str, timeout: int) -> None:
        self.messages.append((text, timeout))


class FakeWindow:
    def __init__(self) -> None:
        self._menu_bar = FakeMenuBar()
        self._status_bar = FakeStatusBar()
        self.actions: list[Any] = []
        self.docks: list[tuple[Any, Any]] = []

    def menuBar(self) -> FakeMenuBar:
        return self._menu_bar

    def statusBar(self) -> FakeStatusBar:
        return self._status_bar

    def addAction(self, action: Any) -> None:
        self.actions.append(action)

    def removeAction(self, action: Any) -> None:
        if action in self.actions:
            self.actions.remove(action)

    def addDockWidget(self, area: Any, dock: Any) -> None:
        self.docks.append((area, dock))

    def removeDockWidget(self, dock: Any) -> None:
        self.docks = [item for item in self.docks if item[1] is not dock]


@pytest.fixture
def window() -> FakeWindow:
    return FakeWindow()


@pytest.fixture
def iface(window: FakeWindow) -> AppWindowInterface:
    return AppWindowInterface(window, toolbar=FakeToolBar(), title="Field tools")


# -- the iface subset the bindings call ---------------------------------------------


def test_the_interface_reports_the_window_it_was_built_for(iface, window) -> None:
    assert iface.window is window
    assert iface.mainWindow() is window
    assert iface.menus == ()


def test_a_toolbar_icon_is_placed_and_the_toolbar_becomes_visible(iface) -> None:
    action = object()

    iface.addToolBarIcon(action)

    assert iface.toolbar.actions == [action]
    assert iface.toolbar.visible is True

    iface.removeToolBarIcon(action)
    assert iface.toolbar.actions == []


def test_a_menu_entry_opens_the_submenu_qgis_would_open(iface, window) -> None:
    """``addPluginToMenu(name, action)``: a submenu ``name`` under Plugins."""
    action = object()

    iface.addPluginToMenu("Field tools", action)

    (plugins,) = window.menuBar().menus
    assert plugins.title == "Plugins"
    (submenu,) = plugins.menus
    assert submenu.title == "Field tools"
    assert submenu.actions == [action]
    assert submenu.object_name == "qgis-sdk-app.plugins-field tools"
    assert iface.menus == ("Plugins", "Plugins/Field tools")


def test_every_menu_family_has_its_own_top_level_menu(iface, window) -> None:
    for add, title in (
        ("addPluginToVectorMenu", "Vector"),
        ("addPluginToRasterMenu", "Raster"),
        ("addPluginToDatabaseMenu", "Database"),
        ("addPluginToWebMenu", "Web"),
        ("addPluginToMeshMenu", "Mesh"),
    ):
        getattr(iface, add)("Field tools", object())
        assert window.menuBar().menus[-1].title == title


def test_one_submenu_is_shared_by_two_actions(iface, window) -> None:
    first, second = object(), object()

    iface.addPluginToMenu("Field tools", first)
    iface.addPluginToMenu("Field tools", second)

    (plugins,) = window.menuBar().menus
    assert plugins.menus[0].actions == [first, second]


def test_removing_an_entry_leaves_an_empty_submenu_out_of_the_bar(
    iface, window
) -> None:
    action = object()
    iface.addPluginToMenu("Field tools", action)

    iface.removePluginMenu("Field tools", action)

    assert window.menuBar().menus == []
    assert iface.menus == ()


def test_removing_an_entry_from_a_menu_nobody_opened_is_harmless(iface) -> None:
    iface.removePluginMenu("Field tools", object())

    assert iface.menus == ()


def test_a_shortcut_is_registered_on_the_window(iface, window) -> None:
    action = object()

    iface.registerMainWindowAction(action, "Ctrl+Shift+P")
    assert window.actions == [action]

    iface.unregisterMainWindowAction(action)
    assert window.actions == []


def test_a_dock_is_placed_on_the_window_and_taken_down_again(iface, window) -> None:
    dock, area = object(), "right"

    iface.addDockWidget(area, dock)
    assert window.docks == [(area, dock)]

    iface.removeDockWidget(dock)
    assert window.docks == []


def test_the_interface_renders_what_it_opened(iface) -> None:
    iface.addPluginToMenu("Field tools", object())

    assert repr(iface) == "AppWindowInterface('Field tools', 2 menu(s))"


def test_the_job_pump_is_named_so_shutdown_can_report_it() -> None:
    assert JOB_PUMP_LOOP == "job-pump"


# -- notifications ------------------------------------------------------------------


@pytest.fixture
def logged(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, Any]]:
    """A ``qgis.core`` stand-in that records what reached the message log."""
    written: list[tuple[str, str, Any]] = []

    class FakeLog:
        @staticmethod
        def logMessage(text, tag, level):
            written.append((text, tag, level))

    levels = types.SimpleNamespace(
        Info="info", Success="success", Warning="warning", Critical="critical"
    )
    core = types.ModuleType("qgis.core")
    core.QgsMessageLog = FakeLog  # type: ignore[attr-defined]
    core.Qgis = types.SimpleNamespace(MessageLevel=levels)  # type: ignore[attr-defined]
    qgis = types.ModuleType("qgis")
    qgis.core = core  # type: ignore[attr-defined]
    monkeypatch.setitem(__import__("sys").modules, "qgis", qgis)
    monkeypatch.setitem(__import__("sys").modules, "qgis.core", core)
    return written


def test_a_notification_reaches_the_log_and_the_status_bar(logged) -> None:
    window = FakeWindow()
    notifications = AppNotifications(window, tag="qgis-sdk app: demo")

    notifications.info("Buffered 12 features")

    ((text, tag, level),) = logged
    assert (text, tag) == ("Buffered 12 features", "qgis-sdk app: demo")
    assert level is not None
    assert window.statusBar().messages == [("Buffered 12 features", 10_000)]


def test_an_action_label_is_shown_in_the_text_because_a_status_line_has_no_button(
    logged,
) -> None:
    """``with_action`` still says what it would have offered."""
    notifications = AppNotifications(FakeWindow(), tag="qgis-sdk app: demo")

    notifications.with_action("Show", "open_fixture").success("Export finished")

    assert logged[0][0] == "Export finished [Show]"


def test_a_headless_app_logs_without_a_status_bar(logged) -> None:
    window = FakeWindow()
    notifications = AppNotifications(None, tag="qgis-sdk app: demo")

    notifications.critical("no window here")

    assert logged[0][0] == "no window here"
    assert window.statusBar().messages == []


# -- the backend's ownership of the application --------------------------------------


class FakeApplication:
    """A ``QgsApplication`` stand-in: records its own lifecycle."""

    nesting: ClassVar[Any] = None
    """What :meth:`instance` answers: ``None`` unless a test nests an app."""

    prefixes: ClassVar[list[tuple[str, bool]]] = []

    def __init__(self, argv: list[str], gui: bool) -> None:
        self.argv = argv
        self.gui = gui
        self.calls: list[str] = []

    @classmethod
    def instance(cls) -> Any:
        return cls.nesting

    @classmethod
    def setPrefixPath(cls, path: str, use_defaults: bool) -> None:
        cls.prefixes.append((path, use_defaults))

    def initQgis(self) -> None:
        self.calls.append("initQgis")

    def exitQgis(self) -> None:
        self.calls.append("exitQgis")

    def exec(self) -> int:
        self.calls.append("exec")
        return 0

    def processEvents(self) -> None:
        self.calls.append("processEvents")

    def quit(self) -> None:
        self.calls.append("quit")


@pytest.fixture
def pyqgis(monkeypatch: pytest.MonkeyPatch) -> type[FakeApplication]:
    """A ``qgis.core`` that offers only what the backend reaches for."""
    FakeApplication.nesting = None
    FakeApplication.prefixes = []
    core = types.ModuleType("qgis.core")
    core.QgsApplication = FakeApplication  # type: ignore[attr-defined]
    monkeypatch.setitem(__import__("sys").modules, "qgis", types.ModuleType("qgis"))
    monkeypatch.setitem(__import__("sys").modules, "qgis.core", core)
    monkeypatch.delenv("QGIS_PREFIX_PATH", raising=False)
    return FakeApplication


def test_a_plain_interpreter_is_told_which_one_to_use(monkeypatch) -> None:
    """No PyQGIS: name the mistake, instead of a traceback from a toolkit import."""
    from qgis_sdk.adapters.app import QtAppBackend
    from qgis_sdk.models import QgisSdkAppError

    monkeypatch.setitem(__import__("sys").modules, "qgis.core", None)

    with pytest.raises(QgisSdkAppError, match="cannot import PyQGIS"):
        QtAppBackend().init(())


def test_the_backend_refuses_to_put_a_second_application_in_one_process(pyqgis) -> None:
    """Inside QGIS there is already a ``QgsApplication``; that is not an app."""
    from qgis_sdk.adapters.app import QtAppBackend
    from qgis_sdk.models import QgisSdkAppError

    pyqgis.nesting = object()

    with pytest.raises(QgisSdkAppError, match="a QgsApplication is already running"):
        QtAppBackend().init(())


def test_a_graphical_run_tells_qt_it_has_a_window_system(pyqgis) -> None:
    from qgis_sdk.adapters.app import QtAppBackend

    backend = QtAppBackend()
    backend.init(["--headless"], gui=True)

    application = backend.application
    assert application.argv == ["qgis-sdk-app", "--headless"]
    assert application.gui is True
    assert application.calls == ["initQgis"]


def test_a_headless_run_asks_qt_for_no_window_system(pyqgis) -> None:
    from qgis_sdk.adapters.app import QtAppBackend

    backend = QtAppBackend()
    backend.init([], gui=False)

    assert backend.application.gui is False


def test_the_prefix_path_is_only_set_when_the_environment_names_one(
    pyqgis, monkeypatch: pytest.MonkeyPatch
) -> None:
    from qgis_sdk.adapters.app import QtAppBackend

    QtAppBackend().init(())
    assert pyqgis.prefixes == []

    monkeypatch.setenv("QGIS_PREFIX_PATH", "/opt/qgis")
    QtAppBackend().init(())
    assert pyqgis.prefixes == [("/opt/qgis", True)]


def test_the_event_loop_is_driven_through_the_application(pyqgis) -> None:
    from qgis_sdk.adapters.app import QtAppBackend

    backend = QtAppBackend()
    backend.init(())
    backend.process_events()
    backend.quit()

    assert backend.exec() == 0
    assert backend.application.calls == ["initQgis", "processEvents", "quit", "exec"]


def test_without_an_application_there_is_no_loop_to_run_or_leave(pyqgis) -> None:
    """Every method is safe before :meth:`init`, and ``exec`` says why not."""
    from qgis_sdk.adapters.app import QtAppBackend
    from qgis_sdk.models import QgisSdkAppError

    backend = QtAppBackend()
    backend.process_events()
    backend.quit()
    backend.exit()

    with pytest.raises(QgisSdkAppError, match="never initialised"):
        backend.exec()


def test_the_application_is_torn_down_exactly_once(pyqgis) -> None:
    from qgis_sdk.adapters.app import QtAppBackend

    backend = QtAppBackend()
    backend.init(())
    backend.exit()
    backend.exit()

    assert backend.application.calls == ["initQgis", "exitQgis"]


# -- where an icon comes from --------------------------------------------------------


def test_the_package_directory_is_read_from_the_declaring_module(
    monkeypatch, tmp_path
) -> None:
    from qgis_sdk.adapters.app import _package_directory

    module = types.ModuleType("demo_plugin")
    module.__file__ = str(tmp_path / "demo_plugin" / "__init__.py")
    monkeypatch.setitem(__import__("sys").modules, "demo_plugin", module)

    class FakeApp:
        module = "demo_plugin"

    assert _package_directory(FakeApp()) == tmp_path / "demo_plugin"


def test_a_module_that_is_not_loaded_falls_back_to_the_working_directory() -> None:
    """No guess from a spec string: an unimported module means the cwd."""
    from qgis_sdk.adapters.app import _package_directory

    class FakeApp:
        module = "not_imported_anywhere"

    assert _package_directory(FakeApp()) == Path()

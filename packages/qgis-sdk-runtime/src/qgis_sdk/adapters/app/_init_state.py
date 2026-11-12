"""The PyQGIS side of ``qgis_sdk.app.run``: a ``QgsApplication`` and its window.

The SDK decides *when* an application starts, what it offers its plugin and how
it stops (``qgis_sdk.app._session``); this module is the toolkit those decisions
run on. Three pieces:

``QtAppBackend``
    owns ``QgsApplication`` - ``initQgis`` on :meth:`init`, ``exitQgis`` on
    :meth:`exit` - spins the event loop and delivers what is queued.
``QtAppSurface``
    one run's context and UI: a ``QMainWindow`` with a ``QgsMapCanvas`` when the
    app is graphical, a headless context when it is not, and the placement of the
    plugin's ``@toolbar``/``@menu`` bindings and ``Dialog``/``Dock`` surfaces.
``AppWindowInterface``
    the part of a ``QgisInterface`` an app window can honour - ``mainWindow``,
    the toolbar and menu hooks, dock placement - so the bindings and surfaces
    that place themselves in QGIS Desktop place themselves here unchanged
    (decision-52 point 3: the Desktop-style bindings attach to the app's own
    window).

Nothing here imports Qt at module import: the module is imported when an app is
actually started, and every Qt name is reached for inside the call that needs it.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Final

from qgis_sdk.core import Host, NamedLoop, PluginContext, ResourceScope
from qgis_sdk.services import Notification, NotificationsBase


class CcState1:
    """A mutable record shared by the phases of one long function."""

    def __init__(_cc_self, **values):
        _cc_self.__dict__.update(values)


class CcReturn1:
    """An early return travelling out of a phase."""

    def __init__(_cc_self, value):
        _cc_self.value = value


def cc_init_p1_1(_s1):
    _s1.description = _s1.app.describe()
    _s1.self._gui = _s1.gui
    _s1.self._title = _s1.title
    _s1.self._plugin_id = _s1.description.id
    _s1.self._bindings_description: BindingsDescription = _s1.description.bindings
    _s1.self._window: Any = None
    _s1.self._canvas: Any = None
    _s1.self._interface: AppWindowInterface | None = None
    _s1.self._surfaces: Any = None
    _s1.self._bindings: Any = None


def cc_init_p2(_s1):
    if _s1.gui:
        _s1.self._open_window()
        from qgis_sdk.adapters.surfaces import SurfaceHost

        _s1.SurfaceHost = SurfaceHost

        assert _s1.self._interface is not None
        _s1.self._surfaces = _s1.SurfaceHost(
            _s1.self._interface,
            plugin_id=_s1.self._plugin_id,
            title=_s1.title,
            bindings=_s1.self._bindings_description,
        )


def cc_init_p3(_s1):
    _s1.self._context = app_context(
        ResourceScope(),
        plugin_id=_s1.self._plugin_id,
        window=_s1.self._window,
        canvas=_s1.self._canvas,
        ui=_s1.self._surfaces,
    )


def cc_init_p4(_s1):
    if _s1.gui:
        from qgis_sdk.adapters.surfaces import DesktopBindings

        _s1.DesktopBindings = DesktopBindings

        assert _s1.self._surfaces is not None
        _s1.self._bindings = _s1.DesktopBindings(
            _s1.self._interface,
            plugin_id=_s1.self._plugin_id,
            title=_s1.title,
            bindings=_s1.self._bindings_description,
            surfaces=_s1.self._surfaces,
            package_directory=_package_directory(_s1.app),
        )


class _CcState:
    """A mutable record shared by the phases of one long function."""

    def __init__(_cc_self, **values):
        _cc_self.__dict__.update(values)


class _CcReturn:
    """An early return travelling out of a phase."""

    def __init__(_cc_self, value):
        _cc_self.value = value


def _cc_init_p1(_s):
    _s.self._window = _s.window
    _s.self._tag = _s.tag


def bind_setup2(runtime, self):
    loops: list[NamedLoop] = []
    service = runtime.jobs
    layouts = self._context.layouts if self._context.has("layouts") else None
    algorithms = self._context.algorithms if self._context.has("algorithms") else None
    return algorithms, layouts, loops, service


def bind_phase1(loops, runtime, self):
    if self._surfaces is not None and self._bindings is not None:
        self._surfaces.attach(runtime, self._context)
        self._bindings.install(runtime)
        self._surfaces.restore_docks()
        self._bindings.sync_toggles()
    return tuple(loops)


def init_phase1(QgsApplication, argv, gui, prefix, self):
    if prefix:
        QgsApplication.setPrefixPath(prefix, True)
    # PyQt6's ``QgsApplication`` takes ``list[bytes]`` and raises
    # "expected bytes, str found" for a list of str; bytes works on both
    # bindings, and every other place the SDK constructs one already does
    # this (the dev probe, the catalogue, the pytest plugin).
    arguments = [b"qgis-sdk-app", *(item.encode("utf-8") for item in argv)]
    self._application = QgsApplication(arguments, gui)
    self._application.initQgis()


if TYPE_CHECKING:
    from qgis_sdk.bindings import BindingsDescription
JOB_PUMP_LOOP: Final = "job-pump"
LAYOUT_PUMP_LOOP: Final = "layouts-job-pump"
ALGORITHMS_PUMP_LOOP: Final = "algorithms-job-pump"
_MENU_PAIRS: Final[Mapping[str, str]] = {
    "addPluginToMenu": "Plugins",
    "addPluginToVectorMenu": "Vector",
    "addPluginToRasterMenu": "Raster",
    "addPluginToDatabaseMenu": "Database",
    "addPluginToWebMenu": "Web",
    "addPluginToMeshMenu": "Mesh",
}


class AppNotifications(NotificationsBase):
    """Notifications in an app window: the status bar, and the QGIS message log.

    ``with_action`` has no button here - a status-bar message is one line, and a
    button that disappears with it is a worse affordance than none - so a
    notification that carries one shows its label in the text. Every level also
    reaches ``QgsMessageLog``, which is where a headless run's messages end up.
    """

    def __init__(self, window: Any | None, *, tag: str) -> None:
        _s = _CcState(**locals())
        for _p in (_cc_init_p1,):
            _r = _p(_s)
            if isinstance(_r, _CcReturn):
                return
        return

    def _deliver(self, notification: Notification) -> None:
        from qgis.core import QgsMessageLog

        from qgis_sdk.adapters.qgis.notifications import LEVEL_MAP

        text = notification.message
        if notification.action is not None:
            text = f"{text} [{notification.action.label}]"
        QgsMessageLog.logMessage(text, self._tag, LEVEL_MAP[notification.level])
        if self._window is not None:
            self._window.statusBar().showMessage(text, 10_000)


class _AppWindowInterfaceMixin1:
    @property
    def window(self) -> Any:
        """The ``QMainWindow`` this interface places things in."""
        return self._window

    @property
    def toolbar(self) -> Any:
        """The plugin toolbar the window owns."""
        return self._toolbar

    @property
    def menus(self) -> tuple[str, ...]:
        """The menu paths opened so far (``"Plugins/Native app"``), in creation order."""
        return tuple(self._menus)

    def mainWindow(self) -> Any:
        return self._window

    def addToolBarIcon(self, action: Any) -> None:
        self._toolbar.addAction(action)
        self._toolbar.setVisible(True)

    def removeToolBarIcon(self, action: Any) -> None:
        self._toolbar.removeAction(action)

    def _menu(self, path: str) -> Any:
        """The menu at ``"Plugins/Native app"``, created level by level on first use."""
        parent: Any = self._window.menuBar()
        pieces = path.split("/")
        menu: Any = None
        for index, part in enumerate(pieces):
            key = "/".join(pieces[: index + 1])
            menu = self._menus.get(key)
            if menu is None:
                menu = parent.addMenu(part)
                menu.setObjectName(f"qgis-sdk-app.{key.casefold().replace('/', '-')}")
                self._menus[key] = menu
            parent = menu
        return menu

    def _add_to_menu(self, family: str, name: str, action: Any) -> None:
        """``iface.addPluginToMenu(name, action)``: the submenu ``name``, under ``family``."""
        self._menu(f"{_MENU_PAIRS[family]}/{name}").addAction(action)

    def _remove_from_menu(self, family: str, name: str, action: Any) -> None:
        """Take one action back out; the menus this empties go with it.

        QGIS withdraws a plugin's submenu when its last entry goes, and an app
        window has nowhere to leave an empty one either, so the prune walks up
        from the submenu to the family menu.
        """
        pieces = f"{_MENU_PAIRS[family]}/{name}".split("/")
        for depth in range(len(pieces), 0, -1):
            key = "/".join(pieces[:depth])
            menu = self._menus.get(key)
            if menu is None:
                continue
            if depth == len(pieces):
                menu.removeAction(action)
            if not menu.isEmpty():
                break
            menu.parentWidget().removeAction(menu.menuAction())
            del self._menus[key]

    def addPluginToMenu(self, name: str, action: Any) -> None:
        self._add_to_menu("addPluginToMenu", name, action)

    def removePluginMenu(self, name: str, action: Any) -> None:
        self._remove_from_menu("addPluginToMenu", name, action)

    def addPluginToVectorMenu(self, name: str, action: Any) -> None:
        self._add_to_menu("addPluginToVectorMenu", name, action)

    def removePluginVectorMenu(self, name: str, action: Any) -> None:
        self._remove_from_menu("addPluginToVectorMenu", name, action)


class _AppWindowInterfaceMixin2:
    def addPluginToRasterMenu(self, name: str, action: Any) -> None:
        self._add_to_menu("addPluginToRasterMenu", name, action)

    def removePluginRasterMenu(self, name: str, action: Any) -> None:
        self._remove_from_menu("addPluginToRasterMenu", name, action)

    def addPluginToDatabaseMenu(self, name: str, action: Any) -> None:
        self._add_to_menu("addPluginToDatabaseMenu", name, action)

    def removePluginDatabaseMenu(self, name: str, action: Any) -> None:
        self._remove_from_menu("addPluginToDatabaseMenu", name, action)

    def addPluginToWebMenu(self, name: str, action: Any) -> None:
        self._add_to_menu("addPluginToWebMenu", name, action)

    def removePluginWebMenu(self, name: str, action: Any) -> None:
        self._remove_from_menu("addPluginToWebMenu", name, action)

    def addPluginToMeshMenu(self, name: str, action: Any) -> None:
        self._add_to_menu("addPluginToMeshMenu", name, action)

    def removePluginMeshMenu(self, name: str, action: Any) -> None:
        self._remove_from_menu("addPluginToMeshMenu", name, action)

    def registerMainWindowAction(self, action: Any, shortcut: str) -> None:
        self._window.addAction(action)

    def unregisterMainWindowAction(self, action: Any) -> None:
        self._window.removeAction(action)

    def addDockWidget(self, area: Any, dock: Any) -> None:
        self._window.addDockWidget(area, dock)

    def removeDockWidget(self, dock: Any) -> None:
        self._window.removeDockWidget(dock)


class AppWindowInterface(_AppWindowInterfaceMixin1, _AppWindowInterfaceMixin2):
    """A ``QMainWindow`` dressed as the ``iface`` the SDK's bindings expect.

    The methods are the subset ``DesktopBindings`` and ``SurfaceHost`` call -
    ``mainWindow``, the toolbar hooks, one add/remove pair per menu family,
    dock placement and main-window shortcuts. Shortcuts use the window's own
    action list rather than the QGIS shortcut manager: an app has one window, so
    there is nothing to arbitrate between plugins.
    """

    def __init__(self, window: Any, *, toolbar: Any, title: str) -> None:
        self._window = window
        self._toolbar = toolbar
        self._title = title
        self._menus: dict[str, Any] = {}

    def __repr__(self) -> str:
        return f"AppWindowInterface({self._title!r}, {len(self._menus)} menu(s))"


def app_context(
    scope: ResourceScope,
    *,
    plugin_id: str,
    window: Any | None = None,
    ui: Any | None = None,
    canvas: Any | None = None,
) -> PluginContext:
    """The context an app host offers: every curated service, no ``iface``.

    ``ctx.host`` is ``app``, ``ctx.desktop`` refuses by name - there is no
    ``QgisInterface`` behind a standalone application - and ``ctx.ui`` exists
    exactly when there is a window to open surfaces in. ``canvas`` is that
    window's ``QgsMapCanvas``, so a graphical app has ``ctx.canvas`` and a
    headless one has no view at all. That is the whole
    difference from a Desktop plugin, and it is stated here rather than inferred
    from a missing attribute somewhere downstream (decision-52 point 4).
    """
    from qgis_sdk.adapters.qgis import NativeContextOptions, native_plugin_context

    context = native_plugin_context(
        scope,
        NativeContextOptions(
            settings_prefix=plugin_id,
            notifications=AppNotifications(window, tag=f"qgis-sdk app: {plugin_id}"),
            host=Host.APP,
            canvas=canvas,
        ),
    )
    return context if ui is None else context.with_services(ui=ui)


def _package_directory(app):
    """The author's package directory, resolved without a module-level cycle."""
    from ._surface import package_directory

    return package_directory(app)

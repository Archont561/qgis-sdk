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

import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from qgis_sdk.app._backend import AppSurface
from qgis_sdk.core import Host, NamedLoop, PluginContext, PluginRuntime, ResourceScope
from qgis_sdk.core._application import QgisSdkPlugin
from qgis_sdk.models import QgisSdkAppError
from qgis_sdk.services import Notification, NotificationsBase

if TYPE_CHECKING:
    from qgis_sdk.bindings import BindingsDescription

__all__ = [
    "JOB_PUMP_LOOP",
    "AppNotifications",
    "AppWindowInterface",
    "QtAppBackend",
    "QtAppSurface",
    "app_context",
]

#: The name the app's job pump is registered under. Named because shutdown
#: reports the loops it stops (decision-69 point 4).
JOB_PUMP_LOOP: Final = "job-pump"

#: ``@menu("Vector/...")`` -> the menu this window opens for that family. An app
#: has one menu bar, so every family is a menu in it, created on first use.
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
        self._window = window
        self._tag = tag

    def _deliver(self, notification: Notification) -> None:
        from qgis.core import QgsMessageLog

        from qgis_sdk.adapters.qgis.notifications import LEVEL_MAP

        text = notification.message
        if notification.action is not None:
            text = f"{text} [{notification.action.label}]"
        QgsMessageLog.logMessage(text, self._tag, LEVEL_MAP[notification.level])
        if self._window is not None:
            self._window.statusBar().showMessage(text, 10_000)


class AppWindowInterface:
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
        """The menu names opened so far, in creation order."""
        return tuple(self._menus)

    def mainWindow(self) -> Any:
        return self._window

    def addToolBarIcon(self, action: Any) -> None:
        self._toolbar.addAction(action)
        self._toolbar.setVisible(True)

    def removeToolBarIcon(self, action: Any) -> None:
        self._toolbar.removeAction(action)

    def _menu(self, name: str) -> Any:
        menu = self._menus.get(name)
        if menu is None:
            menu = self._window.menuBar().addMenu(name)
            menu.setObjectName(f"qgis-sdk-app.{name.casefold()}")
            self._menus[name] = menu
        return menu

    def _add_to_menu(self, family: str, action: Any) -> None:
        self._menu(_MENU_PAIRS[family]).addAction(action)

    def _remove_from_menu(self, family: str, action: Any) -> None:
        menu = self._menus.get(_MENU_PAIRS[family])
        if menu is not None:
            menu.removeAction(action)

    def addPluginToMenu(self, name: str, action: Any) -> None:
        self._add_to_menu("addPluginToMenu", action)

    def removePluginMenu(self, name: str, action: Any) -> None:
        self._remove_from_menu("addPluginToMenu", action)

    def addPluginToVectorMenu(self, name: str, action: Any) -> None:
        self._add_to_menu("addPluginToVectorMenu", action)

    def removePluginVectorMenu(self, name: str, action: Any) -> None:
        self._remove_from_menu("addPluginToVectorMenu", action)

    def addPluginToRasterMenu(self, name: str, action: Any) -> None:
        self._add_to_menu("addPluginToRasterMenu", action)

    def removePluginRasterMenu(self, name: str, action: Any) -> None:
        self._remove_from_menu("addPluginToRasterMenu", action)

    def addPluginToDatabaseMenu(self, name: str, action: Any) -> None:
        self._add_to_menu("addPluginToDatabaseMenu", action)

    def removePluginDatabaseMenu(self, name: str, action: Any) -> None:
        self._remove_from_menu("addPluginToDatabaseMenu", action)

    def addPluginToWebMenu(self, name: str, action: Any) -> None:
        self._add_to_menu("addPluginToWebMenu", action)

    def removePluginWebMenu(self, name: str, action: Any) -> None:
        self._remove_from_menu("addPluginToWebMenu", action)

    def addPluginToMeshMenu(self, name: str, action: Any) -> None:
        self._add_to_menu("addPluginToMeshMenu", action)

    def removePluginMeshMenu(self, name: str, action: Any) -> None:
        self._remove_from_menu("addPluginToMeshMenu", action)

    def registerMainWindowAction(self, action: Any, shortcut: str) -> None:
        self._window.addAction(action)

    def unregisterMainWindowAction(self, action: Any) -> None:
        self._window.removeAction(action)

    def addDockWidget(self, area: Any, dock: Any) -> None:
        self._window.addDockWidget(area, dock)

    def removeDockWidget(self, dock: Any) -> None:
        self._window.removeDockWidget(dock)

    def __repr__(self) -> str:
        return f"AppWindowInterface({self._title!r}, {len(self._menus)} menu(s))"


def app_context(
    scope: ResourceScope,
    *,
    plugin_id: str,
    window: Any | None = None,
    ui: Any | None = None,
) -> PluginContext:
    """The context an app host offers: every curated service, no ``iface``.

    ``ctx.host`` is ``app``, ``ctx.desktop`` refuses by name - there is no
    ``QgisInterface`` behind a standalone application - and ``ctx.ui`` exists
    exactly when there is a window to open surfaces in. That is the whole
    difference from a Desktop plugin, and it is stated here rather than inferred
    from a missing attribute somewhere downstream (decision-52 point 4).
    """
    from qgis_sdk.adapters.qgis import native_plugin_context

    context = native_plugin_context(
        scope,
        settings_prefix=plugin_id,
        iface=None,
        notifications=AppNotifications(window, tag=f"qgis-sdk app: {plugin_id}"),
        host=Host.APP,
    )
    return context if ui is None else context.with_services(ui=ui)


class QtAppSurface:
    """One app run's window (when graphical), context and bindings."""

    def __init__(self, app: QgisSdkPlugin, *, gui: bool, title: str) -> None:
        description = app.describe()
        self._gui = gui
        self._title = title
        self._plugin_id = description.id
        self._bindings_description: BindingsDescription = description.bindings
        self._window: Any = None
        self._canvas: Any = None
        self._interface: AppWindowInterface | None = None
        self._surfaces: Any = None
        self._bindings: Any = None
        if gui:
            self._open_window()
            from qgis_sdk.adapters.surfaces import SurfaceHost

            assert self._interface is not None
            self._surfaces = SurfaceHost(
                self._interface,
                plugin_id=self._plugin_id,
                title=title,
                bindings=self._bindings_description,
            )
        self._context = app_context(
            ResourceScope(),
            plugin_id=self._plugin_id,
            window=self._window,
            ui=self._surfaces,
        )
        if gui:
            from qgis_sdk.adapters.surfaces import DesktopBindings

            assert self._surfaces is not None
            self._bindings = DesktopBindings(
                self._interface,
                plugin_id=self._plugin_id,
                title=title,
                bindings=self._bindings_description,
                surfaces=self._surfaces,
                package_directory=_package_directory(app),
            )

    def _open_window(self) -> None:
        """Create and show the window: a map canvas, a toolbar, a status bar."""
        from qgis.gui import QgsMapCanvas
        from qgis.PyQt.QtWidgets import QMainWindow

        window = QMainWindow()
        window.setWindowTitle(self._title)
        window.resize(1200, 800)
        canvas = QgsMapCanvas(window)
        canvas.setObjectName("qgis-sdk-app.canvas")
        window.setCentralWidget(canvas)
        toolbar = window.addToolBar(self._title)
        toolbar.setObjectName(f"{self._plugin_id}.toolbar")
        window.statusBar()
        window.menuBar()
        self._window = window
        self._canvas = canvas
        self._interface = AppWindowInterface(window, toolbar=toolbar, title=self._title)
        window.show()

    @property
    def context(self) -> PluginContext:
        """The context the runtime binds, built before the plugin starts."""
        return self._context

    @property
    def window(self) -> Any:
        """The ``QMainWindow``, or ``None`` for a headless app."""
        return self._window

    @property
    def canvas(self) -> Any:
        """The ``QgsMapCanvas`` the window shows, or ``None`` when headless."""
        return self._canvas

    @property
    def interface(self) -> AppWindowInterface | None:
        """The ``iface``-shaped view of the window, or ``None`` when headless."""
        return self._interface

    @property
    def surfaces(self) -> Any:
        """``ctx.ui``: the surface host that answers ``open``/``toggle``."""
        return self._surfaces

    @property
    def bindings(self) -> Any:
        """The placed toolbar/menu/shortcut actions, once :meth:`bind` ran."""
        return self._bindings

    def bind(self, runtime: PluginRuntime) -> tuple[NamedLoop, ...]:
        """Place the UI and start the job pump; return the loops started."""
        loops: list[NamedLoop] = []
        service = runtime.jobs
        if service is not None:
            from qgis_sdk.adapters.qgis.jobs import QgsJobPump

            pump = QgsJobPump(service, name=JOB_PUMP_LOOP, parent=self._window)
            pump.start()
            loops.append(pump)
        if self._surfaces is not None and self._bindings is not None:
            self._surfaces.attach(runtime, self._context)
            self._bindings.install(runtime)
            self._surfaces.restore_docks()
            self._bindings.sync_toggles()
        return tuple(loops)

    def close(self) -> None:
        """Remove the bindings, close the surfaces, close the window."""
        if self._bindings is not None:
            self._bindings.remove()
            self._bindings = None
        if self._surfaces is not None:
            self._surfaces.close_all()
        if self._window is not None:
            self._window.close()
            self._window = None
        self._canvas = None
        self._interface = None


class QtAppBackend:
    """``QgsApplication`` ownership and the event loop, for ``qgis_sdk.app.run``."""

    def __init__(self) -> None:
        self._application: Any = None
        self._exited = False

    @property
    def application(self) -> Any:
        """The ``QgsApplication`` this backend created, once :meth:`init` ran."""
        return self._application

    def init(self, argv: Sequence[str]) -> None:
        """Create and initialise the application; refuse to nest one in QGIS."""
        try:
            from qgis.core import QgsApplication
        except ImportError as error:
            # The common mistake: a distribution installed into an interpreter
            # that is not the QGIS one. Say which, instead of a traceback from
            # inside a toolkit import.
            raise QgisSdkAppError(
                "this interpreter cannot import PyQGIS (`qgis.core`), so it "
                "cannot start a standalone app; run it with the QGIS install's "
                "interpreter, or use `qgis-sdk run`, which finds one"
            ) from error
        if QgsApplication.instance() is not None:
            raise QgisSdkAppError(
                "a QgsApplication is already running in this process, so this is "
                "a plugin inside QGIS, not a standalone app; `qgis_sdk.app.run` "
                "belongs in a plain interpreter (`qgis-sdk run`)"
            )
        prefix = os.environ.get("QGIS_PREFIX_PATH")
        if prefix:
            QgsApplication.setPrefixPath(prefix, True)
        self._application = QgsApplication(["qgis-sdk-app", *argv], False)
        self._application.initQgis()

    def build(self, app: QgisSdkPlugin, *, gui: bool, title: str) -> AppSurface:
        """The surface for this run: a window when ``gui``, a headless context else."""
        return QtAppSurface(app, gui=gui, title=title)

    def exec(self) -> int:
        """Run the application's event loop until it quits."""
        if self._application is None:
            raise QgisSdkAppError("the application was never initialised")
        return int(self._application.exec())

    def process_events(self) -> None:
        """Deliver what is already queued and return."""
        if self._application is not None:
            self._application.processEvents()

    def quit(self) -> None:
        """Leave the event loop; a no-op before it started."""
        if self._application is not None:
            self._application.quit()

    def exit(self) -> None:
        """Tear the application down, once."""
        if self._exited or self._application is None:
            return
        self._exited = True
        self._application.exitQgis()


def _package_directory(app: QgisSdkPlugin) -> Path:
    """The author's package directory, for the icons its bindings name.

    Read from the module that declared the application (``qgis_sdk`` records it
    when the plugin is built), never guessed from a spec string: an app may be
    built into a distribution whose layout differs from the source tree.
    """
    module = getattr(app, "module", None)
    loaded = sys.modules.get(module) if isinstance(module, str) else None
    file = getattr(loaded, "__file__", None)
    return Path(file).resolve().parent if file is not None else Path()

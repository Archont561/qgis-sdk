from __future__ import annotations

import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from qgis_sdk.app._backend import AppSurface
from qgis_sdk.core import NamedLoop, PluginContext, PluginRuntime
from qgis_sdk.core._application import QgisSdkPlugin
from qgis_sdk.models import QgisSdkAppError

from ._init_state import (
    ALGORITHMS_PUMP_LOOP,
    JOB_PUMP_LOOP,
    LAYOUT_PUMP_LOOP,
    AppWindowInterface,
    CcReturn1,
    CcState1,
    bind_phase1,
    bind_setup2,
    cc_init_p1_1,
    cc_init_p2,
    cc_init_p3,
    cc_init_p4,
    init_phase1,
)


class QtAppSurface:
    """One app run's window (when graphical), context and bindings."""

    def __init__(self, app: QgisSdkPlugin, *, gui: bool, title: str) -> None:
        _s1 = CcState1(self=self, app=app, gui=gui, title=title)
        for _p1 in (cc_init_p1_1, cc_init_p2, cc_init_p3, cc_init_p4):
            _r1 = _p1(_s1)
            if isinstance(_r1, CcReturn1):
                return
        return

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
        algorithms, layouts, loops, service = bind_setup2(runtime, self)
        if service is None and layouts is None and algorithms is None:
            return tuple(loops)
        from qgis_sdk.adapters.qgis.jobs import QgsJobPump

        if service is not None:
            pump = QgsJobPump(service, name=JOB_PUMP_LOOP, parent=self._window)
            pump.start()
            loops.append(pump)
        # An export of a print layout submits to the layouts service's own job
        # service, which needs its own tick whether or not the plugin declares
        # jobs of its own (TASK-89).
        if layouts is not None:
            layout_pump = QgsJobPump(
                layouts.jobs, name=LAYOUT_PUMP_LOOP, parent=self._window
            )
            layout_pump.start()
            loops.append(layout_pump)
        # A batch submits to the algorithms service's own job service, for the
        # same reason (TASK-94).
        if algorithms is not None:
            algorithms_pump = QgsJobPump(
                algorithms.jobs, name=ALGORITHMS_PUMP_LOOP, parent=self._window
            )
            algorithms_pump.start()
            loops.append(algorithms_pump)
        return bind_phase1(loops, runtime, self)

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

    def init(self, argv: Sequence[str], *, gui: bool = False) -> None:
        """Create and initialise the application; refuse to nest one in QGIS.

        ``gui`` decides Qt's ``GUIenabled`` flag: a window may only be created
        under an application that was told it has a window system, and a headless
        run has no business asking for one.
        """
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
        init_phase1(QgsApplication, argv, gui, prefix, self)

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


def package_directory(app: QgisSdkPlugin) -> Path:
    """The author's package directory, for the icons its bindings name.

    Read from the module that declared the application (``qgis_sdk`` records it
    when the plugin is built), never guessed from a spec string: an app may be
    built into a distribution whose layout differs from the source tree.
    """
    module = getattr(app, "module", None)
    loaded = sys.modules.get(module) if isinstance(module, str) else None
    file = getattr(loaded, "__file__", None)
    return Path(file).resolve().parent if file is not None else Path()

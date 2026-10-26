"""Run the reload coordinator inside QGIS Desktop (the ``qgis --code`` side).

Everything that touches ``qgis.utils`` or Qt for ``qgis-sdk dev`` lives
here, imported only inside the QGIS process. The policy itself is
:mod:`.reloader`, tested without QGIS; this module is measured by the
opt-in devtools harness (``QGIS_SDK_DEVTOOLS=1``), which runs it in a real
QGIS.
"""

from __future__ import annotations

import os
import sys
import time
import traceback
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from qgis_sdk.core import QuiesceOutcome

from .reloader import (
    DEBOUNCE_MS,
    WATCH_INTERVAL_MS,
    NotifyLevel,
    ReloadCoordinator,
    SourceWatcher,
)


class QgisUtilsHost:
    """The real :class:`PluginHost`, over ``qgis.utils``."""

    def __init__(self) -> None:
        import qgis.utils

        self._utils = qgis.utils

    def available(self, name: str) -> bool:
        self._utils.updateAvailablePlugins()
        return name in self._utils.available_plugins

    def load(self, name: str) -> bool:
        return bool(self._utils.loadPlugin(name))

    def start(self, name: str) -> bool:
        return bool(self._utils.startPlugin(name))

    def unload(self, name: str) -> bool:
        unloaded = bool(self._utils.unloadPlugin(name))
        self.forget(name)
        return unloaded

    def forget(self, name: str) -> None:
        """Drop the plugin's modules so the next load reads the edited sources.

        ``qgis.utils`` forgets what its import hook saw; the source modules a
        plugin reached in other ways (``importlib``, the host package's
        extended ``__path__``) would otherwise survive as stale copies.
        """
        forget = getattr(self._utils, "_unloadPluginModules", None)
        if forget is not None:
            forget(name)
        for module in [m for m in sys.modules if m.split(".")[0] == name]:
            del sys.modules[module]

    def running(self, name: str) -> bool:
        return name in self._utils.active_plugins

    def quiesce(self, name: str) -> QuiesceOutcome:
        runtime = self._runtime(name)
        if runtime is None:
            return QuiesceOutcome(
                refused=False, blockers=()
            )  # not an SDK plugin: nothing to ask
        return runtime.quiesce()

    def resume(self, name: str) -> None:
        runtime = self._runtime(name)
        if runtime is not None:
            runtime.resume()

    def _runtime(self, name: str) -> object | None:
        held = self._utils.plugins.get(name)
        runtime = getattr(held, "runtime", None)
        if runtime is None or not hasattr(runtime, "quiesce"):
            return None
        return runtime


@dataclass
class DevSession:
    """Everything the probe keeps alive for the lifetime of QGIS."""

    request: Mapping[str, object]
    coordinator: ReloadCoordinator
    watcher: SourceWatcher | None
    timers: list[object] = field(default_factory=list)
    actions: list[object] = field(default_factory=list)

    def pump(self, seconds: float) -> None:
        """Run the Qt event loop for ``seconds``; timers and the watcher fire."""
        from qgis.PyQt.QtCore import QCoreApplication

        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            QCoreApplication.processEvents()
            time.sleep(0.02)

    def pump_until(self, condition: Callable[[], bool], *, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if condition():
                return True
            self.pump(0.05)
        return condition()


def say(message: str) -> None:
    """Write to the terminal that started ``qgis-sdk dev``, whatever QGIS does to stderr."""
    log = sys.__stderr__ or sys.stderr
    log.write(f"qgis-sdk dev: {message}\n")
    log.flush()


def bootstrap(request: Mapping[str, object]) -> DevSession:
    """Start the source plugin inside QGIS Desktop and keep it reloadable.

    Called by the ``--code`` probe with the request ``plan_dev`` wrote:
    installs the Reload action (Ctrl+Shift+R), the debounce timer, the
    source watcher when ``watch`` is on, and starts the plugin. With
    ``exercise`` set it hands over to :mod:`.exercise`, which drives the
    policy and quits QGIS.
    """
    import qgis.utils
    from qgis.core import Qgis
    from qgis.PyQt.QtCore import QCoreApplication, QTimer
    from qgis.PyQt.QtGui import QKeySequence
    from qgis.PyQt.QtWidgets import QAction

    root = Path(str(request["root"]))
    plugin = str(request["plugin"])
    iface = qgis.utils.iface
    levels = {
        "info": Qgis.MessageLevel.Info,
        "warning": Qgis.MessageLevel.Warning,
        "critical": Qgis.MessageLevel.Critical,
    }

    def notify(level: NotifyLevel, text: str) -> None:
        if iface is not None:
            iface.messageBar().pushMessage(
                "qgis-sdk dev", text, level=levels[level], duration=8
            )

    debounce = QTimer()
    debounce.setSingleShot(True)
    debounce.setInterval(DEBOUNCE_MS)
    coordinator = ReloadCoordinator(
        root=root,
        plugin=plugin,
        host=QgisUtilsHost(),
        say=say,
        notify=notify,
        schedule=debounce.start,
        pump=lambda: (QCoreApplication.processEvents(), time.sleep(0.05)),
    )
    debounce.timeout.connect(lambda: coordinator.reload())
    session = DevSession(request=request, coordinator=coordinator, watcher=None)
    session.timers.append(debounce)

    if iface is not None:
        action = QAction(f"Reload {plugin}", iface.mainWindow())
        action.setShortcut(QKeySequence("Ctrl+Shift+R"))
        action.triggered.connect(lambda _checked=False: coordinator.reload())
        iface.addToolBarIcon(action)
        session.actions.append(action)

    if request.get("watch", False):
        watcher = SourceWatcher(root, plugin, on_change=coordinator.request)
        ticker = QTimer()
        ticker.setInterval(WATCH_INTERVAL_MS)
        ticker.timeout.connect(watcher.poll)
        session.watcher = watcher
        session.timers.append(ticker)
        if not request.get("exercise"):
            ticker.start()
            say(f"watching {root / plugin} for Python changes")

    started = coordinator.start()
    exercise = request.get("exercise")
    if exercise:
        from .exercise import run_exercise

        run_exercise(session, Path(str(exercise)))
    elif not started:
        say(f"{plugin} is disabled; fix the error and press Reload (Ctrl+Shift+R)")
    return session


def report_bootstrap_failure(exercise: object) -> None:
    """Last resort for the probe: keep QGIS up, show what happened, fail an exercise."""
    import json

    say("bootstrap failed:\n" + traceback.format_exc())
    if exercise:
        Path(str(exercise)).write_text(
            json.dumps({"started": False, "error": traceback.format_exc()}),
            encoding="utf-8",
        )
        os._exit(1)

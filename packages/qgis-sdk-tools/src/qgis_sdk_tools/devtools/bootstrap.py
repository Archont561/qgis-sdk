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


class _CcState:
    """A mutable record shared by the phases of one long function."""

    def __init__(_cc_self, **values):
        _cc_self.__dict__.update(values)


class _CcReturn:
    """An early return travelling out of a phase."""

    def __init__(_cc_self, value):
        _cc_self.value = value


class _CcBreak:
    """A loop break travelling out of a phase."""


class _CcContinue:
    """A loop continue travelling out of a phase."""


def _cc_bootstrap_p1(_s):
    import qgis.utils

    _s.qgis = qgis
    from qgis.core import Qgis

    _s.Qgis = Qgis
    from qgis.PyQt.QtCore import QCoreApplication, QTimer

    _s.QCoreApplication = QCoreApplication
    _s.QTimer = QTimer
    from qgis.PyQt.QtGui import QKeySequence

    _s.QKeySequence = QKeySequence
    from qgis.PyQt.QtWidgets import QAction

    _s.QAction = QAction

    _s.root = Path(str(_s.request["root"]))
    _s.plugin = str(_s.request["plugin"])
    _s.iface = _s.qgis.utils.iface


def _cc_bootstrap_p2(_s):
    _s.levels = {
        "info": _s.Qgis.MessageLevel.Info,
        "warning": _s.Qgis.MessageLevel.Warning,
        "critical": _s.Qgis.MessageLevel.Critical,
    }

    def notify(level: NotifyLevel, text: str) -> None:
        if _s.iface is not None:
            _s.iface.messageBar().pushMessage(
                "qgis-sdk dev", text, level=_s.levels[level], duration=8
            )

    _s.notify = notify


def _cc_bootstrap_p3(_s):

    _s.debounce = _s.QTimer()
    _s.debounce.setSingleShot(True)
    _s.debounce.setInterval(DEBOUNCE_MS)


def _cc_bootstrap_p4(_s):
    _s.coordinator = ReloadCoordinator(
        root=_s.root,
        plugin=_s.plugin,
        host=QgisUtilsHost(),
        say=say,
        notify=_s.notify,
        schedule=_s.debounce.start,
        pump=lambda: (_s.QCoreApplication.processEvents(), time.sleep(0.05)),
    )
    _s.debounce.timeout.connect(lambda: _s.coordinator.reload())
    _s.session = DevSession(
        request=_s.request, coordinator=_s.coordinator, watcher=None
    )
    _s.session.timers.append(_s.debounce)


def _cc_bootstrap_p5(_s):

    if _s.iface is not None:
        _s.action = _s.QAction(f"Reload {_s.plugin}", _s.iface.mainWindow())
        _s.action.setShortcut(_s.QKeySequence("Ctrl+Shift+R"))
        _s.action.triggered.connect(lambda _checked=False: _s.coordinator.reload())
        _s.iface.addToolBarIcon(_s.action)
        _s.session.actions.append(_s.action)


def _cc_bootstrap_p6(_s):

    if _s.request.get("watch", False):
        _s.watcher = SourceWatcher(_s.root, _s.plugin, on_change=_s.coordinator.request)
        _s.ticker = _s.QTimer()
        _s.ticker.setInterval(WATCH_INTERVAL_MS)
        _s.ticker.timeout.connect(_s.watcher.poll)
        _s.session.watcher = _s.watcher
        _s.session.timers.append(_s.ticker)
        if not _s.request.get("exercise"):
            _s.ticker.start()
            say(f"watching {_s.root / _s.plugin} for Python changes")


def _cc_bootstrap_p7(_s):

    _s.started = _s.coordinator.start()
    _s.exercise = _s.request.get("exercise")
    if _s.exercise:
        from .exercise import run_exercise

        _s.run_exercise = run_exercise

        _s.run_exercise(_s.session, Path(str(_s.exercise)))
    elif not _s.started:
        say(f"{_s.plugin} is disabled; fix the error and press Reload (Ctrl+Shift+R)")
    return _CcReturn(_s.session)


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
    _s = _CcState(request=request)
    for _p in (
        _cc_bootstrap_p1,
        _cc_bootstrap_p2,
        _cc_bootstrap_p3,
        _cc_bootstrap_p4,
        _cc_bootstrap_p5,
        _cc_bootstrap_p6,
        _cc_bootstrap_p7,
    ):
        _r = _p(_s)
        if isinstance(_r, _CcReturn):
            return _r.value
    return None


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

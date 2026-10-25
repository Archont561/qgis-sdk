"""Generation-safe plugin reload inside QGIS Desktop for ``qgis-sdk dev``.

The policy is decision-15 and decision-21, in this order for every reload:

1. **Preflight** the next revision without touching the running one: every
   module compiles and ``check_project`` finds nothing QGIS would refuse
   (syntax, metadata, project shape). Architecture findings only warn.
2. **Quiesce** the running revision through its own runtime
   (``PluginRuntime.quiesce``): owned work is cancelled and given a bounded
   time to reach a safe point. A refusal names the blockers, the revision
   is resumed and left exactly as it was, and the message says a restart is
   the way out - no thread is killed and nothing unsaved is discarded.
3. **Replace**: unload, then load and start the source again. A failure
   after teardown cannot be undone, so the plugin is disabled visibly
   (message bar + terminal) until the next reload succeeds.

Requests are serialised and coalesced: a reload while one is in flight is
folded into exactly one follow-up, and a host timer debounces bursts from
the editor or the watcher. Each attempt gets a generation number so
messages and reports can be tied to the attempt they belong to. Frontend
changes are not this module's business: Vite's HMR owns them.

The core is plain Python so it can be driven without QGIS; the Qt and
``qgis.utils`` glue lives at the bottom and is only imported by
:func:`bootstrap`, which the ``qgis --code`` probe calls.
"""

from __future__ import annotations

import os
import sys
import time
import traceback
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Literal, Protocol

from qgis_sdk.core import QuiesceOutcome

from qgis_sdk_tools.check import check_project

Outcome = Literal["reloaded", "refused", "disabled", "coalesced"]
NotifyLevel = Literal["info", "warning", "critical"]

#: How long a revision gets to reach a safe point before the reload is refused.
QUIESCE_SECONDS: Final = 2.0
#: Bursts of edits within this window become one reload.
DEBOUNCE_MS: Final = 300
#: How often the source watcher compares the tree.
WATCH_INTERVAL_MS: Final = 500
#: Findings of these rules only warn: the revision would still run.
ADVISORY_RULES: Final = frozenset({"QGIS001", "ARCH001"})
#: Directories under the plugin package the watcher never looks into.
UNWATCHED: Final = frozenset({"web", "__pycache__", "node_modules"})
WATCHED_FILES: Final = ("metadata.txt",)


class PluginHost(Protocol):
    """What the coordinator needs from ``qgis.utils``; faked in tests."""

    def available(self, name: str) -> bool: ...  # QGIS can see the package
    def load(self, name: str) -> bool: ...  # import it
    def start(self, name: str) -> bool: ...  # classFactory + initGui
    def unload(self, name: str) -> bool: ...  # unload + drop its modules
    def forget(self, name: str) -> None: ...  # drop modules after a failed load
    def running(self, name: str) -> bool: ...  # in active_plugins
    def quiesce(self, name: str) -> QuiesceOutcome: ...  # PluginRuntime.quiesce
    def resume(self, name: str) -> None: ...  # PluginRuntime.resume


@dataclass(frozen=True, slots=True)
class ReloadReport:
    """What one reload attempt did; the exercise writes these out."""

    generation: int
    outcome: Outcome
    revision: int
    running: bool
    problems: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    reason: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "generation": self.generation,
            "outcome": self.outcome,
            "revision": self.revision,
            "running": self.running,
            "problems": list(self.problems),
            "blockers": list(self.blockers),
            "reason": self.reason,
        }


def preflight(root: Path, plugin: str) -> tuple[list[str], list[str]]:
    """Check the next revision before the running one is touched.

    Returns ``(problems, warnings)``: problems refuse the reload (a module
    that does not compile, metadata QGIS would reject, a project ``check``
    cannot read), warnings are advisory findings about the plugin package
    (native imports outside the adapter, layer violations). Findings outside
    the plugin package - the project's tests, say - never block a reload.
    """
    root = Path(root)
    package = root / plugin
    problems: list[str] = []
    warnings: list[str] = []
    for path in sorted(package.rglob("*.py")):
        if any(part in UNWATCHED for part in path.relative_to(package).parts):
            continue
        try:
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
        except SyntaxError as error:
            where = path.relative_to(root).as_posix()
            problems.append(f"{where}:{error.lineno}: {error.msg}")
    if problems:
        return problems, warnings  # check_project would only repeat them
    report = check_project(root)
    for finding in report.diagnostics:
        if finding.severity != "error":
            continue
        parts = finding.path.parts
        in_package = parts[:1] == (plugin,)
        is_project_shape = finding.rule.startswith(("PROJECT", "CONFIG"))
        if not (in_package or is_project_shape):
            continue
        line = f"{finding.path.as_posix()}: {finding.rule} {finding.message}"
        if finding.rule in ADVISORY_RULES:
            warnings.append(line)
        else:
            problems.append(line)
    return problems, warnings


class ReloadCoordinator:
    """Serialise reloads of one source plugin and apply the policy above."""

    def __init__(
        self,
        *,
        root: Path,
        plugin: str,
        host: PluginHost,
        say: Callable[[str], None],
        notify: Callable[[NotifyLevel, str], None],
        schedule: Callable[[], None] | None = None,
        quiesce_timeout: float = QUIESCE_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        pump: Callable[[], None] | None = None,
        preflight: Callable[[Path, str], tuple[list[str], list[str]]] = preflight,
    ) -> None:
        """``schedule`` arms the host's debounce timer, which calls ``reload``.

        ``pump`` runs between safe-point checks (the Qt event loop in QGIS)
        and ``clock`` bounds the wait; both are injectable so the bound is
        testable without sleeping.
        """
        self._root = Path(root)
        self._plugin = plugin
        self._host = host
        self._say = say
        self._notify = notify
        self._schedule = schedule
        self._quiesce_timeout = quiesce_timeout
        self._clock = clock
        self._pump = pump if pump is not None else (lambda: time.sleep(0.05))
        self._preflight = preflight
        self.revision = 0
        self.generation = 0
        self.running = False
        self._busy = False
        self._pending = False

    @property
    def plugin(self) -> str:
        return self._plugin

    # -- entry points

    def request(self) -> None:
        """Ask for a reload soon; bursts collapse into one through the timer."""
        if self._schedule is not None:
            self._schedule()
        else:
            self.reload()

    def start(self) -> bool:
        """Load and start the package the way QGIS's Plugins dialog would."""
        return self._start()

    def reload(self) -> ReloadReport:
        """Run one reload now; a call during another is folded into a follow-up."""
        if self._busy:
            self._pending = True
            return self._report("coalesced", reason="a reload is already in flight")
        self._busy = True
        try:
            report = self._reload_once()
            while self._pending:
                self._pending = False
                report = self._reload_once()
        finally:
            self._busy = False
        return report

    # -- the policy

    def _reload_once(self) -> ReloadReport:
        self.generation += 1
        plugin = self._plugin
        problems, warnings = self._preflight(self._root, plugin)
        for warning in warnings:
            self._say(f"warning: {warning}")
        if problems:
            more = f" (+{len(problems) - 1} more)" if len(problems) > 1 else ""
            kept = (
                f"revision {self.revision} keeps running"
                if self.running
                else f"{plugin} stays disabled"
            )
            self._say(f"reload refused, {kept}: {problems[0]}{more}")
            self._notify("critical", f"reload refused: {problems[0]}{more}")
            return self._report("refused", problems=tuple(problems), reason="preflight")
        if self.running:
            outcome = self._quiesce()
            if outcome.refused:
                self._host.resume(plugin)
                first = outcome.blockers[0] if outcome.blockers else "unknown"
                more = (
                    f" (+{len(outcome.blockers) - 1} more)"
                    if len(outcome.blockers) > 1
                    else ""
                )
                self._say(
                    f"reload refused, revision {self.revision} keeps running: "
                    f"{first}{more}; finish or cancel that work and Reload, or "
                    "restart `qgis-sdk dev`"
                )
                self._notify("critical", f"{plugin} reload refused: {first}{more}")
                return self._report(
                    "refused", blockers=outcome.blockers, reason="quiesce"
                )
            if not self._host.unload(plugin):
                self.running = False
                self._say(
                    f"unload of revision {self.revision} failed; {plugin} is "
                    "disabled and its old modules may linger: restart `qgis-sdk dev`"
                )
                self._notify(
                    "critical", f"{plugin} unload failed: restart qgis-sdk dev"
                )
                return self._report("disabled", reason="unload failed; restart")
            self.running = False
        if self._start():
            self._notify("info", f"{plugin} reloaded (revision {self.revision})")
            return self._report("reloaded")
        self._say(
            f"{plugin} is disabled until a Reload succeeds; fix the error, or "
            "restart `qgis-sdk dev`"
        )
        self._notify("critical", f"{plugin} is disabled: fix the error and Reload")
        return self._report("disabled", reason="start failed after teardown")

    def _quiesce(self) -> QuiesceOutcome:
        """Give the running revision a bounded time to reach a safe point."""
        deadline = self._clock() + self._quiesce_timeout
        while True:
            outcome = self._host.quiesce(self._plugin)
            if not outcome.refused or self._clock() >= deadline:
                return outcome
            self._pump()

    def _start(self) -> bool:
        host, plugin, root = self._host, self._plugin, self._root
        if not host.available(plugin):
            self._say(
                f"{plugin} is not a plugin QGIS can see under {root} (metadata.txt?)"
            )
            return False
        if not host.load(plugin):
            host.forget(plugin)
            self._say(
                f"{plugin} failed to import (see the QGIS Python error); fix it and Reload"
            )
            return False
        if not host.start(plugin):
            self._say(
                f"{plugin} failed in classFactory/initGui (see the QGIS Python "
                "error); fix it and Reload"
            )
            return False
        self.revision += 1
        self.running = True
        self._say(f"{plugin} running (revision {self.revision}) from {root / plugin}")
        return True

    def _report(self, outcome: Outcome, **fields: object) -> ReloadReport:
        return ReloadReport(
            generation=self.generation,
            outcome=outcome,
            revision=self.revision,
            running=self.running,
            **fields,  # type: ignore[arg-type]
        )


class SourceWatcher:
    """Poll the plugin's Python sources and metadata for changes.

    Polling, not inotify: it is portable, cheap at plugin size, and runs on
    the GUI thread so a change can call straight into the coordinator. The
    ``web/`` tree is Vite's, caches are nobody's, and the project's tests
    are not part of the running plugin.
    """

    def __init__(
        self, root: Path, plugin: str, *, on_change: Callable[[], None]
    ) -> None:
        self._package = Path(root) / plugin
        self._on_change = on_change
        self._seen = self.snapshot()

    def snapshot(self) -> dict[Path, tuple[int, int]]:
        """``{path: (mtime_ns, size)}`` of every watched file right now."""
        seen: dict[Path, tuple[int, int]] = {}
        for directory, dirnames, filenames in os.walk(self._package):
            dirnames[:] = [d for d in dirnames if d not in UNWATCHED]
            for filename in filenames:
                if filename.endswith(".py") or filename in WATCHED_FILES:
                    path = Path(directory) / filename
                    try:
                        stat = path.stat()
                    except OSError:  # removed between listing and stat
                        continue
                    seen[path] = (stat.st_mtime_ns, stat.st_size)
        return seen

    def poll(self) -> bool:
        """Compare with the last snapshot; call ``on_change`` once if it differs."""
        current = self.snapshot()
        if current == self._seen:
            return False
        self._seen = current
        self._on_change()
        return True

    def resync(self) -> None:
        """Take the current tree as the baseline, forgetting edits made meanwhile."""
        self._seen = self.snapshot()


# --- QGIS glue --------------------------------------------------------------


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
        return bool(self._utils.unloadPlugin(name))

    def forget(self, name: str) -> None:
        forget = getattr(self._utils, "_unloadPluginModules", None)
        if forget is not None:
            forget(name)

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
            say(f"watching {root / plugin} for Python and metadata changes")

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

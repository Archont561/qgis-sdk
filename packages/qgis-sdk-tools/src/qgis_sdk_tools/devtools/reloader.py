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

Everything here is plain Python so it can be driven without QGIS; the Qt
and ``qgis.utils`` glue is :mod:`.bootstrap`, which the ``qgis --code``
probe calls.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal, Protocol, TypedDict, Unpack

from qgis_sdk.core import QuiesceOutcome

from qgis_sdk_tools.check import check_project
from qgis_sdk_tools.paths import walk_files


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


def _cc_reload_once_p1(_s):
    _s.self.generation += 1
    _s.plugin = _s.self._plugin
    _s.problems, _s.warnings = _s.self._preflight(_s.self._root, _s.plugin)
    for warning in _s.warnings:
        _s.warning = warning
        _s.self._say(f"warning: {_s.warning}")


def _cc_reload_once_p2(_s):
    _s.self._host.resume(_s.plugin)
    _s.first = _s.outcome.blockers[0] if _s.outcome.blockers else "unknown"
    _s.more = (
        f" (+{len(_s.outcome.blockers) - 1} more)"
        if len(_s.outcome.blockers) > 1
        else ""
    )
    _s.self._say(
        f"reload refused, revision {_s.self.revision} keeps running: "
        f"{_s.first}{_s.more}; finish or cancel that work and Reload, or "
        "restart `qgis-sdk dev`"
    )


def _cc_reload_once_p3(_s):
    _s.self._notify("critical", f"{_s.plugin} reload refused: {_s.first}{_s.more}")
    return _CcReturn(
        _s.self._report("refused", blockers=_s.outcome.blockers, reason="quiesce")
    )


def _cc_reload_once_p4(_s):
    _s.outcome = _s.self._quiesce()
    if _s.outcome.refused:
        for _p in (_cc_reload_once_p2, _cc_reload_once_p3):
            _r = _p(_s)
            if isinstance(_r, _CcReturn):
                return _r


def _cc_reload_once_p5(_s):
    if not _s.self._host.unload(_s.plugin):
        _s.self.running = False
        _s.self._say(
            f"unload of revision {_s.self.revision} failed; {_s.plugin} is "
            "disabled and its old modules may linger: restart `qgis-sdk dev`"
        )
        _s.self._notify("critical", f"{_s.plugin} unload failed: restart qgis-sdk dev")
        return _CcReturn(_s.self._report("disabled", reason="unload failed; restart"))
    _s.self.running = False


def _cc_reload_once_p6(_s):
    if _s.problems:
        _s.more = f" (+{len(_s.problems) - 1} more)" if len(_s.problems) > 1 else ""
        _s.kept = (
            f"revision {_s.self.revision} keeps running"
            if _s.self.running
            else f"{_s.plugin} stays disabled"
        )
        _s.self._say(f"reload refused, {_s.kept}: {_s.problems[0]}{_s.more}")
        _s.self._notify("critical", f"reload refused: {_s.problems[0]}{_s.more}")
        return _CcReturn(
            _s.self._report("refused", problems=tuple(_s.problems), reason="preflight")
        )


def _cc_reload_once_p7(_s):
    if _s.self.running:
        for _p in (_cc_reload_once_p4, _cc_reload_once_p5):
            _r = _p(_s)
            if isinstance(_r, _CcReturn):
                return _r
    if _s.self._start():
        _s.self._notify("info", f"{_s.plugin} reloaded (revision {_s.self.revision})")
        return _CcReturn(_s.self._report("reloaded"))
    return _CcReturn(_reload_once_phase1(_s.plugin, _s.self))


def _preflight_tail1(**values):
    plugin = values["plugin"]
    problems = values["problems"]
    root = values["root"]
    warnings = values["warnings"]
    if problems:
        return problems, warnings  # check_project would only repeat them
    report = check_project(root)
    for finding in report.diagnostics:
        if finding.severity != "error":
            continue
        parts = finding.path.parts
        in_package = parts[:1] == (plugin,)
        is_project_shape = finding.rule.startswith(PROJECT_RULES)
        if not (in_package or is_project_shape):
            continue
        line = f"{finding.path.as_posix()}: {finding.rule} {finding.message}"
        if finding.rule in ADVISORY_RULES:
            warnings.append(line)
        else:
            problems.append(line)
    return problems, warnings


def _init_facts1(preflight, self):
    self._preflight = preflight
    self.revision = 0
    self.generation = 0
    self.running = False
    self._busy = False
    self._pending = False


def _reload_once_phase1(plugin, self):
    self._say(
        f"{plugin} is disabled until a Reload succeeds; fix the error, or "
        "restart `qgis-sdk dev`"
    )
    self._notify("critical", f"{plugin} is disabled: fix the error and Reload")
    return self._report("disabled", reason="start failed after teardown")


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


#: Rule families raised on ``pyproject.toml`` that still concern the plugin:
#: the host package is rendered from them (decision-43).
PROJECT_RULES: Final = ("PROJECT", "CONFIG", "META", "GRANT", "VERSION")


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
    return _preflight_tail1(**{**globals(), **locals()})


class ReloadCoordinator:
    """Serialise reloads of one source plugin and apply the policy above."""

    def __init__(self, **options: Unpack[_InitOptions1]) -> None:
        """``schedule`` arms the host's debounce timer, which calls ``reload``.

        ``pump`` runs between safe-point checks (the Qt event loop in QGIS)
        and ``clock`` bounds the wait; both are injectable so the bound is
        testable without sleeping.
        """
        values = _InitValues1(**options)
        self._root = Path(values.root)
        self._plugin = values.plugin
        self._host = values.host
        self._say = values.say
        self._notify = values.notify
        self._schedule = values.schedule
        self._quiesce_timeout = values.quiesce_timeout
        self._clock = values.clock
        self._pump = (
            values.pump if values.pump is not None else (lambda: time.sleep(0.05))
        )
        _init_facts1(values.preflight, self)

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
        _s = _CcState(self=self)
        for _p in (_cc_reload_once_p1, _cc_reload_once_p6, _cc_reload_once_p7):
            _r = _p(_s)
            if isinstance(_r, _CcReturn):
                return _r.value
        return None

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
                f"{plugin} is not a plugin QGIS can see (the generated package under "
                f"{root / '.qgis-sdk' / 'dev' / 'host'} is missing?)"
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
    """Poll the plugin's Python sources for changes.

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
        for path in walk_files(self._package, skip=UNWATCHED, suffix=".py"):
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


class _InitOptions1(TypedDict, total=False):
    root: Path
    plugin: str
    host: PluginHost
    say: Callable[[str], None]
    notify: Callable[[NotifyLevel, str], None]
    schedule: Callable[[], None] | None
    quiesce_timeout: float
    clock: Callable[[], float]
    pump: Callable[[], None] | None
    preflight: Callable[[Path, str], tuple[list[str], list[str]]]


@dataclass(frozen=True, slots=True)
class _InitValues1:
    root: Path
    plugin: str
    host: PluginHost
    say: Callable[[str], None]
    notify: Callable[[NotifyLevel, str], None]
    schedule: Callable[[], None] | None = None
    quiesce_timeout: float = QUIESCE_SECONDS
    clock: Callable[[], float] = time.monotonic
    pump: Callable[[], None] | None = None
    preflight: Callable[[Path, str], tuple[list[str], list[str]]] = preflight

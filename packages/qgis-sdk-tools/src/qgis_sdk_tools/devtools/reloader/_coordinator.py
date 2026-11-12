"""Serialise reloads of one source plugin and apply the policy."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict, Unpack

from qgis_sdk.core import QuiesceOutcome

from ._preflight import preflight
from ._types import QUIESCE_SECONDS, NotifyLevel, Outcome, PluginHost, ReloadReport

__all__ = ["ReloadCoordinator"]


class _CcState:
    """A mutable record shared by the phases of one long function."""

    def __init__(_cc_self, **values):
        _cc_self.__dict__.update(values)


class _CcReturn:
    """An early return travelling out of a phase."""

    def __init__(_cc_self, value):
        _cc_self.value = value


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

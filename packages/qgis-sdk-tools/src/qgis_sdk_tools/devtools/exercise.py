"""Drive the reload policy end to end inside QGIS and write what happened.

``qgis-sdk dev --exercise REPORT`` is how the opt-in harness
(``tests/test_devtools_native.py``) proves the reload policy without a human
at the keyboard: the steps below are the checks in order, each recorded under
a stable key, and QGIS quits with the report's verdict.

The full exercise edits the scaffold's ``ping`` action between reloads, so it
only fits a project that declares one; with ``--ui native``'s ``ui.py`` it
also edits the dialog and opens it from its bound action after the reload. Any other project - the reference
plugin, a user's own - gets :func:`run_smoke`: start, one reload, the view
when there is a web UI, unload; the report says ``"smoke": true``.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from qgis_sdk.core import WorkerContext

from .bootstrap import DevSession, say

STUCK_SECONDS = 2.0  # the coordinator's bound; the gate stays shut longer
SETTLE_SECONDS = 4.0  # generous for a debounce + reload on a slow runner


@dataclass
class _Exercise:
    """The one running session and the helpers every acceptance check shares."""

    session: DevSession
    coordinator: Any
    plugin: str
    package: Path
    report: dict[str, Any]
    qgis_utils: Any

    def active(self) -> bool:
        return (
            self.coordinator.running and self.plugin in self.qgis_utils.active_plugins
        )

    def actions(self) -> Any:
        return self.qgis_utils.plugins[self.plugin].runtime.actions

    def held(self) -> Any:
        return self.qgis_utils.plugins[self.plugin]

    def ping(self, value: int) -> object:
        return self.actions()["ping"](value)

    def edit(self, source: Path, old: str, new: str) -> str:
        original = source.read_text(encoding="utf-8")
        source.write_text(original.replace(old, new, 1), encoding="utf-8")
        return original


def _exercise_syntax_error(ex: _Exercise) -> None:
    """AC1: a syntax error is refused before anything is unloaded."""
    broken = ex.package / "zz_broken_by_qgis_sdk_dev.py"
    broken.write_text("def (\n", encoding="utf-8")
    try:
        refused = ex.coordinator.reload()
        ex.report["reload_refused"] = refused.outcome == "refused"
        ex.report["kept_running"] = ex.active()
    finally:
        broken.unlink()


def _exercise_edit_between_reloads(ex: _Exercise, source: Path) -> None:
    """AC2: an edit between reloads is what runs afterwards."""
    original = ex.edit(source, "return value\n", "return value + 1000\n")
    try:
        ex.report["reload_after_fix"] = ex.coordinator.reload().outcome == "reloaded"
        ex.report["ping_after_edit"] = ex.ping(1)
    finally:
        source.write_text(original, encoding="utf-8")


def _exercise_stuck(ex: _Exercise) -> None:
    """AC3: work with no safe point refuses the reload, then recovers."""
    gate = threading.Event()
    stuck = _stuck_job(ex.held().runtime, gate)
    try:
        refused = ex.coordinator.reload()
        ex.report["stuck_refused"] = refused.outcome == "refused"
        ex.report["stuck_blockers"] = list(refused.blockers)
        ex.report["kept_running_stuck"] = (
            ex.active() and stuck.status.value == "running"
        )
    finally:
        gate.set()
    released = ex.coordinator.reload()
    ex.report["reload_after_release"] = released.outcome == "reloaded"


def _exercise_start_failure(ex: _Exercise, source: Path) -> None:
    """AC1: a failure after teardown disables visibly; the next fix recovers."""
    original = ex.edit(
        source,
        "from __future__ import annotations\n",
        "from __future__ import annotations\n"
        'raise RuntimeError("broken on import by the qgis-sdk exercise")\n',
    )
    try:
        disabled = ex.coordinator.reload()
        ex.report["start_failure_disabled"] = (
            disabled.outcome == "disabled"
            and not ex.coordinator.running
            and ex.plugin not in ex.qgis_utils.active_plugins
        )
    finally:
        source.write_text(original, encoding="utf-8")
    ex.report["reload_after_start_failure"] = (
        ex.coordinator.reload().outcome == "reloaded"
    )


def _exercise_coalescing(ex: _Exercise) -> None:
    """AC2: back-to-back requests become one reload."""
    before = ex.coordinator.revision
    ex.coordinator.request()
    ex.coordinator.request()
    ex.coordinator.request()
    ex.session.pump_until(
        lambda: ex.coordinator.revision > before, timeout=SETTLE_SECONDS
    )
    ex.session.pump(0.5)  # a second fire would land here
    ex.report["coalesced"] = ex.coordinator.revision - before == 1


def _exercise_watcher(ex: _Exercise, source: Path) -> None:
    """AC2 (decision-15): the watcher reloads on a saved edit, once."""
    ex.report["watch_reloaded"] = None
    if ex.session.watcher is None:
        return
    ticker = ex.session.timers[1]
    ex.session.watcher.resync()
    ticker.start()  # type: ignore[attr-defined]
    before = ex.coordinator.revision
    original = ex.edit(source, "return value\n", "return value + 2000\n")
    try:
        reloaded = ex.session.pump_until(
            lambda: ex.coordinator.revision > before, timeout=SETTLE_SECONDS
        )
        ex.session.pump(0.5)
        ex.report["watch_reloaded"] = reloaded and ex.coordinator.revision - before == 1
        ex.report["ping_after_watched_edit"] = ex.ping(1)
    finally:
        source.write_text(original, encoding="utf-8")
        before = ex.coordinator.revision
        ex.session.pump_until(
            lambda: ex.coordinator.revision > before, timeout=SETTLE_SECONDS
        )
        ticker.stop()  # type: ignore[attr-defined]


def _exercise_surface(ex: _Exercise) -> None:
    """A surface edited between reloads is what the next opening builds."""
    ui_source = ex.package / "ui.py"
    ex.report["surface"] = None
    if not (ui_source.is_file() and "open_ping" in ex.actions()):
        return
    before_edit = _surface_round(ex.held(), ex.session, ex.plugin)
    original = ex.edit(ui_source, 'LogView(label="Answers")', 'LogView(label="Edited")')
    try:
        reloaded = ex.coordinator.reload().outcome == "reloaded"
        after_edit = _surface_round(ex.held(), ex.session, ex.plugin)
    finally:
        ui_source.write_text(original, encoding="utf-8")
    ex.report["surface"] = {
        "before": before_edit,
        "reloaded": reloaded,
        "after": after_edit,
    }


def _run_exercise_steps(ex: _Exercise) -> None:
    """Every acceptance check in order, each recorded under a stable key."""
    source = ex.package / "plugin.py"
    coordinator = ex.coordinator
    # AC2: a plain reload replaces the revision.
    ex.report["reload_ok"] = coordinator.reload().outcome == "reloaded"
    _exercise_syntax_error(ex)
    _exercise_edit_between_reloads(ex, source)
    _exercise_stuck(ex)
    _exercise_start_failure(ex, source)
    _exercise_coalescing(ex)
    _exercise_watcher(ex, source)
    _exercise_surface(ex)
    ex.report["revision"] = coordinator.revision
    if ex.session.request.get("web"):
        held = ex.held()
        held.show_view()
        ex.report["view_shown"] = held._view is not None
        ex.session.pump(0.1)
    ex.report["unloaded"] = bool(ex.qgis_utils.unloadPlugin(ex.plugin))


def run_exercise(session: DevSession, path: Path) -> None:
    """Drive the reload policy end to end and write the report QGIS quits with."""
    import qgis.utils

    coordinator = session.coordinator
    plugin = coordinator.plugin
    root = Path(str(session.request["root"]))
    report: dict[str, Any] = {"started": coordinator.running, "error": None}
    ex = _Exercise(session, coordinator, plugin, root / plugin, report, qgis.utils)
    if coordinator.running and "ping" not in ex.actions():
        run_smoke(session, path)
        return
    try:
        _run_exercise_steps(ex)
    except BaseException as error:  # noqa: BLE001 - the report is the only way out
        report["error"] = "".join(traceback.format_exception(error))
        say(report["error"])
    Path(path).write_text(json.dumps(report), encoding="utf-8")
    sys.__stderr__.flush() if sys.__stderr__ else None
    os._exit(0 if report["error"] is None else 1)


def _surface_round(held: Any, session: DevSession, plugin: str) -> dict[str, Any]:
    """Open the scaffold's dialog through its bound action, use it, close it.

    Everything is read off the author's instance (the declared ``answers``
    log view, the ``pinged`` method), so this needs no Qt import: the host
    built the widget, bound ``ctx`` and disposes the view when the window
    closes. ``initial`` is the log view's label, which the edit between the
    rounds changes.
    """
    surfaces = held.surfaces
    held.runtime.actions["open_ping"]()
    session.pump(0.1)
    (record,) = surfaces.dialogs
    surface = record.surface
    shown = bool(record.widget.isVisible())
    initial = surface.answers.label
    surface.pinged()
    answer = str(surface.answers.records()[-1].fields["value"])
    record.widget.close()
    session.pump(0.1)
    return {
        "placed": any(
            action.objectName() == f"{plugin}.open_ping"
            for action in held.desktop_bindings.placed
        ),
        "shown": shown,
        "initial": initial,
        "answer": answer,
        "closed": record.closed and surfaces.dialogs == (),
    }


def _stuck_job(runtime: Any, gate: threading.Event) -> Any:
    """Submit a job whose worker blocks on ``gate``; a real thread, never killed."""
    from qgis_sdk.jobs import JobService, job

    @job(id="exercise.stuck", title="Stuck on purpose")
    def stuck(ctx: WorkerContext, value: int) -> int:
        gate.wait()  # the whole body is the worker's; nothing interrupts it
        return value

    context = runtime.instance.ctx
    # The runtime's own service when the plugin declares jobs, else one over
    # the same scope and worker backend: either way this is real work under a
    # real host, not a test double.
    jobs = runtime.jobs
    if jobs is None:
        jobs = JobService(context.scope, workers=context.workers)
    handle = jobs.bind(stuck).delay(value=1)
    jobs.tick()  # now suspended on the handoff
    return handle


def run_smoke(session: DevSession, path: Path) -> None:
    """The lifecycle a project without a ``ping`` action can prove: start, reload, view, unload."""
    import qgis.utils

    coordinator = session.coordinator
    plugin = coordinator.plugin
    report: dict[str, Any] = {
        "smoke": True,
        "started": coordinator.running,
        "error": None,
    }
    try:
        report["reload_ok"] = coordinator.reload().outcome == "reloaded"
        report["revision"] = coordinator.revision
        held = qgis.utils.plugins[plugin]
        report["actions"] = sorted(held.runtime.actions)
        if session.request.get("web"):
            held.show_view()
            report["view_shown"] = held._view is not None
            session.pump(0.1)
        report["unloaded"] = bool(qgis.utils.unloadPlugin(plugin))
    except BaseException as error:  # noqa: BLE001 - the report is the only way out
        report["error"] = "".join(traceback.format_exception(error))
        say(report["error"])
    Path(path).write_text(json.dumps(report), encoding="utf-8")
    sys.__stderr__.flush() if sys.__stderr__ else None
    os._exit(0 if report["error"] is None else 1)

"""Drive the reload policy end to end inside QGIS and write what happened.

``qgis-sdk dev --exercise REPORT`` is how the opt-in harness
(``tests/test_devtools_native.py``) proves TASK-21 without a human at the
keyboard: the steps below are the acceptance criteria in order, each
recorded under a stable key, and QGIS quits with the report's verdict.

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
from pathlib import Path
from typing import Any

from qgis_sdk.core import JobContext

from .bootstrap import DevSession, say

STUCK_SECONDS = 2.0  # the coordinator's bound; the gate stays shut longer
SETTLE_SECONDS = 4.0  # generous for a debounce + reload on a slow runner


def run_exercise(session: DevSession, path: Path) -> None:
    import qgis.utils

    coordinator = session.coordinator
    plugin = coordinator.plugin
    root = Path(str(session.request["root"]))
    package = root / plugin
    report: dict[str, Any] = {"started": coordinator.running, "error": None}

    def active() -> bool:
        return coordinator.running and plugin in qgis.utils.active_plugins

    def ping(value: int) -> object:
        return qgis.utils.plugins[plugin].runtime.actions["ping"](value)

    def edit(source: Path, old: str, new: str) -> str:
        original = source.read_text(encoding="utf-8")
        source.write_text(original.replace(old, new, 1), encoding="utf-8")
        return original

    if coordinator.running and "ping" not in qgis.utils.plugins[plugin].runtime.actions:
        run_smoke(session, path)
        return

    try:
        # AC2: a plain reload replaces the revision.
        report["reload_ok"] = coordinator.reload().outcome == "reloaded"

        # AC1: a syntax error is refused before anything is unloaded.
        broken = package / "zz_broken_by_qgis_sdk_dev.py"
        broken.write_text("def (\n", encoding="utf-8")
        try:
            refused = coordinator.reload()
            report["reload_refused"] = refused.outcome == "refused"
            report["kept_running"] = active()
        finally:
            broken.unlink()

        # AC2: an edit between reloads is what runs afterwards.
        source = package / "plugin.py"
        original = edit(source, "return value\n", "return value + 1000\n")
        try:
            report["reload_after_fix"] = coordinator.reload().outcome == "reloaded"
            report["ping_after_edit"] = ping(1)
        finally:
            source.write_text(original, encoding="utf-8")

        # AC3: work that cannot reach a safe point refuses the reload, names
        # itself, and keeps running; once it finishes the reload goes through.
        gate = threading.Event()
        stuck = _stuck_job(qgis.utils.plugins[plugin].runtime, gate)
        try:
            refused = coordinator.reload()
            report["stuck_refused"] = refused.outcome == "refused"
            report["stuck_blockers"] = list(refused.blockers)
            report["kept_running_stuck"] = active() and stuck.status.value == "running"
        finally:
            gate.set()
        released = coordinator.reload()
        report["reload_after_release"] = released.outcome == "reloaded"

        # AC1: a failure after teardown disables visibly; the next fix recovers.
        original = edit(
            source,
            "from __future__ import annotations\n",
            "from __future__ import annotations\n"
            'raise RuntimeError("broken on import by the qgis-sdk exercise")\n',
        )
        try:
            disabled = coordinator.reload()
            report["start_failure_disabled"] = (
                disabled.outcome == "disabled"
                and not coordinator.running
                and plugin not in qgis.utils.active_plugins
            )
        finally:
            source.write_text(original, encoding="utf-8")
        report["reload_after_start_failure"] = (
            coordinator.reload().outcome == "reloaded"
        )

        # AC2: back-to-back requests become one reload.
        before = coordinator.revision
        coordinator.request()
        coordinator.request()
        coordinator.request()
        session.pump_until(
            lambda: coordinator.revision > before, timeout=SETTLE_SECONDS
        )
        session.pump(0.5)  # a second fire would land here
        report["coalesced"] = coordinator.revision - before == 1

        # AC2 (decision-15): the watcher reloads on a saved edit, once.
        report["watch_reloaded"] = None
        if session.watcher is not None:
            ticker = session.timers[1]
            session.watcher.resync()
            ticker.start()  # type: ignore[attr-defined]
            before = coordinator.revision
            original = edit(source, "return value\n", "return value + 2000\n")
            try:
                report["watch_reloaded"] = session.pump_until(
                    lambda: coordinator.revision > before, timeout=SETTLE_SECONDS
                )
                session.pump(0.5)
                report["watch_reloaded"] = (
                    report["watch_reloaded"] and coordinator.revision - before == 1
                )
                report["ping_after_watched_edit"] = ping(1)
            finally:
                source.write_text(original, encoding="utf-8")
                before = coordinator.revision
                session.pump_until(
                    lambda: coordinator.revision > before, timeout=SETTLE_SECONDS
                )
                ticker.stop()  # type: ignore[attr-defined]

        # TASK-67: a surface edited between reloads is what the next opening
        # builds; the bound action stays on the toolbar across revisions.
        ui_source = package / "ui.py"
        report["surface"] = None
        if (
            ui_source.is_file()
            and "open_ping" in qgis.utils.plugins[plugin].runtime.actions
        ):
            before_edit = _surface_round(qgis.utils.plugins[plugin], session, plugin)
            original = edit(
                ui_source, 'LogView(label="Answers")', 'LogView(label="Edited")'
            )
            try:
                reloaded = coordinator.reload().outcome == "reloaded"
                after_edit = _surface_round(qgis.utils.plugins[plugin], session, plugin)
            finally:
                ui_source.write_text(original, encoding="utf-8")
            report["surface"] = {
                "before": before_edit,
                "reloaded": reloaded,
                "after": after_edit,
            }

        report["revision"] = coordinator.revision
        if session.request.get("web"):
            held = qgis.utils.plugins[plugin]
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
    async def stuck(ctx: JobContext, value: int) -> int:
        await ctx.workers.offload(gate.wait)
        return value

    context = runtime.instance.ctx
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

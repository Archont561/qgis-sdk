"""Drive the reload policy end to end inside QGIS and write what happened.

``qgis-sdk dev --exercise REPORT`` is how the opt-in harness
(``tests/test_devtools_native.py``) proves TASK-21 without a human at the
keyboard: the steps below are the acceptance criteria in order, each
recorded under a stable key, and QGIS quits with the report's verdict.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import traceback
from pathlib import Path
from typing import Any

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


def _stuck_job(runtime: Any, gate: threading.Event) -> Any:
    """Submit a job whose worker blocks on ``gate``; a real thread, never killed."""
    from qgis_sdk.jobs import JobContext, JobService, job

    @job(id="exercise.stuck", title="Stuck on purpose")
    class Stuck:
        def __init__(self, ctx: JobContext) -> None:
            self.ctx = ctx

        async def run(self, inputs: int) -> int:
            await self.ctx.require_workers().offload(gate.wait)
            return inputs

    context = runtime.instance.ctx
    jobs = JobService(context.scope, workers=context.require_workers())
    handle = jobs.bind(Stuck).delay(1)
    jobs.tick()  # now suspended on the handoff
    return handle

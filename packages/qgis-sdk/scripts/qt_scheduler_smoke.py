"""Headless Qt scheduler qualification harness for the TASK-13 spike.

This script starts a real QGIS application, drives the SDK's pure
:class:`~qgis_sdk.core.scheduling.StepScheduler` from a real Qt event loop with a
real ``QThreadPool`` worker, and prints a machine-readable report covering GUI
responsiveness, worker-to-GUI thread handoff, cooperative cancellation, late
callbacks after disposal, and refused replacement while work is stuck.

It is **not** a QGIS Desktop GUI qualification: there is no display, no real
``iface``, and event delivery is driven by ``processEvents()``. Windows, macOS and
a real Desktop session stay tracked by TASK-33.

Run it from the repository root with the default Pixi environment::

    pixi run -e default python packages/qgis-sdk/scripts/qt_scheduler_smoke.py

The summary and verdict helpers are pure, so the QGIS-free suite can test them;
the end-to-end run is opt-in through the test suite.
"""

from __future__ import annotations

import contextlib
import json
import platform
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from pathlib import Path

HEARTBEAT_INTERVAL_MS = 2
BLOCKING_HANDLER_MS = 60
WORKER_DURATION_MS = 60
GUI_GAP_BUDGET_MS = 40
STUCK_ACK_MS = 250
QUIESCE_TICKS = 8
PHASE_DEADLINE_MS = 8000

SCRIPT_DIR = Path(__file__).resolve().parent
SOURCE_ROOT = SCRIPT_DIR.parent / "src"

VERDICT_ADOPT = "adopt-scheduler-seam"
VERDICT_REVIEW = "review-scope-before-async-syntax"

# Criteria that decide the spike. A failure here must trigger explicit scope
# review (ADR-22) rather than a silent downgrade to a blocking-only API.
DECIDING_CRITERIA = (
    "gui_responsive_for_scheduled_work",
    "handoff_delivered_on_gui_thread",
    "work_ran_off_the_gui_thread",
    "worker_acknowledged_cancellation",
    "late_report_dropped_after_disposal",
    "replacement_refused_while_stuck",
)


@dataclass(frozen=True)
class GapSummary:
    """Observed spacing between event-loop heartbeats during one phase."""

    count: int
    max_ms: float
    mean_ms: float

    def stalled(self, budget_ms: float) -> bool:
        """Return whether any gap exceeded the responsiveness budget."""
        return self.count > 0 and self.max_ms > budget_ms

    def responsive(self, budget_ms: float) -> bool:
        """Return whether the loop kept pace within the budget."""
        return self.count > 0 and self.max_ms <= budget_ms


def summarise_gaps(gaps: Sequence[float]) -> GapSummary:
    """Summarise raw millisecond gaps; the caller owns the measurement order."""
    if not gaps:
        return GapSummary(count=0, max_ms=0.0, mean_ms=0.0)
    return GapSummary(
        count=len(gaps),
        max_ms=max(gaps),
        mean_ms=sum(gaps) / len(gaps),
    )


def delivered_only_on(expected_thread: int, deliveries: Sequence[int]) -> bool:
    """Return whether every delivery happened on the expected thread."""
    return bool(deliveries) and all(thread == expected_thread for thread in deliveries)


def ran_on_a_different_thread(gui_thread: int, workers: Sequence[int]) -> bool:
    """Return whether every recorded worker ran off the GUI thread."""
    return bool(workers) and all(thread != gui_thread for thread in workers)


def decide_verdict(criteria: Mapping[str, bool]) -> tuple[str, tuple[str, ...]]:
    """Return the spike verdict and the criteria that forced a scope review.

    A failing deciding criterion never yields an "adopt" verdict: the scope is
    revisited instead of quietly shrinking the promised API surface.
    """
    failing = tuple(name for name in DECIDING_CRITERIA if not criteria.get(name, False))
    if failing:
        return VERDICT_REVIEW, failing
    return VERDICT_ADOPT, ()


@dataclass(frozen=True)
class SchedulerReport:
    """What one headless Qt scheduling run observed."""

    platform: str
    python_version: str
    qgis_version: str | None
    qt_version: str | None
    qgis_initialised: bool
    event_loop_polled: bool
    gui_thread_id: int
    worker_thread_ids: tuple[int, ...]
    delivery_thread_ids: tuple[int, ...]
    blocking_phase: GapSummary
    scheduled_phase: GapSummary
    gui_responsive_for_scheduled_work: bool
    handoff_delivered_on_gui_thread: bool
    work_ran_off_the_gui_thread: bool
    worker_acknowledged_cancellation: bool
    author_cleanup_ran: bool
    late_report_dropped_after_disposal: bool
    replacement_refused_while_stuck: bool
    refused_blocker: str | None
    verdict: str
    scope_review_criteria: tuple[str, ...]
    error: str | None = None

    @property
    def criteria(self) -> dict[str, bool]:
        """Return the observed criteria the verdict is derived from."""
        return {
            "gui_responsive_for_scheduled_work": self.gui_responsive_for_scheduled_work,
            "handoff_delivered_on_gui_thread": self.handoff_delivered_on_gui_thread,
            "work_ran_off_the_gui_thread": self.work_ran_off_the_gui_thread,
            "worker_acknowledged_cancellation": self.worker_acknowledged_cancellation,
            "late_report_dropped_after_disposal": (
                self.late_report_dropped_after_disposal
            ),
            "replacement_refused_while_stuck": self.replacement_refused_while_stuck,
        }

    @property
    def passed(self) -> bool:
        """Return whether the harness ran and every deciding criterion held."""
        return (
            self.qgis_initialised
            and self.event_loop_polled
            and self.author_cleanup_ran
            and self.verdict == VERDICT_ADOPT
            and self.scope_review_criteria == ()
        )

    def to_dict(self) -> dict[str, object]:
        """Return the report as a JSON-serialisable mapping."""
        payload = asdict(self)
        payload["passed"] = self.passed
        payload["blocking_phase_max_ms"] = round(self.blocking_phase.max_ms, 3)
        payload["scheduled_phase_max_ms"] = round(self.scheduled_phase.max_ms, 3)
        payload["worker_thread_ids"] = list(self.worker_thread_ids)
        payload["delivery_thread_ids"] = list(self.delivery_thread_ids)
        payload["scope_review_criteria"] = list(self.scope_review_criteria)
        return payload


def _deadline() -> float:
    return time.monotonic() + (PHASE_DEADLINE_MS / 1000)


def _pump_for(application: object, scheduler: object, seconds: float) -> None:
    """Keep the Qt loop and the scheduler running for a bounded wall-clock window."""
    limit = time.monotonic() + seconds
    while time.monotonic() < limit:
        _pump_once(application, scheduler)


def _pump(application: object, scheduler: object, done: Callable[[], bool]) -> bool:
    """Run the Qt event loop and the scheduler until ``done`` or the deadline."""
    limit = _deadline()
    while not done():
        _pump_once(application, scheduler)
        if time.monotonic() > limit:
            return False
    return True


def _pump_once(application: object, scheduler: object) -> None:
    """Dispatch pending Qt events, then advance the scheduler by one tick."""
    from PyQt6.QtCore import QEventLoop

    application.processEvents(  # type: ignore[union-attr]
        QEventLoop.ProcessEventsFlag.AllEvents, 5
    )
    scheduler.tick()  # type: ignore[union-attr]
    time.sleep(0.001)


def _run_phases(application: object) -> SchedulerReport:
    """Exercise the scheduler against a live Qt event loop and thread pool."""
    from PyQt6.QtCore import QT_VERSION_STR, QRunnable, QThread, QThreadPool
    from qgis_sdk.core import Handoff, JobState, ResourceScope, StepScheduler
    from qgis_sdk.models import QgisSdkJobCancelledError

    class _Worker(QRunnable):
        """Run a callable on the pool; the callable owns its own reporting."""

        def __init__(self, action: Callable[[], None]) -> None:
            super().__init__()
            self._action = action
            self.setAutoDelete(True)

        def run(self) -> None:
            self._action()

    gui_thread = int(QThread.currentThreadId())
    marks: list[float] = []

    from PyQt6.QtCore import QTimer

    timer = QTimer()
    timer.setInterval(HEARTBEAT_INTERVAL_MS)

    def beat() -> None:
        marks.append(time.perf_counter())

    timer.timeout.connect(beat)
    timer.start()

    def gaps_since(start_index: int) -> list[float]:
        """Return the inter-heartbeat gaps from a recorded baseline index onward."""
        window = marks[start_index:]
        return [
            (window[index] - window[index - 1]) * 1000
            for index in range(1, len(window))
        ]

    def baseline_index() -> int:
        """Return the index of the most recent heartbeat, as a gap starting point."""
        return max(len(marks) - 1, 0)

    pool = QThreadPool.globalInstance()

    # Phases 1-3 run under one owner scope. Disposal gets its own scope, because a
    # disposed scope must refuse new work (ADR-21) rather than be reused.
    scope = ResourceScope()
    scheduler = StepScheduler(scope)

    # Phase 1 (control): a blocking handler on the GUI thread must starve the loop.
    _pump(application, scheduler, lambda: len(marks) >= 3)
    control_start = baseline_index()
    time.sleep(BLOCKING_HANDLER_MS / 1000)
    event_loop_polled = _pump(
        application, scheduler, lambda: len(marks) > control_start + 1
    )
    blocking_phase = summarise_gaps(gaps_since(control_start))

    # Phase 2: the same duration of work off-thread, resumed on the GUI thread.
    scheduled_start = baseline_index()
    handoff = Handoff()
    worker_ids: list[int] = []
    delivery_ids: list[int] = []
    results: list[object] = []

    async def scheduled() -> None:
        value = await handoff
        delivery_ids.append(int(QThread.currentThreadId()))
        results.append(value)

    def do_work() -> None:
        worker_ids.append(int(QThread.currentThreadId()))
        time.sleep(WORKER_DURATION_MS / 1000)
        handoff.resolve("payload")

    job = scheduler.submit(scheduled())
    pool.start(_Worker(do_work))
    scheduled_polled = _pump(application, scheduler, lambda: job.state.settled)
    scheduled_phase = summarise_gaps(gaps_since(scheduled_start))

    # Phase 3: cancellation is cooperative - the worker acknowledges, then cleanup runs.
    cancel_handoff = Handoff()
    cancel_worker_ids: list[int] = []
    iterations: list[int] = []
    cancelled: list[bool] = []

    async def cancellable() -> None:
        try:
            await cancel_handoff
        except QgisSdkJobCancelledError:
            cancelled.append(True)
            raise

    def do_cancellable_work() -> None:
        cancel_worker_ids.append(int(QThread.currentThreadId()))
        rounds = 0
        while rounds < 10_000 and not cancel_job.cancellation.is_cancelled():
            rounds += 1
            time.sleep(0.001)
        iterations.append(rounds)
        cancel_handoff.resolve("acknowledged")

    cancel_job = scheduler.submit(cancellable())
    # Start the job into its suspension first: cancelling a queued job runs no
    # author code at all, which would not exercise the cooperative path here.
    scheduler.tick()
    pool.start(_Worker(do_cancellable_work))
    time.sleep(WORKER_DURATION_MS / 1000)
    cancel_job.cancel()
    _pump(application, scheduler, lambda: cancel_job.state.settled)
    worker_acknowledged = bool(iterations) and cancelled == [True]
    scope.close()

    # Phase 4: a report that arrives after the owner disposed must not be delivered.
    late_scope = ResourceScope()
    late_scheduler = StepScheduler(late_scope)
    late_handoff = Handoff()
    late_deliveries: list[object] = []

    async def awaiting_late_report() -> None:
        late_deliveries.append(await late_handoff)

    late_job = late_scheduler.submit(awaiting_late_report())
    late_scheduler.tick()

    def report_late() -> None:
        time.sleep(0.05)
        late_handoff.resolve("too late")

    pool.start(_Worker(report_late))
    late_scope.close()
    _pump_for(application, late_scheduler, 0.2)
    late_report_dropped = (
        late_scheduler.dropped_reports == 1
        and late_deliveries == []
        and late_job.state is JobState.FAILED
    )

    # Phase 5: stuck work that ignores cancellation refuses an in-process replacement.
    stuck_scope = ResourceScope()
    stuck_scheduler = StepScheduler(stuck_scope)
    stuck_handoff = Handoff()

    async def stuck() -> None:
        await stuck_handoff

    stuck_job = stuck_scheduler.submit(stuck())

    def acknowledge_late() -> None:
        time.sleep(STUCK_ACK_MS / 1000)
        stuck_handoff.resolve("late acknowledgement")

    pool.start(_Worker(acknowledge_late))
    stuck_scheduler.tick()
    outcome = stuck_scheduler.quiesce(max_ticks=QUIESCE_TICKS)
    blocker = outcome.blockers[0] if outcome.blockers else None
    refusal_left_the_job_running = stuck_job.state is JobState.WAITING
    stuck_scheduler.resume()
    _pump(application, stuck_scheduler, lambda: stuck_job.state.settled)
    stuck_scope.close()

    timer.stop()
    pool.waitForDone(2000)

    criteria = {
        "gui_responsive_for_scheduled_work": scheduled_phase.responsive(
            GUI_GAP_BUDGET_MS
        )
        and blocking_phase.stalled(GUI_GAP_BUDGET_MS),
        "handoff_delivered_on_gui_thread": delivered_only_on(gui_thread, delivery_ids)
        and results == ["payload"],
        "work_ran_off_the_gui_thread": ran_on_a_different_thread(
            gui_thread, worker_ids
        ),
        "worker_acknowledged_cancellation": worker_acknowledged,
        "late_report_dropped_after_disposal": late_report_dropped,
        "replacement_refused_while_stuck": outcome.refused
        and bool(blocker)
        and refusal_left_the_job_running,
    }
    verdict, reasons = decide_verdict(criteria)

    return SchedulerReport(
        platform=platform.platform(),
        python_version=platform.python_version(),
        qgis_version=_qgis_version(),
        qt_version=QT_VERSION_STR,
        qgis_initialised=True,
        event_loop_polled=event_loop_polled and scheduled_polled,
        gui_thread_id=gui_thread,
        worker_thread_ids=tuple(worker_ids + cancel_worker_ids),
        delivery_thread_ids=tuple(delivery_ids),
        blocking_phase=blocking_phase,
        scheduled_phase=scheduled_phase,
        gui_responsive_for_scheduled_work=criteria["gui_responsive_for_scheduled_work"],
        handoff_delivered_on_gui_thread=criteria["handoff_delivered_on_gui_thread"],
        work_ran_off_the_gui_thread=criteria["work_ran_off_the_gui_thread"],
        worker_acknowledged_cancellation=criteria["worker_acknowledged_cancellation"],
        author_cleanup_ran=cancelled == [True],
        late_report_dropped_after_disposal=criteria[
            "late_report_dropped_after_disposal"
        ],
        replacement_refused_while_stuck=criteria["replacement_refused_while_stuck"],
        refused_blocker=blocker,
        verdict=verdict,
        scope_review_criteria=reasons,
    )


def _qgis_version() -> str | None:
    """Return the QGIS version when the bindings import, else nothing."""
    try:
        from qgis.core import Qgis

        return str(Qgis.QGIS_VERSION)
    except Exception:  # noqa: BLE001 - the report keeps the version absent instead
        return None


def _qt_version() -> str | None:
    """Return the Qt version when PyQt imports, else nothing."""
    try:
        from PyQt6.QtCore import QT_VERSION_STR

        return str(QT_VERSION_STR)
    except Exception:  # noqa: BLE001 - the report keeps the version absent instead
        return None


def run_smoke() -> SchedulerReport:
    """Start a headless QGIS application and report what the run observed."""
    import os

    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))
    from desktop_lifecycle_smoke import (
        headless_environment,
        qgis_python_path,
    )

    prefix = Path(sys.prefix)
    for key, value in headless_environment(prefix, os.environ).items():
        os.environ[key] = value
    for path in (qgis_python_path(prefix), SOURCE_ROOT):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))

    try:
        from qgis.core import QgsApplication

        QgsApplication.setPrefixPath(str(prefix), True)
        application = QgsApplication([b"qgis-sdk-scheduler-smoke"], True)
        application.initQgis()
    except Exception as error:  # noqa: BLE001 - report broken environments
        return _failed_report(
            f"QGIS initialisation failed: {error}", qgis_initialised=False
        )

    try:
        return _run_phases(application)
    except Exception as error:  # noqa: BLE001 - report broken environments
        return _failed_report(f"{type(error).__name__}: {error}", qgis_initialised=True)
    finally:
        with contextlib.suppress(Exception):
            application.exitQgis()


def _failed_report(error: str, *, qgis_initialised: bool) -> SchedulerReport:
    """Return a non-passing report that still states the verdict explicitly."""
    criteria = dict.fromkeys(DECIDING_CRITERIA, False)
    verdict, reasons = decide_verdict(criteria)
    empty = GapSummary(count=0, max_ms=0.0, mean_ms=0.0)
    return replace(
        SchedulerReport(
            platform=platform.platform(),
            python_version=platform.python_version(),
            qgis_version=_qgis_version(),
            qt_version=_qt_version(),
            qgis_initialised=qgis_initialised,
            event_loop_polled=False,
            gui_thread_id=0,
            worker_thread_ids=(),
            delivery_thread_ids=(),
            blocking_phase=empty,
            scheduled_phase=empty,
            gui_responsive_for_scheduled_work=False,
            handoff_delivered_on_gui_thread=False,
            work_ran_off_the_gui_thread=False,
            worker_acknowledged_cancellation=False,
            author_cleanup_ran=False,
            late_report_dropped_after_disposal=False,
            replacement_refused_while_stuck=False,
            refused_blocker=None,
            verdict=verdict,
            scope_review_criteria=reasons,
        ),
        error=error,
    )


def main() -> int:
    """Run the smoke and print its report as JSON."""
    report = run_smoke()
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

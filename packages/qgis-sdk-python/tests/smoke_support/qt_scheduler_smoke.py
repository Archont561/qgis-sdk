"""Headless Qt scheduler qualification harness for the TASK-13 spike.

This helper starts a real QGIS application, drives the SDK's pure
:class:`~qgis_sdk.core.scheduling.StepScheduler` from a real Qt event loop with a
real ``QThreadPool`` worker, and prints a machine-readable report covering GUI
responsiveness, worker-to-GUI thread handoff, cooperative cancellation, late
callbacks after disposal, and refused replacement while work is stuck.

It is **not** a QGIS Desktop GUI qualification: there is no display, no real
``iface``, and event delivery is driven by ``processEvents()``. Windows, macOS and
a real Desktop session stay tracked by TASK-33.

Run its pytest smoke test with ``pytest -m smoke``.

The summary and verdict helpers are pure, so the QGIS-free suite can test them;
the end-to-end run is opt-in through the test suite.
"""

from __future__ import annotations

import contextlib
import platform
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from pathlib import Path


def _failed_report_value(empty, error, qgis_initialised, reasons, verdict):
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


HEARTBEAT_INTERVAL_MS = 2
BLOCKING_HANDLER_MS = 60
WORKER_DURATION_MS = 60
GUI_GAP_BUDGET_MS = 40
STUCK_ACK_MS = 250
QUIESCE_TICKS = 8
PHASE_DEADLINE_MS = 8000

# Sampling and draining knobs for the phases below, kept beside the budgets so a
# port to another platform can retune one list instead of hunting literals.
GUI_STALL_SAMPLES = 3
CANCELLATION_POLL_ROUNDS = 10_000
CANCELLATION_POLL_INTERVAL_S = 0.001
LATE_REPORT_DELAY_MS = 50
DISPOSED_DRAIN_S = 0.2
POOL_DRAIN_MS = 2000

SCRIPT_DIR = Path(__file__).resolve().parent
SOURCE_ROOT = SCRIPT_DIR.parents[2] / "qgis-sdk-runtime" / "src"

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
        return all(
            (
                self.qgis_initialised,
                self.event_loop_polled,
                self.author_cleanup_ran,
                self.verdict == VERDICT_ADOPT,
                self.scope_review_criteria == (),
            )
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


@dataclass(frozen=True)
class _Heartbeat:
    """Heartbeat timestamps sampled on the GUI thread, and the windows inside them.

    A phase takes the baseline index before it starts and reads its latency picture
    out of the same marks afterwards, which is why measuring and stepping stay apart.
    """

    marks: list[float]

    def baseline_index(self) -> int:
        """Return the index of the most recent heartbeat, as a gap starting point."""
        return max(len(self.marks) - 1, 0)

    def gaps_since(self, start_index: int) -> list[float]:
        """Return the inter-heartbeat gaps from a recorded baseline index onward."""
        window = self.marks[start_index:]
        return [
            (window[index] - window[index - 1]) * 1000
            for index in range(1, len(window))
        ]

    def phase(self, start_index: int) -> GapSummary:
        """Summarise the gaps sampled since a phase took its baseline."""
        return summarise_gaps(self.gaps_since(start_index))

    def has_at_least(self, count: int) -> bool:
        """Whether this many heartbeats have been sampled."""
        return len(self.marks) >= count


@dataclass(frozen=True)
class _Harness:
    """What every phase shares: the live loop, the pool, and the GUI thread id."""

    application: object
    pool: object
    worker: Callable[[Callable[[], None]], object]
    gui_thread: int
    heartbeat: _Heartbeat

    def start(self, action: Callable[[], None]) -> None:
        """Run ``action`` on the pool, so it is provably not on the GUI thread."""
        self.pool.start(self.worker(action))

    def pump(self, scheduler: object, done: Callable[[], bool]) -> bool:
        """Drive the loop and ``scheduler`` until ``done`` or the phase deadline."""
        return _pump(self.application, scheduler, done)


@dataclass(frozen=True)
class _ScheduledEvidence:
    """Thread ids and the value carried by one off-thread handoff."""

    summary: GapSummary
    polled: bool
    worker_thread_ids: tuple[int, ...]
    delivery_thread_ids: tuple[int, ...]
    results: tuple[object, ...]


@dataclass(frozen=True)
class _ReplacementEvidence:
    """What a stuck job did to an in-process replacement attempt."""

    refused: bool
    blocker: str | None
    still_waiting: bool


@dataclass
class _ScheduledFacts:
    """The mutable observations one scheduled-work phase collects."""

    handoff: object
    worker_ids: list[int]
    delivery_ids: list[int]
    results: list[object]


@dataclass
class _CancellationFacts:
    """The mutable observations one cooperative-cancellation phase collects."""

    handoff: object
    job: object
    worker_ids: list[int]
    iterations: list[int]
    cancelled: list[bool]


@dataclass
class _LateFacts:
    """The mutable observations one disposal-phase report collects."""

    handoff: object
    deliveries: list[object]


@dataclass(frozen=True, slots=True)
class _QtRig:
    """The live Qt loop, its worker factory and the version it reported."""

    harness: _Harness
    timer: object
    qt_version: str


@dataclass(frozen=True, slots=True)
class _OwnedEvidence:
    """Phases 1-3, all measured under one owner scope."""

    blocking_phase: GapSummary
    control_polled: bool
    scheduled: _ScheduledEvidence
    cancel_worker_ids: tuple[int, ...]
    worker_acknowledged: bool
    cleanup_ran: bool


@dataclass(frozen=True, slots=True)
class _DisposalEvidence:
    """Phases 4-5, each measured under its own disposed scope."""

    late_report_dropped: bool
    replacement: _ReplacementEvidence


@dataclass(frozen=True, slots=True)
class _PhaseEvidence:
    """Every phase's answer, plus the two facts the report header needs."""

    owned: _OwnedEvidence
    disposal: _DisposalEvidence
    gui_thread: int
    qt_version: str


async def _scheduled(facts: _ScheduledFacts) -> None:
    """Record the thread a handoff was delivered on, and the value it carried."""
    from PyQt6.QtCore import QThread

    value = await facts.handoff
    facts.delivery_ids.append(int(QThread.currentThreadId()))
    facts.results.append(value)


def _do_scheduled_work(facts: _ScheduledFacts) -> None:
    """Sleep off-thread, then resolve the handoff back onto the GUI thread."""
    from PyQt6.QtCore import QThread

    facts.worker_ids.append(int(QThread.currentThreadId()))
    time.sleep(WORKER_DURATION_MS / 1000)
    facts.handoff.resolve("payload")


async def _cancellable(facts: _CancellationFacts) -> None:
    """Cooperatively acknowledge cancellation rather than swallowing it."""
    from qgis_sdk.models import QgisSdkJobCancelledError

    try:
        await facts.handoff
    except QgisSdkJobCancelledError:
        facts.cancelled.append(True)
        raise


def _do_cancellable_work(facts: _CancellationFacts) -> None:
    """Poll until the job is cancelled, then acknowledge on the worker thread."""
    from PyQt6.QtCore import QThread

    facts.worker_ids.append(int(QThread.currentThreadId()))
    rounds = 0
    while (
        rounds < CANCELLATION_POLL_ROUNDS and not facts.job.cancellation.is_cancelled()
    ):
        rounds += 1
        time.sleep(CANCELLATION_POLL_INTERVAL_S)
    facts.iterations.append(rounds)
    facts.handoff.resolve("acknowledged")


async def _awaiting_late_report(facts: _LateFacts) -> None:
    facts.deliveries.append(await facts.handoff)


def _report_late(handoff: object) -> None:
    time.sleep(LATE_REPORT_DELAY_MS / 1000)
    handoff.resolve("too late")


async def _stuck(handoff: object) -> None:
    await handoff


def _acknowledge_late(handoff: object) -> None:
    time.sleep(STUCK_ACK_MS / 1000)
    handoff.resolve("late acknowledgement")


def _stuck_evidence(
    harness: _Harness, scheduler: object, scope: object, job: object
) -> _ReplacementEvidence:
    """Quiesce a stuck job, resume it and report what the attempt observed."""
    from qgis_sdk.core import JobState

    outcome = scheduler.quiesce(max_ticks=QUIESCE_TICKS)
    blocker = outcome.blockers[0] if outcome.blockers else None
    still_waiting = job.state is JobState.WAITING
    scheduler.resume()
    harness.pump(scheduler, lambda: job.state.settled)
    scope.close()
    return _ReplacementEvidence(
        refused=outcome.refused and bool(blocker) and still_waiting,
        blocker=blocker,
        still_waiting=still_waiting,
    )


def _qt_worker_class():
    """A QRunnable that runs one callable on the pool."""
    from PyQt6.QtCore import QRunnable

    class _Worker(QRunnable):
        def __init__(self, action: Callable[[], None]) -> None:
            super().__init__()
            self._action = action
            self.setAutoDelete(True)

        def run(self) -> None:
            self._action()

    return _Worker


def _qt_rig(application: object) -> _QtRig:
    """Start the heartbeat timer and wire the shared harness to a live pool."""
    from PyQt6.QtCore import QT_VERSION_STR, QThread, QThreadPool, QTimer

    marks: list[float] = []

    def beat() -> None:
        marks.append(time.perf_counter())

    timer = QTimer()
    timer.setInterval(HEARTBEAT_INTERVAL_MS)
    timer.timeout.connect(beat)
    timer.start()
    harness = _Harness(
        application=application,
        pool=QThreadPool.globalInstance(),
        worker=_qt_worker_class(),
        gui_thread=int(QThread.currentThreadId()),
        heartbeat=_Heartbeat(marks),
    )
    return _QtRig(harness, timer, str(QT_VERSION_STR))


def _owned_phases(
    harness: _Harness, scheduler: object, scope: object
) -> _OwnedEvidence:
    """Phases 1-3 share one owner scope, then dispose it."""
    blocking_phase, control_polled = _phase_blocking_control(harness, scheduler)
    scheduled = _phase_scheduled_work(harness, scheduler)
    cancel_worker_ids, worker_acknowledged, cleanup_ran = _phase_cancellation(
        harness, scheduler
    )
    scope.close()
    return _OwnedEvidence(
        blocking_phase,
        control_polled,
        scheduled,
        cancel_worker_ids,
        worker_acknowledged,
        cleanup_ran,
    )


def _disposal_phases(harness: _Harness) -> _DisposalEvidence:
    """A disposed scope gets its own phases, so it can refuse new work."""
    return _DisposalEvidence(
        late_report_dropped=_phase_late_report(harness),
        replacement=_phase_stuck_replacement(harness),
    )


def _criteria(evidence: _PhaseEvidence) -> dict[str, bool]:
    """The six deciding criteria, each read from one phase's evidence."""
    owned, disposal = evidence.owned, evidence.disposal
    return {
        "gui_responsive_for_scheduled_work": all(
            (
                owned.scheduled.polled,
                owned.control_polled,
                owned.scheduled.summary.responsive(GUI_GAP_BUDGET_MS),
                owned.blocking_phase.stalled(GUI_GAP_BUDGET_MS),
            )
        ),
        "handoff_delivered_on_gui_thread": delivered_only_on(
            evidence.gui_thread, list(owned.scheduled.delivery_thread_ids)
        )
        and owned.scheduled.results == ("payload",),
        "work_ran_off_the_gui_thread": ran_on_a_different_thread(
            evidence.gui_thread, list(owned.scheduled.worker_thread_ids)
        ),
        "worker_acknowledged_cancellation": owned.worker_acknowledged,
        "late_report_dropped_after_disposal": disposal.late_report_dropped,
        "replacement_refused_while_stuck": disposal.replacement.refused,
    }


def _scheduler_report(
    evidence: _PhaseEvidence, checks: Mapping[str, bool]
) -> SchedulerReport:
    """Assemble the report from the phases and the verdict they decided."""
    owned, disposal = evidence.owned, evidence.disposal
    verdict, reasons = decide_verdict(checks)
    return SchedulerReport(
        platform=platform.platform(),
        python_version=platform.python_version(),
        qgis_version=_qgis_version(),
        qt_version=evidence.qt_version,
        qgis_initialised=True,
        event_loop_polled=owned.control_polled and owned.scheduled.polled,
        gui_thread_id=evidence.gui_thread,
        worker_thread_ids=owned.scheduled.worker_thread_ids + owned.cancel_worker_ids,
        delivery_thread_ids=owned.scheduled.delivery_thread_ids,
        blocking_phase=owned.blocking_phase,
        scheduled_phase=owned.scheduled.summary,
        gui_responsive_for_scheduled_work=checks["gui_responsive_for_scheduled_work"],
        handoff_delivered_on_gui_thread=checks["handoff_delivered_on_gui_thread"],
        work_ran_off_the_gui_thread=checks["work_ran_off_the_gui_thread"],
        worker_acknowledged_cancellation=checks["worker_acknowledged_cancellation"],
        author_cleanup_ran=owned.cleanup_ran,
        late_report_dropped_after_disposal=checks["late_report_dropped_after_disposal"],
        replacement_refused_while_stuck=checks["replacement_refused_while_stuck"],
        refused_blocker=disposal.replacement.blocker,
        verdict=verdict,
        scope_review_criteria=reasons,
    )


def _report_from_phases(rig: _QtRig) -> SchedulerReport:
    """Drive every phase against one harness, then close the timer and pool."""
    from qgis_sdk.core import ResourceScope, StepScheduler

    scope = ResourceScope()
    scheduler = StepScheduler(scope)
    owned = _owned_phases(rig.harness, scheduler, scope)
    disposal = _disposal_phases(rig.harness)
    rig.timer.stop()
    rig.harness.pool.waitForDone(POOL_DRAIN_MS)
    evidence = _PhaseEvidence(owned, disposal, rig.harness.gui_thread, rig.qt_version)
    criteria = _criteria(evidence)
    return _scheduler_report(evidence, criteria)


def _prepare_qgis_environment() -> Path:
    """Point the interpreter at a headless QGIS before any binding is imported."""
    import os

    from smoke_support.desktop_lifecycle_smoke import (
        headless_environment,
        qgis_python_path,
    )

    prefix = Path(sys.prefix)
    for key, value in headless_environment(prefix, os.environ).items():
        os.environ[key] = value
    for path in (qgis_python_path(prefix), SOURCE_ROOT):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    return prefix


def _phase_blocking_control(
    harness: _Harness, scheduler: object
) -> tuple[GapSummary, bool]:
    """Phase 1 (control): a blocking handler on the GUI thread must starve the loop."""
    heartbeat = harness.heartbeat
    harness.pump(scheduler, lambda: heartbeat.has_at_least(GUI_STALL_SAMPLES))
    start = heartbeat.baseline_index()
    time.sleep(BLOCKING_HANDLER_MS / 1000)
    polled = harness.pump(scheduler, lambda: len(heartbeat.marks) > start + 1)
    return heartbeat.phase(start), polled


def _phase_scheduled_work(harness: _Harness, scheduler: object) -> _ScheduledEvidence:
    """Phase 2: the same duration of work off-thread, resumed on the GUI thread."""
    from qgis_sdk.core import Handoff

    start = harness.heartbeat.baseline_index()
    facts = _ScheduledFacts(Handoff(), [], [], [])
    job = scheduler.submit(_scheduled(facts))
    harness.start(lambda: _do_scheduled_work(facts))
    polled = harness.pump(scheduler, lambda: job.state.settled)
    return _ScheduledEvidence(
        summary=harness.heartbeat.phase(start),
        polled=polled,
        worker_thread_ids=tuple(facts.worker_ids),
        delivery_thread_ids=tuple(facts.delivery_ids),
        results=tuple(facts.results),
    )


def _phase_cancellation(
    harness: _Harness, scheduler: object
) -> tuple[tuple[int, ...], bool, bool]:
    """Phase 3: cancellation is cooperative - the worker acknowledges, then cleanup runs."""
    from qgis_sdk.core import Handoff

    facts = _CancellationFacts(Handoff(), None, [], [], [])
    facts.job = scheduler.submit(_cancellable(facts))
    # Start the job into its suspension first: cancelling a queued job runs no
    # author code at all, which would not exercise the cooperative path here.
    scheduler.tick()
    harness.start(lambda: _do_cancellable_work(facts))
    time.sleep(WORKER_DURATION_MS / 1000)
    facts.job.cancel()
    harness.pump(scheduler, lambda: facts.job.state.settled)
    return (
        tuple(facts.worker_ids),
        bool(facts.iterations) and facts.cancelled == [True],
        facts.cancelled == [True],
    )


def _phase_late_report(harness: _Harness) -> bool:
    """Phase 4: a report that arrives after the owner disposed must not be delivered."""
    from qgis_sdk.core import Handoff, JobState, ResourceScope, StepScheduler

    late_scope = ResourceScope()
    late_scheduler = StepScheduler(late_scope)
    facts = _LateFacts(Handoff(), [])
    late_job = late_scheduler.submit(_awaiting_late_report(facts))
    late_scheduler.tick()
    harness.start(lambda: _report_late(facts.handoff))
    late_scope.close()
    _pump_for(harness.application, late_scheduler, DISPOSED_DRAIN_S)
    return (
        late_scheduler.dropped_reports == 1
        and facts.deliveries == []
        and late_job.state is JobState.FAILED
    )


def _phase_stuck_replacement(harness: _Harness) -> _ReplacementEvidence:
    """Phase 5: stuck work that ignores cancellation refuses an in-process replacement."""
    from qgis_sdk.core import Handoff, ResourceScope, StepScheduler

    scope = ResourceScope()
    scheduler = StepScheduler(scope)
    handoff = Handoff()
    job = scheduler.submit(_stuck(handoff))
    harness.start(lambda: _acknowledge_late(handoff))
    scheduler.tick()
    return _stuck_evidence(harness, scheduler, scope, job)


def _run_phases(application: object) -> SchedulerReport:
    """Exercise the scheduler against a live Qt event loop and thread pool.

    Each phase owns its own measurement and evidence; this function only wires the
    shared harness together and assembles the report, so porting one phase to a new
    platform cannot silently change what another one asserts.
    """
    return _report_from_phases(_qt_rig(application))


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
    prefix = _prepare_qgis_environment()
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
    return _failed_report_value(empty, error, qgis_initialised, reasons, verdict)

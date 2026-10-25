"""Deterministic tests for cooperative cancellation of scheduled jobs.

Cancellation is polled at suspension points rather than forced, so these tests pin
where a stop request may and may not land. Nothing here waits on wall-clock time.
"""

from __future__ import annotations

from qgis_sdk.core.scheduling import (
    Handoff,
    JobState,
    StepScheduler,
    Yield,
)
from qgis_sdk.core.scope import ResourceScope
from qgis_sdk.models import (
    QgisSdkJobCancelledError,
)


def scheduler_with_scope() -> StepScheduler:
    return StepScheduler(ResourceScope())


def test_cancellation_is_delivered_at_the_next_suspension_point() -> None:
    events: list[str] = []

    async def body() -> None:
        try:
            while True:
                await Yield()
        finally:
            events.append("cleanup")

    scheduler = scheduler_with_scope()
    job = scheduler.submit(body())
    scheduler.tick()

    assert job.cancel() is True
    scheduler.tick()

    assert events == ["cleanup"]
    assert job.state is JobState.CANCELLED
    assert job.cancellation.is_cancelled() is True


def test_author_code_may_suppress_cancellation_and_finish() -> None:
    async def body() -> str:
        try:
            await Yield()
        except QgisSdkJobCancelledError:
            return "finished-anyway"
        await Yield()
        return "not-cancelled"

    scheduler = scheduler_with_scope()
    job = scheduler.submit(body())
    scheduler.tick()
    job.cancel()
    scheduler.tick()

    assert job.state is JobState.COMPLETED
    assert job.result == "finished-anyway"


def test_cancelling_a_queued_job_runs_no_author_code() -> None:
    events: list[str] = []

    async def body() -> None:
        events.append("ran")

    scheduler = scheduler_with_scope()
    job = scheduler.submit(body())

    assert job.cancel() is True
    scheduler.tick()

    assert events == []
    assert job.state is JobState.CANCELLED
    assert job.steps == 0


def test_cancelting_a_settled_job_reports_that_it_cannot_be_stopped() -> None:
    async def body() -> None:
        return None

    scheduler = scheduler_with_scope()
    job = scheduler.submit(body())
    scheduler.tick()

    assert job.state is JobState.COMPLETED
    assert job.cancel() is False


def test_the_cancellation_signal_points_back_at_its_own_job() -> None:
    async def body() -> None:
        await Yield()

    scheduler = scheduler_with_scope()
    job = scheduler.submit(body())

    assert job.cancellation.job is job
    assert job.cancellation.is_cancelled() is False

    job.cancel()
    assert job.cancellation.is_cancelled() is True

    # A queued job still holds its coroutine until a tick settles it; disposing the
    # owner is what releases it, so the test cleans up through that path.
    scheduler.close()
    assert job.state is JobState.CANCELLED


def test_cancelling_a_job_suspended_on_a_cancellable_handoff_tells_the_worker() -> None:
    told: list[str] = []
    handoff = Handoff(on_cancel=lambda: told.append("stop"))
    outcome: list[str] = []

    async def body() -> None:
        try:
            await handoff
        except QgisSdkJobCancelledError:
            outcome.append("cancelled at the handoff")
            raise

    scheduler = scheduler_with_scope()
    job = scheduler.submit(body())
    scheduler.tick()
    assert job.state is JobState.WAITING

    assert job.cancel() is True
    assert told == ["stop"], (
        "the hook runs once, inside cancel(), on the driving thread"
    )
    assert job.cancel() is False
    assert told == ["stop"]

    # Nothing resumes until the worker acknowledges by reporting; then the job
    # sees the cancellation, not the report.
    scheduler.tick()
    assert job.state is JobState.WAITING
    handoff.fail(RuntimeError("aborted"))
    scheduler.tick()
    assert job.state is JobState.CANCELLED
    assert outcome == ["cancelled at the handoff"]


def test_a_handoff_without_a_hook_still_waits_for_its_worker() -> None:
    handoff = Handoff()

    async def body() -> None:
        await handoff

    scheduler = scheduler_with_scope()
    job = scheduler.submit(body())
    scheduler.tick()

    assert job.cancel() is True
    scheduler.tick()
    assert job.state is JobState.WAITING


def test_quiesce_succeeds_when_the_hook_makes_the_worker_report() -> None:
    handoff = Handoff(on_cancel=lambda: handoff.fail(RuntimeError("aborted")))

    async def body() -> None:
        await handoff

    scheduler = scheduler_with_scope()
    scheduler.submit(body())
    scheduler.tick()

    outcome = scheduler.quiesce(max_ticks=4)

    assert outcome.safe_to_replace
    assert outcome.blockers == ()

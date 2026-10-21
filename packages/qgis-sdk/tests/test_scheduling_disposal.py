"""Deterministic tests for disposal, quiesce and late worker reports.

Disposal is the reload boundary: these tests pin that a job never resumes after
it, a late report is counted rather than delivered, and a replacement is refused
while work cannot reach a safe point. Nothing here waits on wall-clock time.
"""

from __future__ import annotations

import warnings

import pytest
from qgis_sdk.core.scheduling import (
    Handoff,
    JobState,
    QuiesceOutcome,
    StepScheduler,
    Yield,
)
from qgis_sdk.core.scope import ResourceScope
from qgis_sdk.models import (
    QgisSdkJobCancelledError,
    QgisSdkSchedulingBlockedError,
    QgisSdkScopeClosedError,
)


def scheduler_with_scope() -> StepScheduler:
    return StepScheduler(ResourceScope())


def test_a_job_abandoned_during_a_tick_is_never_resumed_later_in_that_tick() -> None:
    """Disposal detaches the whole generation, including jobs not started yet."""
    ran: list[str] = []

    async def closer() -> None:
        scheduler.close()
        await Yield()

    async def neighbour() -> None:
        ran.append("neighbour author code")

    scheduler = scheduler_with_scope()
    scheduler.submit(closer())
    abandoned = scheduler.submit(neighbour())

    # The job that disposes the scope is submitted first, so the still-queued
    # neighbour is in this same tick's snapshot when disposal lands mid-step.
    scheduler.tick()

    assert ran == []
    assert abandoned.state is JobState.FAILED
    assert isinstance(abandoned.error, QgisSdkScopeClosedError)
    assert abandoned.steps == 0


@pytest.mark.parametrize("ending", ["yield", "return", "raise"])
def test_disposal_wins_over_whatever_the_abandoned_job_does_next(
    ending: str,
) -> None:
    """Author code already on the stack cannot un-settle a job disposal abandoned."""
    handoff = Handoff()

    async def body() -> object:
        scheduler.close()
        if ending == "yield":
            await handoff
        elif ending == "return":
            return "late"
        raise ValueError("late")

    scheduler = scheduler_with_scope()
    job = scheduler.submit(body())

    scheduler.tick()

    assert job.state is JobState.FAILED
    assert isinstance(job.error, QgisSdkScopeClosedError)
    assert job.awaiting is None
    assert job.result is None
    assert handoff.owner is None


def test_submitting_after_disposal_is_refused() -> None:
    async def body() -> None:
        return None

    scheduler = scheduler_with_scope()
    scheduler.close()

    with pytest.raises(QgisSdkScopeClosedError):
        scheduler.submit(body())


def test_work_awaiting_an_unresolved_handoff_blocks_replacement() -> None:
    async def body() -> None:
        await Handoff()

    scheduler = scheduler_with_scope()
    job = scheduler.submit(body())
    scheduler.tick()

    outcome = scheduler.quiesce()

    assert outcome.refused is True
    assert outcome.safe_to_replace is False
    assert outcome.blockers == (
        f"job {job.id} is waiting on an unresolved worker handoff",
    )
    assert scheduler.quiescing is True


def test_quiesce_clears_once_the_worker_reports() -> None:
    handoff = Handoff()

    async def body() -> None:
        await handoff

    scheduler = scheduler_with_scope()
    scheduler.submit(body())
    scheduler.tick()

    handoff.resolve("acknowledged")
    outcome = scheduler.quiesce()

    assert outcome == QuiesceOutcome(refused=False, blockers=())
    assert outcome.safe_to_replace is True
    assert scheduler.quiescing is False
    assert scheduler.jobs == {}


def test_a_busy_loop_that_ignores_cancellation_is_named_as_a_blocker() -> None:
    async def body() -> None:
        while True:
            try:
                await Yield()
            except QgisSdkJobCancelledError:
                continue

    scheduler = scheduler_with_scope()
    job = scheduler.submit(body())
    scheduler.tick()

    outcome = scheduler.quiesce(max_ticks=4)

    assert outcome.refused is True
    assert outcome.blockers == (f"job {job.id} is still waiting after cancellation",)

    scheduler.resume()
    assert scheduler.quiescing is False

    # Refusing a replacement keeps the old generation running and observable.
    resumed = scheduler.submit(body())
    assert tuple(scheduler.jobs) == (job.id, resumed.id)
    scheduler.tick()
    assert resumed.state is JobState.WAITING
    assert resumed.cancellation.is_cancelled() is False


def test_quiesce_reports_which_jobs_are_still_active() -> None:
    outcomes: list[str] = []

    async def finishing() -> None:
        try:
            await Yield()
        except QgisSdkJobCancelledError:
            pass
        outcomes.append("finished")

    async def stuck() -> None:
        await Handoff()

    scheduler = scheduler_with_scope()
    scheduler.submit(finishing())
    scheduler.submit(stuck())
    scheduler.tick()

    outcome = scheduler.quiesce()

    assert outcomes == ["finished"]
    assert outcome.blockers == ("job 2 is waiting on an unresolved worker handoff",)


def test_a_late_worker_report_after_disposal_is_dropped_not_delivered() -> None:
    resumed: list[object] = []
    handoff = Handoff()

    async def body() -> None:
        value = await handoff
        resumed.append(value)

    scheduler = scheduler_with_scope()
    job = scheduler.submit(body())
    scheduler.tick()

    scheduler.close()
    handoff.resolve("too late")
    scheduler.tick()

    assert resumed == []
    assert scheduler.dropped_reports == 1
    assert job.state is JobState.FAILED
    assert isinstance(job.error, QgisSdkScopeClosedError)
    assert handoff.owner is None


def test_a_report_queued_before_disposal_is_still_not_delivered() -> None:
    handoff = Handoff()

    async def body() -> None:
        await handoff

    scheduler = scheduler_with_scope()
    job = scheduler.submit(body())
    scheduler.tick()

    handoff.resolve("queued but never read")

    scheduler.close()

    assert scheduler.dropped_reports == 1
    assert job.state is JobState.FAILED
    assert job.awaiting is None


def test_disposal_is_idempotent_and_releases_a_queued_job() -> None:
    events: list[str] = []

    async def body() -> None:
        events.append("ran")

    scheduler = scheduler_with_scope()
    job = scheduler.submit(body())

    scheduler.close()
    scheduler.close()

    assert events == []
    assert job.state is JobState.FAILED
    assert job.cancellation.is_cancelled() is False


def test_submitting_while_quiescing_is_refused_without_leaking_the_coroutine() -> None:
    started: list[str] = []

    async def body() -> None:
        started.append("ran")

    async def stuck() -> None:
        await Handoff()

    scheduler = scheduler_with_scope()
    scheduler.submit(stuck())
    scheduler.tick()
    assert scheduler.quiesce(max_ticks=2).refused is True

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with pytest.raises(QgisSdkSchedulingBlockedError) as refused:
            scheduler.submit(body())

    assert refused.value.blockers == ("the scheduler is quiescing for replacement",)
    assert started == []
    assert [str(entry.message) for entry in caught] == []


def test_a_refusal_is_reportable_to_a_qualification_summary() -> None:
    async def body() -> None:
        await Handoff()

    scheduler = scheduler_with_scope()
    job = scheduler.submit(body())
    scheduler.tick()

    outcome = scheduler.quiesce(max_ticks=2)

    assert outcome.as_dict() == {
        "refused": True,
        "blockers": [f"job {job.id} is waiting on an unresolved worker handoff"],
    }
    assert outcome.safe_to_replace is False

"""Deterministic tests for the step scheduler used by the TASK-13 spike.

The scheduler drives real coroutines one bounded step at a time and never owns a
thread, so every test here is reproducible: nothing waits on wall-clock time and
no assertion depends on how fast a host event loop runs.
"""

from __future__ import annotations

import warnings
from collections.abc import Generator

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
    QgisSdkUnsupportedCapabilityError,
)


class _HostShutdown(BaseException):
    """A non-``Exception`` control-flow signal, like the interpreter's own exits."""


def scheduler_with_scope() -> StepScheduler:
    return StepScheduler(ResourceScope())


def test_submit_does_not_run_author_code_until_the_first_tick() -> None:
    events: list[str] = []

    async def body() -> None:
        events.append("ran")

    scheduler = scheduler_with_scope()
    job = scheduler.submit(body())

    assert events == []
    assert job.state is JobState.QUEUED

    scheduler.tick()

    assert events == ["ran"]
    assert job.state is JobState.COMPLETED


def test_a_yielded_step_resumes_on_the_next_tick() -> None:
    events: list[str] = []

    async def body() -> str:
        events.append("first")
        await Yield()
        events.append("second")
        return "done"

    scheduler = scheduler_with_scope()
    job = scheduler.submit(body())

    assert scheduler.tick() == 1
    assert events == ["first"]
    assert job.state is JobState.WAITING

    assert scheduler.tick() == 1
    assert events == ["first", "second"]
    assert job.state is JobState.COMPLETED
    assert job.result == "done"
    assert scheduler.tick() == 0


def test_an_error_raised_by_the_job_is_observable_on_the_handle() -> None:
    class JobBodyError(RuntimeError):
        pass

    async def body() -> None:
        await Yield()
        raise JobBodyError("author failure")

    scheduler = scheduler_with_scope()
    job = scheduler.submit(body())
    scheduler.tick()
    scheduler.tick()

    assert job.state is JobState.FAILED
    assert isinstance(job.error, JobBodyError)


def test_an_exception_is_not_swallowed_by_the_next_tick_being_empty() -> None:
    async def body() -> None:
        raise ValueError("immediate")

    scheduler = scheduler_with_scope()
    job = scheduler.submit(body())
    scheduler.tick()

    assert job.state is JobState.FAILED
    assert isinstance(job.error, ValueError)


@pytest.mark.parametrize(
    "interrupting",
    [KeyboardInterrupt, SystemExit, _HostShutdown],
)
def test_a_host_interruption_propagates_instead_of_becoming_a_quiet_job_failure(
    interrupting: type[BaseException],
) -> None:
    """The scheduler must not swallow control flow the host raised through it."""

    async def body() -> None:
        await Yield()
        raise interrupting

    scheduler = scheduler_with_scope()
    job = scheduler.submit(body())
    scheduler.tick()

    with pytest.raises(interrupting):
        scheduler.tick()

    assert job.state is JobState.FAILED
    assert isinstance(job.error, interrupting)
    assert scheduler.jobs == {}
    assert scheduler.drain(max_ticks=4) == 0


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


def test_a_job_submitted_during_a_tick_starts_on_the_next_one() -> None:
    """The tick advances the generation it started with, not one that grew mid-tick."""
    order: list[str] = []

    async def parent() -> None:
        order.append("parent")
        scheduler.submit(child())

    async def child() -> None:
        order.append("child")

    scheduler = scheduler_with_scope()
    scheduler.submit(parent())

    scheduler.tick()
    assert order == ["parent"]

    scheduler.tick()
    assert order == ["parent", "child"]


def test_a_handoff_resumes_only_when_the_worker_reports() -> None:
    resumed: list[object] = []
    pending = Handoff()

    async def body() -> None:
        value = await pending
        resumed.append(value)

    scheduler = scheduler_with_scope()
    job = scheduler.submit(body())

    scheduler.tick()
    assert job.state is JobState.WAITING
    assert resumed == []

    # A worker reports from wherever it runs; the awaiting job is not resumed here.
    pending.resolve("payload")
    assert resumed == []

    scheduler.tick()
    assert resumed == ["payload"]
    assert job.state is JobState.COMPLETED


def test_submitting_after_disposal_is_refused() -> None:
    async def body() -> None:
        return None

    scheduler = scheduler_with_scope()
    scheduler.close()

    with pytest.raises(QgisSdkScopeClosedError):
        scheduler.submit(body())


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


def test_awaiting_an_unsupported_awaitable_fails_the_job() -> None:
    class NotAStep:
        def __await__(self) -> Generator[object, None, None]:
            return (yield "not-a-step")

    async def body() -> None:
        await NotAStep()

    scheduler = scheduler_with_scope()
    job = scheduler.submit(body())
    scheduler.tick()

    assert job.state is JobState.FAILED
    assert isinstance(job.error, QgisSdkUnsupportedCapabilityError)
    assert job.error.capability == "awaitable str"


def test_drain_runs_every_job_once_and_prunes_settled_jobs() -> None:
    async def body() -> str:
        await Yield()
        return "ok"

    scheduler = scheduler_with_scope()
    jobs = [scheduler.submit(body()) for _ in range(3)]

    assert scheduler.drain() == 2
    assert [job.result for job in jobs] == ["ok", "ok", "ok"]
    assert scheduler.jobs == {}


def test_the_step_budget_stops_one_hot_job_from_starving_the_tick() -> None:
    async def hot() -> None:
        handoff = Handoff()
        handoff.resolve("ready")
        for _ in range(10):
            await handoff

    async def calm() -> None:
        await Yield()

    scheduler = StepScheduler(ResourceScope(), max_steps_per_job=2)
    busy = scheduler.submit(hot())
    calm_job = scheduler.submit(calm())

    assert scheduler.tick() == 3
    assert busy.steps == 2
    assert calm_job.steps == 1
    assert busy.awaiting is None or busy.awaiting.reported is False


def test_a_rejected_worker_report_fails_the_awaiting_job() -> None:
    class WorkerFailed(RuntimeError):
        pass

    handoff = Handoff()

    async def body() -> None:
        await handoff

    scheduler = scheduler_with_scope()
    job = scheduler.submit(body())
    scheduler.tick()

    handoff.fail(WorkerFailed("disk gone"))
    scheduler.tick()

    assert job.state is JobState.FAILED
    assert isinstance(job.error, WorkerFailed)


def test_an_awaiting_job_reports_itself_as_settled_only_after_the_worker_reports() -> (
    None
):
    handoff = Handoff()

    async def body() -> None:
        await handoff

    scheduler = scheduler_with_scope()
    job = scheduler.submit(body())
    scheduler.tick()

    assert job.settled is False
    assert handoff.owner is job

    handoff.resolve("ack")
    scheduler.tick()

    assert job.settled is True
    assert handoff.owner is None


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


def test_a_rejected_step_budget_is_reported_immediately() -> None:
    with pytest.raises(ValueError, match="max_steps_per_job must be at least 1"):
        StepScheduler(ResourceScope(), max_steps_per_job=0)


def test_the_scheduler_follows_the_owning_scope_lifetime() -> None:
    scope = ResourceScope()
    scheduler = StepScheduler(scope)

    assert scheduler.closed is False

    scope.close()

    assert scheduler.closed is True


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

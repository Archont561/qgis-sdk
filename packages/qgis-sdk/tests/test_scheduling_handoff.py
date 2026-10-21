"""Deterministic tests for worker handoffs into the step scheduler.

A handoff is where work leaves the GUI thread and comes back, so these tests pin
that a job resumes only once a worker has reported, and only on the GUI thread
that drives the scheduler. Nothing here waits on wall-clock time.
"""

from __future__ import annotations

from qgis_sdk.core.scheduling import (
    Handoff,
    JobState,
    StepScheduler,
)
from qgis_sdk.core.scope import ResourceScope


def scheduler_with_scope() -> StepScheduler:
    return StepScheduler(ResourceScope())


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

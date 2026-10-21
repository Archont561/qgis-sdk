"""Deterministic tests for how the step scheduler advances jobs.

The scheduler drives real coroutines one bounded step at a time and never owns a
thread, so nothing here waits on wall-clock time and no assertion depends on how
fast a host event loop runs. Worker handoff, cancellation and disposal each have
their own module beside this one.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from qgis_sdk.core.scheduling import (
    Handoff,
    JobState,
    StepScheduler,
    Yield,
)
from qgis_sdk.core.scope import ResourceScope
from qgis_sdk.models import (
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


def test_a_rejected_step_budget_is_reported_immediately() -> None:
    with pytest.raises(ValueError, match="max_steps_per_job must be at least 1"):
        StepScheduler(ResourceScope(), max_steps_per_job=0)


def test_the_scheduler_follows_the_owning_scope_lifetime() -> None:
    scope = ResourceScope()
    scheduler = StepScheduler(scope)

    assert scheduler.closed is False

    scope.close()

    assert scheduler.closed is True

"""Scheduling scenarios against the public StepScheduler API."""

from __future__ import annotations

from dataclasses import dataclass, field

from pytest_bdd import given, scenarios, then, when
from qgis_sdk.core import (
    Handoff,
    Job,
    JobState,
    QuiesceOutcome,
    ResourceScope,
    StepScheduler,
    Yield,
)
from qgis_sdk.models import QgisSdkScopeClosedError

scenarios("features/step_scheduling.feature")


@dataclass
class SchedulingScenario:
    scope: ResourceScope
    scheduler: StepScheduler
    job: Job | None = None
    handoff: Handoff | None = None
    events: list[str] = field(default_factory=list)
    outcome: QuiesceOutcome | None = None
    raised: BaseException | None = None


def scheduling_scenario() -> SchedulingScenario:
    scope = ResourceScope()
    return SchedulingScenario(scope, StepScheduler(scope))


@given("a job that yields once before it returns a value", target_fixture="scenario")
def job_yielding_once_before_returning() -> SchedulingScenario:
    scenario = scheduling_scenario()

    async def body() -> str:
        scenario.events.append("step")
        await Yield()
        scenario.events.append("step")
        return "value"

    scenario.job = scenario.scheduler.submit(body())
    return scenario


@when("the host advances the scheduler twice")
def advance_twice(scenario: SchedulingScenario) -> None:
    scenario.scheduler.tick()
    scenario.scheduler.tick()


@then("the job body ran exactly twice")
def body_ran_twice(scenario: SchedulingScenario) -> None:
    assert scenario.events == ["step", "step"]
    assert scenario.job is not None
    assert scenario.job.steps == 2


@then("the job completed with its returned value")
def job_completed(scenario: SchedulingScenario) -> None:
    assert scenario.job is not None
    assert scenario.job.state is JobState.COMPLETED
    assert scenario.job.result == "value"
    assert scenario.scheduler.jobs == {}


@given(
    "a job that cleans up in a finally block while awaiting a yield",
    target_fixture="scenario",
)
def job_with_cleanup() -> SchedulingScenario:
    scenario = scheduling_scenario()

    async def body() -> None:
        try:
            while True:
                await Yield()
        finally:
            scenario.events.append("cleanup")

    scenario.job = scenario.scheduler.submit(body())
    scenario.scheduler.tick()
    return scenario


@when("the job is cancelled and the host advances the scheduler")
def cancel_and_tick(scenario: SchedulingScenario) -> None:
    assert scenario.job is not None
    scenario.job.cancel()
    scenario.scheduler.tick()


@then("the author cleanup ran once")
def cleanup_ran(scenario: SchedulingScenario) -> None:
    assert scenario.events == ["cleanup"]


@then("the job is cancelled")
def job_is_cancelled(scenario: SchedulingScenario) -> None:
    assert scenario.job is not None
    assert scenario.job.state is JobState.CANCELLED


@given("a job still waiting on an unresolved worker handoff", target_fixture="scenario")
def job_awaiting_worker() -> SchedulingScenario:
    scenario = scheduling_scenario()
    scenario.handoff = Handoff()

    async def body() -> None:
        await scenario.handoff

    scenario.job = scenario.scheduler.submit(body())
    scenario.scheduler.tick()
    return scenario


@when("the host asks the scheduler to quiesce")
def quiesce(scenario: SchedulingScenario) -> None:
    scenario.outcome = scenario.scheduler.quiesce(max_ticks=4)
    assert scenario.outcome is not None


@then("the replacement is refused with that job named")
def replacement_refused(scenario: SchedulingScenario) -> None:
    assert scenario.outcome.refused is True
    assert scenario.outcome.blockers == (
        f"job {scenario.job.id} is waiting on an unresolved worker handoff",
    )


@then("the job is still waiting rather than disposed")
def job_still_waiting(scenario: SchedulingScenario) -> None:
    assert scenario.job.state is JobState.WAITING
    assert tuple(scenario.scheduler.jobs) == (scenario.job.id,)


@when("the owning scope is disposed and the worker reports afterwards")
def dispose_then_report(scenario: SchedulingScenario) -> None:
    scenario.scope.close()
    scenario.handoff.resolve("too late")
    scenario.scheduler.tick()


@then("the late report is counted as dropped")
def late_report_dropped(scenario: SchedulingScenario) -> None:
    assert scenario.scheduler.dropped_reports == 1
    assert scenario.handoff.owner is None


@then("the job body never resumes")
def job_never_resumes(scenario: SchedulingScenario) -> None:
    assert scenario.events == []
    assert scenario.job.state is JobState.FAILED
    assert scenario.scheduler.jobs == {}


@given(
    "a job that raises a host interrupt while it is stepped",
    target_fixture="scenario",
)
def job_raising_host_interrupt() -> SchedulingScenario:
    scenario = scheduling_scenario()

    async def body() -> None:
        scenario.events.append("author code")
        raise KeyboardInterrupt

    scenario.job = scenario.scheduler.submit(body())
    return scenario


@when("the host advances the scheduler and control flow escapes")
def advance_letting_control_flow_escape(scenario: SchedulingScenario) -> None:
    try:
        scenario.scheduler.tick()
    except BaseException as error:  # noqa: BLE001 - this step observes what escapes
        scenario.raised = error


@then("the interrupt reaches the caller of the tick")
def interrupt_reaches_the_host(scenario: SchedulingScenario) -> None:
    assert isinstance(scenario.raised, KeyboardInterrupt)


@then("the job reports that interrupt as its error")
def job_reports_the_interrupt(scenario: SchedulingScenario) -> None:
    assert scenario.job is not None
    assert scenario.job.state is JobState.FAILED
    assert isinstance(scenario.job.error, KeyboardInterrupt)


@then("the scheduler holds no active jobs")
def scheduler_holds_no_active_jobs(scenario: SchedulingScenario) -> None:
    assert scenario.scheduler.jobs == {}


@given(
    "a job that disposes its scope and then returns a value",
    target_fixture="scenario",
)
def job_disposing_its_own_scope() -> SchedulingScenario:
    scenario = scheduling_scenario()

    async def body() -> str:
        scenario.scope.close()
        return "value the host will not see"

    scenario.job = scenario.scheduler.submit(body())
    return scenario


@when("the host advances the scheduler")
def advance_once(scenario: SchedulingScenario) -> None:
    scenario.scheduler.tick()


@then("the job is failed by the closed scope")
def job_failed_by_closed_scope(scenario: SchedulingScenario) -> None:
    assert scenario.job is not None
    assert scenario.job.state is JobState.FAILED
    assert isinstance(scenario.job.error, QgisSdkScopeClosedError)
    assert scenario.job.awaiting is None
    assert scenario.job.result is None

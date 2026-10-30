"""Scoped-jobs scenarios against the public ``JobService`` / ``JobHandle`` API.

Every step goes through what a plugin author or a host sees: ``bind``,
``delay``, the handle, its subscriptions, ``tick`` and the owning scopes. The
worker is the in-memory ``FakeWorkers`` so a scenario decides when work
reports.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import pytest
from pytest_bdd import given, parsers, scenarios, then, when
from qgis_sdk.core import ResourceScope, WorkerContext
from qgis_sdk.jobs import JobHandle, JobService, JobStatus, JobSubscription, job
from qgis_sdk.models import QgisSdkJobWaitRefusedError
from qgis_sdk.testing import FakeWorkers

scenarios("features/scoped_jobs.feature")


@dataclass(frozen=True)
class SumResult:
    total: int


AUTHOR_CODE_RAN: list[str] = []


@job(id="bdd.sum", title="Sum two numbers")
def add(ctx: WorkerContext, a: int, b: int) -> SumResult:
    AUTHOR_CODE_RAN.append("ran")
    return SumResult(a + b)


@dataclass
class JobsScenario:
    plugin: ResourceScope
    view: ResourceScope
    workers: FakeWorkers
    jobs: JobService
    view_jobs: JobService
    handle: JobHandle | None = None
    events: list[tuple[str, object]] = field(default_factory=list)
    events_at_disposal: int | None = None
    late: list[object] = field(default_factory=list)
    late_subscription: JobSubscription | None = None
    nested_ticks: list[int] = field(default_factory=list)
    reentering: JobHandle | None = None
    hidden: bool = False

    def subscribe(self, handle: JobHandle) -> None:
        handle.on_progress(lambda fraction: self.events.append(("progress", fraction)))
        handle.on_success(lambda result: self.events.append(("success", result)))
        handle.on_failure(lambda error: self.events.append(("failure", error)))
        handle.on_cancelled(lambda: self.events.append(("cancelled", None)))

    def submit(
        self, service: JobService, function: Callable[..., object], a: int, b: int
    ) -> JobHandle:
        self.handle = service.bind(function).delay(a=a, b=b)
        self.subscribe(self.handle)
        return self.handle


def _scenario(*, gui_thread: bool) -> JobsScenario:
    AUTHOR_CODE_RAN.clear()
    plugin = ResourceScope()
    workers = FakeWorkers()
    jobs = JobService(plugin, workers=workers, gui_thread=lambda: gui_thread)
    view = plugin.child()
    return JobsScenario(plugin, view, workers, jobs, jobs.scoped(view))


@pytest.fixture()
def scenario_cleanup():
    scenarios_made: list[JobsScenario] = []
    yield scenarios_made
    for made in scenarios_made:
        if not made.plugin.closed:
            made.plugin.close()


@given("a plugin with a view and a worker pool", target_fixture="scenario")
def plugin_with_view(scenario_cleanup: list[JobsScenario]) -> JobsScenario:
    made = _scenario(gui_thread=False)
    scenario_cleanup.append(made)
    return made


@given(
    "a plugin with a view and a worker pool on the GUI thread",
    target_fixture="scenario",
)
def plugin_with_view_on_gui_thread(
    scenario_cleanup: list[JobsScenario],
) -> JobsScenario:
    made = _scenario(gui_thread=True)
    scenario_cleanup.append(made)
    return made


# -- when


@when(parsers.parse("the view binds the sum job and delays it with {a:d} and {b:d}"))
def view_delays_sum(scenario: JobsScenario, a: int, b: int) -> None:
    scenario.submit(scenario.view_jobs, add, a, b)


@when("the view delays the sum job through its parent service")
def view_delays_through_parent(scenario: JobsScenario) -> None:
    parent = scenario.view_jobs.parent
    assert parent is scenario.jobs
    scenario.submit(parent, add, 1, 2)


@when("the view delays a job that is cancelled while it runs and ignores it")
def view_delays_stubborn(scenario: JobsScenario) -> None:
    @job(id="bdd.stubborn", title="Ignores a request")
    def stubborn(ctx: WorkerContext, a: int, b: int) -> SumResult:
        assert scenario.handle is not None
        scenario.handle.cancel()
        # The body sees the request and does not stop: the job still ends
        # cancelled, because a request that arrives before the worker reports
        # settles at the report (decision-65 keeps decision-21's safety rule).
        assert ctx.cancellation.is_cancelled()
        return SumResult(a + b)

    scenario.submit(scenario.view_jobs, stubborn, 1, 2)


@when("the view delays a job that re-enters the tick while it runs")
def view_delays_reentering(scenario: JobsScenario) -> None:
    @job(id="bdd.reentrant", title="Opens a modal dialog while running")
    def reentrant(ctx: WorkerContext, a: int, b: int) -> SumResult:
        scenario.nested_ticks.append(scenario.jobs.tick())
        return SumResult(a + b)

    scenario.reentering = scenario.view_jobs.bind(reentrant).delay(a=0, b=0)


@when("the host ticks once")
def host_ticks(scenario: JobsScenario) -> None:
    scenario.jobs.tick()


@when("the worker runs the job and the host ticks once")
def worker_runs_then_tick(scenario: JobsScenario) -> None:
    scenario.workers.run_all()
    scenario.jobs.tick()


@when("the handle is cancelled")
def handle_cancelled(scenario: JobsScenario) -> None:
    assert scenario.handle is not None
    scenario.handle.cancel()


@when("a late subscriber attaches to success")
def late_subscriber(scenario: JobsScenario) -> None:
    assert scenario.handle is not None
    scenario.late_subscription = scenario.handle.on_success(scenario.late.append)


@when("the view is disposed")
def view_disposed(scenario: JobsScenario) -> None:
    scenario.view.close()
    scenario.events_at_disposal = len(scenario.events)


@when("the view is hidden")
def view_hidden(scenario: JobsScenario) -> None:
    scenario.hidden = True  # the host hides the widget; the scope is untouched


# -- then


@then("no author code has run")
def no_author_code(scenario: JobsScenario) -> None:
    assert AUTHOR_CODE_RAN == []


@then(parsers.parse("the handle is queued with attempt {attempt:d}"))
def handle_queued(scenario: JobsScenario, attempt: int) -> None:
    assert scenario.handle is not None
    assert scenario.handle.status is JobStatus.QUEUED
    assert scenario.handle.attempt == attempt


@then(parsers.parse("the handle succeeded with total {total:d}"))
def handle_succeeded(scenario: JobsScenario, total: int) -> None:
    assert scenario.handle is not None
    assert scenario.handle.status is JobStatus.SUCCEEDED
    assert scenario.handle.result == SumResult(total)


@then("the handle is cancelled with cancellation requested")
def handle_cancelled_requested(scenario: JobsScenario) -> None:
    assert scenario.handle is not None
    assert scenario.handle.status is JobStatus.CANCELLED
    assert scenario.handle.cancel_requested is True


@then("the handle is running with no cancellation requested")
def handle_running_open(scenario: JobsScenario) -> None:
    assert scenario.handle is not None
    assert scenario.handle.status is JobStatus.RUNNING
    assert scenario.handle.cancel_requested is False


@then("the handle is still running with cancellation requested")
def handle_running_requested(scenario: JobsScenario) -> None:
    assert scenario.handle is not None
    assert scenario.handle.status is JobStatus.RUNNING
    assert scenario.handle.cancel_requested is True


@then("the handle is cancelled")
def handle_cancelled_state(scenario: JobsScenario) -> None:
    assert scenario.handle is not None
    assert scenario.handle.status is JobStatus.CANCELLED


@then("the cancelled subscriber was told exactly once")
def cancelled_once(scenario: JobsScenario) -> None:
    terminal = [kind for kind, _ in scenario.events if kind != "progress"]
    assert terminal == ["cancelled"]


@then(parsers.parse("the late subscriber heard total {total:d} exactly once"))
def late_heard(scenario: JobsScenario, total: int) -> None:
    assert scenario.late == [SumResult(total)]


@then("the late subscription is already complete")
def late_complete(scenario: JobsScenario) -> None:
    assert scenario.late_subscription is not None
    assert scenario.late_subscription.active is False


@then("the handle has its owner closed and cancellation requested")
def owner_closed_requested(scenario: JobsScenario) -> None:
    assert scenario.handle is not None
    assert scenario.handle.owner_closed is True
    assert scenario.handle.cancel_requested is True


@then("the handle has its owner open and no cancellation requested")
def owner_open(scenario: JobsScenario) -> None:
    assert scenario.handle is not None
    assert scenario.handle.owner_closed is False
    assert scenario.handle.cancel_requested is False


@then("the view's subscribers heard nothing after disposal")
def nothing_after_disposal(scenario: JobsScenario) -> None:
    assert scenario.events_at_disposal is not None
    assert len(scenario.events) == scenario.events_at_disposal


@then(parsers.parse("the view's success subscriber heard total {total:d}"))
def view_heard_success(scenario: JobsScenario, total: int) -> None:
    assert scenario.hidden is True
    assert ("success", SumResult(total)) in scenario.events


@then(parsers.parse("waiting on the handle is refused with code {code}"))
def wait_refused(scenario: JobsScenario, code: str) -> None:
    assert scenario.handle is not None
    with pytest.raises(QgisSdkJobWaitRefusedError) as info:
        scenario.handle.get(timeout=0.01)
    assert info.value.code == code


@then(
    parsers.parse(
        "the nested tick returned {steps:d} and the re-entering job succeeded"
    )
)
def nested_tick_ignored(scenario: JobsScenario, steps: int) -> None:
    assert scenario.nested_ticks == [steps]
    assert scenario.reentering is not None
    assert scenario.reentering.status is JobStatus.SUCCEEDED

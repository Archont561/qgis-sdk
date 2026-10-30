"""Scoped local jobs: worker-first execution, delivery and ownership (decisions 13, 21, 65).

Every rule here is pinned without Qt: "the GUI thread" is whichever thread the
test built the service on, the worker pool is a fake whose completions the test
releases, and the body is never called by *this* thread. Since 0.9.0 a job body
runs in its entirety on a worker, so a test drives a job in three moves -
``jobs.tick()`` submits, ``workers.run_all()`` is the worker, ``jobs.tick()``
delivers - which the ``drive`` fixture does at once. The native file proves the
same service over a real ``QThreadPool`` and a real event loop, and
``test_jobs_worker_first.py`` holds the contract's own evidence.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import ClassVar

import pytest
from qgis_sdk.core import JobContext, ResourceScope, WorkerContext
from qgis_sdk.declarations import QgisSdkDeclarationError
from qgis_sdk.jobs import (
    JobDescription,
    JobHandle,
    JobService,
    JobStatus,
    JobSubscription,
    describe_job,
    job,
)
from qgis_sdk.models import (
    QgisSdkJobCancelledError,
    QgisSdkJobNotSettledError,
    QgisSdkJobPrerequisiteError,
    QgisSdkJobRejectedError,
    QgisSdkJobWaitRefusedError,
    QgisSdkScopeClosedError,
    QgisSdkUnsupportedCapabilityError,
)
from qgis_sdk.testing import FakeWorkers, ThreadWorkers

# -- authoring surface ----------------------------------------------------------


@dataclass(frozen=True)
class SumResult:
    total: int


@job(id="demo.sum", title="Sum two numbers")
def add(ctx: WorkerContext, a: int, b: int) -> SumResult:
    ctx.progress.report(0.5)
    return SumResult(total=a + b)


@job(id="demo.plain", title="Sum two numbers quietly")
def plain_add(ctx: WorkerContext, a: int, b: int) -> SumResult:
    return SumResult(total=a + b)


def test_a_job_function_is_described_from_its_signature() -> None:
    description = describe_job(add)

    assert isinstance(description, JobDescription)
    assert description.id == "demo.sum"
    assert description.title == "Sum two numbers"
    assert description.parameters == ("a", "b")
    assert description.required == ("a", "b")
    assert description.annotations == {"a": int, "b": int}
    assert description.result_type is SumResult
    assert description.inputs_schema["properties"]["a"]["type"] == "integer"
    assert description.result_schema["properties"]["total"]["type"] == "integer"
    # A body runs on a worker, which runs no event loop, so no job is a
    # coroutine function (decision-65). The field stays in the description for
    # a reader that still parses the 0.8 transport.
    assert description.asynchronous is False
    assert description.to_dict()["result"]["type"] == "SumResult"
    assert description.to_dict()["inputs"] == description.inputs_schema


def _no_context(a: int) -> SumResult:
    return SumResult(a)


def _untyped_context(ctx, a: int) -> SumResult:  # type: ignore[no-untyped-def]
    return SumResult(a)


def _untyped_parameter(ctx: WorkerContext, a) -> SumResult:  # type: ignore[no-untyped-def]
    return SumResult(a)


def _no_result(ctx: WorkerContext, a: int):  # type: ignore[no-untyped-def]
    return None


def _generator(ctx: WorkerContext, a: int) -> SumResult:  # type: ignore[misc]
    yield SumResult(a)


def _plain(ctx: WorkerContext, a: int) -> SumResult:
    return SumResult(a)


async def _coroutine(ctx: WorkerContext, a: int) -> SumResult:
    return SumResult(a)


def _driving_thread_context(ctx: JobContext, a: int) -> SumResult:
    return SumResult(a)


def _decorated(fn: Callable[..., object]) -> Callable[..., object]:
    return job(id=f"demo.refused.{fn.__name__}", title=fn.__name__)(fn)


@pytest.mark.parametrize(
    ("declare", "problem"),
    [
        pytest.param(lambda: _decorated(_no_context), "WorkerContext", id="no context"),
        pytest.param(
            lambda: _decorated(_untyped_context), "WorkerContext", id="untyped context"
        ),
        pytest.param(
            lambda: _decorated(_untyped_parameter),
            "unsupported annotation",
            id="untyped parameter",
        ),
        pytest.param(lambda: _decorated(_no_result), "result", id="no declared result"),
        pytest.param(lambda: _decorated(_generator), "generator", id="generator"),
        pytest.param(lambda: _plain, "@job", id="not decorated"),
        pytest.param(
            lambda: job(id="demo.twice", title="Twice")(add),
            "duplicate",
            id="decorated twice",
        ),
    ],
)
def test_a_declaration_that_cannot_be_described_is_refused(
    declare: Callable[[], Callable[..., object]], problem: str
) -> None:
    with pytest.raises(QgisSdkDeclarationError, match=problem):
        describe_job(declare())


def test_an_async_job_is_refused_with_the_migration_it_needs() -> None:
    """AC 5: no ``async def`` job survives into 0.9.0 with the old semantics."""
    with pytest.raises(QgisSdkDeclarationError, match="runs no event loop") as info:
        describe_job(_decorated(_coroutine))

    message = str(info.value)
    assert "plain `def`" in message
    assert "subscriber" in message  # where the GUI work goes instead


def test_a_jobcontext_annotation_is_refused_with_the_migration_it_needs() -> None:
    """A driving-thread context is an unsupported declaration, named as such."""
    with pytest.raises(QgisSdkDeclarationError, match="WorkerContext") as info:
        describe_job(_decorated(_driving_thread_context))

    assert "driving thread" in str(info.value)


# -- fixtures -------------------------------------------------------------------


class _Recorder:
    """What one subscriber saw, in order, for assertions on delivery."""

    def __init__(self) -> None:
        self.events: list[tuple[str, object]] = []

    def progress(self, fraction: float) -> None:
        self.events.append(("progress", fraction))

    def success(self, result: object) -> None:
        self.events.append(("success", result))

    def failure(self, error: BaseException) -> None:
        self.events.append(("failure", type(error).__name__))

    def cancelled(self) -> None:
        self.events.append(("cancelled", None))

    def subscribe_all(self, handle: JobHandle) -> list[JobSubscription]:
        return [
            handle.on_progress(self.progress),
            handle.on_success(self.success),
            handle.on_failure(self.failure),
            handle.on_cancelled(self.cancelled),
        ]

    @property
    def terminal(self) -> list[tuple[str, object]]:
        return [event for event in self.events if event[0] != "progress"]


@pytest.fixture()
def plugin_scope() -> Iterator[ResourceScope]:
    scope = ResourceScope()
    yield scope
    # Unload at the end of every test, as a plugin would: a job the test never
    # drove is abandoned here instead of leaking into the next test.
    scope.close()


@pytest.fixture()
def workers() -> FakeWorkers:
    return FakeWorkers()


@pytest.fixture()
def jobs(plugin_scope: ResourceScope, workers: FakeWorkers) -> JobService:
    return JobService(plugin_scope, workers=workers, gui_thread=lambda: False)


@pytest.fixture()
def drive(jobs: JobService, workers: FakeWorkers) -> Callable[[], None]:
    """Submit, let the worker run the body, deliver: one job, one round trip."""

    def run() -> None:
        jobs.tick()
        workers.run_all()
        jobs.tick()

    return run


@pytest.fixture()
def submit(jobs: JobService) -> Callable[[Callable[..., object]], JobHandle]:
    """Submit and stop: the body is on the worker and has not run yet."""

    def start(function: Callable[..., object], /, **arguments: object) -> JobHandle:
        handle = jobs.bind(function).delay(**arguments)
        jobs.tick()
        return handle

    return start


@pytest.fixture()
def view_scope(plugin_scope: ResourceScope) -> ResourceScope:
    return plugin_scope.child()


@pytest.fixture()
def view_jobs(jobs: JobService, view_scope: ResourceScope) -> JobService:
    return jobs.scoped(view_scope)


# -- submission and typed handles -----------------------------------------------


def test_bind_then_delay_submits_without_running_author_code(
    jobs: JobService, drive: Callable[[], None]
) -> None:
    called: list[WorkerContext] = []

    @job(id="demo.spy", title="Spy")
    def spy(ctx: WorkerContext, a: int, b: int) -> SumResult:
        called.append(ctx)
        return SumResult(a)

    handle = jobs.bind(spy).delay(a=1, b=2)

    assert handle.status is JobStatus.QUEUED
    assert handle.id == "demo.spy#1"
    assert handle.attempt == 1
    assert handle.description.id == "demo.spy"
    assert called == []  # nothing runs on submission
    jobs.tick()
    assert called == []  # the first tick only hands the body to a worker
    assert handle.status is JobStatus.RUNNING
    drive()
    assert len(called) == 1
    assert handle.status is JobStatus.SUCCEEDED
    assert handle.result == SumResult(1)


def test_each_submission_has_its_own_logical_id_and_a_first_attempt(
    jobs: JobService, drive: Callable[[], None]
) -> None:
    bound = jobs.bind(add)
    first = bound.delay(a=1, b=1)
    second = bound.delay(a=2, b=2)

    assert (first.id, second.id) == ("demo.sum#1", "demo.sum#2")
    assert (first.attempt, second.attempt) == (1, 1)
    drive()
    assert (first.result.total, second.result.total) == (2, 4)


def test_arguments_of_the_wrong_type_are_rejected_before_anything_runs(
    jobs: JobService, workers: FakeWorkers
) -> None:
    with pytest.raises(QgisSdkJobRejectedError, match="a must be int") as info:
        jobs.bind(add).delay(a="1", b=2)  # type: ignore[arg-type]
    assert info.value.code == "job_rejected"
    assert info.value.job_id == "demo.sum"
    assert jobs.active == ()
    assert workers.pending == 0  # nothing reached a worker


def test_a_host_without_a_worker_backend_refuses_the_submission(
    plugin_scope: ResourceScope,
) -> None:
    """AC 1: no backend is a refusal, never a quiet return to the old model."""
    jobs = JobService(plugin_scope, gui_thread=lambda: False)  # no workers

    with pytest.raises(QgisSdkJobRejectedError, match="no worker backend") as info:
        jobs.bind(add).delay(a=1, b=2)

    assert "never runs on the driving thread" in str(info.value)
    assert jobs.active == ()
    assert jobs.tick() == 0


def test_binding_an_undeclared_function_fails_at_bind_time(
    jobs: JobService,
) -> None:
    with pytest.raises(QgisSdkDeclarationError):
        jobs.bind(_plain)


def test_a_result_of_the_wrong_type_fails_the_job(
    jobs: JobService, drive: Callable[[], None]
) -> None:
    @job(id="demo.liar", title="Liar")
    def liar(ctx: WorkerContext, a: int, b: int) -> SumResult:
        return 3  # type: ignore[return-value]

    handle = jobs.bind(liar).delay(a=1, b=2)
    drive()

    assert handle.status is JobStatus.FAILED
    assert isinstance(handle.error, QgisSdkDeclarationError)
    assert "SumResult" in str(handle.error)


def test_a_failure_in_the_body_is_the_job_s_outcome_not_the_tick_s(
    jobs: JobService, drive: Callable[[], None]
) -> None:
    @job(id="demo.boom", title="Boom")
    def boom(ctx: WorkerContext, a: int, b: int) -> SumResult:
        raise ValueError("no")

    handle = jobs.bind(boom).delay(a=1, b=2)
    recorder = _Recorder()
    recorder.subscribe_all(handle)
    drive()

    assert handle.status is JobStatus.FAILED
    assert isinstance(handle.error, ValueError)
    assert recorder.terminal == [("failure", "ValueError")]
    with pytest.raises(ValueError, match="no"):
        _ = handle.result  # the failure itself, as get() would raise it


def test_the_result_is_not_available_before_the_job_succeeds(
    jobs: JobService,
) -> None:
    handle = jobs.bind(add).delay(a=1, b=2)
    with pytest.raises(QgisSdkJobNotSettledError, match="queued") as info:
        _ = handle.result
    assert info.value.code == "job_not_settled"
    assert handle.error is None


def test_a_service_over_a_closed_scope_refuses_to_submit(
    jobs: JobService, plugin_scope: ResourceScope
) -> None:
    bound = jobs.bind(add)
    plugin_scope.close()
    with pytest.raises(QgisSdkScopeClosedError):
        bound.delay(a=1, b=2)
    with pytest.raises(QgisSdkScopeClosedError):
        jobs.bind(add)


# -- progress, success, failure, cancellation subscriptions ---------------------


def test_callbacks_fire_on_the_tick_in_order_and_each_terminal_once(
    jobs: JobService, drive: Callable[[], None]
) -> None:
    handle = jobs.bind(add).delay(a=2, b=3)
    recorder = _Recorder()
    recorder.subscribe_all(handle)

    assert recorder.events == []
    drive()
    drive()  # a settled job delivers nothing a second time

    assert recorder.events == [("progress", 0.5), ("success", SumResult(5))]
    assert handle.progress == 0.5


def test_a_subscription_is_disposable_and_disposal_is_idempotent(
    jobs: JobService, drive: Callable[[], None]
) -> None:
    handle = jobs.bind(add).delay(a=2, b=3)
    recorder = _Recorder()
    subscription = handle.on_success(recorder.success)
    assert subscription.active is True

    assert subscription.dispose() is True
    assert subscription.dispose() is False
    assert subscription.active is False
    drive()
    assert recorder.events == []


def test_a_late_subscriber_replays_the_current_state_once(
    jobs: JobService, drive: Callable[[], None]
) -> None:
    handle = jobs.bind(add).delay(a=2, b=3)
    drive()
    assert handle.status is JobStatus.SUCCEEDED

    recorder = _Recorder()
    subscriptions = recorder.subscribe_all(handle)
    # The replay is synchronous: a UI that subscribes after the fact draws now.
    assert recorder.events == [("progress", 0.5), ("success", SumResult(5))]
    # A terminal replay completes the subscription; progress stays open for
    # nothing more, so it is complete as well. Failure/cancelled never fire.
    assert [subscription.active for subscription in subscriptions] == [
        False,
        False,
        False,
        False,
    ]
    drive()
    assert len(recorder.events) == 2


def test_a_late_progress_subscriber_without_any_report_gets_nothing(
    jobs: JobService, drive: Callable[[], None]
) -> None:
    @job(id="demo.quiet", title="Quiet")
    def quiet(ctx: WorkerContext, a: int, b: int) -> SumResult:
        return SumResult(a)

    handle = jobs.bind(quiet).delay(a=1, b=2)
    recorder = _Recorder()
    handle.on_progress(recorder.progress)
    drive()
    handle.on_progress(recorder.progress)
    assert recorder.events == []
    assert handle.progress is None


def test_progress_reported_on_the_worker_is_delivered_on_the_tick(
    jobs: JobService,
    workers: FakeWorkers,
) -> None:
    """The worker reports; nothing reaches a subscriber until the driving tick."""
    events_seen_from_worker: list[int] = []

    @job(id="demo.worker-progress", title="Worker progress")
    def worker_progress(ctx: WorkerContext, a: int, b: int) -> SumResult:
        for step in (0.25, 0.5, 0.75):
            ctx.progress.report(step)
        events_seen_from_worker.append(len(recorder.events))
        return SumResult(a)

    recorder = _Recorder()
    handle = jobs.bind(worker_progress).delay(a=7, b=0)
    handle.on_progress(recorder.progress)
    jobs.tick()
    assert handle.status is JobStatus.RUNNING

    thread = threading.Thread(target=workers.run_all)
    thread.start()
    thread.join()
    # Nothing reached the subscriber from the worker thread...
    assert events_seen_from_worker == [0]
    assert recorder.events == []
    jobs.tick()
    # ...and the tick coalesced the burst into the latest fraction.
    assert recorder.events == [("progress", 0.75)]
    assert handle.status is JobStatus.SUCCEEDED


def test_a_progress_fraction_outside_the_unit_interval_is_refused(
    jobs: JobService, drive: Callable[[], None]
) -> None:
    @job(id="demo.overflow", title="Overflow")
    def overflow(ctx: WorkerContext, a: int, b: int) -> SumResult:
        ctx.progress.report(1.5)
        return SumResult(0)

    handle = jobs.bind(overflow).delay(a=0, b=0)
    drive()
    assert handle.status is JobStatus.FAILED
    assert isinstance(handle.error, ValueError)


def test_a_failing_callback_is_detached_and_reported_not_raised(
    jobs: JobService, drive: Callable[[], None]
) -> None:
    handle = jobs.bind(add).delay(a=2, b=3)
    recorder = _Recorder()

    def explode(result: object) -> None:
        raise RuntimeError("ui gone")

    broken = handle.on_success(explode)
    handle.on_success(recorder.success)
    drive()

    assert recorder.events == [("success", SumResult(5))]
    assert broken.active is False
    assert len(jobs.faults) == 1
    fault = jobs.faults[0]
    assert fault.job_id == "demo.sum#1"
    assert fault.event == "success"
    assert isinstance(fault.error, RuntimeError)


def test_a_fault_hook_hears_about_failing_callbacks(
    plugin_scope: ResourceScope, workers: FakeWorkers
) -> None:
    heard = []
    jobs = JobService(
        plugin_scope, workers=workers, on_fault=heard.append, gui_thread=lambda: False
    )
    handle = jobs.bind(add).delay(a=2, b=3)
    handle.on_progress(lambda fraction: 1 / 0)
    jobs.tick()
    workers.run_all()
    jobs.tick()
    assert [fault.event for fault in heard] == ["progress"]


# -- cancellation ---------------------------------------------------------------


def test_cancel_before_the_worker_starts_settles_as_cancelled(
    jobs: JobService,
) -> None:
    called = []

    @job(id="demo.never", title="Never runs")
    def never(ctx: WorkerContext, a: int, b: int) -> SumResult:
        called.append(ctx)
        return SumResult(0)

    handle = jobs.bind(never).delay(a=0, b=0)
    recorder = _Recorder()
    recorder.subscribe_all(handle)

    assert handle.cancel() is True
    assert handle.cancel_requested is True
    assert handle.status is JobStatus.QUEUED  # a request, not a state
    jobs.tick()

    assert handle.status is JobStatus.CANCELLED
    assert called == []
    assert recorder.terminal == [("cancelled", None)]
    assert handle.cancel() is False


def test_cancellation_is_a_request_until_the_worker_acknowledges_it(
    jobs: JobService, workers: FakeWorkers, submit: Callable[..., JobHandle]
) -> None:
    handle = submit(plain_add, a=1, b=2)
    recorder = _Recorder()
    recorder.subscribe_all(handle)
    assert handle.status is JobStatus.RUNNING
    assert workers.pending == 1

    assert handle.cancel() is True
    jobs.tick()
    # Still running: the worker has not reported, so nothing can be acknowledged.
    assert handle.status is JobStatus.RUNNING
    assert handle.cancel_requested is True
    assert recorder.terminal == []
    assert workers.cancelled == 1  # the backend was told, as a courtesy

    workers.run_all()
    jobs.tick()
    assert handle.status is JobStatus.CANCELLED
    assert recorder.terminal == [("cancelled", None)]


def test_the_worker_sees_the_request_through_its_context(
    jobs: JobService, workers: FakeWorkers, submit: Callable[..., JobHandle]
) -> None:
    """The body polls ``ctx.cancellation``; it is the signal, not a kill."""
    seen: list[bool] = []

    @job(id="demo.polls", title="Polls")
    def polls(ctx: WorkerContext, a: int, b: int) -> SumResult:
        seen.append(ctx.cancellation.is_cancelled())
        return SumResult(a)

    handle = submit(polls, a=1, b=2)
    assert seen == []  # the body has not started
    handle.cancel()
    workers.run_all()
    jobs.tick()

    assert seen == [True]
    assert handle.status is JobStatus.CANCELLED


def test_stuck_work_stays_running_and_is_named_as_a_blocker(
    jobs: JobService, workers: FakeWorkers, submit: Callable[..., JobHandle]
) -> None:
    handle = submit(plain_add, a=1, b=2)
    handle.cancel()
    for _ in range(5):
        jobs.tick()

    assert handle.status is JobStatus.RUNNING
    assert handle.cancel_requested is True
    outcome = jobs.quiesce(max_ticks=3)
    assert outcome.refused is True
    assert outcome.blockers == (
        f"job {handle.id} is waiting on an unresolved worker handoff",
    )
    assert workers.pending == 1


# -- ownership: views, hiding, plugins ------------------------------------------


def test_a_view_owned_job_is_detached_and_asked_to_stop_when_the_view_closes(
    jobs: JobService,
    view_jobs: JobService,
    view_scope: ResourceScope,
    workers: FakeWorkers,
    submit: Callable[..., JobHandle],
) -> None:
    handle = view_jobs.bind(add).delay(a=1, b=2)
    recorder = _Recorder()
    recorder.subscribe_all(handle)
    jobs.tick()

    view_scope.close()

    # Detached immediately, cancellation requested, but the plugin's scheduler
    # keeps the job until the worker reports: nothing is torn down under it.
    assert handle.cancel_requested is True
    assert handle.status is JobStatus.RUNNING
    assert handle.owner_closed is True
    workers.run_all()
    jobs.tick()
    assert handle.status is JobStatus.CANCELLED
    assert recorder.events == []  # no callback reached the closed view
    with pytest.raises(QgisSdkScopeClosedError):
        handle.on_cancelled(recorder.cancelled)


def test_hiding_a_view_is_not_disposal(
    jobs: JobService, view_jobs: JobService, workers: FakeWorkers
) -> None:
    class Dock:
        hidden = False

        def hide(self) -> None:
            self.hidden = True

    dock = Dock()
    handle = view_jobs.bind(add).delay(a=1, b=2)
    recorder = _Recorder()
    recorder.subscribe_all(handle)
    jobs.tick()
    dock.hide()  # the host hides the widget; the scope is untouched
    workers.run_all()
    jobs.tick()

    assert dock.hidden is True
    assert handle.cancel_requested is False
    assert handle.status is JobStatus.SUCCEEDED
    assert recorder.terminal == [("success", SumResult(3))]


def test_plugin_lifetime_work_is_explicit_and_outlives_the_view(
    jobs: JobService,
    view_jobs: JobService,
    view_scope: ResourceScope,
    workers: FakeWorkers,
) -> None:
    assert view_jobs.parent is jobs
    assert jobs.parent is None
    handle = view_jobs.parent.bind(add).delay(a=1, b=2)
    view_recorder = _Recorder()
    plugin_recorder = _Recorder()
    # The view's callbacks on a plugin-owned job are owned by the view.
    handle.on_success(view_recorder.success, owner=view_scope)
    handle.on_success(plugin_recorder.success)
    jobs.tick()

    view_scope.close()
    workers.run_all()
    jobs.tick()

    assert handle.cancel_requested is False
    assert handle.status is JobStatus.SUCCEEDED
    assert view_recorder.events == []
    assert plugin_recorder.events == [("success", SumResult(3))]


def test_a_finished_job_does_not_replay_into_a_view_closed_afterwards(
    jobs: JobService,
    view_jobs: JobService,
    view_scope: ResourceScope,
    drive: Callable[[], None],
) -> None:
    handle = view_jobs.bind(add).delay(a=1, b=2)
    drive()
    assert handle.status is JobStatus.SUCCEEDED
    assert handle.owner_closed is False

    view_scope.close()

    assert handle.owner_closed is True
    with pytest.raises(QgisSdkScopeClosedError):
        handle.on_success(lambda result: pytest.fail("replayed into a closed view"))
    assert handle.result == SumResult(3)  # the handle itself still answers


def test_a_subscription_owner_must_be_open(
    jobs: JobService, view_scope: ResourceScope
) -> None:
    handle = jobs.bind(add).delay(a=1, b=2)
    view_scope.close()
    with pytest.raises(QgisSdkScopeClosedError):
        handle.on_success(lambda result: None, owner=view_scope)


def test_unloading_the_plugin_abandons_everything_without_callbacks(
    jobs: JobService,
    view_jobs: JobService,
    plugin_scope: ResourceScope,
    workers: FakeWorkers,
) -> None:
    running = view_jobs.bind(add).delay(a=1, b=2)
    recorder = _Recorder()
    recorder.subscribe_all(running)
    jobs.tick()
    queued = jobs.bind(add).delay(a=1, b=2)
    recorder.subscribe_all(queued)

    plugin_scope.close()

    assert running.status is JobStatus.CANCELLED  # the view asked first
    assert queued.status is JobStatus.FAILED
    assert isinstance(queued.error, QgisSdkScopeClosedError)
    assert recorder.terminal == []
    assert jobs.active == ()
    workers.run_all()  # a late worker report reaches nobody
    assert jobs.tick() == 0
    assert recorder.terminal == []


def test_a_settled_job_leaves_the_active_set_and_its_attempt_scope_closes(
    jobs: JobService, drive: Callable[[], None]
) -> None:
    closed = []
    scopes: list[ResourceScope] = []

    @job(id="demo.scoped", title="Scoped")
    def scoped(ctx: WorkerContext, a: int, b: int) -> SumResult:
        return SumResult(0)

    handle = jobs.bind(scoped).delay(a=0, b=0)
    assert jobs.active == (handle,)
    scopes.append(handle._attempt.scope)  # the attempt's own scope
    drive()
    assert jobs.active == ()
    assert scopes[0].closed is True
    assert closed == []


# -- the worker context ----------------------------------------------------------


@job(id="demo.offline", title="Asks for the project")
def needs_project(ctx: WorkerContext, a: int, b: int) -> SumResult:
    _ = ctx.project
    return SumResult(0)


@pytest.mark.parametrize(
    ("fn", "capability"),
    [
        pytest.param(needs_project, "project", id="project"),
    ],
)
def test_the_worker_context_refuses_a_driving_thread_capability(
    jobs: JobService, drive: Callable[[], None], fn, capability: str
) -> None:
    """AC 2: the refusal names the capability *and* why a worker cannot have it."""
    handle = jobs.bind(fn).delay(a=1, b=2)
    drive()

    assert handle.status is JobStatus.FAILED
    assert isinstance(handle.error, QgisSdkUnsupportedCapabilityError)
    assert handle.error.capability == capability
    assert "driving thread" in str(handle.error)


def test_a_worker_failure_reaches_the_job_as_its_exception(
    jobs: JobService, drive: Callable[[], None]
) -> None:
    @job(id="demo.worker-fails", title="Worker fails")
    def worker_fails(ctx: WorkerContext, a: int, b: int) -> SumResult:
        raise OSError("disk full")

    handle = jobs.bind(worker_fails).delay(a=1, b=2)
    drive()
    assert handle.status is JobStatus.FAILED
    assert isinstance(handle.error, OSError)


def test_the_worker_context_is_fresh_per_attempt(
    jobs: JobService, drive: Callable[[], None]
) -> None:
    contexts: list[WorkerContext] = []

    @job(id="demo.ctx", title="Context")
    def record(ctx: WorkerContext, a: int, b: int) -> SumResult:
        contexts.append(ctx)
        return SumResult(0)

    bound = jobs.bind(record)
    bound.delay(a=0, b=0)
    bound.delay(a=0, b=0)
    drive()

    first, second = contexts
    assert first is not second
    assert first.progress is not second.progress
    # Only the two worker-appropriate services exist, and neither is a
    # driving-thread one wearing another name.
    assert sorted(name for name in dir(type(first)) if not name.startswith("_")) == [
        "cancellation",
        "progress",
    ]


# -- waiting -----------------------------------------------------------------------


def test_get_is_refused_on_the_driving_thread(
    plugin_scope: ResourceScope, workers: FakeWorkers
) -> None:
    jobs = JobService(plugin_scope, workers=workers, gui_thread=lambda: True)
    handle = jobs.bind(add).delay(a=1, b=2)
    with pytest.raises(QgisSdkJobWaitRefusedError) as info:
        handle.get()
    assert info.value.code == "job_wait_refused"
    jobs.tick()
    workers.run_all()
    jobs.tick()
    # Even a settled job is not read through get() there: the API has one
    # meaning, and the result property is the GUI-thread form.
    with pytest.raises(QgisSdkJobWaitRefusedError):
        handle.get()
    assert handle.result == SumResult(3)


def test_get_waits_for_the_outcome_off_the_driving_thread(
    jobs: JobService, workers: FakeWorkers
) -> None:
    handle = jobs.bind(plain_add).delay(a=1, b=2)
    box: list[object] = []

    def wait() -> None:
        try:
            box.append(handle.get(timeout=5))
        except BaseException as error:  # noqa: BLE001 - recorded for the assertion
            box.append(error)

    waiter = threading.Thread(target=wait)
    waiter.start()
    jobs.tick()
    workers.run_all()
    jobs.tick()
    waiter.join(timeout=5)

    assert box == [SumResult(3)]


def test_get_times_out_as_not_settled_and_raises_the_failure(
    jobs: JobService, workers: FakeWorkers, drive: Callable[[], None]
) -> None:
    @job(id="demo.boom2", title="Boom")
    def boom(ctx: WorkerContext, a: int, b: int) -> SumResult:
        raise KeyError("missing")

    handle = jobs.bind(boom).delay(a=1, b=2)
    with pytest.raises(QgisSdkJobNotSettledError):
        handle.get(timeout=0.01)
    drive()
    with pytest.raises(KeyError):
        handle.get(timeout=0.01)

    cancelled = jobs.bind(add).delay(a=1, b=2)
    cancelled.cancel()
    jobs.tick()
    workers.run_all()
    jobs.tick()
    with pytest.raises(QgisSdkJobCancelledError):
        cancelled.get(timeout=0.01)


def test_the_default_gui_thread_is_the_main_thread(
    plugin_scope: ResourceScope, workers: FakeWorkers
) -> None:
    jobs = JobService(plugin_scope, workers=workers)
    handle = jobs.bind(add).delay(a=1, b=2)
    with pytest.raises(QgisSdkJobWaitRefusedError):
        handle.get()


# -- no retries, ever -----------------------------------------------------------


def test_resubmission_is_explicit_and_nothing_retries_on_its_own(
    jobs: JobService, workers: FakeWorkers
) -> None:
    attempts = []

    @job(id="demo.flaky", title="Flaky")
    def flaky(ctx: WorkerContext, a: int, b: int) -> SumResult:
        attempts.append(1)
        raise TimeoutError("transient")

    bound = jobs.bind(flaky)
    first = bound.delay(a=0, b=0)
    for _ in range(3):
        jobs.tick()
        workers.run_all()
        jobs.tick()
    assert first.status is JobStatus.FAILED
    assert len(attempts) == 1

    second = bound.delay(a=0, b=0)
    jobs.tick()
    workers.run_all()
    jobs.tick()
    assert second.id == "demo.flaky#2"
    assert second.attempt == 1
    assert len(attempts) == 2
    assert not hasattr(JobHandle, "retry")


# -- dependencies: ctx.jobs.after(handle) -------------------------------------------


def test_a_dependent_job_is_not_handed_to_a_worker_until_its_prerequisite_settles(
    jobs: JobService, workers: FakeWorkers, drive: Callable[[], None]
) -> None:
    order: list[str] = []

    @job(id="dep.first", title="First")
    def first(ctx: WorkerContext, a: int) -> SumResult:
        order.append("first")
        return SumResult(a)

    @job(id="dep.second", title="Second")
    def second(ctx: WorkerContext, a: int) -> SumResult:
        order.append("second")
        return SumResult(a)

    prerequisite = jobs.bind(first).delay(a=1)
    dependent = jobs.after(prerequisite).bind(second).delay(a=2)
    assert dependent.status is JobStatus.QUEUED
    assert workers.pending == 0  # delay submits; the tick is what hands over

    jobs.tick()
    assert dependent.status is JobStatus.RUNNING  # waiting, not running a body
    assert workers.pending == 1  # only the prerequisite's body
    assert workers.items[0].title == "First"

    workers.run_all()  # the prerequisite's body
    jobs.tick()
    assert order == ["first"]
    assert prerequisite.status is JobStatus.SUCCEEDED
    assert workers.pending == 1  # now the dependent's body is handed over
    assert workers.items[1].title == "Second"

    workers.run_all()
    jobs.tick()
    assert order == ["first", "second"]
    assert dependent.status is JobStatus.SUCCEEDED
    assert dependent.result == SumResult(2)


def test_the_one_call_and_chained_forms_spell_the_same_dependency(
    jobs: JobService, workers: FakeWorkers, drive: Callable[[], None]
) -> None:
    prerequisite = jobs.bind(add).delay(a=1, b=1)
    chained = jobs.bind(add).after(prerequisite).delay(a=2, b=2)
    one_call = jobs.after(prerequisite).delay(add, a=3, b=3)

    assert chained._attempt.prerequisites == (prerequisite,)
    assert one_call._attempt.prerequisites == (prerequisite,)
    for _ in range(3):
        jobs.tick()
        workers.run_all()
    jobs.tick()
    assert [chained.status, one_call.status] == [
        JobStatus.SUCCEEDED,
        JobStatus.SUCCEEDED,
    ]
    assert (chained.result.total, one_call.result.total) == (4, 6)


def test_a_long_chain_runs_in_order_one_tick_at_a_time(
    jobs: JobService, workers: FakeWorkers
) -> None:
    order: list[int] = []

    @job(id="dep.step", title="Step")
    def step(ctx: WorkerContext, index: int) -> SumResult:
        order.append(index)
        return SumResult(index)

    handles = [jobs.bind(step).delay(index=0)]
    for index in (1, 2, 3):
        handles.append(jobs.after(handles[-1]).bind(step).delay(index=index))

    for _ in range(8):
        jobs.tick()
        workers.run_all()
        jobs.tick()

    assert order == [0, 1, 2, 3]
    assert all(handle.status is JobStatus.SUCCEEDED for handle in handles)


def test_a_failed_prerequisite_fails_the_dependent_job_without_running_it(
    jobs: JobService, workers: FakeWorkers, drive: Callable[[], None]
) -> None:
    ran: list[str] = []

    @job(id="dep.boom", title="Boom")
    def boom(ctx: WorkerContext, a: int) -> SumResult:
        raise ValueError("no precondition")

    @job(id="dep.never", title="Never")
    def never(ctx: WorkerContext, a: int) -> SumResult:
        ran.append("never")
        return SumResult(a)

    prerequisite = jobs.bind(boom).delay(a=1)
    dependent = jobs.after(prerequisite).delay(never, a=2)
    drive()
    jobs.tick()

    assert dependent.status is JobStatus.FAILED
    assert isinstance(dependent.error, QgisSdkJobPrerequisiteError)
    assert dependent.error.code == "job_prerequisite_failed"
    assert dependent.error.prerequisite_id == prerequisite.id
    assert dependent.error.prerequisite_status == "failed"
    assert "never ran" in str(dependent.error)
    assert ran == []


def test_a_cancelled_prerequisite_fails_the_dependent_job_as_well(
    jobs: JobService, workers: FakeWorkers
) -> None:
    prerequisite = jobs.bind(plain_add).delay(a=1, b=1)
    dependent = jobs.after(prerequisite).delay(plain_add, a=2, b=2)

    prerequisite.cancel()
    jobs.tick()  # the prerequisite is closed before it ever ran
    jobs.tick()  # ...and the dependent hears about it

    assert prerequisite.status is JobStatus.CANCELLED
    assert dependent.status is JobStatus.FAILED
    assert isinstance(dependent.error, QgisSdkJobPrerequisiteError)
    assert dependent.error.prerequisite_status == "cancelled"


def test_a_dependent_job_can_be_cancelled_while_it_waits(
    jobs: JobService, workers: FakeWorkers
) -> None:
    prerequisite = jobs.bind(add).delay(a=1, b=1)
    dependent = jobs.after(prerequisite).delay(add, a=2, b=2)
    recorder = _Recorder()
    recorder.subscribe_all(dependent)

    jobs.tick()
    assert dependent.status is JobStatus.RUNNING
    assert dependent.cancel() is True
    jobs.tick()

    assert dependent.status is JobStatus.CANCELLED
    assert recorder.terminal == [("cancelled", None)]
    assert workers.pending == 1  # only the prerequisite's body was ever handed over


def test_after_refuses_something_that_is_not_a_job_handle(jobs: JobService) -> None:
    with pytest.raises(TypeError, match=r"after\(\) takes job handles"):
        jobs.after("demo.sum#1")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match=r"after\(\) takes job handles"):
        jobs.bind(add).after(object())  # type: ignore[arg-type]


def test_the_job_reaches_the_backend_with_its_title(
    jobs: JobService, workers: FakeWorkers, drive: Callable[[], None]
) -> None:
    """AC 1's other half: a backend that shows work is told what it is showing."""
    handle = jobs.bind(add).delay(a=1, b=2)
    jobs.tick()

    (item,) = workers.items
    assert item.title == "Sum two numbers"
    assert item.progress is not None
    assert item.cancel is not None

    # What a task bar's cancel button calls: a request through the same path.
    item.cancel()
    assert handle.cancel_requested is True

    workers.run_all()
    jobs.tick()
    assert handle.status is JobStatus.CANCELLED


# -- AC 1: a real worker thread, distinct from the driving thread ------------------


@pytest.fixture()
def threads() -> Iterator[ThreadWorkers]:
    workers = ThreadWorkers()
    yield workers
    workers.close()


@pytest.fixture()
def threaded_jobs(plugin_scope: ResourceScope, threads: ThreadWorkers) -> JobService:
    return JobService(plugin_scope, workers=threads, gui_thread=lambda: False)


def test_a_body_runs_on_a_worker_and_never_on_the_driving_thread(
    threaded_jobs: JobService, threads: ThreadWorkers
) -> None:
    """AC 1: the driving thread submits and delivers; the worker runs the body."""
    driving = threading.get_ident()
    bodies: list[int] = []
    seen: list[tuple[str, int]] = []
    started = threading.Event()
    release = threading.Event()

    @job(id="thread.where", title="Where am I")
    def where(ctx: WorkerContext, a: int, b: int) -> SumResult:
        bodies.append(threading.get_ident())
        started.set()
        release.wait(5)  # held until the test has looked at the tick
        ctx.progress.report(0.5)
        return SumResult(a + b)

    handle = threaded_jobs.bind(where).delay(a=2, b=3)
    handle.on_progress(lambda f: seen.append(("progress", threading.get_ident())))
    handle.on_success(lambda r: seen.append(("success", threading.get_ident())))

    threaded_jobs.tick()
    assert started.wait(5)
    # The tick returned while the body was still running: it is not the thread
    # that runs author code, and delivery waits for the worker.
    assert handle.status is JobStatus.RUNNING
    assert driving not in bodies
    assert seen == []

    release.set()
    threads.wait()
    threaded_jobs.tick()

    assert len(bodies) == 1
    assert bodies[0] != driving
    assert threads.thread_ids == bodies
    assert handle.status is JobStatus.SUCCEEDED
    assert handle.result == SumResult(5)
    # Every callback, including the progress the worker reported, ran on the
    # thread that ticked, never on the worker.
    assert [kind for kind, _ in seen] == ["progress", "success"]
    assert all(thread == driving for _, thread in seen)
    assert threads.pending == 0


def test_a_failing_body_on_a_real_worker_is_the_job_s_failure(
    threaded_jobs: JobService, threads: ThreadWorkers
) -> None:
    @job(id="thread.fails", title="Fails off-thread")
    def fails(ctx: WorkerContext, a: int, b: int) -> SumResult:
        raise OSError("the disk went away")

    handle = threaded_jobs.bind(fails).delay(a=1, b=2)
    threaded_jobs.tick()
    threads.wait()
    threaded_jobs.tick()

    assert handle.status is JobStatus.FAILED
    assert isinstance(handle.error, OSError)
    assert threads.cancelled == 0


def test_cancelling_a_job_on_a_real_worker_tells_the_backend_once(
    threaded_jobs: JobService, threads: ThreadWorkers
) -> None:
    """The request is forwarded, the thread is not killed, and the report decides."""
    started = threading.Event()
    release = threading.Event()
    observed: list[bool] = []

    @job(id="thread.cooperative", title="Cooperative")
    def cooperative(ctx: WorkerContext, a: int, b: int) -> SumResult:
        started.set()
        observed.append(ctx.cancellation.is_cancelled())
        release.wait(5)
        observed.append(ctx.cancellation.is_cancelled())
        return SumResult(a + b)

    handle = threaded_jobs.bind(cooperative).delay(a=1, b=2)
    threaded_jobs.tick()
    assert started.wait(5)  # the body is running on a worker

    assert handle.cancel() is True
    assert threads.cancelled == 1  # the backend heard about it
    threaded_jobs.tick()
    # Nothing was interrupted: the job is still running until the worker reports.
    assert handle.status is JobStatus.RUNNING
    assert handle.cancel_requested is True

    release.set()
    threads.wait()
    threaded_jobs.tick()

    assert observed == [False, True]
    assert handle.status is JobStatus.CANCELLED
    with pytest.raises(QgisSdkJobCancelledError):
        _ = handle.result


# -- 2026-10-25 audit follow-ups ----------------------------------------------------


class _Reentrant:
    """Stands in for author code that reaches for the driving thread.

    Since 0.9.0 the body runs on a worker, so a tick from there is not a
    nested tick at all: it is the wrong thread, and it must do nothing rather
    than advance the scheduler from a worker (TASK-44, decision-65).
    """

    service: ClassVar[JobService]
    nested: ClassVar[list[int]] = []


@job(id="demo.reentrant", title="Re-enters the tick from author code")
def reentrant_run(ctx: WorkerContext, a: int, b: int) -> SumResult:
    _Reentrant.nested.append(_Reentrant.service.tick())
    return SumResult(total=a + b)


def _run_on_a_worker(workers: FakeWorkers) -> None:
    """Run the pending bodies on another thread: author code, where it belongs."""
    thread = threading.Thread(target=workers.run_all)
    thread.start()
    thread.join()


def test_a_tick_entered_from_author_code_is_a_no_op(
    jobs: JobService, workers: FakeWorkers
) -> None:
    _Reentrant.service = jobs
    _Reentrant.nested = []
    first = jobs.bind(reentrant_run).delay(a=1, b=2)
    second = jobs.bind(add).delay(a=3, b=4)

    jobs.tick()
    _run_on_a_worker(workers)
    jobs.tick()
    _run_on_a_worker(workers)
    jobs.tick()

    assert _Reentrant.nested == [0]
    assert first.status is JobStatus.SUCCEEDED
    assert first.result == SumResult(3)
    assert second.status is JobStatus.SUCCEEDED


def test_a_tick_entered_from_a_subscriber_is_a_no_op(
    jobs: JobService, drive: Callable[[], None]
) -> None:
    seen: list[object] = []
    handle = jobs.bind(add).delay(a=1, b=2)
    later = jobs.bind(add).delay(a=5, b=6)
    handle.on_progress(lambda fraction: seen.append(("nested", jobs.tick())))
    handle.on_success(lambda result: seen.append(("success", result)))
    later.on_success(lambda result: seen.append(("later", result)))

    drive()

    # Both jobs settled on the outer tick; the nested call did nothing and
    # delivery order is the outer tick's.
    assert seen == [("nested", 0), ("success", SumResult(3)), ("later", SumResult(11))]
    assert handle.status is JobStatus.SUCCEEDED
    assert later.status is JobStatus.SUCCEEDED
    assert jobs.faults == ()


def test_a_quiesce_entered_from_author_code_is_refused_without_stopping_anything(
    jobs: JobService, workers: FakeWorkers
) -> None:
    outcomes: list[object] = []

    @job(id="demo.reentrant.quiesce", title="Quiesces from the worker")
    def quiesce_inside(ctx: WorkerContext, a: int, b: int) -> SumResult:
        outcomes.append(jobs.quiesce(max_ticks=1))
        return SumResult(total=a)

    handle = jobs.bind(quiesce_inside).delay(a=9, b=0)
    jobs.tick()
    _run_on_a_worker(workers)
    jobs.tick()

    assert handle.status is JobStatus.SUCCEEDED
    (outcome,) = outcomes
    assert outcome.refused is True
    blocker = (
        "the tick and quiesce belong to the thread that built the service; a "
        "job body runs on a worker and has no tick of its own"
    )
    assert outcome.blockers == (blocker,)


def test_result_raises_the_failure_of_a_failed_job(
    jobs: JobService, drive: Callable[[], None]
) -> None:
    @job(id="demo.boom3", title="Boom")
    def boom(ctx: WorkerContext, a: int, b: int) -> SumResult:
        raise KeyError("missing")

    handle = jobs.bind(boom).delay(a=1, b=2)
    drive()

    assert handle.status is JobStatus.FAILED
    with pytest.raises(KeyError) as info:
        _ = handle.result
    assert info.value is handle.error


def test_result_raises_cancelled_for_a_cancelled_job(
    jobs: JobService,
) -> None:
    handle = jobs.bind(add).delay(a=1, b=2)
    handle.cancel()
    jobs.tick()

    assert handle.status is JobStatus.CANCELLED
    with pytest.raises(QgisSdkJobCancelledError):
        _ = handle.result
    assert handle.error is None


def test_a_finished_job_leaves_nothing_behind_on_an_explicit_subscription_owner(
    jobs: JobService,
    view_jobs: JobService,
    plugin_scope: ResourceScope,
    drive: Callable[[], None],
) -> None:
    hooks_before = len(plugin_scope._callbacks)
    for i in range(20):
        handle = view_jobs.bind(add).delay(a=i, b=1)
        handle.on_success(lambda result: None, owner=plugin_scope)
        handle.on_progress(lambda fraction: None, owner=plugin_scope)
        drive()
        assert handle.status is JobStatus.SUCCEEDED

    # One hook per owner scope at most, never one per subscription; the
    # subscriptions themselves are gone.
    assert len(plugin_scope._callbacks) <= hooks_before + 1
    assert jobs._runtime.owner_hooks.get(plugin_scope) in (None, {})


def test_an_explicit_owner_still_detaches_an_active_subscription(
    jobs: JobService,
    view_jobs: JobService,
    plugin_scope: ResourceScope,
    workers: FakeWorkers,
) -> None:
    other_view = plugin_scope.child()
    seen: list[object] = []
    handle = view_jobs.bind(plain_add).delay(a=1, b=2)
    subscription = handle.on_success(
        lambda result: seen.append(result), owner=other_view
    )
    jobs.tick()

    other_view.close()
    assert subscription.active is False
    workers.run_all()
    jobs.tick()

    assert handle.status is JobStatus.SUCCEEDED
    assert seen == []
    assert jobs._runtime.owner_hooks.get(other_view) is None


def test_a_derived_service_is_a_complete_object(
    jobs: JobService, view_jobs: JobService
) -> None:
    assert sorted(vars(jobs)) == sorted(vars(view_jobs))
    assert view_jobs.parent is jobs
    assert view_jobs.faults == jobs.faults

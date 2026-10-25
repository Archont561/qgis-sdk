"""Scoped local jobs over the step scheduler (TASK-15, decisions 13 and 21).

Every rule here is pinned without Qt: the scheduler is driven by hand, the
worker pool is a fake whose completions the test releases, and "the GUI
thread" is whatever the test says it is. The native file proves the same
service over a real ``QThreadPool`` and a real event loop.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from qgis_sdk.core import JobContext, ResourceScope
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
    QgisSdkJobRejectedError,
    QgisSdkJobWaitRefusedError,
    QgisSdkScopeClosedError,
    QgisSdkUnsupportedCapabilityError,
)
from qgis_sdk.testing import FakeWorkers

# -- authoring surface ----------------------------------------------------------


@dataclass(frozen=True)
class SumInputs:
    a: int
    b: int


@dataclass(frozen=True)
class SumResult:
    total: int


@job(id="demo.sum", title="Sum two numbers")
class Sum:
    def __init__(self, ctx: JobContext) -> None:
        self.ctx = ctx

    def run(self, inputs: SumInputs) -> SumResult:
        self.ctx.progress.report(0.5)
        return SumResult(total=inputs.a + inputs.b)


@job(id="demo.offloaded", title="Sum off the driving thread")
class OffloadedSum:
    def __init__(self, ctx: JobContext) -> None:
        self.ctx = ctx

    async def run(self, inputs: SumInputs) -> SumResult:
        workers = self.ctx.require_workers()
        self.ctx.progress.report(0.1)
        total = await workers.offload(lambda: inputs.a + inputs.b)
        self.ctx.progress.report(1.0)
        return SumResult(total=total)


def test_a_job_class_is_described_without_being_constructed() -> None:
    description = describe_job(Sum)

    assert isinstance(description, JobDescription)
    assert description.id == "demo.sum"
    assert description.title == "Sum two numbers"
    assert description.inputs_type is SumInputs
    assert description.result_type is SumResult
    assert description.inputs_schema["properties"]["a"]["type"] == "integer"
    assert description.result_schema["properties"]["total"]["type"] == "integer"
    assert description.asynchronous is False
    assert describe_job(OffloadedSum).asynchronous is True
    assert description.to_dict()["inputs"]["type"] == "SumInputs"


def test_a_job_class_needs_a_typed_run_of_its_own() -> None:
    with pytest.raises(QgisSdkDeclarationError, match="run"):

        @job(id="demo.norun", title="No run")
        class NoRun:
            pass

        describe_job(NoRun)

    with pytest.raises(QgisSdkDeclarationError, match="annotated"):

        @job(id="demo.untyped", title="Untyped")
        class Untyped:
            def run(self, inputs) -> SumResult:  # type: ignore[no-untyped-def]
                return SumResult(0)

        describe_job(Untyped)

    with pytest.raises(QgisSdkDeclarationError, match="result"):

        @job(id="demo.noresult", title="No result")
        class NoResult:
            def run(self, inputs: SumInputs):  # type: ignore[no-untyped-def]
                return None

        describe_job(NoResult)

    with pytest.raises(QgisSdkDeclarationError, match="@job"):
        describe_job(SumInputs)

    with pytest.raises(QgisSdkDeclarationError, match="duplicate"):
        job(id="demo.twice", title="Twice")(Sum)


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
    # Unload at the end of every test, as a plugin would: a queued job the test
    # never drove is abandoned here instead of leaking an unstarted coroutine.
    scope.close()


@pytest.fixture()
def workers() -> FakeWorkers:
    return FakeWorkers()


@pytest.fixture()
def jobs(plugin_scope: ResourceScope, workers: FakeWorkers) -> JobService:
    return JobService(plugin_scope, workers=workers, gui_thread=lambda: False)


@pytest.fixture()
def view_scope(plugin_scope: ResourceScope) -> ResourceScope:
    return plugin_scope.child()


@pytest.fixture()
def view_jobs(jobs: JobService, view_scope: ResourceScope) -> JobService:
    return jobs.scoped(view_scope)


# -- submission and typed handles -----------------------------------------------


def test_bind_then_delay_submits_without_running_author_code(
    jobs: JobService,
) -> None:
    constructed: list[JobContext] = []

    @job(id="demo.spy", title="Spy")
    class Spy:
        def __init__(self, ctx: JobContext) -> None:
            constructed.append(ctx)

        def run(self, inputs: SumInputs) -> SumResult:
            return SumResult(inputs.a)

    handle = jobs.bind(Spy).delay(SumInputs(1, 2))

    assert handle.status is JobStatus.QUEUED
    assert handle.id == "demo.spy#1"
    assert handle.attempt == 1
    assert handle.description.id == "demo.spy"
    assert constructed == []  # construction is part of the first step
    jobs.tick()
    assert len(constructed) == 1
    assert handle.status is JobStatus.SUCCEEDED
    assert handle.result == SumResult(1)


def test_each_submission_has_its_own_logical_id_and_a_first_attempt(
    jobs: JobService,
) -> None:
    bound = jobs.bind(Sum)
    first = bound.delay(SumInputs(1, 1))
    second = bound.delay(SumInputs(2, 2))

    assert (first.id, second.id) == ("demo.sum#1", "demo.sum#2")
    assert (first.attempt, second.attempt) == (1, 1)
    jobs.tick()
    assert (first.result.total, second.result.total) == (2, 4)


def test_inputs_of_the_wrong_type_are_rejected_before_anything_runs(
    jobs: JobService,
) -> None:
    with pytest.raises(QgisSdkJobRejectedError, match="SumInputs") as info:
        jobs.bind(Sum).delay({"a": 1, "b": 2})  # type: ignore[arg-type]
    assert info.value.code == "job_rejected"
    assert info.value.job_id == "demo.sum"
    assert jobs.active == ()


def test_binding_an_undeclared_class_fails_at_bind_time(jobs: JobService) -> None:
    with pytest.raises(QgisSdkDeclarationError):
        jobs.bind(SumInputs)


def test_a_result_of_the_wrong_type_fails_the_job(jobs: JobService) -> None:
    @job(id="demo.liar", title="Liar")
    class Liar:
        def __init__(self, ctx: JobContext) -> None:
            pass

        def run(self, inputs: SumInputs) -> SumResult:
            return 3  # type: ignore[return-value]

    handle = jobs.bind(Liar).delay(SumInputs(1, 2))
    jobs.tick()

    assert handle.status is JobStatus.FAILED
    assert isinstance(handle.error, QgisSdkDeclarationError)
    assert "SumResult" in str(handle.error)


def test_a_failure_in_run_is_the_job_s_outcome_not_the_tick_s(
    jobs: JobService,
) -> None:
    @job(id="demo.boom", title="Boom")
    class Boom:
        def __init__(self, ctx: JobContext) -> None:
            pass

        def run(self, inputs: SumInputs) -> SumResult:
            raise ValueError("no")

    handle = jobs.bind(Boom).delay(SumInputs(1, 2))
    recorder = _Recorder()
    recorder.subscribe_all(handle)
    jobs.tick()

    assert handle.status is JobStatus.FAILED
    assert isinstance(handle.error, ValueError)
    assert recorder.terminal == [("failure", "ValueError")]
    with pytest.raises(QgisSdkJobNotSettledError):
        _ = handle.result


def test_the_result_is_not_available_before_the_job_succeeds(
    jobs: JobService,
) -> None:
    handle = jobs.bind(Sum).delay(SumInputs(1, 2))
    with pytest.raises(QgisSdkJobNotSettledError, match="queued") as info:
        _ = handle.result
    assert info.value.code == "job_not_settled"
    assert handle.error is None


def test_a_service_over_a_closed_scope_refuses_to_submit(
    jobs: JobService, plugin_scope: ResourceScope
) -> None:
    bound = jobs.bind(Sum)
    plugin_scope.close()
    with pytest.raises(QgisSdkScopeClosedError):
        bound.delay(SumInputs(1, 2))
    with pytest.raises(QgisSdkScopeClosedError):
        jobs.bind(Sum)


# -- progress, success, failure, cancellation subscriptions ---------------------


def test_callbacks_fire_on_the_tick_in_order_and_each_terminal_once(
    jobs: JobService,
) -> None:
    handle = jobs.bind(Sum).delay(SumInputs(2, 3))
    recorder = _Recorder()
    recorder.subscribe_all(handle)

    assert recorder.events == []
    jobs.tick()
    jobs.tick()

    assert recorder.events == [("progress", 0.5), ("success", SumResult(5))]
    assert handle.progress == 0.5


def test_a_subscription_is_disposable_and_disposal_is_idempotent(
    jobs: JobService,
) -> None:
    handle = jobs.bind(Sum).delay(SumInputs(2, 3))
    recorder = _Recorder()
    subscription = handle.on_success(recorder.success)
    assert subscription.active is True

    assert subscription.dispose() is True
    assert subscription.dispose() is False
    assert subscription.active is False
    jobs.tick()
    assert recorder.events == []


def test_a_late_subscriber_replays_the_current_state_once(jobs: JobService) -> None:
    handle = jobs.bind(Sum).delay(SumInputs(2, 3))
    jobs.tick()
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
    jobs.tick()
    assert len(recorder.events) == 2


def test_a_late_progress_subscriber_without_any_report_gets_nothing(
    jobs: JobService,
) -> None:
    @job(id="demo.quiet", title="Quiet")
    class Quiet:
        def __init__(self, ctx: JobContext) -> None:
            pass

        def run(self, inputs: SumInputs) -> SumResult:
            return SumResult(inputs.a)

    handle = jobs.bind(Quiet).delay(SumInputs(1, 2))
    recorder = _Recorder()
    handle.on_progress(recorder.progress)
    jobs.tick()
    handle.on_progress(recorder.progress)
    assert recorder.events == []
    assert handle.progress is None


def test_progress_reported_from_a_worker_thread_is_delivered_on_the_tick(
    jobs: JobService, workers: FakeWorkers
) -> None:
    @job(id="demo.worker-progress", title="Worker progress")
    class WorkerProgress:
        def __init__(self, ctx: JobContext) -> None:
            self.ctx = ctx

        async def run(self, inputs: SumInputs) -> SumResult:
            def work() -> int:
                for step in (0.25, 0.5, 0.75):
                    self.ctx.progress.report(step)
                return inputs.a

            return SumResult(await self.ctx.require_workers().offload(work))

    handle = jobs.bind(WorkerProgress).delay(SumInputs(7, 0))
    recorder = _Recorder()
    handle.on_progress(recorder.progress)
    jobs.tick()
    assert handle.status is JobStatus.RUNNING

    thread = threading.Thread(target=workers.run_all)
    thread.start()
    thread.join()
    # Nothing reached the subscriber from the worker thread...
    assert recorder.events == []
    jobs.tick()
    # ...and the tick coalesced the burst into the latest fraction.
    assert recorder.events == [("progress", 0.75)]
    assert handle.status is JobStatus.SUCCEEDED


def test_a_progress_fraction_outside_the_unit_interval_is_refused(
    jobs: JobService,
) -> None:
    @job(id="demo.overflow", title="Overflow")
    class Overflow:
        def __init__(self, ctx: JobContext) -> None:
            self.ctx = ctx

        def run(self, inputs: SumInputs) -> SumResult:
            self.ctx.progress.report(1.5)
            return SumResult(0)

    handle = jobs.bind(Overflow).delay(SumInputs(0, 0))
    jobs.tick()
    assert handle.status is JobStatus.FAILED
    assert isinstance(handle.error, ValueError)


def test_a_failing_callback_is_detached_and_reported_not_raised(
    jobs: JobService,
) -> None:
    handle = jobs.bind(Sum).delay(SumInputs(2, 3))
    recorder = _Recorder()

    def explode(result: object) -> None:
        raise RuntimeError("ui gone")

    broken = handle.on_success(explode)
    handle.on_success(recorder.success)
    jobs.tick()

    assert recorder.events == [("success", SumResult(5))]
    assert broken.active is False
    assert len(jobs.faults) == 1
    fault = jobs.faults[0]
    assert fault.job_id == "demo.sum#1"
    assert fault.event == "success"
    assert isinstance(fault.error, RuntimeError)


def test_a_fault_hook_hears_about_failing_callbacks(
    plugin_scope: ResourceScope,
) -> None:
    heard = []
    jobs = JobService(plugin_scope, on_fault=heard.append, gui_thread=lambda: False)
    handle = jobs.bind(Sum).delay(SumInputs(2, 3))
    handle.on_progress(lambda fraction: 1 / 0)
    jobs.tick()
    assert [fault.event for fault in heard] == ["progress"]


# -- cancellation ---------------------------------------------------------------


def test_cancel_before_the_first_step_settles_as_cancelled(
    jobs: JobService,
) -> None:
    constructed = []

    @job(id="demo.never", title="Never runs")
    class Never:
        def __init__(self, ctx: JobContext) -> None:
            constructed.append(ctx)

        def run(self, inputs: SumInputs) -> SumResult:
            return SumResult(0)

    handle = jobs.bind(Never).delay(SumInputs(0, 0))
    recorder = _Recorder()
    recorder.subscribe_all(handle)

    assert handle.cancel() is True
    assert handle.cancel_requested is True
    assert handle.status is JobStatus.QUEUED  # a request, not a state
    jobs.tick()

    assert handle.status is JobStatus.CANCELLED
    assert constructed == []
    assert recorder.terminal == [("cancelled", None)]
    assert handle.cancel() is False


def test_cancellation_is_a_request_until_the_job_acknowledges_it(
    jobs: JobService, workers: FakeWorkers
) -> None:
    handle = jobs.bind(OffloadedSum).delay(SumInputs(1, 2))
    recorder = _Recorder()
    recorder.subscribe_all(handle)
    jobs.tick()
    assert handle.status is JobStatus.RUNNING
    assert workers.pending == 1

    assert handle.cancel() is True
    jobs.tick()
    # Still running: the worker has not reported, so nothing can be acknowledged.
    assert handle.status is JobStatus.RUNNING
    assert handle.cancel_requested is True
    assert recorder.terminal == []
    assert workers.cancelled == 1  # the worker was told, as a courtesy

    workers.run_all()
    jobs.tick()
    assert handle.status is JobStatus.CANCELLED
    assert recorder.terminal == [("cancelled", None)]


def test_author_cleanup_runs_when_cancellation_is_delivered(
    jobs: JobService, workers: FakeWorkers
) -> None:
    cleaned = []

    @job(id="demo.cleanup", title="Cleanup")
    class Cleanup:
        def __init__(self, ctx: JobContext) -> None:
            self.ctx = ctx

        async def run(self, inputs: SumInputs) -> SumResult:
            try:
                await self.ctx.require_workers().offload(lambda: 1)
            except QgisSdkJobCancelledError:
                cleaned.append("partial output removed")
                raise
            return SumResult(0)

    handle = jobs.bind(Cleanup).delay(SumInputs(0, 0))
    jobs.tick()
    handle.cancel()
    workers.run_all()
    jobs.tick()

    assert cleaned == ["partial output removed"]
    assert handle.status is JobStatus.CANCELLED


def test_a_sync_run_that_finishes_despite_a_request_succeeds_honestly(
    jobs: JobService,
) -> None:
    """A request is not a state: work that completed anyway reports success."""
    seen = []

    @job(id="demo.stubborn", title="Stubborn")
    class Stubborn:
        def __init__(self, ctx: JobContext) -> None:
            self.ctx = ctx

        def run(self, inputs: SumInputs) -> SumResult:
            handle.cancel()
            seen.append(self.ctx.cancellation.is_cancelled())
            return SumResult(inputs.a)

    handle = jobs.bind(Stubborn).delay(SumInputs(4, 0))
    jobs.tick()

    assert seen == [True]
    assert handle.status is JobStatus.SUCCEEDED
    assert handle.cancel_requested is True


def test_stuck_work_stays_running_and_is_named_as_a_blocker(
    jobs: JobService, workers: FakeWorkers
) -> None:
    handle = jobs.bind(OffloadedSum).delay(SumInputs(1, 2))
    jobs.tick()
    handle.cancel()
    for _ in range(5):
        jobs.tick()

    assert handle.status is JobStatus.RUNNING
    assert handle.cancel_requested is True
    outcome = jobs.quiesce(max_ticks=3)
    assert outcome.refused is True
    assert outcome.blockers == ("job 1 is waiting on an unresolved worker handoff",)
    assert workers.pending == 1


# -- ownership: views, hiding, plugins ------------------------------------------


def test_a_view_owned_job_is_detached_and_asked_to_stop_when_the_view_closes(
    jobs: JobService, view_jobs: JobService, view_scope: ResourceScope, workers
) -> None:
    handle = view_jobs.bind(OffloadedSum).delay(SumInputs(1, 2))
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
    assert recorder.events == [("progress", 0.1)]
    with pytest.raises(QgisSdkScopeClosedError):
        handle.on_cancelled(recorder.cancelled)
    assert recorder.events == [("progress", 0.1)]


def test_hiding_a_view_is_not_disposal(
    jobs: JobService, view_jobs: JobService, workers: FakeWorkers
) -> None:
    class Dock:
        hidden = False

        def hide(self) -> None:
            self.hidden = True

    dock = Dock()
    handle = view_jobs.bind(OffloadedSum).delay(SumInputs(1, 2))
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
    jobs: JobService, view_jobs: JobService, view_scope: ResourceScope, workers
) -> None:
    assert view_jobs.parent is jobs
    assert jobs.parent is None
    handle = view_jobs.parent.bind(OffloadedSum).delay(SumInputs(1, 2))
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
    jobs: JobService, view_jobs: JobService, view_scope: ResourceScope
) -> None:
    handle = view_jobs.bind(Sum).delay(SumInputs(1, 2))
    jobs.tick()
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
    handle = jobs.bind(Sum).delay(SumInputs(1, 2))
    view_scope.close()
    with pytest.raises(QgisSdkScopeClosedError):
        handle.on_success(lambda result: None, owner=view_scope)


def test_unloading_the_plugin_abandons_everything_without_callbacks(
    jobs: JobService, view_jobs: JobService, plugin_scope: ResourceScope, workers
) -> None:
    running = view_jobs.bind(OffloadedSum).delay(SumInputs(1, 2))
    recorder = _Recorder()
    recorder.subscribe_all(running)
    jobs.tick()
    queued = jobs.bind(Sum).delay(SumInputs(1, 2))
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
    jobs: JobService,
) -> None:
    closed = []

    @job(id="demo.scoped", title="Scoped")
    class Scoped:
        def __init__(self, ctx: JobContext) -> None:
            ctx.scope.on_close(lambda: closed.append(ctx.scope))

        def run(self, inputs: SumInputs) -> SumResult:
            return SumResult(0)

    handle = jobs.bind(Scoped).delay(SumInputs(0, 0))
    assert jobs.active == (handle,)
    jobs.tick()
    assert jobs.active == ()
    assert len(closed) == 1
    assert closed[0].closed is True


# -- workers and the job context ------------------------------------------------


def test_a_job_without_workers_fails_explicitly_when_it_asks_for_them(
    plugin_scope: ResourceScope,
) -> None:
    jobs = JobService(plugin_scope, gui_thread=lambda: False)
    handle = jobs.bind(OffloadedSum).delay(SumInputs(1, 2))
    jobs.tick()
    assert handle.status is JobStatus.FAILED
    assert isinstance(handle.error, QgisSdkUnsupportedCapabilityError)


def test_a_worker_failure_reaches_the_job_as_its_exception(
    jobs: JobService, workers: FakeWorkers
) -> None:
    @job(id="demo.worker-fails", title="Worker fails")
    class WorkerFails:
        def __init__(self, ctx: JobContext) -> None:
            self.ctx = ctx

        async def run(self, inputs: SumInputs) -> SumResult:
            def work() -> int:
                raise OSError("disk full")

            return SumResult(await self.ctx.require_workers().offload(work))

    handle = jobs.bind(WorkerFails).delay(SumInputs(1, 2))
    jobs.tick()
    workers.run_all()
    jobs.tick()
    assert handle.status is JobStatus.FAILED
    assert isinstance(handle.error, OSError)


def test_the_job_context_is_fresh_per_attempt_and_carries_the_services(
    jobs: JobService, workers: FakeWorkers
) -> None:
    contexts: list[JobContext] = []

    @job(id="demo.ctx", title="Context")
    class Ctx:
        def __init__(self, ctx: JobContext) -> None:
            contexts.append(ctx)

        def run(self, inputs: SumInputs) -> SumResult:
            return SumResult(0)

    bound = jobs.bind(Ctx)
    bound.delay(SumInputs(0, 0))
    bound.delay(SumInputs(0, 0))
    jobs.tick()

    first, second = contexts
    assert first is not second
    assert first.scope is not second.scope
    assert first.scope.closed and second.scope.closed
    assert first.workers is workers
    assert first.network is None


def test_a_job_without_a_network_fails_explicitly_when_it_asks_for_one(
    jobs: JobService,
) -> None:
    @job(id="demo.offline", title="Offline")
    class Offline:
        def __init__(self, ctx: JobContext) -> None:
            self.ctx = ctx

        def run(self, inputs: SumInputs) -> SumResult:
            self.ctx.require_network()
            return SumResult(0)

    handle = jobs.bind(Offline).delay(SumInputs(0, 0))
    jobs.tick()
    assert handle.status is JobStatus.FAILED
    assert isinstance(handle.error, QgisSdkUnsupportedCapabilityError)
    assert handle.error.capability == "network"


# -- waiting -----------------------------------------------------------------------


def test_get_is_refused_on_the_gui_thread(plugin_scope: ResourceScope) -> None:
    jobs = JobService(plugin_scope, gui_thread=lambda: True)
    handle = jobs.bind(Sum).delay(SumInputs(1, 2))
    with pytest.raises(QgisSdkJobWaitRefusedError) as info:
        handle.get()
    assert info.value.code == "job_wait_refused"
    jobs.tick()
    # Even a settled job is not read through get() there: the API has one
    # meaning, and the result property is the GUI-thread form.
    with pytest.raises(QgisSdkJobWaitRefusedError):
        handle.get()
    assert handle.result == SumResult(3)


def test_get_waits_for_the_outcome_off_the_gui_thread(
    jobs: JobService, workers: FakeWorkers
) -> None:
    handle = jobs.bind(OffloadedSum).delay(SumInputs(1, 2))
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
    jobs: JobService,
) -> None:
    @job(id="demo.boom2", title="Boom")
    class Boom:
        def __init__(self, ctx: JobContext) -> None:
            pass

        def run(self, inputs: SumInputs) -> SumResult:
            raise KeyError("missing")

    handle = jobs.bind(Boom).delay(SumInputs(1, 2))
    with pytest.raises(QgisSdkJobNotSettledError):
        handle.get(timeout=0.01)
    jobs.tick()
    with pytest.raises(KeyError):
        handle.get(timeout=0.01)

    cancelled = jobs.bind(Sum).delay(SumInputs(1, 2))
    cancelled.cancel()
    jobs.tick()
    with pytest.raises(QgisSdkJobCancelledError):
        cancelled.get(timeout=0.01)


def test_the_default_gui_thread_is_the_main_thread(
    plugin_scope: ResourceScope,
) -> None:
    jobs = JobService(plugin_scope)
    handle = jobs.bind(Sum).delay(SumInputs(1, 2))
    with pytest.raises(QgisSdkJobWaitRefusedError):
        handle.get()


# -- no retries, ever -----------------------------------------------------------


def test_resubmission_is_explicit_and_nothing_retries_on_its_own(
    jobs: JobService,
) -> None:
    attempts = []

    @job(id="demo.flaky", title="Flaky")
    class Flaky:
        def __init__(self, ctx: JobContext) -> None:
            pass

        def run(self, inputs: SumInputs) -> SumResult:
            attempts.append(1)
            raise TimeoutError("transient")

    bound = jobs.bind(Flaky)
    first = bound.delay(SumInputs(0, 0))
    for _ in range(3):
        jobs.tick()
    assert first.status is JobStatus.FAILED
    assert len(attempts) == 1

    second = bound.delay(SumInputs(0, 0))
    jobs.tick()
    assert second.id == "demo.flaky#2"
    assert second.attempt == 1
    assert len(attempts) == 2
    assert not hasattr(JobHandle, "retry")

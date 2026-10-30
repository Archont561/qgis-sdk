"""Who owns a submitted job: the invoking view, or the plugin (TASK-116, AC2-4).

Decision-65 §3 made ownership follow the *invocation*: an action the plugin
instance handles still submits the calling window's work, a toolbar call is the
plugin's, and plugin lifetime from a view is the explicit ``ctx.jobs.plugin``.
This file pins that with scripted workers and a real ``PluginRuntime``, so the
dispatch path, the disposal rules and the reload check are all deterministic.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator

import pytest
from qgis_sdk import QgisSdkPlugin
from qgis_sdk.core import PluginContext, PluginRuntime, ResourceScope, WorkerContext
from qgis_sdk.jobs import JobHandle, JobService, JobStatus, job
from qgis_sdk.models import QgisSdkJobWaitRefusedError
from qgis_sdk.testing import FakeWorkers, RecordingNotifications
from qgis_sdk.ui.actions import ViewActions


@job(id="own.record", title="Record a value")
def record(ctx: WorkerContext, value: int) -> int:
    return value


@pytest.fixture
def workers() -> FakeWorkers:
    return FakeWorkers()


def build(workers: FakeWorkers) -> tuple[PluginRuntime, PluginContext]:
    """A started plugin whose two actions submit one job each."""
    app = QgisSdkPlugin(id="demo", title="Demo")
    app.jobs = {"record": record}

    @app.action(id="submit", title="Submit")
    def submit(ctx: PluginContext, value: int) -> JobHandle:
        return ctx.jobs.record.delay(value=value)

    @app.action(id="submit_for_plugin", title="Submit for the plugin")
    def submit_for_plugin(ctx: PluginContext, value: int) -> JobHandle:
        return ctx.jobs.plugin.record.delay(value=value)

    @app.action(id="value", title="Value")
    def value_action(ctx: PluginContext, value: int) -> int:
        return value

    scope = ResourceScope()
    context = PluginContext(
        scope=scope,
        notifications=RecordingNotifications(scope),
        workers=workers,
    )
    runtime = PluginRuntime(app=app, context=context)
    runtime.start()
    return runtime, runtime.context


@pytest.fixture
def started(workers: FakeWorkers) -> Iterator[tuple[PluginRuntime, PluginContext]]:
    runtime, context = build(workers)
    yield runtime, context
    runtime.unload()


@pytest.fixture
def view_scope(context: PluginContext | None = None) -> Iterator[ResourceScope]:
    scope = ResourceScope()
    yield scope
    if not scope.closed:
        scope.close()


def view_actions(runtime: PluginRuntime, scope: ResourceScope) -> ViewActions:
    return ViewActions(runtime, view_id="demo.view#1", scope=scope)


def settle(service: JobService | None, workers: FakeWorkers, rounds: int = 1) -> None:
    assert service is not None, "the plugin declares no jobs"
    for _ in range(rounds):
        service.tick()
        workers.run_all()
    service.tick()


# -- declaring with the decorator --------------------------------------------------


def test_the_decorator_declares_a_job_the_way_a_sequence_does() -> None:
    from qgis_sdk.jobs import describe_job

    app = QgisSdkPlugin(id="decorated", title="Decorated")

    @app.job(id="dec.record", title="Record")
    def record_value(ctx: WorkerContext, value: int) -> int:
        return value

    @app.job()
    def count_features(ctx: WorkerContext, layer: str) -> int:
        return len(layer)

    @app.job(key="sum")
    def add_numbers(ctx: WorkerContext, left: int, right: int) -> int:
        return left + right

    assert sorted(app.jobs) == ["count_features", "record_value", "sum"]
    assert describe_job(record_value).title == "Record"
    # The decorator applies @job itself, so the function describes on its own.
    assert describe_job(count_features).id.startswith("count_features_")
    assert describe_job(add_numbers).title == "Add numbers"


def test_the_decorator_can_expose_a_function_that_is_already_a_job() -> None:
    app = QgisSdkPlugin(id="decorated", title="Decorated")

    assert app.job()(record) is record
    assert app.jobs == {"record": record}


def test_the_decorator_refuses_a_name_it_already_has() -> None:
    from qgis_sdk.declarations import QgisSdkDeclarationError

    app = QgisSdkPlugin(id="decorated", title="Decorated")
    app.job()(record)

    with pytest.raises(QgisSdkDeclarationError, match="two jobs are named 'record'"):
        app.job()(record)

    with pytest.raises(QgisSdkDeclarationError, match="reserved by `ctx.jobs`"):
        app.job(key="after")(record)


def test_the_decorator_and_an_assignments_share_one_registry() -> None:
    from qgis_sdk.declarations import QgisSdkDeclarationError

    app = QgisSdkPlugin(id="decorated", title="Decorated")
    app.jobs = {"record": record}

    with pytest.raises(QgisSdkDeclarationError, match="both assigned in `jobs`"):
        app.job()(record)

    @app.job(key="again")
    def record_again(ctx: WorkerContext, value: int) -> int:
        return value

    assert sorted(app.jobs) == ["again", "record"]
    with pytest.raises(QgisSdkDeclarationError, match="both assigned in `jobs`"):
        app.jobs = {"again": record}


def test_included_plugins_merge_their_decorated_jobs() -> None:
    from qgis_sdk.declarations import QgisSdkDeclarationError

    child = QgisSdkPlugin(id="child", title="Child")
    child.job()(record)
    parent = QgisSdkPlugin(id="parent", title="Parent")
    parent.include(child)

    assert list(parent.jobs) == ["record"]

    clash = QgisSdkPlugin(id="clash", title="Clash")
    clash.job()(record)
    with pytest.raises(QgisSdkDeclarationError, match="duplicate job name 'record'"):
        parent.include(clash)


def test_a_decorated_job_runs_under_the_runtime(workers: FakeWorkers) -> None:
    app = QgisSdkPlugin(id="decorated", title="Decorated")

    @app.job(key="record")
    def record_value(ctx: WorkerContext, value: int) -> int:
        return value * 2

    @app.action(id="run", title="Run")
    def run(ctx: PluginContext, value: int) -> JobHandle:
        return ctx.jobs.record.delay(value=value)

    scope = ResourceScope()
    context = PluginContext(
        scope=scope,
        notifications=RecordingNotifications(scope),
        workers=workers,
    )
    runtime = PluginRuntime(app=app, context=context)
    runtime.start()
    try:
        handle = runtime.actions["run"](value=4)
        settle(runtime.jobs, workers)
        assert handle.result == 8
    finally:
        runtime.unload()


# -- the capability ----------------------------------------------------------------


def test_the_runtime_adds_jobs_to_the_context_it_was_given(
    started: tuple[PluginRuntime, PluginContext],
) -> None:
    runtime, context = started

    assert context.has("jobs")
    assert context.jobs.names == ("record",)
    assert context is runtime.context
    assert isinstance(runtime.jobs, JobService)
    assert runtime.job_registry.names == ("record",)


def test_a_plugin_without_jobs_keeps_the_context_it_was_given(
    workers: FakeWorkers,
) -> None:
    app = QgisSdkPlugin(id="plain", title="Plain")
    scope = ResourceScope()
    context = PluginContext(scope=scope, notifications=RecordingNotifications(scope))
    runtime = PluginRuntime(app=app, context=context)

    assert runtime.context is context
    assert not context.has("jobs")
    assert runtime.jobs is None
    runtime.unload()


def test_a_host_provided_registry_is_refused_rather_than_merged(
    workers: FakeWorkers,
) -> None:
    from qgis_sdk.declarations import QgisSdkDeclarationError
    from qgis_sdk.jobs import Jobs

    app = QgisSdkPlugin(id="both", title="Both")
    app.jobs = {"record": record}
    scope = ResourceScope()
    host_service = JobService(scope, workers=workers)
    context = PluginContext(
        scope=scope,
        notifications=RecordingNotifications(scope),
        jobs=Jobs(host_service),
    )

    with pytest.raises(QgisSdkDeclarationError, match="already provides 'jobs'"):
        PluginRuntime(app=app, context=context)


# -- AC3: the invoking owner -------------------------------------------------------


def test_a_plugin_level_call_submits_plugin_owned_work(
    started: tuple[PluginRuntime, PluginContext], workers: FakeWorkers
) -> None:
    runtime, context = started
    handle = runtime.actions["submit"](value=1)

    assert handle.owner_closed is False
    assert context.scope.closed is False
    settle(runtime.jobs, workers)
    assert handle.status is JobStatus.SUCCEEDED
    assert handle.result == 1


def test_a_view_launched_action_submits_view_owned_work(
    started: tuple[PluginRuntime, PluginContext], workers: FakeWorkers
) -> None:
    runtime, context = started
    view_scope = context.scope.child()
    handle = view_actions(runtime, view_scope).call("submit", value=2)

    assert isinstance(handle, JobHandle)
    view_scope.close()

    assert handle.owner_closed is True
    assert handle.cancel_requested is True
    settle(runtime.jobs, workers)
    assert handle.status is JobStatus.CANCELLED


def test_view_code_opts_in_to_the_plugin_lifetime_explicitly(
    started: tuple[PluginRuntime, PluginContext], workers: FakeWorkers
) -> None:
    runtime, context = started
    view_scope = context.scope.child()
    handle = view_actions(runtime, view_scope).call("submit_for_plugin", value=3)

    view_scope.close()
    assert handle.owner_closed is False

    settle(runtime.jobs, workers)
    assert handle.status is JobStatus.SUCCEEDED
    assert handle.result == 3


def test_two_views_calling_at_once_keep_their_own_owner(
    started: tuple[PluginRuntime, PluginContext], workers: FakeWorkers
) -> None:
    runtime, context = started
    first, second = context.scope.child(), context.scope.child()
    handles: dict[str, JobHandle] = {}
    ready = threading.Barrier(2)

    def dispatch(name: str, scope: ResourceScope) -> None:
        actions = view_actions(runtime, scope)
        ready.wait()
        handles[name] = actions.call("submit", value=len(name))

    threads = [
        threading.Thread(target=dispatch, args=("first", first)),
        threading.Thread(target=dispatch, args=("second", second)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    first.close()
    assert handles["first"].owner_closed is True
    assert handles["second"].owner_closed is False

    second.close()
    settle(runtime.jobs, workers)
    assert handles["first"].status is JobStatus.CANCELLED
    assert handles["second"].status is JobStatus.CANCELLED


def test_an_invoking_scope_that_is_not_ours_leaves_the_work_plugin_owned(
    started: tuple[PluginRuntime, PluginContext], workers: FakeWorkers
) -> None:
    from qgis_sdk.jobs import invoking

    runtime, _context = started
    stranger = ResourceScope()
    try:
        with invoking(stranger):
            handle = runtime.actions["submit"](value=4)
        stranger.close()

        assert handle.owner_closed is False
        settle(runtime.jobs, workers)
        assert handle.status is JobStatus.SUCCEEDED
    finally:
        if not stranger.closed:
            stranger.close()


def test_the_testing_harness_builds_the_same_view_scoped_facade(
    started: tuple[PluginRuntime, PluginContext], workers: FakeWorkers
) -> None:
    from qgis_sdk.testing import fake_ui_context

    runtime, context = started
    view_scope = context.scope.child()
    ui = fake_ui_context(view_scope, runtime=runtime)

    assert ui.jobs.names == ("record",)
    handle = ui.actions.call("submit", value=10)
    assert handle.owner_closed is False

    view_scope.close()
    settle(runtime.jobs, workers)
    assert handle.status is JobStatus.CANCELLED


# -- AC4: disposal, hiding and replacement -----------------------------------------


def test_callbacks_a_view_subscribed_stop_on_disposal(
    started: tuple[PluginRuntime, PluginContext], workers: FakeWorkers
) -> None:
    runtime, context = started
    view_scope = context.scope.child()
    jobs = context.jobs.scoped(view_scope)
    seen: list[object] = []

    handle = jobs.record.delay(value=5)
    jobs.watch(
        handle,
        on_success=seen.append,
        on_progress=seen.append,
        on_failure=seen.append,
        on_cancelled=seen.append,
    )
    view_scope.close()
    settle(runtime.jobs, workers)

    assert seen == []
    assert handle.status is JobStatus.CANCELLED


def test_a_hidden_view_keeps_delivering_until_it_is_disposed(
    started: tuple[PluginRuntime, PluginContext], workers: FakeWorkers
) -> None:
    """Only disposal ends ownership; a dock's visibility is the host's business."""
    runtime, context = started
    view_scope = context.scope.child()
    jobs = context.jobs.scoped(view_scope)
    seen: list[object] = []

    handle = jobs.record.delay(value=6)
    jobs.watch(handle, on_success=seen.append)
    settle(runtime.jobs, workers)

    assert seen == [6]
    assert handle.status is JobStatus.SUCCEEDED
    view_scope.close()


def test_plugin_owned_work_outlives_the_view_that_started_it(
    started: tuple[PluginRuntime, PluginContext], workers: FakeWorkers
) -> None:
    runtime, context = started
    view_scope = context.scope.child()
    jobs = context.jobs.scoped(view_scope)
    seen: list[object] = []

    handle = jobs.plugin.record.delay(value=7)
    jobs.watch(handle, on_success=seen.append)
    assert handle.owner_closed is False

    view_scope.close()
    settle(runtime.jobs, workers)

    assert handle.status is JobStatus.SUCCEEDED
    assert handle.result == 7
    assert seen == []  # the view's callback went with the view


def test_a_running_view_job_blocks_replacement_until_its_worker_reports(
    started: tuple[PluginRuntime, PluginContext], workers: FakeWorkers
) -> None:
    runtime, context = started
    view_scope = context.scope.child()
    handle = view_actions(runtime, view_scope).call("submit", value=8)
    runtime.jobs.tick()

    outcome = runtime.quiesce()
    assert outcome.refused is True
    assert handle.id in " ".join(outcome.blockers)

    view_scope.close()
    workers.run_all()
    runtime.jobs.tick()

    assert runtime.quiesce().safe_to_replace is True


def test_the_gui_thread_is_never_told_to_wait(
    started: tuple[PluginRuntime, PluginContext],
) -> None:
    runtime, _context = started
    handle = runtime.actions["submit"](value=9)

    with pytest.raises(QgisSdkJobWaitRefusedError):
        handle.get()

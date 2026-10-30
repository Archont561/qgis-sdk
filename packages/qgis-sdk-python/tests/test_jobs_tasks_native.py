"""Jobs as ``QgsTask``s under ``QgsApplication.taskManager()`` (TASK-82, decision-65).

The QGIS-free suite pins the job rules with scripted workers; `test_jobs_native`
proves the same service over a plain ``QThreadPool``. This file is the native
worker-first evidence: the whole body runs inside one task the task manager
owns, the task bar shows the job's title and its progress, cancelling the task
asks the job to stop, and callbacks still arrive on the thread that ticks.

The imports are guarded like the other native modules so a host without QGIS
reports what it lacks instead of failing collection.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass

import pytest

pytestmark = pytest.mark.qgis

try:
    from qgis.core import QgsApplication, QgsTask
    from qgis_sdk.adapters.qgis import QgsTaskWorkers
    from qgis_sdk.core import ResourceScope, WorkerContext
    from qgis_sdk.jobs import JobService, JobStatus, job
    from qgis_sdk.models import QgisSdkJobPrerequisiteError
except ImportError as error:  # pragma: no cover - depends on the host
    pytest.skip(
        f"the task-manager backend needs QGIS: {error}", allow_module_level=True
    )

DEADLINE_SECONDS = 10.0


@dataclass(frozen=True)
class Total:
    total: int
    thread: int


@pytest.fixture(scope="module")
def app(qgis_app):
    """The session's one application (see ``tests/layers.py``)."""
    return qgis_app


@pytest.fixture()
def plugin_scope() -> Iterator[ResourceScope]:
    scope = ResourceScope()
    yield scope
    if not scope.closed:
        scope.close()


@pytest.fixture()
def workers(app, plugin_scope: ResourceScope) -> QgsTaskWorkers:
    return QgsTaskWorkers(plugin_scope)


@pytest.fixture()
def jobs(app, plugin_scope: ResourceScope, workers: QgsTaskWorkers) -> JobService:
    return JobService(plugin_scope, workers=workers, gui_thread=lambda: False)


def drive(app, jobs: JobService, until: Callable[[], bool]) -> int:
    """Tick from the GUI thread while Qt's own threads do the work."""
    ticks = 0
    deadline = time.monotonic() + DEADLINE_SECONDS
    while not until():
        if time.monotonic() > deadline:
            raise AssertionError("condition not met within the deadline")
        jobs.tick()
        app.processEvents()
        ticks += 1
        time.sleep(0.001)
    return ticks


def test_the_whole_body_runs_in_one_task_the_task_manager_owns(
    app, jobs: JobService, workers: QgsTaskWorkers
) -> None:
    """AC 1: one task, the job's title, a worker thread, callbacks on the tick."""
    gui = threading.get_ident()
    seen: list[tuple[str, int]] = []
    started = threading.Event()
    release = threading.Event()
    bodies: list[int] = []

    @job(id="task.count", title="Count in the task bar")
    def count(ctx: WorkerContext, count: int) -> Total:
        bodies.append(threading.get_ident())
        started.set()
        release.wait(5)
        for step in range(1, count + 1):
            ctx.progress.report(step / count)
        return Total(total=count, thread=threading.get_ident())

    handle = jobs.bind(count).delay(count=4)
    handle.on_progress(
        lambda fraction: seen.append(("progress", threading.get_ident()))
    )
    handle.on_success(lambda result: seen.append(("success", threading.get_ident())))

    jobs.tick()
    assert started.wait(5)

    # The job is one task under the application's manager, titled as declared,
    # and the thread that ticked is free while it runs.
    assert workers.manager is QgsApplication.taskManager()
    (task,) = workers.tasks
    assert isinstance(task, QgsTask)
    assert task.description() == "Count in the task bar"
    assert workers.manager.countActiveTasks() >= 1
    assert gui not in bodies
    assert seen == []

    release.set()
    drive(app, jobs, lambda: handle.status.settled)

    assert handle.status is JobStatus.SUCCEEDED
    assert handle.result.total == 4
    assert handle.result.thread == bodies[0]
    assert [kind for kind, _ in seen] == ["progress", "success"]
    assert all(thread == gui for _, thread in seen)
    assert workers.submitted == 1


def test_progress_reported_by_the_body_reaches_the_task(
    app, jobs: JobService, workers: QgsTaskWorkers
) -> None:
    """The task bar's bar follows ``ctx.progress``; the job is not asked twice."""
    fractions: list[float] = []
    release = threading.Event()

    @job(id="task.progress", title="Report progress")
    def progress_job(ctx: WorkerContext) -> Total:
        ctx.progress.report(0.25)
        ctx.progress.report(0.5)
        release.wait(5)
        return Total(total=1, thread=threading.get_ident())

    # Connected before the task exists: a progress signal for a task the
    # manager has already dropped is a QGIS-level assertion, not a test's.
    workers.manager.progressChanged.connect(
        lambda task_id, fraction: fractions.append(fraction)
    )

    handle = jobs.bind(progress_job).delay()
    jobs.tick()
    drive(app, jobs, lambda: len(workers.tasks) == 1)
    (task,) = workers.tasks
    assert task.description() == "Report progress"

    release.set()
    drive(app, jobs, lambda: handle.status.settled)

    assert handle.status is JobStatus.SUCCEEDED
    assert handle.progress == 0.5
    # The worker's reports reached the manager on the 0..100 scale it uses,
    # and completion is the last one it emits.
    assert [fraction for fraction in fractions if fraction < 100.0] == [25.0, 50.0]
    assert fractions[-1] == pytest.approx(100.0)


def test_cancelling_the_task_asks_the_job_to_stop_without_killing_it(
    app, jobs: JobService, workers: QgsTaskWorkers
) -> None:
    """The task bar's cancel button is a request: the body decides when to stop."""
    gui = threading.get_ident()
    started = threading.Event()
    release = threading.Event()
    observed: list[bool] = []
    threads: list[int] = []

    @job(id="task.cooperative", title="Cooperative")
    def cooperative(ctx: WorkerContext, count: int) -> Total:
        threads.append(threading.get_ident())
        started.set()
        release.wait(5)
        observed.append(ctx.cancellation.is_cancelled())
        return Total(total=count, thread=threading.get_ident())

    handle = jobs.bind(cooperative).delay(count=2)
    jobs.tick()
    assert started.wait(5)
    (task,) = workers.tasks

    task.cancel()  # exactly what the task bar does

    assert handle.cancel_requested is True
    release.set()
    drive(app, jobs, lambda: handle.status.settled)

    assert observed == [True]
    assert handle.status is JobStatus.CANCELLED
    assert threads and threads[0] != gui


def test_a_task_the_manager_never_starts_acknowledges_without_running_the_body(
    app, jobs: JobService, workers: QgsTaskWorkers
) -> None:
    """AC 2: a queued task skipped after a request settles instead of blocking a reload."""
    ran: list[str] = []
    gate = threading.Event()

    @job(id="task.hold", title="Hold the manager")
    def hold(ctx: WorkerContext) -> Total:
        ran.append("hold")
        gate.wait(5)
        return Total(total=0, thread=threading.get_ident())

    @job(id="task.queued", title="Queued behind it")
    def queued(ctx: WorkerContext) -> Total:
        ran.append("queued")
        return Total(total=0, thread=threading.get_ident())

    pool = workers.manager.threadPool()
    previous = pool.maxThreadCount()
    pool.setMaxThreadCount(1)  # one worker: the second task stays queued
    try:
        holder = jobs.bind(hold).delay()
        second = jobs.bind(queued).delay()
        drive(
            app,
            jobs,
            lambda: workers.submitted == 2 and ran == ["hold"],
        )

        assert second.cancel() is True
        gate.set()
        drive(app, jobs, lambda: holder.status.settled and second.status.settled)
    finally:
        gate.set()
        pool.setMaxThreadCount(previous)

    assert holder.status is JobStatus.SUCCEEDED
    assert second.status is JobStatus.CANCELLED
    assert second.cancel_requested is True
    assert ran == ["hold"]  # the queued body never ran


def test_jobs_after_runs_the_dependent_body_only_once_the_prerequisite_succeeded(
    app, jobs: JobService, workers: QgsTaskWorkers
) -> None:
    """AC 2: ``ctx.jobs.after`` is enforced before the dependent task exists."""
    order: list[str] = []

    @job(id="task.first", title="First")
    def first(ctx: WorkerContext) -> Total:
        time.sleep(0.05)
        order.append("first")
        return Total(total=1, thread=threading.get_ident())

    @job(id="task.second", title="Second")
    def second(ctx: WorkerContext) -> Total:
        order.append("second")
        return Total(total=2, thread=threading.get_ident())

    prerequisite = jobs.bind(first).delay()
    dependent = jobs.after(prerequisite).bind(second).delay()

    assert workers.submitted == 0  # nothing is handed over before the first tick
    jobs.tick()
    assert workers.submitted == 1  # only the prerequisite reached the manager
    drive(app, jobs, lambda: dependent.status.settled)

    assert order == ["first", "second"]
    assert (prerequisite.status, dependent.status) == (
        JobStatus.SUCCEEDED,
        JobStatus.SUCCEEDED,
    )


def test_a_failed_prerequisite_fails_the_dependent_job_without_running_it(
    app, jobs: JobService
) -> None:
    ran: list[str] = []

    @job(id="task.boom", title="Boom")
    def boom(ctx: WorkerContext) -> Total:
        raise ValueError("no precondition")

    @job(id="task.never", title="Never")
    def never(ctx: WorkerContext) -> Total:
        ran.append("never")
        return Total(total=0, thread=threading.get_ident())

    prerequisite = jobs.bind(boom).delay()
    dependent = jobs.after(prerequisite).delay(never)
    drive(app, jobs, lambda: dependent.status.settled)

    assert prerequisite.status is JobStatus.FAILED
    assert dependent.status is JobStatus.FAILED
    assert isinstance(dependent.error, QgisSdkJobPrerequisiteError)
    assert dependent.error.prerequisite_id == prerequisite.id
    assert ran == []

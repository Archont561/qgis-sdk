"""Scoped jobs over a real ``QThreadPool`` and a real Qt event loop (TASK-15).

The QGIS-free suite pins every job rule with a scripted worker. This file is the
thread evidence decision-13 asks for: the offloaded callable runs on a pool
thread, progress it reports from there reaches the subscriber on the GUI thread,
the typed result is delivered on the GUI thread by a timer-driven ``tick``, and
a disposed view's callbacks are never run even though the pool keeps working.

The imports are guarded like ``test_ui_native.py`` so a host without Qt reports
what it lacks instead of failing collection.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass

import pytest

# The qt layer: a real event loop and thread pool, no QGIS needed. The headless
# environment and the bindings path are prepared by tests/conftest.py.
pytestmark = pytest.mark.qt

try:
    from PyQt6.QtCore import QThread, QThreadPool, QTimer
    from qgis_sdk.adapters.qgis.workers import ThreadPoolWorkers
    from qgis_sdk.core import JobContext, ResourceScope
    from qgis_sdk.jobs import JobService, JobStatus, job
    from qgis_sdk.models import QgisSdkJobWaitRefusedError
except ImportError as error:  # pragma: no cover - depends on the host
    pytest.skip(f"native jobs need Qt: {error}", allow_module_level=True)

DEADLINE_SECONDS = 10.0


@dataclass(frozen=True)
class Inputs:
    count: int
    delay_seconds: float = 0.0


@dataclass(frozen=True)
class Result:
    total: int
    thread: int


@job(id="native.count", title="Count on a worker")
class Count:
    def __init__(self, ctx: JobContext) -> None:
        self.ctx = ctx

    async def run(self, inputs: Inputs) -> Result:
        def work() -> Result:
            total = 0
            for step in range(1, inputs.count + 1):
                if self.ctx.cancellation.is_cancelled():
                    break
                time.sleep(inputs.delay_seconds)
                total += step
                self.ctx.progress.report(step / inputs.count)
            return Result(total=total, thread=threading.get_ident())

        return await self.ctx.require_workers().offload(work)


@pytest.fixture(scope="module")
def app(qt_app):
    """The session's one application (see ``tests/layers.py``)."""
    return qt_app


@pytest.fixture()
def plugin_scope() -> Iterator[ResourceScope]:
    scope = ResourceScope()
    yield scope
    if not scope.closed:
        scope.close()


@pytest.fixture()
def pool() -> Iterator[QThreadPool]:
    pool = QThreadPool()
    pool.setMaxThreadCount(2)
    yield pool
    pool.waitForDone(5000)


@pytest.fixture()
def jobs(app, plugin_scope: ResourceScope, pool: QThreadPool) -> JobService:
    workers = ThreadPoolWorkers(plugin_scope, pool=pool)
    return JobService(
        plugin_scope,
        workers=workers,
        gui_thread=lambda: QThread.currentThread() is app.thread(),
    )


def drive(app, jobs: JobService, until: Callable[[], bool]) -> int:
    """Tick from a timer on the event loop, the way a host would, until ``until``."""
    ticks = 0
    timer = QTimer()
    timer.setInterval(1)

    def on_timeout() -> None:
        nonlocal ticks
        ticks += 1
        jobs.tick()

    timer.timeout.connect(on_timeout)
    timer.start()
    deadline = time.monotonic() + DEADLINE_SECONDS
    try:
        while not until():
            if time.monotonic() > deadline:
                raise AssertionError("condition not met within the deadline")
            app.processEvents()
            time.sleep(0.001)
    finally:
        timer.stop()
    return ticks


def test_work_runs_on_the_pool_and_every_callback_runs_on_the_gui_thread(
    app, jobs: JobService
) -> None:
    gui = threading.get_ident()
    seen: list[tuple[str, int, object]] = []
    handle = jobs.bind(Count).delay(Inputs(count=5))
    handle.on_progress(lambda f: seen.append(("progress", threading.get_ident(), f)))
    handle.on_success(lambda r: seen.append(("success", threading.get_ident(), r)))

    drive(app, jobs, lambda: handle.status.settled)

    assert handle.status is JobStatus.SUCCEEDED
    result = handle.result
    assert result.total == 15
    assert result.thread != gui
    assert seen[-1][0] == "success"
    assert all(thread == gui for _, thread, _ in seen)
    fractions = [payload for kind, _, payload in seen if kind == "progress"]
    assert fractions == sorted(fractions)
    assert fractions[-1] == 1.0


def test_get_is_refused_on_the_gui_thread_and_works_from_another(
    app, jobs: JobService
) -> None:
    handle = jobs.bind(Count).delay(Inputs(count=3))
    with pytest.raises(QgisSdkJobWaitRefusedError):
        handle.get(timeout=0.01)

    box: list[object] = []
    waiter = threading.Thread(target=lambda: box.append(handle.get(timeout=5)))
    waiter.start()
    drive(app, jobs, lambda: not waiter.is_alive())
    waiter.join(timeout=1)

    assert box == [handle.result]


def test_disposing_the_view_detaches_callbacks_while_the_pool_keeps_working(
    app, jobs: JobService, plugin_scope: ResourceScope
) -> None:
    view_scope = plugin_scope.child()
    view_jobs = jobs.scoped(view_scope)
    seen: list[str] = []
    handle = view_jobs.bind(Count).delay(Inputs(count=50, delay_seconds=0.01))
    handle.on_progress(lambda f: seen.append("progress"))
    handle.on_success(lambda r: seen.append("success"))
    handle.on_cancelled(lambda: seen.append("cancelled"))

    drive(app, jobs, lambda: handle.progress is not None)
    seen_before = len(seen)
    view_scope.close()

    assert handle.owner_closed is True
    assert handle.cancel_requested is True
    drive(app, jobs, lambda: handle.status.settled)

    # The worker saw the request and stopped early; the job acknowledged it on
    # the GUI thread; the disposed view heard none of it.
    assert handle.status is JobStatus.CANCELLED
    assert len(seen) == seen_before
    assert "cancelled" not in seen


def test_a_cancelled_job_still_queued_on_the_pool_acknowledges_without_running(
    app, jobs: JobService, pool: QThreadPool
) -> None:
    ran: list[int] = []

    @job(id="native.blocker", title="Hold the pool")
    class Blocker:
        def __init__(self, ctx: JobContext) -> None:
            self.ctx = ctx

        async def run(self, inputs: Inputs) -> Result:
            def hold() -> Result:
                time.sleep(inputs.delay_seconds)
                ran.append(1)
                return Result(0, threading.get_ident())

            return await self.ctx.require_workers().offload(hold)

    pool.setMaxThreadCount(1)
    holder = jobs.bind(Blocker).delay(Inputs(count=0, delay_seconds=0.2))
    queued = jobs.bind(Blocker).delay(Inputs(count=0, delay_seconds=0.0))
    drive(
        app,
        jobs,
        lambda: (
            holder.status is JobStatus.RUNNING and queued.status is JobStatus.RUNNING
        ),
    )
    assert queued.cancel() is True

    drive(app, jobs, lambda: holder.status.settled and queued.status.settled)

    assert holder.status is JobStatus.SUCCEEDED
    assert queued.status is JobStatus.CANCELLED
    assert ran == [1]  # the queued callable never ran

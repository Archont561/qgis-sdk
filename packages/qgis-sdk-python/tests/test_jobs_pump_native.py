"""Named jobs in a real runtime: the registry, the task manager and the pump.

The pure suites pin the names and the ownership rules with scripted workers;
this file proves the native half of TASK-116 - ``ctx.jobs.<name>`` on a started
plugin, the body running as one ``QgsTask``, and its callbacks arriving because
a ``QTimer`` ticked the service on the GUI thread, not because a test did.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass

import pytest


class _CcState:
    """A mutable record shared by the phases of one long function."""

    def __init__(_cc_self, **values):
        _cc_self.__dict__.update(values)


class _CcReturn:
    """An early return travelling out of a phase."""

    def __init__(_cc_self, value):
        _cc_self.value = value


class _CcBreak:
    """A loop break travelling out of a phase."""


class _CcContinue:
    """A loop continue travelling out of a phase."""


def _cc_test_a_started_p_p1(_s):
    from qgis_sdk import QgisSdkPlugin

    _s.QgisSdkPlugin = QgisSdkPlugin

    _s.scope = ResourceScope()
    _s.context = PluginContext(
        RecordingNotifications(_s.scope),
        _s.scope,
        PluginServices(workers=QgsTaskWorkers(_s.scope)),
    )
    _s.software = _s.QgisSdkPlugin(id="native.hosted", title="Native hosted")
    _s.software.jobs = (read,)


def _cc_test_a_started_p_p2(_s):

    @_s.software.action(id="read", title="Read")
    def read_action(ctx: PluginContext, value: int) -> JobHandle:
        return ctx.jobs.read.delay(value=value)

    _s.read_action = read_action

    _s.runtime = PluginRuntime(app=_s.software, context=_s.context)
    _s.runtime.start()
    _s.pump = QgsJobPump(_s.runtime.jobs)
    _s.seen: list[Reading] = []


def _cc_test_a_started_p_p3(_s):
    try:
        assert _s.runtime.context.has("jobs")
        _s.handle = _s.runtime.actions["read"](value=13)
        _s.runtime.context.jobs.watch(
            _s.handle, on_progress=lambda _: None, on_success=_s.seen.append
        )

        _s.pump.start()
        spin(_s.app, lambda: _s.handle.status.settled)
    finally:
        _s.pump.stop()
        _s.runtime.unload()


def _cc_test_a_started_p_p4(_s):

    assert _s.handle.status is JobStatus.SUCCEEDED
    assert _s.seen == [Reading(13, _s.seen[0].thread)]
    assert _s.scope.closed is True


pytestmark = pytest.mark.qgis

try:
    from qgis_sdk.adapters.qgis import QgsJobPump, QgsTaskWorkers
    from qgis_sdk.core import (
        PluginContext,
        PluginRuntime,
        PluginServices,
        ResourceScope,
        WorkerContext,
    )
    from qgis_sdk.declarations import QgisSdkDeclarationError
    from qgis_sdk.jobs import JobHandle, JobRegistry, JobService, JobStatus, job
    from qgis_sdk.testing import RecordingNotifications
except ImportError as error:  # pragma: no cover - depends on the host
    pytest.skip(f"the native job runtime needs QGIS: {error}", allow_module_level=True)

DEADLINE_SECONDS = 10.0


@dataclass(frozen=True)
class Reading:
    value: int
    thread: int


@job(id="native.read", title="Read a value")
def read(ctx: WorkerContext, value: int) -> Reading:
    ctx.progress.report(0.5)
    return Reading(value, threading.get_ident())


@pytest.fixture(scope="module")
def app(qgis_app):
    return qgis_app


@pytest.fixture
def plugin_scope() -> Iterator[ResourceScope]:
    scope = ResourceScope()
    yield scope
    if not scope.closed:
        scope.close()


@pytest.fixture
def workers(app, plugin_scope: ResourceScope) -> QgsTaskWorkers:
    return QgsTaskWorkers(plugin_scope)


@pytest.fixture
def service(app, plugin_scope: ResourceScope, workers: QgsTaskWorkers) -> JobService:
    registry = JobRegistry.from_declaration({"read": read}, path="plugin 'native'")
    return JobService(plugin_scope, workers=workers, registry=registry)


def spin(app, until: Callable[[], bool]) -> None:
    """Let Qt run its event loop - timer, task manager, delivery - until ``until``."""
    deadline = time.monotonic() + DEADLINE_SECONDS
    while not until():
        if time.monotonic() > deadline:
            raise AssertionError("condition not met within the deadline")
        app.processEvents()
        time.sleep(0.001)


# -- the pump ----------------------------------------------------------------------


def test_the_pump_ticks_the_service_from_a_timer(app, service: JobService) -> None:
    seen: list[Reading] = []
    pump = QgsJobPump(service)
    try:
        assert pump.running is False
        pump.start()
        assert pump.running is True

        handle = service.read.delay(value=11)
        handle.on_success(seen.append)

        spin(app, lambda: handle.status.settled)
    finally:
        pump.stop()

    assert pump.running is False
    assert handle.status is JobStatus.SUCCEEDED
    assert seen == [Reading(11, seen[0].thread)]
    assert seen[0].thread != threading.get_ident()  # the body ran on a task thread


def test_the_pump_refuses_an_interval_it_cannot_use(service: JobService) -> None:
    with pytest.raises(ValueError, match="interval_ms must be positive"):
        QgsJobPump(service, interval_ms=0)

    pump = QgsJobPump(service, interval_ms=25)
    assert pump.interval_ms == 25
    assert "stopped" in repr(pump)


def test_nothing_reaches_the_task_manager_until_something_ticks(
    app, service: JobService, workers: QgsTaskWorkers
) -> None:
    pump = QgsJobPump(service)  # built, never started
    handle = service.read.delay(value=12)

    assert workers.submitted == 0
    pump.tick()
    assert workers.submitted == 1
    # A tick submits the body; it does not promise the task manager is still
    # holding it when the tick returns. A body that finishes at once is reported
    # inside the same tick's remaining step budget, so the handle is running or
    # already settled - never still queued. What the tick guarantees is the
    # submission, which is what this test is about.
    assert handle.status is not JobStatus.QUEUED
    deadline = time.monotonic() + DEADLINE_SECONDS
    while not handle.status.settled:  # manual ticks, no timer
        if time.monotonic() > deadline:
            raise AssertionError("the job never settled")
        pump.tick()
        app.processEvents()
        time.sleep(0.001)


# -- the started plugin ------------------------------------------------------------


def test_a_started_plugin_exposes_its_declared_jobs(app) -> None:
    _s = _CcState(app=app)
    for _p in (
        _cc_test_a_started_p_p1,
        _cc_test_a_started_p_p2,
        _cc_test_a_started_p_p3,
        _cc_test_a_started_p_p4,
    ):
        _r = _p(_s)
        if isinstance(_r, _CcReturn):
            return _r.value
    return None


def test_the_desktop_adapter_arms_the_pump_when_it_starts_and_stops_it_on_unload(
    app,
) -> None:
    from qgis_sdk import QgisSdkPlugin
    from qgis_sdk.adapters.desktop import DesktopLifecycleAdapter

    software = QgisSdkPlugin(id="native.pumped", title="Native pumped")
    software.jobs = {"read": read}

    def factory(iface: object | None) -> PluginContext:
        scope = ResourceScope()
        return PluginContext(
            RecordingNotifications(scope),
            scope,
            PluginServices(workers=QgsTaskWorkers(scope)),
        )

    adapter = DesktopLifecycleAdapter(software, None, context_factory=factory)
    assert adapter.job_pump is None  # nothing ticks before the plugin runs

    adapter.initGui()
    pump = adapter.job_pump
    assert pump is not None
    assert pump.running is True

    adapter.unload()
    assert adapter.job_pump is None
    assert pump.running is False


def test_an_invalid_registry_is_refused_at_startup_not_at_submission(app) -> None:
    from qgis_sdk import QgisSdkPlugin

    software = QgisSdkPlugin(id="native.bad", title="Native bad")

    def bare(ctx: WorkerContext) -> int:  # no @job: the registry refuses it
        return 1

    with pytest.raises(QgisSdkDeclarationError, match="is not a @job declaration"):
        software.jobs = {"bad": bare}  # the author hears about it at once

    software._jobs = {"bad": bare}  # bypassing the setter does not bypass the runtime
    scope = ResourceScope()
    context = PluginContext(RecordingNotifications(scope), scope)
    with pytest.raises(QgisSdkDeclarationError, match="Plugin 'native.bad'"):
        PluginRuntime(app=software, context=context)
    scope.close()

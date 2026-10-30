"""Request-scoped jobs on the server host: ticked at request start, abandoned with it.

Decision-52 point 2 says a job a QGIS Server hook submits is request-scoped
unless it is declared plugin-owned, and the implementation note fixes what that
means in practice: a server has no GUI thread and no job pump, so the request is
the clock. The host ticks the plugin's service when a request starts, and when
the response is sent the request scope closes and its jobs are *abandoned* - they
name themselves cancelled instead of pretending they finished, a worker still
running is asked to stop, nothing is delivered, and the plugin's scheduler does
not keep them.

Nothing here imports QGIS: the hooks are plain functions, the interface is the
scripted ``FakeServerInterface``, and the worker pool is one whose completions
the test releases by hand.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from qgis_sdk.core import ResourceScope, WorkerContext
from qgis_sdk.jobs import (
    JobHandle,
    JobRegistry,
    JobService,
    JobStatus,
    JobSubscription,
    job,
)
from qgis_sdk.models import (
    QgisSdkJobCancelledError,
    QgisSdkScopeClosedError,
    QgisSdkUnsupportedCapabilityError,
)
from qgis_sdk.server import (
    ServerContext,
    ServerHooks,
    ServerHost,
    ServerRequest,
    ServerResponse,
    filter,
)
from qgis_sdk.testing import FakeServerInterface, FakeWorkers


@dataclass(frozen=True)
class SumResult:
    total: int


@job(id="demo.sum", title="Sum two numbers")
def add(ctx: WorkerContext, a: int, b: int) -> SumResult:
    return SumResult(total=a + b)


# -- what a test drives ------------------------------------------------------------


class _Recorder:
    """Every terminal callback a subscription could fire, recorded in order."""

    def __init__(self) -> None:
        self.events: list[tuple[str, object]] = []

    def success(self, result: object) -> None:
        self.events.append(("success", result))

    def failure(self, error: BaseException) -> None:
        self.events.append(("failure", type(error).__name__))

    def cancelled(self) -> None:
        self.events.append(("cancelled", None))

    def subscribe_all(self, handle: JobHandle) -> list[JobSubscription]:
        return [
            handle.on_success(self.success),
            handle.on_failure(self.failure),
            handle.on_cancelled(self.cancelled),
        ]


class _Submitted:
    """What the hooks of the requests in one test left behind, read afterwards."""

    def __init__(self) -> None:
        self.handles: list[JobHandle] = []
        self.contexts: list[ServerContext] = []


@pytest.fixture()
def plugin_scope() -> Iterator[ResourceScope]:
    scope = ResourceScope()
    yield scope
    # Unloading the plugin at the end of every test, as a real host would: a job
    # the test never drove is abandoned here rather than leaking into the next.
    scope.close()


@pytest.fixture()
def workers() -> FakeWorkers:
    return FakeWorkers()


@pytest.fixture()
def service(plugin_scope: ResourceScope, workers: FakeWorkers) -> JobService:
    return JobService(
        plugin_scope,
        workers=workers,
        registry=JobRegistry.from_declaration({"add": add}, path="plugin 'demo'"),
        gui_thread=lambda: False,
    )


def wms(**params: str) -> ServerRequest:
    return ServerRequest(
        method="GET",
        url="http://localhost/qgis/qgis_mapserv.fcgi",
        params=params,
        headers={"Accept": "text/xml"},
    )


def host_for(
    hooks: ServerHooks, service: JobService | None, interface: FakeServerInterface
) -> ServerHost:
    host = ServerHost(hooks, interface, jobs=service)
    host.register()
    return host


# -- a submitted job is request-scoped ---------------------------------------------


def test_the_request_scope_owns_what_a_hook_submits(service: JobService) -> None:
    """``ctx.jobs`` on a ``ServerContext`` is a service over *this* request's scope."""

    submitted = _Submitted()

    @filter()
    def submit(
        ctx: ServerContext, request: ServerRequest, response: ServerResponse
    ) -> None:
        submitted.contexts.append(ctx)
        submitted.handles.append(ctx.jobs.add.delay(a=1, b=2))

    scope = ResourceScope()
    host_for(ServerHooks((submit,)), service, FakeServerInterface()).handle(
        wms(SERVICE="WMS"), scope=scope
    )

    context = submitted.contexts[0]
    assert context.jobs.scope is scope
    assert context.jobs.scope is not service.scope
    assert submitted.handles[0].owner_closed is False
    scope.close()


def test_the_response_abandons_a_request_job_without_pretending_it_finished(
    service: JobService, workers: FakeWorkers
) -> None:
    """AC 3: the response is sent, so the job names itself cancelled - and says why."""

    submitted = _Submitted()
    recorder = _Recorder()

    @filter()
    def submit(
        ctx: ServerContext, request: ServerRequest, response: ServerResponse
    ) -> None:
        handle = ctx.jobs.add.delay(a=1, b=2)
        recorder.subscribe_all(handle)
        submitted.handles.append(handle)

    scope = ResourceScope()
    host_for(ServerHooks((submit,)), service, FakeServerInterface()).handle(
        wms(SERVICE="WMS"), scope=scope
    )
    handle = submitted.handles[0]
    assert handle.status is JobStatus.QUEUED  # submitted, not started yet

    scope.close()  # the response is sent

    assert handle.status is JobStatus.CANCELLED
    assert handle.owner_closed is True
    assert handle.cancel_requested is True
    assert recorder.events == []
    with pytest.raises(QgisSdkJobCancelledError):
        handle.get(timeout=0)
    with pytest.raises(QgisSdkJobCancelledError):
        _ = handle.result
    # Nothing is left for a later request to tick, and a late worker report
    # reaches nobody.
    assert service.active == ()
    assert service.tick() == 0
    assert workers.run_all() == 0
    assert recorder.events == []


def test_an_abandoned_job_leaves_the_plugin_scheduler(service: JobService) -> None:
    """A request that ends must not leave the plugin's scheduler holding its work."""

    submitted = _Submitted()

    @filter()
    def submit(
        ctx: ServerContext, request: ServerRequest, response: ServerResponse
    ) -> None:
        submitted.handles.append(ctx.jobs.add.delay(a=1, b=2))

    scope = ResourceScope()
    host = host_for(ServerHooks((submit,)), service, FakeServerInterface())
    host.handle(wms(SERVICE="WMS"), scope=scope)
    assert len(service.active) == 1

    scope.close()

    assert service.active == ()
    assert host.jobs is service
    assert host.jobs.faults == ()


def test_a_plugin_owned_job_outlives_the_request(
    service: JobService, workers: FakeWorkers
) -> None:
    """``ctx.jobs.plugin`` is how a hook says "this one is not the request's"."""

    submitted = _Submitted()
    recorder = _Recorder()

    @filter()
    def submit(
        ctx: ServerContext, request: ServerRequest, response: ServerResponse
    ) -> None:
        handle = ctx.jobs.plugin.add.delay(a=2, b=3)
        recorder.subscribe_all(handle)
        submitted.handles.append(handle)

    scope = ResourceScope()
    host = host_for(ServerHooks((submit,)), service, FakeServerInterface())
    host.handle(wms(SERVICE="WMS"), scope=scope)
    handle = submitted.handles[0]

    scope.close()

    assert handle.status is JobStatus.QUEUED
    assert handle.owner_closed is False
    host.tick()  # the next request's tick starts it
    assert workers.run_all() == 1
    host.tick()
    assert handle.status is JobStatus.SUCCEEDED
    assert handle.owner_closed is False
    assert recorder.events == [("success", SumResult(total=5))]


def test_the_host_ticks_the_service_when_a_request_starts(
    service: JobService, workers: FakeWorkers
) -> None:
    """The request is the clock: a plugin-owned job advances one step per request."""

    submitted = _Submitted()

    @filter()
    def submit(
        ctx: ServerContext, request: ServerRequest, response: ServerResponse
    ) -> None:
        submitted.handles.append(ctx.jobs.plugin.add.delay(a=1, b=1))

    host = host_for(ServerHooks((submit,)), service, FakeServerInterface())
    first = ResourceScope()
    host.handle(wms(SERVICE="WMS"), scope=first)
    first.close()
    handle = submitted.handles[0]
    assert workers.pending == 0  # submitted during request 1, after its tick

    second = ResourceScope()
    host.handle(wms(SERVICE="WMS"), scope=second)
    assert workers.pending == 1  # request 2's tick handed it to the worker
    workers.run_all()
    assert handle.status is JobStatus.RUNNING  # the report is not delivered yet

    third = ResourceScope()
    host.handle(wms(SERVICE="WMS"), scope=third)
    assert handle.status is JobStatus.SUCCEEDED
    second.close()
    third.close()


def test_a_request_job_is_refused_once_its_request_is_over(service: JobService) -> None:
    """A context kept past its response cannot submit new work on that scope."""

    submitted = _Submitted()

    @filter()
    def submit(
        ctx: ServerContext, request: ServerRequest, response: ServerResponse
    ) -> None:
        submitted.contexts.append(ctx)

    scope = ResourceScope()
    host_for(ServerHooks((submit,)), service, FakeServerInterface()).handle(
        wms(SERVICE="WMS"), scope=scope
    )
    context = submitted.contexts[0]
    scope.close()

    with pytest.raises(QgisSdkScopeClosedError):
        context.jobs.add.delay(a=1, b=2)


# -- a host without a job service ---------------------------------------------------


def test_a_host_without_a_job_service_refuses_jobs_by_name() -> None:
    """The capability is absent, not broken: ``ctx.jobs`` says which name is missing."""

    seen: list[frozenset[str]] = []

    @filter()
    def inspect(
        ctx: ServerContext, request: ServerRequest, response: ServerResponse
    ) -> None:
        seen.append(ctx.capabilities)
        with pytest.raises(QgisSdkUnsupportedCapabilityError):
            _ = ctx.jobs

    host_for(ServerHooks((inspect,)), None, FakeServerInterface()).handle(
        wms(SERVICE="WMS")
    )

    assert "jobs" not in seen[0]


def test_the_scripted_interface_serves_with_a_job_service(service: JobService) -> None:
    """``FakeServerInterface.serve`` derives the same request scope a server does."""

    submitted = _Submitted()

    @filter()
    def submit(
        ctx: ServerContext, request: ServerRequest, response: ServerResponse
    ) -> None:
        submitted.handles.append(ctx.jobs.add.delay(a=1, b=2))

    scope = ResourceScope()
    response = FakeServerInterface().serve(
        ServerHooks((submit,)), wms(SERVICE="WMS"), scope=scope, jobs=service
    )

    assert response.status == 400  # nothing serves WMS here; the hook still ran
    assert len(submitted.handles) == 1
    scope.close()
    assert submitted.handles[0].status is JobStatus.CANCELLED

"""The plugin's declared job names: validated once, read by name (TASK-116).

Decision-65 §2 replaced "pass the function" with "name the job": a plugin
declares ``jobs = {"add": add}`` or ``jobs = (add, count_features)``, and an
action writes ``ctx.jobs.add.delay(left=1, right=2)``. This file pins the
declaration half - names, derived names, refusals, and the fact that a
submission is a dictionary read - with scripted workers, so nothing here needs
QGIS and every rule is deterministic.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from qgis_sdk.core import ResourceScope, WorkerContext
from qgis_sdk.declarations import QgisSdkDeclarationError
from qgis_sdk.jobs import (
    RESERVED_JOB_NAMES,
    JobDescription,
    JobHandle,
    JobRegistry,
    Jobs,
    JobService,
    JobStatus,
    job,
)
from qgis_sdk.testing import FakeWorkers


@dataclass(frozen=True)
class Total:
    total: int


@job(id="reg.add", title="Add two numbers")
def add(ctx: WorkerContext, left: int, right: int) -> Total:
    return Total(left + right)


@job(id="reg.count", title="Count features")
def count_features(ctx: WorkerContext, layer: str) -> int:
    return len(layer)


def _same_name(other_id: str):
    """A second function *called* ``count_features`` with its own id.

    The collision the mapping form exists to resolve: two modules, one name.
    """

    def count_features(ctx: WorkerContext, layer: str) -> int:
        return len(layer) + 1

    return job(id=other_id, title="Count otherwise")(count_features)


count_features_other = _same_name("reg.count.other")
assert count_features_other.__name__ == "count_features"  # the point of the fixture


def bare(ctx: WorkerContext) -> int:
    return 1


@pytest.fixture
def workers() -> FakeWorkers:
    return FakeWorkers()


@pytest.fixture
def scope() -> Iterator[ResourceScope]:
    scope = ResourceScope()
    yield scope
    if not scope.closed:
        scope.close()


@pytest.fixture
def service(scope: ResourceScope, workers: FakeWorkers) -> JobService:
    registry = JobRegistry.from_declaration(
        {"add": add, "count": count_features}, path="plugin 'demo'"
    )
    return JobService(
        scope, workers=workers, registry=registry, gui_thread=lambda: False
    )


@pytest.fixture
def jobs(service: JobService) -> Jobs:
    return Jobs(service)


def finish(service: JobService, workers: FakeWorkers) -> None:
    """Tick, run the body on the worker, tick: one submission, delivered."""
    service.tick()
    workers.run_all()
    service.tick()


# -- declaring: the two forms ------------------------------------------------------


def test_a_mapping_keeps_the_keys_the_plugin_wrote() -> None:
    registry = JobRegistry.from_declaration(
        {"sum": add, "count": count_features}, path="plugin 'demo'"
    )

    assert registry.names == ("sum", "count")
    assert registry.description("sum").id == "reg.add"
    assert registry.description("count").title == "Count features"


def test_a_sequence_derives_each_name_from_the_function() -> None:
    registry = JobRegistry.from_declaration((add, count_features), path="plugin 'demo'")

    assert registry.names == ("add", "count_features")
    # The derived name is the function's, not the id's: a bare ``@job`` id
    # carries a module/qualname suffix that no one would type.
    assert registry.description("add").id == "reg.add"


def test_a_sequence_derives_the_name_a_bare_decorator_would() -> None:
    @job
    def count_layers(ctx: WorkerContext) -> int:
        return 2

    registry = JobRegistry.from_declaration((count_layers,), path="plugin 'demo'")

    assert registry.names == ("count_layers",)
    assert registry.description("count_layers").id.startswith("count_layers_")


def test_a_plugin_that_declares_nothing_has_an_empty_registry() -> None:
    registry = JobRegistry.from_declaration(None, path="plugin 'demo'")

    assert registry.names == ()
    assert len(registry) == 0
    assert "add" not in registry
    with pytest.raises(AttributeError, match="declares no job 'add'.*none"):
        registry.description("add")


# -- declaring: what is refused ----------------------------------------------------


@pytest.mark.parametrize(
    ("declaration", "message"),
    [
        ("add", "jobs must be a mapping of names"),
        ({"add": 3}, "jobs\\['add'\\] is not a @job declaration"),
        ((bare,), r"jobs\[0\] \(bare\) is not a @job declaration"),
        ({"_private": add}, "must be a plain Python identifier"),
        ({"not a name": add}, "must be a plain Python identifier"),
        ({1: add}, "job names must be strings"),
        ({"after": add}, "reserved by `ctx.jobs`"),
        ({"delay": add}, "reserved by `ctx.jobs`"),
        ({}, None),
    ],
)
def test_a_declaration_that_cannot_be_read_by_name_is_refused(
    declaration: object, message: str | None
) -> None:
    if message is None:
        assert len(JobRegistry.from_declaration(declaration, path="plugin 'demo'")) == 0
        return
    with pytest.raises(QgisSdkDeclarationError, match=message):
        JobRegistry.from_declaration(declaration, path="plugin 'demo'")


def test_two_functions_with_the_same_name_are_refused_with_the_way_forward() -> None:
    with pytest.raises(
        QgisSdkDeclarationError, match="two jobs are named 'count_features'"
    ):
        JobRegistry.from_declaration(
            (count_features, count_features_other), path="plugin 'demo'"
        )

    registry = JobRegistry.from_declaration(
        {"count": count_features, "count_other": count_features_other},
        path="plugin 'demo'",
    )
    assert registry.names == ("count", "count_other")


def test_two_names_for_one_job_id_are_refused() -> None:
    with pytest.raises(QgisSdkDeclarationError, match="declare the same id 'reg.add'"):
        JobRegistry.from_declaration(
            {"first": add, "second": add}, path="plugin 'demo'"
        )


def test_every_name_the_service_answers_to_is_reserved() -> None:
    """A job may not shadow what ``ctx.jobs`` itself reads (AC1)."""

    surface = {
        name
        for cls in (Jobs, JobService)
        for name in dir(cls)
        if not name.startswith("_")
    }
    assert surface - RESERVED_JOB_NAMES == set()


# -- reaching a job by name --------------------------------------------------------


def test_a_declared_name_binds_to_the_validated_description(jobs: Jobs) -> None:
    bound = jobs.add

    assert isinstance(bound.description, JobDescription)
    assert (bound.description.id, bound.description.title) == (
        "reg.add",
        "Add two numbers",
    )
    assert bound.description.inputs_schema["required"] == ["left", "right"]
    assert jobs.names == ("add", "count")
    assert len(jobs) == 2
    assert "add" in jobs and "nope" not in jobs
    assert list(jobs) == ["add", "count"]
    assert jobs.describe("add").title == "Add two numbers"


def test_an_unknown_name_lists_what_the_plugin_declares(jobs: Jobs) -> None:
    with pytest.raises(AttributeError, match="declares no job 'subtract'.*add, count"):
        _ = jobs.subtract
    with pytest.raises(AttributeError, match="declares no job 'subtract'"):
        jobs["subtract"]


def test_a_submission_by_name_validates_inputs_and_delivers_the_result(
    service: JobService, workers: FakeWorkers, jobs: Jobs
) -> None:
    handle = jobs.add.delay(left=2, right=3)

    assert isinstance(handle, JobHandle)
    assert handle.status is JobStatus.QUEUED
    finish(service, workers)

    assert handle.status is JobStatus.SUCCEEDED
    assert handle.result == Total(total=5)
    assert handle.description.id == "reg.add"


def test_bad_inputs_are_refused_by_name_before_anything_is_queued(jobs: Jobs) -> None:
    from qgis_sdk.models import QgisSdkJobRejectedError

    with pytest.raises(QgisSdkJobRejectedError) as raised:
        jobs.add.delay(left=1)

    assert raised.value.job_id == "reg.add"
    assert "missing right" in " ".join(raised.value.problems)


def test_the_registry_never_reaches_for_a_module_during_submission(
    service: JobService, workers: FakeWorkers, jobs: Jobs, monkeypatch
) -> None:
    """AC1: the lookup is prebuilt; nothing is inspected on the way to a worker."""

    def refuse(function: object) -> None:
        raise AssertionError("submission described a declaration again")

    monkeypatch.setattr("qgis_sdk.jobs._registry.describe_job", refuse)
    handle = jobs.add.delay(left=1, right=1)
    finish(service, workers)

    assert handle.result == Total(total=2)


def test_the_facade_reports_what_is_declared_and_what_is_running(
    service: JobService, workers: FakeWorkers, jobs: Jobs, scope: ResourceScope
) -> None:
    handle = jobs.add.delay(left=1, right=2)

    assert jobs.scope is scope
    assert jobs.active == (handle,)
    assert jobs.faults == ()
    assert "add" in repr(jobs)
    with pytest.raises(AttributeError):
        _ = jobs._private

    finish(service, workers)
    assert jobs.active == ()

    other = ResourceScope()
    try:
        assert jobs.scoped(other).names == jobs.names
        assert jobs.plugin.names == jobs.names
        assert jobs.plugin.scope is scope  # the plugin's own service here
    finally:
        other.close()


# -- ordering and watching ---------------------------------------------------------


def test_a_named_job_can_be_ordered_behind_another(
    service: JobService, workers: FakeWorkers, jobs: Jobs
) -> None:
    first = jobs.add.delay(left=1, right=1)
    second = jobs.after(first).add.delay(left=10, right=10)

    assert second.description.id == "reg.add"
    service.tick()
    workers.run_all()  # only the prerequisite has a body yet
    for _ in range(2):
        service.tick()
        workers.run_all()
    service.tick()

    assert first.status is JobStatus.SUCCEEDED
    assert second.status is JobStatus.SUCCEEDED
    assert second.result == Total(total=20)


def test_after_refuses_anything_that_is_not_a_handle(jobs: Jobs) -> None:
    with pytest.raises(TypeError, match="after\\(\\) takes job handles"):
        jobs.after("reg.add")  # type: ignore[arg-type]


def test_the_ordered_view_reads_like_the_registry(
    service: JobService, workers: FakeWorkers, jobs: Jobs
) -> None:
    first = jobs.add.delay(left=1, right=1)
    ordered = jobs.after(first)

    assert ordered.names == ("add", "count")
    assert len(ordered) == 2
    assert "count" in ordered
    assert list(ordered) == ["add", "count"]
    assert ordered["add"].description.id == "reg.add"
    assert first.id in repr(ordered)
    with pytest.raises(AttributeError):
        _ = ordered._private
    finish(service, workers)


def test_watch_subscribes_the_four_events_to_one_owner(
    service: JobService, workers: FakeWorkers, jobs: Jobs
) -> None:
    seen: list[tuple[str, object]] = []
    handle = jobs.add.delay(left=1, right=2)
    jobs.watch(
        handle,
        on_progress=lambda fraction: seen.append(("progress", fraction)),
        on_success=lambda result: seen.append(("success", result)),
        on_failure=lambda error: seen.append(("failure", error)),
        on_cancelled=lambda: seen.append(("cancelled", None)),
    )
    service.tick()
    workers.run_all()
    service.tick()

    assert seen == [("success", Total(total=3))]


def test_watching_a_settled_handle_replays_once(
    service: JobService, jobs: Jobs
) -> None:
    handle = jobs.add.delay(left=1, right=1)
    handle.cancel()  # before any worker saw it: settled as cancelled
    service.tick()
    assert handle.status is JobStatus.CANCELLED

    seen: list[str] = []
    jobs.watch(handle, on_cancelled=lambda: seen.append("cancelled"))

    assert seen == ["cancelled"]

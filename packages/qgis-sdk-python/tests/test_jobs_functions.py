"""``@job`` declares a function; the runtime injects the ``WorkerContext`` (decisions 38, 65).

A job is written the way an action is: keyword parameters with annotations,
a declared result, and the context first. The decorator attaches metadata and
nothing else, so the function stays an ordinary callable a test can run with
a fake context; the class form decision-13 chose is gone. Since 0.9.0 the body
is a plain ``def`` that runs in its entirety on a worker, so the injected
context is the worker's: progress and cancellation only.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Annotated, Literal

import pytest
from qgis_sdk.core import ResourceScope, WorkerContext
from qgis_sdk.declarations import QgisSdkDeclarationError, describe
from qgis_sdk.jobs import JobService, JobStatus, describe_job, job
from qgis_sdk.models import QgisSdkJobRejectedError
from qgis_sdk.testing import FakeWorkers


@dataclass(frozen=True)
class SumResult:
    total: int


@job(id="fn.sum", title="Sum two numbers")
def sum_numbers(ctx: WorkerContext, a: int, b: int = 0) -> SumResult:
    ctx.progress.report(0.5)
    return SumResult(total=a + b)


@pytest.fixture
def workers() -> FakeWorkers:
    return FakeWorkers()


@pytest.fixture
def jobs(workers: FakeWorkers) -> Iterator[JobService]:
    scope = ResourceScope()
    yield JobService(scope, workers=workers, gui_thread=lambda: False)
    scope.close()


@pytest.fixture
def drive(jobs: JobService, workers: FakeWorkers):
    """Submit, run the body on the worker, deliver: one job, one round trip."""
    jobs.tick()

    def finish() -> None:
        workers.run_all()
        jobs.tick()

    return finish


# -- declaring ------------------------------------------------------------------------


def test_a_job_function_is_described_from_its_signature() -> None:
    description = describe_job(sum_numbers)

    assert (description.id, description.title) == ("fn.sum", "Sum two numbers")
    assert description.parameters == ("a", "b")
    assert description.required == ("a",)
    assert description.inputs_schema["properties"]["a"]["type"] == "integer"
    assert description.inputs_schema["required"] == ["a"]
    assert description.result_type is SumResult
    assert description.result_schema["properties"]["total"]["type"] == "integer"
    assert description.asynchronous is False


def test_the_transport_form_carries_the_inputs_schema_and_the_result() -> None:
    payload = describe_job(sum_numbers).to_dict()

    assert payload["inputs"] == describe_job(sum_numbers).inputs_schema
    assert payload["result"] == {
        "type": "SumResult",
        "schema": describe_job(sum_numbers).result_schema,
    }
    assert payload["asynchronous"] is False


def test_the_generic_describe_answers_for_a_job_function() -> None:
    assert describe(sum_numbers).id == "fn.sum"


def test_the_decorator_leaves_the_function_callable_as_written() -> None:
    class FakeProgress:
        def __init__(self) -> None:
            self.reported: list[float] = []

        def report(self, fraction: float) -> None:
            self.reported.append(fraction)

    class FakeContext:
        def __init__(self) -> None:
            self.progress = FakeProgress()

    fake = FakeContext()
    assert sum_numbers(fake, 2, b=3) == SumResult(total=5)  # type: ignore[arg-type]
    assert fake.progress.reported == [0.5]


def test_a_bare_decorator_derives_the_id_and_title_from_the_function() -> None:
    @job
    def count_features(ctx: WorkerContext, layer_id: str) -> int:
        return 0

    description = describe_job(count_features)

    assert description.id.startswith("count_features_")
    assert description.title == "Count features"


def test_the_class_form_is_refused_with_the_way_forward() -> None:
    with pytest.raises(QgisSdkDeclarationError, match="@job declares a function"):

        @job(id="legacy.sum", title="Legacy")
        class Legacy:
            def run(self, inputs: int) -> int:
                return inputs


def test_a_duplicate_declaration_is_refused() -> None:
    with pytest.raises(QgisSdkDeclarationError, match="duplicate @job"):

        @job(id="fn.twice", title="Twice")
        @job(id="fn.once", title="Once")
        def twice(ctx: WorkerContext) -> int:
            return 1


def _missing_context(a: int) -> int:
    return a


def _context_second(a: int, ctx: WorkerContext) -> int:
    return a


def _untyped_context(ctx, a: int) -> int:  # type: ignore[no-untyped-def]
    return a


def _no_result(ctx: WorkerContext, a: int):  # type: ignore[no-untyped-def]
    return a


def _untyped_input(ctx: WorkerContext, a) -> int:  # type: ignore[no-untyped-def]
    return a


def _variadic(ctx: WorkerContext, *values: int) -> int:
    return sum(values)


def _generator(ctx: WorkerContext, a: int):  # type: ignore[no-untyped-def]
    yield a


@pytest.mark.parametrize(
    ("function", "message"),
    [
        (_missing_context, "first parameter must be the WorkerContext"),
        (_context_second, "first parameter must be the WorkerContext"),
        (_untyped_context, "first parameter must be the WorkerContext"),
        (_no_result, "must declare its result"),
        (_untyped_input, "inputs.a"),
        (_variadic, "variadic and positional-only inputs are unsupported"),
        (_generator, "not a generator"),
    ],
)
def test_a_signature_that_cannot_be_described_is_refused(function, message) -> None:
    with pytest.raises(QgisSdkDeclarationError, match=message):
        describe_job(job(id="fn.bad", title="Bad")(function))


def test_describing_an_undeclared_function_is_refused() -> None:
    def plain(ctx: WorkerContext) -> int:
        return 1

    with pytest.raises(
        QgisSdkDeclarationError, match="describe_job requires a function with @job"
    ):
        describe_job(plain)
    with pytest.raises(
        QgisSdkDeclarationError, match="describe_job requires a function with @job"
    ):
        describe_job(SumResult)  # type: ignore[arg-type]


# -- submitting -------------------------------------------------------------------------


def test_delay_takes_the_parameters_as_keywords_and_injects_the_context(
    jobs: JobService, workers: FakeWorkers, drive: Callable[[], None]
) -> None:
    handle = jobs.bind(sum_numbers).delay(a=1, b=2)

    assert handle.status is JobStatus.QUEUED
    jobs.tick()

    # The tick handed the body to a worker; only the worker runs it.
    assert handle.status is JobStatus.RUNNING
    assert workers.pending == 1

    workers.run_all()
    drive()

    assert handle.status is JobStatus.SUCCEEDED
    assert handle.result == SumResult(total=3)
    assert handle.progress == 0.5


def test_a_defaulted_parameter_may_be_omitted(
    jobs: JobService, drive: Callable[[], None]
) -> None:
    handle = jobs.bind(sum_numbers).delay(a=4)
    jobs.tick()
    drive()

    assert handle.result == SumResult(total=4)


def test_the_service_offers_delay_as_a_shorthand_for_bind_then_delay(
    jobs: JobService, drive: Callable[[], None]
) -> None:
    handle = jobs.delay(sum_numbers, a=2, b=2)
    jobs.tick()
    drive()

    assert handle.result == SumResult(total=4)
    assert handle.description.id == "fn.sum"


@pytest.mark.parametrize(
    ("arguments", "problem"),
    [
        ({"b": 1}, "missing a"),
        ({"a": 1, "c": 2}, "unexpected c"),
        ({"a": "1"}, "a must be int, not str"),
        ({"a": 1, "b": None}, "b must be int, not NoneType"),
    ],
)
def test_arguments_outside_the_signature_are_rejected_before_anything_runs(
    jobs: JobService, arguments: dict, problem: str
) -> None:
    bound = jobs.bind(sum_numbers)

    with pytest.raises(QgisSdkJobRejectedError) as raised:
        bound.delay(**arguments)

    assert raised.value.job_id == "fn.sum"
    assert problem in " ".join(raised.value.problems)
    assert jobs.active == ()


def test_positional_arguments_are_not_accepted(jobs: JobService) -> None:
    with pytest.raises(TypeError):
        jobs.bind(sum_numbers).delay(1, 2)  # type: ignore[misc]


@dataclass(frozen=True)
class Window:
    lower: int
    upper: int


@job(id="fn.typed", title="Typed inputs")
def typed(
    ctx: WorkerContext,
    window: Window,
    mode: Literal["fast", "exact"],
    label: str | None = None,
    weights: list[float] | None = None,
    unit: Annotated[str, "metres"] = "m",
) -> str:
    return f"{window.lower}-{window.upper} {mode} {label} {weights} {unit}"


def test_the_argument_check_understands_the_annotations_actions_use(
    jobs: JobService, drive: Callable[[], None]
) -> None:
    handle = jobs.bind(typed).delay(
        window=Window(1, 2), mode="fast", weights=[0.5], unit="km"
    )
    jobs.tick()
    drive()

    assert handle.result == "1-2 fast None [0.5] km"


@pytest.mark.parametrize(
    ("arguments", "problem"),
    [
        ({"window": (1, 2), "mode": "fast"}, "window must be Window, not tuple"),
        ({"window": Window(1, 2), "mode": "slow"}, "mode must be one of"),
        (
            {"window": Window(1, 2), "mode": "fast", "label": 3},
            "label must be str | None",
        ),
        (
            {"window": Window(1, 2), "mode": "fast", "weights": 0.5},
            "weights must be list",
        ),
        (
            {"window": Window(1, 2), "mode": "fast", "unit": 7},
            "unit must be str, not int",
        ),
    ],
)
def test_annotated_arguments_of_the_wrong_shape_are_rejected(
    jobs: JobService, arguments: dict, problem: str
) -> None:
    with pytest.raises(QgisSdkJobRejectedError) as raised:
        jobs.bind(typed).delay(**arguments)

    assert problem in " ".join(raised.value.problems)


def test_binding_an_undeclared_function_fails_at_bind_time(jobs: JobService) -> None:
    def plain(ctx: WorkerContext) -> int:
        return 1

    with pytest.raises(QgisSdkDeclarationError, match="requires a function with @job"):
        jobs.bind(plain)


def test_a_result_of_the_wrong_type_still_fails_the_job(
    jobs: JobService, drive: Callable[[], None]
) -> None:
    @job(id="fn.liar", title="Liar")
    def liar(ctx: WorkerContext) -> SumResult:
        return "three"  # type: ignore[return-value]

    handle = jobs.bind(liar).delay()
    jobs.tick()
    drive()

    assert handle.status is JobStatus.FAILED
    assert isinstance(handle.error, QgisSdkDeclarationError)
    assert "returned str, not the declared SumResult" in str(handle.error)

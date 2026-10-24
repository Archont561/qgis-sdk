"""The authoring surface: inspect without constructing, run with a fresh context."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from qgis_sdk.algorithms import (
    AlgorithmDescription,
    AlgorithmResult,
    algorithm,
    describe_algorithm,
    invoke,
)
from qgis_sdk.core import AlgorithmContext, ResourceScope
from qgis_sdk.declarations import QgisSdkDeclarationError
from qgis_sdk.models import (
    BufferRequest,
    CentroidRequest,
    QgisSdkAlgorithmCancelledError,
    QgisSdkAlgorithmRejectedError,
    QgisSdkScopeClosedError,
    VectorLayerInfo,
)
from qgis_sdk.reference import BufferLayer, BufferResult, CentroidLayer, CentroidResult
from qgis_sdk.testing import FakeAlgorithms, FakeLayers, FakeProject


@dataclass(frozen=True, slots=True)
class Request:
    value: str


@dataclass(frozen=True, slots=True)
class Result:
    output: VectorLayerInfo


class Clock:
    """A cancellation signal a test can flip, including from inside ``run``."""

    def __init__(self, cancelled: bool = False) -> None:
        self.cancelled = cancelled

    def is_cancelled(self) -> bool:
        return self.cancelled


class Silent:
    """Count nothing; present so a test can pass a Progress explicitly."""

    def report(self, fraction: float) -> None:
        """Ignore the fraction."""


def _declared(
    source: Path = Path("output.gpkg"),
) -> tuple[FakeAlgorithms, FakeLayers, FakeProject, ResourceScope]:
    """Build the three fakes over one scope with a source and declared outputs."""
    scope = ResourceScope()
    layers = FakeLayers(scope)
    layers.register(
        Path("source.gpkg"),
        name="points",
        geometry_type="point",
        field_names=("id", "value"),
        crs="EPSG:4326",
    )
    layers.open_vector(Path("source.gpkg"))
    algorithms = FakeAlgorithms(layers, scope)
    algorithms.declare_output(
        BufferRequest,
        source,
        name="buffer",
        geometry_type="polygon",
        field_names=("id", "value"),
        crs="EPSG:3857",
    )
    algorithms.declare_output(
        CentroidRequest,
        source.with_name("centroid.gpkg"),
        name="centroid",
        geometry_type="point",
        field_names=("id", "value"),
        crs="EPSG:4326",
    )
    return algorithms, layers, FakeProject(layers, scope), scope


def test_describing_an_algorithm_never_constructs_it() -> None:
    constructions: list[AlgorithmContext] = []

    @algorithm(id="test.observe", title="Observe")
    class Observed:
        def __init__(self, ctx: AlgorithmContext) -> None:
            constructions.append(ctx)

        def run(self, inputs: Request) -> Result:
            raise AssertionError("describe_algorithm must not call run")

    description = describe_algorithm(Observed)

    assert (description.id, description.title) == ("test.observe", "Observe")
    assert constructions == []
    assert description.inputs_schema["required"] == ["value"]
    assert description.inputs_schema["properties"]["value"] == {"type": "string"}


def test_the_description_names_its_types_for_a_generator() -> None:
    description = describe_algorithm(BufferLayer)

    payload = description.to_dict()
    assert payload["schema_version"] == 1
    assert payload["inputs"]["type"] == "BufferRequest"
    assert payload["result"]["type"] == "BufferResult"
    # The working CRS is required by the generated contract, not just by prose:
    # a bridge client cannot omit it and let the adapter guess.
    assert "working_crs" in payload["inputs"]["schema"]["required"]


def test_a_description_can_be_json_encoded() -> None:
    import json

    encoded = json.dumps(describe_algorithm(CentroidLayer).to_dict())

    assert '"reference.centroid"' in encoded


@pytest.mark.parametrize(
    ("build", "message"),
    [
        (lambda: describe_algorithm(type("Bare", (), {})), "requires a class with"),
        (
            lambda: describe_algorithm(
                type("HandSet", (), {"__qgis_sdk_algorithm__": object()})
            ),
            "requires a class with",
        ),
    ],
)
def test_an_undecorated_class_is_refused(build, message) -> None:
    with pytest.raises(QgisSdkDeclarationError, match=message):
        build()


def test_a_decorated_class_without_run_is_refused() -> None:
    cls = algorithm(id="test.norun", title="No run")(type("NoRun", (), {}))

    with pytest.raises(QgisSdkDeclarationError, match="needs its own run method"):
        describe_algorithm(cls)


def test_a_duplicate_declaration_is_refused() -> None:
    @algorithm(id="test.once", title="Once")
    class Once:
        def run(self, inputs: Request) -> Result: ...

    with pytest.raises(QgisSdkDeclarationError, match="duplicate"):
        algorithm(id="test.once", title="Once")(Once)


def test_decorating_a_non_class_is_refused() -> None:
    with pytest.raises(QgisSdkDeclarationError, match="requires a class"):
        algorithm(id="test.fn", title="Fn")(lambda: None)


@pytest.mark.parametrize(
    ("run", "message"),
    [
        (lambda self: None, "exactly one typed inputs"),
        (lambda self, a, b: None, "exactly one typed inputs"),
        (lambda not_self, inputs: None, "exactly one typed inputs"),
    ],
)
def test_a_run_with_the_wrong_shape_is_refused(run, message) -> None:
    cls = algorithm(id="test.shape", title="Shape")(type("Shape", (), {"run": run}))

    with pytest.raises(QgisSdkDeclarationError, match=message):
        describe_algorithm(cls)


def _unannotated_inputs(self, inputs):
    return None


def _unannotated_result(self, inputs: Request):
    return None


@pytest.mark.parametrize(
    ("run", "message"),
    [
        (_unannotated_inputs, "inputs must be annotated"),
        (_unannotated_result, "must declare its result"),
    ],
)
def test_run_must_annotate_both_sides(run, message) -> None:
    cls = algorithm(id="test.hints", title="Hints")(type("Hints", (), {"run": run}))

    with pytest.raises(QgisSdkDeclarationError, match=message):
        describe_algorithm(cls)


def test_an_annotation_outside_the_contract_subset_is_refused_at_inspection() -> None:
    def run(self, inputs: dict) -> Result: ...

    cls = algorithm(id="test.subset", title="Subset")(type("Subset", (), {"run": run}))

    with pytest.raises(QgisSdkDeclarationError, match="unsupported annotation"):
        describe_algorithm(cls)


def test_each_invocation_gets_a_fresh_instance_and_a_fresh_context() -> None:
    seen: list[tuple[object, AlgorithmContext]] = []

    @algorithm(id="test.fresh", title="Fresh")
    class Fresh:
        def __init__(self, ctx: AlgorithmContext) -> None:
            self.ctx = ctx

        def run(self, inputs: Request) -> Result:
            seen.append((self, self.ctx))
            return Result(
                output=self.ctx.algorithms.execute(
                    BufferRequest(
                        layer_id="layer-1",
                        distance_metres=1.0,
                        working_crs="EPSG:3857",
                    )
                )
            )

    algorithms, _, project, scope = _declared()
    for _ in range(2):
        invoke(
            Fresh,
            Request(value="x"),
            algorithms=algorithms,
            project=project,
            scope=scope,
        )
    scope.close()

    first, second = seen
    assert first[0] is not second[0], "the author instance must not be reused"
    assert first[1] is not second[1], "the context must not be reused"
    assert first[1].scope is not second[1].scope
    assert (first[1].scope.closed, second[1].scope.closed) == (True, True)


def _output() -> VectorLayerInfo:
    """A standalone description, for tests that inspect the result only."""
    return VectorLayerInfo(
        id="layer-1",
        name="buffer",
        geometry_type="polygon",
        field_names=("id",),
        crs="EPSG:3857",
    )


def test_a_successful_invocation_adds_the_output_to_the_project() -> None:
    algorithms, _, project, scope = _declared()

    result = invoke(
        BufferLayer,
        BufferRequest(
            layer_id="layer-1", distance_metres=10.0, working_crs="EPSG:3857"
        ),
        algorithms=algorithms,
        project=project,
        scope=scope,
    )

    assert isinstance(result, AlgorithmResult)
    assert project.layer_ids() == (result.output.id,)
    assert algorithms.requests == [
        BufferRequest(layer_id="layer-1", distance_metres=10.0, working_crs="EPSG:3857")
    ]


def test_the_default_services_are_used_when_none_are_supplied() -> None:
    algorithms, _, project, scope = _declared()

    result = invoke(
        CentroidLayer,
        CentroidRequest(layer_id="layer-1"),
        algorithms=algorithms,
        project=project,
        scope=scope,
    )

    assert result.output.geometry_type == "point"
    assert project.layer_ids() == (result.output.id,)


def test_inputs_of_the_wrong_type_are_refused_before_anything_runs() -> None:
    algorithms, _, project, scope = _declared()

    with pytest.raises(QgisSdkAlgorithmRejectedError) as error:
        invoke(
            BufferLayer,
            CentroidRequest(layer_id="layer-1"),
            algorithms=algorithms,
            project=project,
            scope=scope,
        )

    assert error.value.request == "reference.buffer"
    assert "BufferRequest" in error.value.reasons[0]
    assert (algorithms.requests, project.layer_ids()) == ([], ())


def test_cancellation_before_the_operation_starts_runs_nothing() -> None:
    algorithms, _, project, scope = _declared()

    with pytest.raises(QgisSdkAlgorithmCancelledError) as error:
        invoke(
            BufferLayer,
            BufferRequest(
                layer_id="layer-1", distance_metres=1.0, working_crs="EPSG:3857"
            ),
            algorithms=algorithms,
            project=project,
            scope=scope,
            cancellation=Clock(cancelled=True),
        )

    assert error.value.algorithm_id == "reference.buffer"
    assert (algorithms.requests, project.layer_ids()) == ([], ())


def test_cancellation_after_the_operation_keeps_the_output_out_of_the_project() -> None:
    algorithms, _, project, scope = _declared()
    clock = Clock()

    @algorithm(id="test.cancel", title="Cancel")
    class CancelAfter:
        def __init__(self, ctx: AlgorithmContext) -> None:
            self.ctx = ctx

        def run(self, inputs: Request) -> Result:
            self.ctx.algorithms.execute(
                BufferRequest(
                    layer_id="layer-1", distance_metres=1.0, working_crs="EPSG:3857"
                )
            )
            clock.cancelled = True
            return Result(output=_output())

    with pytest.raises(QgisSdkAlgorithmCancelledError):
        invoke(
            CancelAfter,
            Request(value="x"),
            algorithms=algorithms,
            project=project,
            scope=scope,
            cancellation=clock,
            progress=Silent(),
        )

    assert project.layer_ids() == ()


def test_a_failing_algorithm_leaves_the_project_untouched() -> None:
    algorithms, _, project, scope = _declared()

    @algorithm(id="test.fail", title="Fail")
    class Failing:
        def __init__(self, ctx: AlgorithmContext) -> None:
            self.ctx = ctx

        def run(self, inputs: Request) -> Result:
            raise QgisSdkValidationIssueError("boom")

    with pytest.raises(QgisSdkValidationIssueError):
        invoke(
            Failing,
            Request(value="x"),
            algorithms=algorithms,
            project=project,
            scope=scope,
        )

    assert project.layer_ids() == ()


class QgisSdkValidationIssueError(Exception):
    """A local failure, to prove nothing is added on the way out."""


def test_a_result_of_the_wrong_type_is_refused_and_not_added() -> None:
    algorithms, _, project, scope = _declared()

    @algorithm(id="test.wrong", title="Wrong")
    class Wrong:
        def __init__(self, ctx: AlgorithmContext) -> None:
            self.ctx = ctx

        def run(self, inputs: Request) -> Result:
            return "not a result"  # type: ignore[return-value]

    with pytest.raises(QgisSdkDeclarationError, match="not the declared"):
        invoke(
            Wrong,
            Request(value="x"),
            algorithms=algorithms,
            project=project,
            scope=scope,
        )

    assert project.layer_ids() == ()


def test_invoking_after_the_owner_scope_closed_is_refused() -> None:
    algorithms, _, project, scope = _declared()
    scope.close()

    with pytest.raises(QgisSdkScopeClosedError):
        invoke(
            BufferLayer,
            BufferRequest(
                layer_id="layer-1", distance_metres=1.0, working_crs="EPSG:3857"
            ),
            algorithms=algorithms,
            project=project,
            scope=scope,
        )


def test_the_description_keeps_the_annotations_it_checked() -> None:
    description = describe_algorithm(BufferLayer)

    assert isinstance(description, AlgorithmDescription)
    assert (description.inputs_type, description.result_type) == (
        BufferRequest,
        BufferResult,
    )
    assert description.result_schema["required"] == ["output"]


def test_a_reference_algorithm_only_binds_request_to_result() -> None:
    algorithms, _, project, scope = _declared()

    result = invoke(
        CentroidLayer,
        CentroidRequest(layer_id="layer-1"),
        algorithms=algorithms,
        project=project,
        scope=scope,
    )

    assert isinstance(result.output, VectorLayerInfo)
    assert algorithms.requests == [CentroidRequest(layer_id="layer-1")]


def test_the_reference_classes_are_declared_against_the_documented_ids() -> None:
    assert describe_algorithm(BufferLayer).id == "reference.buffer"
    assert describe_algorithm(CentroidLayer).id == "reference.centroid"
    assert describe_algorithm(CentroidLayer).result_type is CentroidResult


@pytest.mark.parametrize(
    ("build", "message"),
    [
        (
            lambda: BufferRequest(
                layer_id="", distance_metres=1.0, working_crs="EPSG:3857"
            ),
            "layer_id is required",
        ),
        (
            lambda: BufferRequest(
                layer_id="a", distance_metres=0.0, working_crs="EPSG:3857"
            ),
            "positive finite",
        ),
        (
            lambda: BufferRequest(
                layer_id="a", distance_metres=float("nan"), working_crs="EPSG:3857"
            ),
            "positive finite",
        ),
        (
            lambda: BufferRequest(layer_id="a", distance_metres=1.0, working_crs="  "),
            "working_crs is required",
        ),
        (lambda: CentroidRequest(layer_id=""), "layer_id is required"),
    ],
)
def test_a_request_without_its_explicit_values_is_refused(build, message) -> None:
    with pytest.raises(QgisSdkAlgorithmRejectedError) as error:
        build()

    assert message in error.value.reasons[0]
    assert error.value.request in {"buffer", "centroid"}


def test_a_refusal_reports_every_reason_at_once() -> None:
    with pytest.raises(QgisSdkAlgorithmRejectedError) as error:
        BufferRequest(layer_id="", distance_metres=-1.0, working_crs="")

    assert len(error.value.reasons) == 3


def test_the_working_crs_cannot_be_omitted_positionally_by_accident() -> None:
    with pytest.raises(TypeError):
        BufferRequest("layer", 10.0)  # type: ignore[call-arg]


def test_an_unknown_request_type_is_refused_by_the_fake() -> None:
    algorithms, _, _, _scope = _declared()

    @dataclass(frozen=True, slots=True)
    class Undeclared:
        layer_id: str

    with pytest.raises(QgisSdkAlgorithmRejectedError, match="no output declared"):
        algorithms.execute(Undeclared(layer_id="layer-1"))  # type: ignore[arg-type]


def test_the_fake_refuses_after_its_scope_closed() -> None:
    algorithms, _, _, scope = _declared()
    scope.close()

    with pytest.raises(QgisSdkScopeClosedError):
        algorithms.execute(CentroidRequest(layer_id="layer-1"))


def test_an_algorithm_description_is_not_mutable() -> None:
    from dataclasses import FrozenInstanceError

    description = describe_algorithm(BufferLayer)

    with pytest.raises(FrozenInstanceError):
        description.id = "other"  # type: ignore[misc]


def test_progress_is_handed_to_the_context_unchanged() -> None:
    seen: list[Any] = []

    @algorithm(id="test.progress", title="Progress")
    class Reporting:
        def __init__(self, ctx: AlgorithmContext) -> None:
            self.ctx = ctx

        def run(self, inputs: Request) -> Result:
            seen.append(self.ctx.progress)
            return Result(
                output=self.ctx.algorithms.execute(CentroidRequest(layer_id="layer-1"))
            )

    algorithms, _, project, scope = _declared()
    progress = Silent()
    invoke(
        Reporting,
        Request(value="x"),
        algorithms=algorithms,
        project=project,
        scope=scope,
        progress=progress,
    )

    assert seen == [progress]

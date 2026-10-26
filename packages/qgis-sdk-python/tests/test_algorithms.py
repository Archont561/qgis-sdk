"""The authoring surface: inspect a function without calling it, run it with a fresh context."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

import pytest
from qgis_sdk.algorithms import AlgorithmDescription, describe_algorithm, invoke
from qgis_sdk.core import AlgorithmContext, JobContext, PluginContext, ResourceScope
from qgis_sdk.declarations import QgisSdkDeclarationError, describe
from qgis_sdk.models import (
    BufferRequest,
    CentroidRequest,
    CrsInput,
    LayerInput,
    LayerParameter,
    Metres,
    MetresParameter,
    QgisSdkAlgorithmCancelledError,
    QgisSdkAlgorithmRejectedError,
    QgisSdkScopeClosedError,
    QgisSdkUnsupportedCapabilityError,
    VectorLayerInfo,
)
from qgis_sdk.providers import Provider
from qgis_sdk.reference import buffer_layer, centroid_layer, reference_provider
from qgis_sdk.testing import (
    FakeAlgorithms,
    FakeLayers,
    FakeProject,
    RecordingNotifications,
)


class Clock:
    """A cancellation signal a test can flip, including from inside the function."""

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


def _plugin_context(
    algorithms: FakeAlgorithms, project: FakeProject, scope: ResourceScope
) -> PluginContext:
    return PluginContext(
        notifications=RecordingNotifications(scope),
        scope=scope,
        algorithms=algorithms,
        project=project,
    )


def _provider() -> Provider:
    return Provider(id="test", title="Test provider")


BUFFER = {"layer_id": "layer-1", "distance_metres": 10.0, "working_crs": "EPSG:3857"}


# -- describe_algorithm: inputs, kinds, required names, result ---------------------


def test_describing_an_algorithm_never_calls_it() -> None:
    calls: list[Any] = []
    provider = _provider()

    @provider.algorithm(id="observe", title="Observe")
    def observe(ctx: AlgorithmContext, value: str, count: int = 1) -> VectorLayerInfo:
        calls.append(ctx)
        raise AssertionError("describe_algorithm must not call the function")

    description = describe_algorithm(observe)

    assert isinstance(description, AlgorithmDescription)
    assert (description.id, description.title) == ("observe", "Observe")
    assert description.qualified_id == "test:observe"
    assert calls == []
    assert description.parameters == ("value", "count")
    assert description.required == ("value",)
    assert description.kinds == {"value": "string", "count": "integer"}
    assert description.annotations == {"value": str, "count": int}
    assert description.result_type is VectorLayerInfo
    assert description.inputs_schema["required"] == ["value"]
    assert description.inputs_schema["properties"]["count"]["type"] == "integer"
    assert description.result_schema["required"][0] == "id"


def test_the_reference_algorithms_report_their_kinds_and_qualified_ids() -> None:
    buffer = describe_algorithm(buffer_layer)

    assert buffer.id == "buffer"
    assert buffer.group == "Geometry"
    assert buffer.kinds == {
        "layer_id": "layer",
        "distance_metres": "metres",
        "working_crs": "crs",
    }
    assert buffer.required == ("layer_id", "distance_metres", "working_crs")
    assert describe_algorithm(centroid_layer).kinds == {"layer_id": "layer"}
    qualified = [
        algorithm["qualified_id"]
        for algorithm in reference_provider.describe().to_dict()["algorithms"]
    ]
    assert qualified == ["reference:buffer", "reference:centroid"]


def test_the_description_serialises_without_live_types() -> None:
    import json

    payload = describe_algorithm(buffer_layer).to_dict()

    assert payload["schema_version"] == 1
    assert payload["provider"] == "reference"
    assert payload["parameters"] == {
        "layer_id": "layer",
        "distance_metres": "metres",
        "working_crs": "crs",
    }
    # The working CRS is required by the generated contract, not just by prose.
    assert "working_crs" in payload["inputs"]["required"]
    assert payload["result"]["type"] == "VectorLayerInfo"
    assert '"centroid"' in json.dumps(describe_algorithm(centroid_layer).to_dict())


def test_the_alias_and_the_explicit_annotated_form_describe_identically() -> None:
    provider = _provider()

    @provider.algorithm
    def aliased(
        ctx: AlgorithmContext, layer: LayerInput, distance: Metres, crs: CrsInput
    ) -> VectorLayerInfo: ...

    @provider.algorithm
    def explicit(
        ctx: AlgorithmContext,
        layer: Annotated[str, LayerParameter()],
        distance: Annotated[float, MetresParameter()],
        crs: CrsInput,
    ) -> VectorLayerInfo: ...

    first, second = describe_algorithm(aliased), describe_algorithm(explicit)

    assert (
        first.kinds
        == second.kinds
        == {
            "layer": "layer",
            "distance": "metres",
            "crs": "crs",
        }
    )
    assert first.inputs_schema == second.inputs_schema
    assert first.annotations == second.annotations


def test_a_bounded_distance_keeps_the_metres_kind() -> None:
    provider = _provider()

    @provider.algorithm
    def bounded(
        ctx: AlgorithmContext,
        distance: Annotated[float, MetresParameter(minimum=1.0, maximum=50.0)],
    ) -> VectorLayerInfo: ...

    assert describe_algorithm(bounded).kinds == {"distance": "metres"}


def test_describe_dispatches_to_the_algorithm_describer() -> None:
    assert describe(buffer_layer) == describe_algorithm(buffer_layer)


@pytest.mark.parametrize(
    ("build", "message"),
    [
        (lambda: describe_algorithm(lambda ctx: None), "requires a function with"),
        (lambda: describe_algorithm(type("Bare", (), {})), "requires a function with"),
    ],
)
def test_an_undeclared_target_is_refused(build, message) -> None:
    with pytest.raises(QgisSdkDeclarationError, match=message):
        build()


def test_a_hand_set_marker_is_refused() -> None:
    def forged(ctx: AlgorithmContext) -> VectorLayerInfo: ...

    forged.__qgis_sdk_algorithm__ = object()  # type: ignore[attr-defined]

    with pytest.raises(QgisSdkDeclarationError, match="requires a function with"):
        describe_algorithm(forged)


def test_an_algorithm_description_is_not_mutable() -> None:
    from dataclasses import FrozenInstanceError

    description = describe_algorithm(buffer_layer)

    with pytest.raises(FrozenInstanceError):
        description.id = "other"  # type: ignore[misc]


# -- invoke: one runner from any context ---------------------------------------------


def test_each_invocation_gets_a_fresh_context_over_a_child_scope() -> None:
    seen: list[AlgorithmContext] = []
    provider = _provider()

    @provider.algorithm
    def fresh(ctx: AlgorithmContext, value: str) -> VectorLayerInfo:
        seen.append(ctx)
        # The caller's own services, under a scope of this invocation's own.
        assert (ctx.algorithms, ctx.project) == (algorithms, project)
        return ctx.algorithms.execute(CentroidRequest(layer_id="layer-1"))

    algorithms, _, project, scope = _declared()
    ctx = _plugin_context(algorithms, project, scope)
    for _ in range(2):
        invoke(fresh, ctx, value="x")
    scope.close()

    first, second = seen
    assert first is not second, "the context must not be reused"
    assert first.scope is not second.scope
    assert first.scope is not scope
    assert (first.scope.closed, second.scope.closed) == (True, True)


def test_a_successful_invocation_adds_the_output_to_the_project() -> None:
    algorithms, _, project, scope = _declared()

    output = invoke(buffer_layer, _plugin_context(algorithms, project, scope), **BUFFER)

    assert isinstance(output, VectorLayerInfo)
    assert project.layer_ids() == (output.id,)
    assert algorithms.requests == [BufferRequest(**BUFFER)]


def test_add_to_project_false_leaves_presentation_to_the_caller() -> None:
    algorithms, _, project, scope = _declared()
    ctx = _plugin_context(algorithms, project, scope)

    output = invoke(centroid_layer, ctx, add_to_project=False, layer_id="layer-1")

    assert output.geometry_type == "point"
    assert project.layer_ids() == ()


def test_invoke_runs_from_a_job_context() -> None:
    algorithms, _, project, scope = _declared()
    seen: list[AlgorithmContext] = []
    provider = _provider()

    @provider.algorithm
    def observe(ctx: AlgorithmContext, layer_id: LayerInput) -> VectorLayerInfo:
        seen.append(ctx)
        return ctx.algorithms.execute(CentroidRequest(layer_id=layer_id))

    progress, clock = Silent(), Clock()
    ctx = JobContext(
        progress=progress,
        cancellation=clock,
        scope=scope,
        algorithms=algorithms,
        project=project,
    )

    output = invoke(observe, ctx, layer_id="layer-1")

    assert project.layer_ids() == (output.id,)
    # Left out, progress and cancellation are the job's own.
    assert (seen[0].progress, seen[0].cancellation) == (progress, clock)
    assert seen[0].scope is not scope


def test_invoke_runs_from_an_algorithm_context_for_composition() -> None:
    algorithms, _, project, scope = _declared()
    provider = _provider()
    inner_contexts: list[AlgorithmContext] = []

    @provider.algorithm
    def inner(ctx: AlgorithmContext, layer_id: LayerInput) -> VectorLayerInfo:
        inner_contexts.append(ctx)
        return ctx.algorithms.execute(CentroidRequest(layer_id=layer_id))

    @provider.algorithm
    def outer(ctx: AlgorithmContext, layer_id: LayerInput) -> VectorLayerInfo:
        return invoke(inner, ctx, add_to_project=False, layer_id=layer_id)

    output = invoke(
        outer, _plugin_context(algorithms, project, scope), layer_id="layer-1"
    )

    assert project.layer_ids() == (output.id,)
    assert inner_contexts[0].scope.closed
    assert algorithms.requests == [CentroidRequest(layer_id="layer-1")]


def test_a_job_context_without_processing_refuses_by_name() -> None:
    scope = ResourceScope()
    ctx = JobContext(progress=Silent(), cancellation=Clock(), scope=scope)

    with pytest.raises(QgisSdkUnsupportedCapabilityError, match="algorithms"):
        invoke(centroid_layer, ctx, layer_id="layer-1")


def test_adding_to_a_project_the_context_lacks_refuses_before_anything_runs() -> None:
    algorithms, _, _project, scope = _declared()
    ctx = PluginContext(
        notifications=RecordingNotifications(scope), scope=scope, algorithms=algorithms
    )

    with pytest.raises(QgisSdkUnsupportedCapabilityError, match="project"):
        invoke(centroid_layer, ctx, layer_id="layer-1")

    assert algorithms.requests == []


def test_something_other_than_a_context_is_refused_with_the_new_shape() -> None:
    with pytest.raises(QgisSdkDeclarationError, match="PluginContext, JobContext"):
        invoke(buffer_layer, BufferRequest(**BUFFER))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("inputs", "reason"),
    [
        ({"layer_id": "layer-1", "distance_metres": 1.0}, "working_crs is required"),
        ({**BUFFER, "extra": 1}, "unknown input 'extra'"),
        ({**BUFFER, "distance_metres": "far"}, "distance_metres must be a number"),
        ({**BUFFER, "layer_id": 3}, "layer_id must be a str layer id"),
        ({**BUFFER, "distance_metres": True}, "distance_metres must be a number"),
    ],
)
def test_inputs_of_the_wrong_shape_are_refused_before_anything_runs(
    inputs, reason
) -> None:
    algorithms, _, project, scope = _declared()

    with pytest.raises(QgisSdkAlgorithmRejectedError) as error:
        invoke(buffer_layer, _plugin_context(algorithms, project, scope), **inputs)

    assert error.value.request == "buffer"
    assert any(reason in item for item in error.value.reasons)
    assert (algorithms.requests, project.layer_ids()) == ([], ())


def test_a_refusal_reports_every_reason_at_once() -> None:
    algorithms, _, project, scope = _declared()

    with pytest.raises(QgisSdkAlgorithmRejectedError) as error:
        invoke(
            buffer_layer,
            _plugin_context(algorithms, project, scope),
            layer_id=1,
            extra=True,
        )

    assert len(error.value.reasons) == 4


def test_the_function_still_has_the_last_word_on_the_values() -> None:
    algorithms, _, project, scope = _declared()

    with pytest.raises(QgisSdkAlgorithmRejectedError) as error:
        invoke(
            buffer_layer,
            _plugin_context(algorithms, project, scope),
            **{**BUFFER, "working_crs": "  "},
        )

    assert "working_crs is required" in error.value.reasons[0]
    assert (algorithms.requests, project.layer_ids()) == ([], ())


def test_cancellation_before_the_operation_starts_runs_nothing() -> None:
    algorithms, _, project, scope = _declared()

    with pytest.raises(QgisSdkAlgorithmCancelledError) as error:
        invoke(
            buffer_layer,
            _plugin_context(algorithms, project, scope),
            cancellation=Clock(cancelled=True),
            **BUFFER,
        )

    assert error.value.algorithm_id == "buffer"
    assert (algorithms.requests, project.layer_ids()) == ([], ())


def test_cancellation_after_the_operation_keeps_the_output_out_of_the_project() -> None:
    algorithms, _, project, scope = _declared()
    clock = Clock()
    provider = _provider()

    @provider.algorithm
    def cancel_after(ctx: AlgorithmContext, value: str) -> VectorLayerInfo:
        output = ctx.algorithms.execute(CentroidRequest(layer_id="layer-1"))
        clock.cancelled = True
        return output

    with pytest.raises(QgisSdkAlgorithmCancelledError):
        invoke(
            cancel_after,
            _plugin_context(algorithms, project, scope),
            cancellation=clock,
            progress=Silent(),
            value="x",
        )

    assert project.layer_ids() == ()


def test_a_failing_algorithm_leaves_the_project_untouched() -> None:
    algorithms, _, project, scope = _declared()
    provider = _provider()

    @provider.algorithm
    def failing(ctx: AlgorithmContext, value: str) -> VectorLayerInfo:
        raise QgisSdkValidationIssueError("boom")

    with pytest.raises(QgisSdkValidationIssueError):
        invoke(failing, _plugin_context(algorithms, project, scope), value="x")

    assert project.layer_ids() == ()


class QgisSdkValidationIssueError(Exception):
    """A local failure, to prove nothing is added on the way out."""


def test_a_result_of_the_wrong_type_is_refused_and_not_added() -> None:
    algorithms, _, project, scope = _declared()
    provider = _provider()

    @provider.algorithm
    def wrong(ctx: AlgorithmContext, value: str) -> VectorLayerInfo:
        return "not a layer"  # type: ignore[return-value]

    with pytest.raises(QgisSdkDeclarationError, match="not the declared"):
        invoke(wrong, _plugin_context(algorithms, project, scope), value="x")

    assert project.layer_ids() == ()


def test_invoking_after_the_owner_scope_closed_is_refused() -> None:
    algorithms, _, project, scope = _declared()
    ctx = _plugin_context(algorithms, project, scope)
    scope.close()

    with pytest.raises(QgisSdkScopeClosedError):
        invoke(buffer_layer, ctx, **BUFFER)


def test_progress_is_handed_to_the_context_unchanged() -> None:
    seen: list[Any] = []
    provider = _provider()

    @provider.algorithm
    def reporting(ctx: AlgorithmContext, value: str) -> VectorLayerInfo:
        seen.append(ctx.progress)
        return ctx.algorithms.execute(CentroidRequest(layer_id="layer-1"))

    algorithms, _, project, scope = _declared()
    progress = Silent()
    invoke(
        reporting,
        _plugin_context(algorithms, project, scope),
        progress=progress,
        value="x",
    )

    assert seen == [progress]


def test_a_function_can_be_called_directly_with_a_fake_context() -> None:
    """Nothing is injected at decoration: a unit test needs no runner at all."""
    algorithms, _, _project, scope = _declared()
    ctx = AlgorithmContext(
        progress=Silent(), cancellation=Clock(), scope=scope, algorithms=algorithms
    )

    output = centroid_layer(ctx, layer_id="layer-1")

    assert output.geometry_type == "point"
    assert algorithms.requests == [CentroidRequest(layer_id="layer-1")]


# -- the request models the reference functions build ------------------------------


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


def test_a_request_refusal_reports_every_reason_at_once() -> None:
    with pytest.raises(QgisSdkAlgorithmRejectedError) as error:
        BufferRequest(layer_id="", distance_metres=-1.0, working_crs="")

    assert len(error.value.reasons) == 3


def test_the_working_crs_cannot_be_omitted_positionally_by_accident() -> None:
    with pytest.raises(TypeError):
        BufferRequest("layer", 10.0)  # type: ignore[call-arg]


def test_an_unknown_request_type_is_refused_by_the_fake() -> None:
    from dataclasses import dataclass

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

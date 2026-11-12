from __future__ import annotations

from collections.abc import Callable
from typing import Any

from qgis_sdk._published import REQUIRED, published
from qgis_sdk.core import (
    AlgorithmContext,
    AlgorithmServices,
    JobContext,
    PluginContext,
    ResourceScope,
)
from qgis_sdk.declarations import (
    QgisSdkDeclarationError,
    type_name,
)
from qgis_sdk.models import (
    AlgorithmResult,
    QgisSdkAlgorithmCancelledError,
    RasterLayerInfo,
    VectorLayerInfo,
    output_kinds,
)
from qgis_sdk.services import Cancellation, Progress

from ._declaration import (
    CONTEXTS,
    AlgorithmDescription,
    InvokeRequest,
    Run,
    check_inputs,
    describe_algorithm,
    invoke_controls,
)


def _run_context(
    ctx: PluginContext | JobContext | AlgorithmContext,
    description: AlgorithmDescription,
    progress: Progress,
    cancellation: Cancellation,
    add_to_project: bool,
) -> tuple[AlgorithmContext, ResourceScope, Any]:
    """Build a fresh AlgorithmContext over a child scope for one call."""
    ctx.scope.ensure_open()
    algorithms = ctx.algorithms
    project = ctx.project if add_to_project or ctx.has("project") else None
    network = ctx.network if ctx.has("network") else None
    if cancellation.is_cancelled():
        raise QgisSdkAlgorithmCancelledError(description.id)
    scope = ctx.scope.child()
    context = AlgorithmContext(
        progress=progress,
        cancellation=cancellation,
        scope=scope,
        services=AlgorithmServices(
            algorithms=algorithms, project=project, network=network
        ),
    )
    return context, scope, project


def _run(run: Run) -> AlgorithmResult:
    """Run the body, check its result, then commit layers - in that order.

    Ordering is the whole safety story (decision-19): inputs were already
    checked, cancellation was read before anything runs, the function runs
    into a new output, the result is checked against the declared type,
    cancellation is read once more, and only then is the output added to the
    project. A failure or cancellation at any point leaves the project as it
    was, and the child scope always closes.
    """
    request = run.request
    try:
        result = request.function(run.context, **request.inputs)
        _check_result(run.description, result)
        if run.cancellation.is_cancelled():
            raise QgisSdkAlgorithmCancelledError(run.description.id)
        if request.add_to_project:
            assert run.project is not None
            for layer_id in _produced_layers(result):
                run.project.add_layer(layer_id)
    finally:
        run.scope.close()
    return result


def _execute(request: InvokeRequest) -> AlgorithmResult:
    """Validate the call, then run it through one child-scoped context."""
    description = describe_algorithm(request.function)
    if not isinstance(request.ctx, CONTEXTS):
        raise QgisSdkDeclarationError(
            f"invoke({description.id}): the second argument is the context the "
            "runtime injected (a PluginContext, JobContext or AlgorithmContext), "
            f"not {type_name(type(request.ctx))}; inputs are keyword arguments"
        )
    check_inputs(description, request.inputs)
    progress, cancellation = invoke_controls(
        request.ctx, request.progress, request.cancellation
    )
    context, scope, project = _run_context(
        request.ctx,
        description,
        progress,
        cancellation,
        request.add_to_project,
    )
    return _run(Run(request, description, context, scope, project, cancellation))


_CC_SPECS_invoke_1 = (
    ("function", Callable[..., Any], REQUIRED, "positional_only"),
    ("ctx", PluginContext | JobContext | AlgorithmContext, REQUIRED, "positional_only"),
    ("progress", Progress | None, None, "keyword"),
    ("cancellation", Cancellation | None, None, "keyword"),
    ("add_to_project", bool, True, "keyword"),
    ("inputs", Any, REQUIRED, "var_keyword"),
)


@published(_CC_SPECS_invoke_1, returns=AlgorithmResult)
def invoke(_published_values):
    """Run one declared algorithm once from the context the caller already holds.

    ``ctx`` is a PluginContext, JobContext or AlgorithmContext; ``invoke``
    builds a new AlgorithmContext over a child scope and closes it afterwards,
    so nothing an invocation registers outlives it (decision-11, decision-42).
    ``progress``/``cancellation`` omitted are inherited from a job or algorithm
    context. ``add_to_project=False`` leaves the produced layers with the
    caller; the default adds them to ``ctx.project`` on success.
    """
    return _execute(
        InvokeRequest(
            _published_values.function,
            _published_values.ctx,
            dict(_published_values.inputs),
            _published_values.progress,
            _published_values.cancellation,
            _published_values.add_to_project,
        )
    )


def _check_result(description: AlgorithmDescription, result: Any) -> None:
    """Check the handler's result against the declared output kind."""
    kind = output_kinds()[description.result_kind]
    if kind.name == "outputMultilayer":
        accepted = isinstance(result, tuple) and all(
            isinstance(item, VectorLayerInfo) for item in result
        )
    else:
        accepted = isinstance(result, kind.accepted)
    if not accepted:
        raise QgisSdkDeclarationError(
            f"{description.id}: returned {type_name(type(result))}, not the "
            f"declared {kind.result}"
        )


def _produced_layers(result: Any) -> tuple[str, ...]:
    """The layer ids one produced result carries, for ``add_to_project``.

    Layer kinds are added to the project; files, folders, reports and values
    are the caller's to place (decision-19: the project changes last, and a
    file is not a layer).
    """
    if isinstance(result, (VectorLayerInfo, RasterLayerInfo)):
        return (result.id,)
    if isinstance(result, tuple):
        return tuple(item.id for item in result if isinstance(item, VectorLayerInfo))
    return ()

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
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
    AlgorithmDescription,
    check_inputs,
    describe_algorithm,
)

CONTEXTS = (PluginContext, JobContext, AlgorithmContext)


@dataclass(frozen=True, slots=True)
class InvokeRequest:
    """The public ``invoke`` call as one record (decision-81)."""

    function: Callable[..., Any]
    ctx: PluginContext | JobContext | AlgorithmContext
    inputs: dict[str, Any]
    progress: Progress | None
    cancellation: Cancellation | None
    add_to_project: bool


@dataclass(frozen=True, slots=True)
class Run:
    """One invocation's body, checks, child scope and commit target."""

    request: InvokeRequest
    description: AlgorithmDescription
    context: AlgorithmContext
    scope: ResourceScope
    project: Any
    cancellation: Cancellation


class _SilentProgress:
    """Report nothing; a caller that does not care about progress still runs."""

    def report(self, fraction: float) -> None:
        """Discard the fraction."""


class _NotCancelled:
    """Never cancelled; the default for a caller without a cancellation signal."""

    def is_cancelled(self) -> bool:
        """Return that this execution has not been cancelled."""
        return False


def invoke_controls(
    ctx: PluginContext | JobContext | AlgorithmContext,
    progress: Progress | None,
    cancellation: Cancellation | None,
) -> tuple[Progress, Cancellation]:
    """Inherit progress/cancellation from a job or algorithm context."""
    if progress is None:
        progress = getattr(ctx, "progress", None) or _SilentProgress()
    if cancellation is None:
        cancellation = getattr(ctx, "cancellation", None) or _NotCancelled()
    return progress, cancellation


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

    The call runs over a child scope that closes afterwards, so nothing an
    invocation registers outlives it (decision-11, decision-42).

    Args:
        function: The function ``@provider.algorithm`` declared.
        ctx: A plugin, job or algorithm context to run under.
        inputs: The declared inputs, as keyword arguments.
        progress: The sink, or ``None`` to inherit the context's.
        cancellation: The signal, or ``None`` to inherit the context's.
        add_to_project: Whether the produced layers join ``ctx.project``.

    Raises:
        QgisSdkAlgorithmRejectedError: An input is unknown, missing or of the
            wrong kind; every reason is listed at once.
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

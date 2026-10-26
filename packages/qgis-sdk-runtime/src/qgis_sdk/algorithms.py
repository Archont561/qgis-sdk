"""One plain function per algorithm, declared on a provider and run with a context.

decision-42 made an algorithm the same shape as a job: a function whose first
parameter is the :class:`~qgis_sdk.core.AlgorithmContext` the runtime injects,
whose other parameters are typed keyword inputs, and whose result is the
:class:`~qgis_sdk.models.VectorLayerInfo` of the layer it produced::

    tools = Provider(id="field_tools", title="Field tools")

    @tools.algorithm(title="Buffer in a projected CRS", group="Geometry")
    def buffer(
        ctx: AlgorithmContext, layer: LayerInput, distance: Metres, crs: CrsInput
    ) -> VectorLayerInfo:
        return ctx.algorithms.execute(BufferRequest(layer, distance, working_crs=crs))

This module is the authoring surface behind that: :func:`describe_algorithm`
inspects a declared function without calling it, and :func:`invoke` runs one
from the context an action, a job or another algorithm already holds. The work
itself goes through the injected ``Algorithms`` service, so the same function
runs against QGIS and against a fake, and nothing here imports QGIS.

Each input maps to one *parameter kind* - what a host renders for it. The
kinds are deliberately few: a marked layer, a marked CRS, a marked distance in
metres, or a plain primitive. Anything else is refused at decoration, naming
the input and the supported kinds, so no adapter has to invent a widget at run
time (TASK-39).
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Any, get_args, get_origin

from qgis_sdk.core import AlgorithmContext, JobContext, PluginContext
from qgis_sdk.declarations import (
    Metadata,
    QgisSdkDeclarationError,
    canonical_json,
    declared_function_metadata,
    keyword_inputs,
    object_schema,
    register_describer,
    resolve_hints,
    schema_for,
    type_name,
)
from qgis_sdk.models import (
    CrsParameter,
    LayerParameter,
    MetresParameter,
    QgisSdkAlgorithmCancelledError,
    QgisSdkAlgorithmRejectedError,
    VectorLayerInfo,
)
from qgis_sdk.services import Cancellation, Progress

__all__ = [
    "ALGORITHM_ATTRIBUTE",
    "CRS_PARAMETER",
    "LAYER_PARAMETER",
    "METRES_PARAMETER",
    "AlgorithmDeclaration",
    "AlgorithmDescription",
    "describe_algorithm",
    "invoke",
    "parameter_kind",
]

ALGORITHM_ATTRIBUTE = "__qgis_sdk_algorithm__"
"""The marker ``@provider.algorithm`` sets on the function it declares."""

LAYER_PARAMETER = "layer"
"""Kind of an input the host fills with a vector layer."""

CRS_PARAMETER = "crs"
"""Kind of an input the host fills with a coordinate reference system."""

METRES_PARAMETER = "metres"
"""Kind of an input that is a distance in metres."""

_PRIMITIVE_KINDS: dict[Any, str] = {
    str: "string",
    bool: "boolean",
    int: "integer",
    float: "number",
}
_SUPPORTED = "layer, crs, metres, string, integer, number or boolean"
_EXPECTED_VALUE: dict[str, tuple[str, tuple[type, ...]]] = {
    LAYER_PARAMETER: ("a str layer id", (str,)),
    CRS_PARAMETER: ("a str authority code", (str,)),
    METRES_PARAMETER: ("a number of metres", (int, float)),
    "string": ("a str", (str,)),
    "integer": ("an int", (int,)),
    "number": ("a number", (int, float)),
    "boolean": ("a bool", (bool,)),
}


@dataclass(frozen=True)
class AlgorithmDeclaration(Metadata):
    """What ``@provider.algorithm`` records: id, title, group and the provider."""

    provider_id: str
    group: str | None

    @property
    def qualified_id(self) -> str:
        """The ``provider:algorithm`` id a host registers."""
        return f"{self.provider_id}:{self.id}"


def _refuse(path: str, detail: str) -> QgisSdkDeclarationError:
    return QgisSdkDeclarationError(
        f"{path}: {detail}; use Annotated markers ({_SUPPORTED})"
    )


def parameter_kind(path: str, annotation: Any) -> str:
    """Map one input annotation onto a host parameter kind, or refuse it.

    ``LayerInput`` and ``Annotated[str, LayerParameter()]`` are the same
    annotation, so they map to the same kind; a marker on a type it does not
    fit (``Annotated[int, LayerParameter()]``) is refused with ``path`` named.
    """
    base, markers = annotation, ()
    if get_origin(annotation) is Annotated:
        base, *markers = get_args(annotation)
    for marker in markers:
        if isinstance(marker, LayerParameter):
            if base is not str:
                raise _refuse(path, "a layer input must be a str layer id")
            return LAYER_PARAMETER
        if isinstance(marker, CrsParameter):
            if base is not str:
                raise _refuse(path, "a CRS input must be a str authority code")
            return CRS_PARAMETER
        if isinstance(marker, MetresParameter):
            if base not in (float, int):
                raise _refuse(path, "a metres input must be a number")
            return METRES_PARAMETER
        raise _refuse(path, f"unknown parameter marker {marker!r}")
    kind = _PRIMITIVE_KINDS.get(base)
    if kind is None:
        raise _refuse(path, f"cannot express {base!r} as a host parameter")
    return kind


@dataclass(frozen=True)
class AlgorithmDescription:
    """Inspectable algorithm structure: inputs, their kinds, and the result.

    ``annotations`` and ``result_type`` are the live annotations, because an
    invocation checks values against them; ``to_dict`` is the transport-safe
    view a generator or a host registry consumes, and it names types instead.
    ``kinds`` maps each input, in declaration order, onto the host parameter
    kind it renders as.
    """

    id: str
    title: str
    provider_id: str
    group: str | None
    parameters: tuple[str, ...]
    required: tuple[str, ...]
    kinds: dict[str, str]
    annotations: dict[str, Any]
    result_type: Any
    inputs_schema: dict[str, Any]
    result_schema: dict[str, Any]
    schema_version: int = 1

    @property
    def qualified_id(self) -> str:
        """The ``provider:algorithm`` id a host registers."""
        return f"{self.provider_id}:{self.id}"

    def to_dict(self) -> dict[str, Any]:
        """Return the transport representation without live Python types."""
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "title": self.title,
            "qualified_id": self.qualified_id,
            "provider": self.provider_id,
            "group": self.group,
            "parameters": dict(self.kinds),
            "inputs": self.inputs_schema,
            "result": {
                "type": type_name(self.result_type),
                "schema": self.result_schema,
            },
        }

    def to_json(self) -> str:
        """The canonical JSON form shared by every description."""
        return canonical_json(self.to_dict())


def describe_algorithm(function: Callable[..., Any]) -> AlgorithmDescription:
    """Inspect one declared function without calling it.

    The input schemas come from the same generator the plugin declarations
    use, so an algorithm's inputs are held to the same documented typing subset
    as an action's - and on top of that each input has to map to a host
    parameter kind. Both are checked when ``@provider.algorithm`` runs; this
    function re-reads the same declaration for a caller that holds only the
    function.
    """
    declared = declared_function_metadata(
        function, ALGORITHM_ATTRIBUTE, "describe_algorithm", "@provider.algorithm"
    )
    if not isinstance(declared, AlgorithmDeclaration):
        raise QgisSdkDeclarationError(
            "describe_algorithm requires a function with @provider.algorithm"
        )
    return describe_declared_algorithm(function, declared)


def describe_declared_algorithm(
    function: Callable[..., Any], declared: AlgorithmDeclaration
) -> AlgorithmDescription:
    """Describe ``function`` under ``declared``; the provider calls this first.

    Separate from :func:`describe_algorithm` so the provider can validate a
    function *before* committing its marker, and remove the marker again when
    validation refuses - a half-declared algorithm must not describe.
    """
    path = f"algorithm {declared.qualified_id}"
    if (
        not inspect.isfunction(function)
        or inspect.iscoroutinefunction(function)
        or inspect.isgeneratorfunction(function)
        or inspect.isasyncgenfunction(function)
    ):
        raise QgisSdkDeclarationError(
            f"{path}: an algorithm is a plain synchronous function, not a "
            "coroutine or a generator"
        )
    parameters = list(inspect.signature(function).parameters.values())
    hints = resolve_hints(function, path)
    context_first = (
        bool(parameters)
        and parameters[0].kind
        in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.POSITIONAL_ONLY)
        and hints.get(parameters[0].name) is AlgorithmContext
    )
    if not context_first:
        raise QgisSdkDeclarationError(
            f"{path}: first parameter must be the AlgorithmContext the runtime "
            "injects (annotate it `ctx: AlgorithmContext`)"
        )
    inputs = parameters[1:]
    for parameter in inputs:
        if parameter.name not in hints:
            raise QgisSdkDeclarationError(
                f"{path}.{parameter.name}: every input must be annotated"
            )
    properties, required = keyword_inputs(inputs, hints, f"{path}.inputs")
    kinds = {
        parameter.name: parameter_kind(
            f"{path}.{parameter.name}", hints[parameter.name]
        )
        for parameter in inputs
    }
    result_type = hints.get("return", inspect.Signature.empty)
    if result_type is inspect.Signature.empty:
        raise QgisSdkDeclarationError(f"{path}: an algorithm must declare its result")
    if result_type is not VectorLayerInfo:
        raise QgisSdkDeclarationError(
            f"{path}: an algorithm returns the VectorLayerInfo of the layer it "
            f"produced, not {type_name(result_type)}"
        )
    return AlgorithmDescription(
        id=declared.id,
        title=declared.title,
        provider_id=declared.provider_id,
        group=declared.group,
        parameters=tuple(parameter.name for parameter in inputs),
        required=tuple(required),
        kinds=kinds,
        annotations={parameter.name: hints[parameter.name] for parameter in inputs},
        result_type=result_type,
        inputs_schema=object_schema(properties, required),
        result_schema=schema_for(result_type, f"{path}.result", result=True),
    )


register_describer(ALGORITHM_ATTRIBUTE, describe_algorithm)


class _SilentProgress:
    """Report nothing; a caller that does not care about progress still runs."""

    def report(self, fraction: float) -> None:
        """Discard the fraction."""


class _NotCancelled:
    """Never cancelled; the default for a caller without a cancellation signal."""

    def is_cancelled(self) -> bool:
        """Return that this execution has not been cancelled."""
        return False


def _check_inputs(description: AlgorithmDescription, inputs: dict[str, Any]) -> None:
    """Refuse unknown, missing or wrongly shaped inputs, all reasons at once."""
    reasons = [
        f"unknown input {name!r}"
        for name in inputs
        if name not in description.parameters
    ]
    reasons.extend(
        f"{name} is required" for name in description.required if name not in inputs
    )
    for name, value in inputs.items():
        kind = description.kinds.get(name)
        if kind is None:
            continue
        expected, accepted = _EXPECTED_VALUE[kind]
        # bool is an int to Python but not to a spin box.
        if not isinstance(value, accepted) or (
            isinstance(value, bool) and bool not in accepted
        ):
            reasons.append(f"{name} must be {expected}, not {type_name(type(value))}")
    if reasons:
        raise QgisSdkAlgorithmRejectedError(description.id, reasons)


_CONTEXTS = (PluginContext, JobContext, AlgorithmContext)


def invoke(
    function: Callable[..., Any],
    ctx: PluginContext | JobContext | AlgorithmContext,
    /,
    *,
    progress: Progress | None = None,
    cancellation: Cancellation | None = None,
    add_to_project: bool = True,
    **inputs: Any,
) -> VectorLayerInfo:
    """Run one declared algorithm once from the context the caller already holds.

    ``ctx`` is the ``PluginContext`` of an action, the ``JobContext`` of a job
    or the ``AlgorithmContext`` of another algorithm; ``invoke`` reads its
    ``algorithms``, ``project`` and ``scope`` and builds a *new*
    ``AlgorithmContext`` over a child scope for the call, closing that child
    scope again afterwards. Nothing an invocation registers on its scope
    outlives it, so a second run cannot see the first run's context
    (decision-11, kept by decision-42). ``progress`` and ``cancellation`` left
    out are inherited from a job or algorithm context, so a job's cancellation
    reaches the algorithm it runs; a plugin context has neither, and the call
    runs silently and uncancelled.

    ``add_to_project=False`` is for a caller that owns the destination itself:
    the Processing bridge hands the produced layer to a feature sink, and the
    reference workflow styles the output before presenting it. With the
    default the output is added to ``ctx.project`` on success, so a context
    without a project refuses by name before anything runs.

    Ordering is the whole safety story (decision-19). The inputs are checked
    against the declared parameters, cancellation is read before anything
    runs, the function runs into a new output, the result is checked against
    the declared type, cancellation is read once more, and only then is the
    output added to the project. A failure or cancellation at any point leaves
    the project exactly as it was.
    """
    description = describe_algorithm(function)
    if not isinstance(ctx, _CONTEXTS):
        raise QgisSdkDeclarationError(
            f"invoke({description.id}): the second argument is the context the "
            "runtime injected (a PluginContext, JobContext or AlgorithmContext), "
            f"not {type_name(type(ctx))}; inputs are keyword arguments"
        )
    _check_inputs(description, inputs)
    if progress is None:
        progress = getattr(ctx, "progress", None) or _SilentProgress()
    if cancellation is None:
        cancellation = getattr(ctx, "cancellation", None) or _NotCancelled()
    ctx.scope.ensure_open()
    algorithms = ctx.algorithms
    if add_to_project:
        project = ctx.project
    else:
        project = ctx.project if ctx.has("project") else None
    network = ctx.network if ctx.has("network") else None
    if cancellation.is_cancelled():
        raise QgisSdkAlgorithmCancelledError(description.id)
    invocation_scope = ctx.scope.child()
    context = AlgorithmContext(
        progress=progress,
        cancellation=cancellation,
        scope=invocation_scope,
        algorithms=algorithms,
        project=project,
        network=network,
    )
    try:
        result = function(context, **inputs)
        if not isinstance(result, VectorLayerInfo):
            raise QgisSdkDeclarationError(
                f"{description.id}: returned {type_name(type(result))}, not the "
                "declared VectorLayerInfo"
            )
        if cancellation.is_cancelled():
            raise QgisSdkAlgorithmCancelledError(description.id)
        if add_to_project:
            assert project is not None
            project.add_layer(result.id)
    finally:
        invocation_scope.close()
    return result

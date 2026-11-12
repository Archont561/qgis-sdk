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
time.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Any, get_args, get_origin

from qgis_sdk.core import (
    AlgorithmContext,
    JobContext,
    PluginContext,
    ResourceScope,
)
from qgis_sdk.declarations import (
    Metadata,
    QgisSdkDeclarationError,
    canonical_json,
    declared_function_metadata,
    keyword_inputs,
    object_schema,
    register_describer,
    resolve_hints,
    resolve_kind,
    schema_for,
    type_name,
)
from qgis_sdk.models import (
    COLOUR_PATTERN,
    QgisSdkAlgorithmRejectedError,
    RangeParameter,
    output_kind_for,
    parameter_kinds,
)
from qgis_sdk.services import Cancellation, Progress

ALGORITHM_ATTRIBUTE = "__qgis_sdk_algorithm__"
"""The marker ``@provider.algorithm`` sets on the function it declares."""
LAYER_PARAMETER = "layer"
"""Kind of an input the host fills with a vector layer."""
CRS_PARAMETER = "crs"
"""Kind of an input the host fills with a coordinate reference system."""
METRES_PARAMETER = "metres"
"""Kind of an input that is a distance in metres."""


@dataclass(frozen=True)
class AlgorithmDeclaration(Metadata):
    """What ``@provider.algorithm`` records: id, title, group and the provider."""

    provider_id: str
    group: str | None

    @property
    def qualified_id(self) -> str:
        """The ``provider:algorithm`` id a host registers."""
        return f"{self.provider_id}:{self.id}"


def parameter_kind(path: str, annotation: Any) -> str:
    """Map one input annotation onto a host parameter kind name, or refuse it.

    The rule is :func:`qgis_sdk.declarations.resolve_kind`; this returns the
    name a Processing adapter and a form switch on.
    """
    kind, _marker = resolve_kind(path, annotation)
    return kind.name


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
    result_kind: str
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
                "kind": self.result_kind,
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


def _is_plain_function(function: Any) -> bool:
    """Whether ``function`` is the plain synchronous callable an algorithm is.

    A coroutine or a generator is refused because the provider calls the
    function and reads its answer; there is nothing to await and nothing to
    iterate there.
    """
    if not inspect.isfunction(function) or inspect.iscoroutinefunction(function):
        return False
    return not (
        inspect.isgeneratorfunction(function) or inspect.isasyncgenfunction(function)
    )


def _algorithm_signature(
    function: Callable[..., Any], path: str
) -> tuple[list[inspect.Parameter], dict[str, Any]]:
    """Validate the plain function and its injected context; return inputs/hints."""
    if not _is_plain_function(function):
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
    return inputs, hints


def _algorithm_result(hints: dict[str, Any], path: str) -> tuple[Any, Any]:
    """Resolve and validate the one declared output the algorithm returns."""
    result_type = hints.get("return", inspect.Signature.empty)
    if result_type is inspect.Signature.empty:
        raise QgisSdkDeclarationError(f"{path}: an algorithm must declare its result")
    result_kind = output_kind_for(result_type)
    if result_kind is None:
        raise QgisSdkDeclarationError(
            f"{path}: an algorithm returns one declared output - the "
            f"VectorLayerInfo or RasterLayerInfo it produced, a FileRef, "
            f"FolderOutput or HtmlOutput ref, a number, a string, a boolean or "
            f"MultipleLayers - not {type_name(result_type)}"
        )
    return result_type, result_kind


def describe_declared_algorithm(
    function: Callable[..., Any], declared: AlgorithmDeclaration
) -> AlgorithmDescription:
    """Describe ``function`` under ``declared`` before the provider commits."""
    path = f"algorithm {declared.qualified_id}"
    inputs, hints = _algorithm_signature(function, path)
    properties, required = keyword_inputs(inputs, hints, f"{path}.inputs")
    kinds = {
        parameter.name: parameter_kind(
            f"{path}.{parameter.name}", hints[parameter.name]
        )
        for parameter in inputs
    }
    result_type, result_kind = _algorithm_result(hints, path)
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
        result_kind=result_kind.name,
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


def check_inputs(description: AlgorithmDescription, inputs: dict[str, Any]) -> None:
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
        kind_name = description.kinds.get(name)
        if kind_name is None:
            continue
        reason = input_refusal(
            name, parameter_kinds()[kind_name], description.annotations[name], value
        )
        if reason is not None:
            reasons.append(reason)
    if reasons:
        raise QgisSdkAlgorithmRejectedError(description.id, reasons)


def input_refusal(name: str, kind: Any, annotation: Any, value: Any) -> str | None:
    """Say why ``value`` is not what ``kind`` hands a handler, or ``None``.

    Shared by :func:`invoke` and the form coercion, so a toolbox run, a page
    call and a native form refuse the same values with the same words.
    """
    # bool is an int to Python but not to a spin box.
    if not isinstance(value, kind.accepted) or (
        isinstance(value, bool) and bool not in kind.accepted
    ):
        return f"{name} must be {kind.expected}, not {type_name(type(value))}"
    return _kind_refusal(name, kind, annotation, value)


def _kind_refusal(name: str, kind: Any, annotation: Any, value: Any) -> str | None:
    """The refusals that depend on which kind the parameter is."""
    if kind.name in ("file", "directory") and value.kind != kind.name:
        return f"{name} must be a {kind.name} FileRef, not a {value.kind} FileRef"
    if kind.name == "range":
        bounds = _range_of(annotation)
        if bounds is not None and not (bounds.minimum <= value <= bounds.maximum):
            return f"{name} must be between {bounds.minimum} and {bounds.maximum}"
    if kind.name == "colour" and not COLOUR_PATTERN.match(value):
        return f"{name} must be a #RRGGBB or #RRGGBBAA colour"
    if kind.name == "enum":
        choices = get_args(annotation)
        if value not in choices:
            return f"{name} must be one of {', '.join(choices)}"
    return None


def _range_of(annotation: Any) -> RangeParameter | None:
    if get_origin(annotation) is not Annotated:
        return None
    return next(
        (m for m in get_args(annotation)[1:] if isinstance(m, RangeParameter)), None
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

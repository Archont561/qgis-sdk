"""One decorated plain class per algorithm, inspected before it is constructed.

decision-11 replaced the grouped-method sketch with a class per algorithm: one
typed ``run(inputs) -> Result`` entry point, an optional ``self.ctx`` holding the
execution capabilities, and a fresh author instance plus a fresh
``AlgorithmContext`` for every invocation. This module is that authoring surface;
it is not an execution engine. The work itself goes through the injected
``Algorithms`` service, so the same class runs against QGIS and against a fake.

Nothing here imports QGIS: an algorithm class can be described and its request
models can be refused in a pure test, which is why the reference workflow's
validation does not need a QGIS installation to be exercised.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from qgis_sdk.core import AlgorithmContext, ResourceScope
from qgis_sdk.declarations import (
    QgisSdkDeclarationError,
    _hints,
    _Metadata,
    _metadata,
    _schema,
)
from qgis_sdk.models import (
    QgisSdkAlgorithmCancelledError,
    QgisSdkAlgorithmRejectedError,
    VectorLayerInfo,
)
from qgis_sdk.services import Algorithms, Cancellation, Progress, Project

__all__ = [
    "AlgorithmDescription",
    "AlgorithmResult",
    "algorithm",
    "describe_algorithm",
    "invoke",
]

T = TypeVar("T")

_ALGORITHM_ATTRIBUTE = "__qgis_sdk_algorithm__"


class _SilentProgress:
    """Report nothing; a caller that does not care about progress still runs."""

    def report(self, fraction: float) -> None:
        """Discard the fraction."""


class _NotCancelled:
    """Never cancelled; the default for a caller without a cancellation signal."""

    def is_cancelled(self) -> bool:
        """Return that this execution has not been cancelled."""
        return False


def _type_name(annotation: Any) -> str:
    """Name an annotation for an error message, unions included."""
    return getattr(annotation, "__name__", str(annotation))


def algorithm(*, id: str, title: str) -> Callable[[type[T]], type[T]]:
    """Attach algorithm metadata without wrapping or constructing the class."""

    metadata = _metadata(id, title)

    def decorate(cls: type[T]) -> type[T]:
        if not inspect.isclass(cls):
            raise QgisSdkDeclarationError("@algorithm requires a class")
        if _ALGORITHM_ATTRIBUTE in vars(cls):
            raise QgisSdkDeclarationError(f"{id}: duplicate @algorithm declaration")
        setattr(cls, _ALGORITHM_ATTRIBUTE, metadata)
        return cls

    return decorate


@dataclass(frozen=True)
class AlgorithmDescription:
    """Inspectable algorithm structure, including its request/result schemas.

    ``inputs_type`` and ``result_type`` are the annotations themselves, because
    an invocation checks the values against them; ``to_dict`` is the
    transport-safe view a generator would consume, and it names them instead.
    """

    id: str
    title: str
    inputs_type: Any
    result_type: Any
    inputs_schema: dict[str, Any]
    result_schema: dict[str, Any]
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        """Return the transport representation without live Python types."""
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "title": self.title,
            "inputs": {
                "type": _type_name(self.inputs_type),
                "schema": self.inputs_schema,
            },
            "result": {
                "type": _type_name(self.result_type),
                "schema": self.result_schema,
            },
        }


def describe_algorithm(cls: type) -> AlgorithmDescription:
    """Inspect one decorated class without constructing it or calling ``run``.

    The schemas come from the same generator the plugin declarations use, so an
    algorithm's request model is held to the same documented typing subset as an
    action's request - and a type the contract cannot express fails here, at
    inspection time, rather than during a run.
    """
    if not inspect.isclass(cls) or _ALGORITHM_ATTRIBUTE not in vars(cls):
        raise QgisSdkDeclarationError(
            "describe_algorithm requires a class with @algorithm"
        )
    metadata = vars(cls)[_ALGORITHM_ATTRIBUTE]
    if not isinstance(metadata, _Metadata):
        raise QgisSdkDeclarationError(
            "describe_algorithm requires a class with @algorithm"
        )
    run = vars(cls).get("run")
    if not inspect.isfunction(run):
        raise QgisSdkDeclarationError(
            f"{metadata.id}: an algorithm needs its own run method"
        )
    parameters = list(inspect.signature(run).parameters.values())
    if len(parameters) != 2 or parameters[0].name != "self":
        raise QgisSdkDeclarationError(
            f"{metadata.id}: run takes self and exactly one typed inputs argument"
        )
    # Resolved, not raw: a module using `from __future__ import annotations`
    # hands us strings, and a forward reference has to be evaluated the same way
    # a plugin action's annotations are.
    hints = _hints(run, f"algorithm {metadata.id}")
    inputs_type = hints.get(parameters[1].name, inspect.Parameter.empty)
    result_type = hints.get("return", inspect.Signature.empty)
    if inputs_type is inspect.Parameter.empty:
        raise QgisSdkDeclarationError(f"{metadata.id}: run inputs must be annotated")
    if result_type is inspect.Signature.empty:
        raise QgisSdkDeclarationError(f"{metadata.id}: run must declare its result")
    return AlgorithmDescription(
        id=metadata.id,
        title=metadata.title,
        inputs_type=inputs_type,
        result_type=result_type,
        inputs_schema=_schema(inputs_type, f"{metadata.id}.inputs", result=False),
        result_schema=_schema(result_type, f"{metadata.id}.result", result=True),
    )


@dataclass(frozen=True, slots=True)
class AlgorithmResult:
    """What one successful invocation produced: a new, owned output layer."""

    output: VectorLayerInfo


def invoke(
    algorithm: type[T],
    inputs: object,
    *,
    algorithms: Algorithms,
    project: Project,
    scope: ResourceScope,
    progress: Progress | None = None,
    cancellation: Cancellation | None = None,
    add_to_project: bool = True,
) -> AlgorithmResult:
    """Run one algorithm once, adding its output to the project on success.

    Each call constructs a *new* author instance and a *new* ``AlgorithmContext``
    over a child scope of ``scope``, then closes that child scope again. Nothing
    an invocation registers on its scope outlives it, so a second run cannot see
    the first run's context - the property TASK-14 asks to be observed, not
    assumed.

    ``add_to_project=False`` is for a host that owns the destination itself: the
    QGIS Processing bridge hands the produced layer to a feature sink, so adding
    it to the project as well would duplicate it. ``project`` stays required -
    the caller has one, and passing it always keeps the ownership check honest.

    Ordering is the whole safety story (decision-19). The request is checked
    against the declared inputs type, cancellation is read before anything runs,
    the operation runs into a new output, the result is checked against the
    declared result type, cancellation is read once more, and only then is the
    output added to the project. A failure or cancellation at any point leaves
    the project exactly as it was.
    """
    description = describe_algorithm(algorithm)
    if not isinstance(inputs, description.inputs_type):
        raise QgisSdkAlgorithmRejectedError(
            description.id,
            [
                f"inputs must be {_type_name(description.inputs_type)}, not {_type_name(type(inputs))}"
            ],
        )
    progress = progress if progress is not None else _SilentProgress()
    cancellation = cancellation if cancellation is not None else _NotCancelled()
    scope.ensure_open()
    if cancellation.is_cancelled():
        raise QgisSdkAlgorithmCancelledError(description.id)
    invocation_scope = scope.child()
    context = AlgorithmContext(
        progress=progress,
        cancellation=cancellation,
        scope=invocation_scope,
        algorithms=algorithms,
    )
    try:
        result = algorithm(context).run(inputs)
        if not isinstance(result, description.result_type):
            raise QgisSdkDeclarationError(
                f"{description.id}: run returned {_type_name(type(result))}, not the declared {_type_name(description.result_type)}"
            )
        if cancellation.is_cancelled():
            raise QgisSdkAlgorithmCancelledError(description.id)
        if add_to_project:
            project.add_layer(result.output.id)
    finally:
        invocation_scope.close()
    return AlgorithmResult(output=result.output)

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

from dataclasses import dataclass
from typing import Any, TypeVar

from qgis_sdk.core import AlgorithmContext, ResourceScope
from qgis_sdk.declarations import (
    QgisSdkDeclarationError,
    canonical_json,
    class_decorator,
    describe_run_method,
    register_describer,
    type_name,
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


def algorithm(
    cls: type[T] | None = None,
    /,
    *,
    id: str | None = None,
    title: str | None = None,
) -> Any:
    """Attach algorithm metadata without wrapping or constructing the class.

    ``@algorithm`` alone derives the id and title from the class name, the way
    ``@plugin`` does; ``id=`` and ``title=`` override either one.
    """
    return class_decorator(_ALGORITHM_ATTRIBUTE, "@algorithm", cls, id=id, title=title)


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
                "type": type_name(self.inputs_type),
                "schema": self.inputs_schema,
            },
            "result": {
                "type": type_name(self.result_type),
                "schema": self.result_schema,
            },
        }

    def to_json(self) -> str:
        """The canonical JSON form shared by every description."""
        return canonical_json(self.to_dict())


def describe_algorithm(cls: type) -> AlgorithmDescription:
    """Inspect one decorated class without constructing it or calling ``run``.

    The schemas come from the same generator the plugin declarations use, so an
    algorithm's request model is held to the same documented typing subset as an
    action's request - and a type the contract cannot express fails here, at
    inspection time, rather than during a run.
    """
    signature = describe_run_method(cls, _ALGORITHM_ATTRIBUTE, "algorithm")
    return AlgorithmDescription(
        id=signature.metadata.id,
        title=signature.metadata.title,
        inputs_type=signature.inputs_type,
        result_type=signature.result_type,
        inputs_schema=signature.inputs_schema,
        result_schema=signature.result_schema,
    )


register_describer(_ALGORITHM_ATTRIBUTE, describe_algorithm)


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
                f"inputs must be {type_name(description.inputs_type)}, not {type_name(type(inputs))}"
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
                f"{description.id}: run returned {type_name(type(result))}, not the declared {type_name(description.result_type)}"
            )
        if cancellation.is_cancelled():
            raise QgisSdkAlgorithmCancelledError(description.id)
        if add_to_project:
            project.add_layer(result.output.id)
    finally:
        invocation_scope.close()
    return AlgorithmResult(output=result.output)

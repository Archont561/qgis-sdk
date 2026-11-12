"""What the fake and the native ``Algorithms`` share about a generic run.

Pure. Coercing the three request shapes into one :class:`AlgorithmRun`,
naming the destinations a backend allocates and classifying outputs are
rules, not host behaviour, so they live here and both backends obey the same
ones (decision-64).
"""

from __future__ import annotations

from collections.abc import Mapping as _Mapping

from qgis_sdk.models import AlgorithmRun as _AlgorithmRun
from qgis_sdk.models import (
    QgisSdkAlgorithmRejectedError as _QgisSdkAlgorithmRejectedError,
)
from qgis_sdk.models import TypedRun as _TypedRun

from ._destinations import plan_destinations
from ._kinds import (
    DEFAULT_EXTENSIONS,
    FILE_OUTPUT_KINDS,
    MULTI_OUTPUT_KINDS,
    VECTOR_OUTPUT_KINDS,
    output_class,
)
from ._model import declared_model_outputs, model_output_names
from ._names import destination_path

__all__ = [
    "DEFAULT_EXTENSIONS",
    "FILE_OUTPUT_KINDS",
    "MULTI_OUTPUT_KINDS",
    "VECTOR_OUTPUT_KINDS",
    "coerce_run",
    "declared_model_outputs",
    "destination_path",
    "model_output_names",
    "output_class",
    "plan_destinations",
]


def coerce_run(
    request: _AlgorithmRun | _TypedRun | str, params: _Mapping[str, object] | None
) -> _AlgorithmRun:
    """One ``AlgorithmRun`` from any of the three request shapes."""
    if isinstance(request, str):
        return _AlgorithmRun(request, dict(params or {}))
    if params is not None:
        raise _QgisSdkAlgorithmRejectedError(
            getattr(request, "algorithm", "?"),
            ["params go with an algorithm id, not with a request object"],
        )
    if isinstance(request, _TypedRun):
        return request.to_run()
    if isinstance(request, _AlgorithmRun):
        return request
    shape = type(request).__name__
    raise _QgisSdkAlgorithmRejectedError(
        "?",
        [
            f"a run takes an id and params, an AlgorithmRun or a request class, not {shape}"
        ],
    )

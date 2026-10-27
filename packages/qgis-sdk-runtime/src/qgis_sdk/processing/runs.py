"""What the fake and the native ``Algorithms`` share about a generic run.

Pure. Coercing the three request shapes into one :class:`AlgorithmRun`,
naming the destinations a backend allocates and classifying outputs are
rules, not host behaviour, so they live here and both backends obey the same
ones (decision-64).
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from qgis_sdk.models import (
    AlgorithmInfo,
    AlgorithmRun,
    ParameterInfo,
    QgisSdkAlgorithmRejectedError,
    TypedRun,
)

__all__ = [
    "DEFAULT_EXTENSIONS",
    "FILE_OUTPUT_KINDS",
    "VECTOR_OUTPUT_KINDS",
    "coerce_run",
    "destination_path",
    "output_class",
]

#: Output kinds that come back as an owned vector layer.
VECTOR_OUTPUT_KINDS: frozenset[str] = frozenset({"outputVector"})
#: Output kinds that come back as a file ref (a directory ref for folders).
FILE_OUTPUT_KINDS: frozenset[str] = frozenset(
    {
        "outputRaster",
        "outputFile",
        "outputFolder",
        "outputHtml",
        "outputPointCloud",
        "outputVectorTile",
    }
)
#: Extension per destination kind when the registry names none.
DEFAULT_EXTENSIONS: dict[str, str] = {
    "sink": "gpkg",
    "vectorDestination": "gpkg",
    "rasterDestination": "tif",
    "pointCloudDestination": "las",
    "vectorTileDestination": "mbtiles",
    "fileDestination": "out",
}


def coerce_run(
    request: AlgorithmRun | TypedRun | str, params: Mapping[str, object] | None
) -> AlgorithmRun:
    """One ``AlgorithmRun`` from any of the three request shapes."""
    if isinstance(request, str):
        return AlgorithmRun(request, dict(params or {}))
    if params is not None:
        raise QgisSdkAlgorithmRejectedError(
            getattr(request, "algorithm", "?"),
            ["params go with an algorithm id, not with a request object"],
        )
    if isinstance(request, TypedRun):
        return request.to_run()
    if isinstance(request, AlgorithmRun):
        return request
    shape = type(request).__name__
    raise QgisSdkAlgorithmRejectedError(
        "?",
        [
            f"a run takes an id and params, an AlgorithmRun or a request class, not {shape}"
        ],
    )


def destination_path(run_directory: Path, parameter: ParameterInfo) -> Path:
    """Where an allocated destination goes: ``<run dir>/<name>.<extension>``.

    A folder destination is a directory named after the parameter; every
    other kind takes the extension the registry reported, else the kind's
    default.
    """
    stem = parameter.name.lower()
    if parameter.kind == "folderDestination":
        return run_directory / stem
    extension = parameter.extension or DEFAULT_EXTENSIONS.get(parameter.kind, "out")
    return run_directory / f"{stem}.{extension}"


def output_class(info: AlgorithmInfo, name: str) -> str:
    """``vector``, ``file``, ``directory`` or ``value`` for one output name."""
    for output in info.outputs:
        if output.name == name:
            if output.kind in VECTOR_OUTPUT_KINDS:
                return "vector"
            if output.kind == "outputFolder":
                return "directory"
            if output.kind in FILE_OUTPUT_KINDS:
                return "file"
            return "value"
    parameter = info.parameter(name)
    if parameter is not None and parameter.destination:
        if parameter.kind in ("sink", "vectorDestination"):
            return "vector"
        if parameter.kind == "folderDestination":
            return "directory"
        return "file"
    return "value"

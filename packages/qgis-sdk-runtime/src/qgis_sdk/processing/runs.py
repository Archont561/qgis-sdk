"""What the fake and the native ``Algorithms`` share about a generic run.

Pure. Coercing the three request shapes into one :class:`AlgorithmRun`,
naming the destinations a backend allocates and classifying outputs are
rules, not host behaviour, so they live here and both backends obey the same
ones (decision-64).
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Mapping
from pathlib import Path

from qgis_sdk.models import (
    AlgorithmInfo,
    AlgorithmRun,
    FileRef,
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


def plan_destinations(
    info: AlgorithmInfo,
    params: Mapping[str, object],
    resolve_file: Callable[[FileRef], Path],
) -> dict[str, Path]:
    """Validate allocated names and plan at most one new local vector file."""
    allocated: set[str] = set()
    for parameter in info.parameters:
        if not parameter.destination or params.get(parameter.name) is not None:
            continue
        try:
            relative = _destination_name(parameter).lower()
        except ValueError as error:
            raise QgisSdkAlgorithmRejectedError(info.id, [str(error)]) from error
        if relative in allocated:
            raise QgisSdkAlgorithmRejectedError(
                info.id, ["allocated destination names collide"]
            )
        allocated.add(relative)
    supplied = [
        (parameter, params[parameter.name])
        for parameter in info.parameters
        if parameter.destination and params.get(parameter.name) is not None
    ]
    if len(supplied) > 1:
        raise QgisSdkAlgorithmRejectedError(
            info.id, ["at most one explicit destination can be published safely"]
        )
    result: dict[str, Path] = {}
    for parameter, value in supplied:
        if isinstance(value, FileRef):
            path = resolve_file(value)
        elif (
            isinstance(value, str) and value and "://" not in value and "|" not in value
        ):
            path = Path(value)
        else:
            raise QgisSdkAlgorithmRejectedError(
                info.id, [f"{parameter.name} must be a new local file destination"]
            )
        if parameter.kind not in {
            "sink",
            "vectorDestination",
        } or path.suffix.lower() not in {".geojson", ".gpkg"}:
            raise QgisSdkAlgorithmRejectedError(
                info.id,
                [
                    f"{parameter.name} supports only new GeoJSON or GeoPackage vector files"
                ],
            )
        try:
            parent = path.parent.resolve(strict=True)
            path = parent / path.name
            if not parent.is_dir():
                raise ValueError("the destination directory is not a directory")
            try:
                os.lstat(path)
            except FileNotFoundError:
                pass
            else:
                raise ValueError("the destination already exists")
        except ValueError as error:
            raise QgisSdkAlgorithmRejectedError(
                info.id, [f"{parameter.name} cannot be published safely: {error}"]
            ) from error
        except (OSError, RuntimeError) as error:
            raise QgisSdkAlgorithmRejectedError(
                info.id, [f"{parameter.name} destination cannot be verified"]
            ) from error
        result[parameter.name] = path
    return result


def _destination_name(parameter: ParameterInfo) -> str:
    """Keep provider-supplied names and extensions within the run directory."""
    name = parameter.name.lower()
    extension = parameter.extension or DEFAULT_EXTENSIONS.get(parameter.kind, "out")
    if (
        not re.fullmatch(r"[a-z0-9_]{1,128}", name)
        or re.fullmatch(r"(?:con|prn|aux|nul|com[1-9]|lpt[1-9])", name)
        or (
            parameter.kind != "folderDestination"
            and not re.fullmatch(r"[a-zA-Z0-9]{1,16}", extension)
        )
    ):
        raise ValueError(
            "an allocated destination has an unsafe provider-defined name or extension"
        )
    if parameter.kind == "folderDestination":
        return name
    return f"{name}.{extension}"


def destination_path(run_directory: Path, parameter: ParameterInfo) -> Path:
    """Place a qualified allocated destination directly in the run directory."""
    return run_directory / _destination_name(parameter)


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

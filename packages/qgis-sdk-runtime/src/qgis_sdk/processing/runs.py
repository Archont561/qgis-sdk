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
    "MULTI_OUTPUT_KINDS",
    "VECTOR_OUTPUT_KINDS",
    "coerce_run",
    "destination_path",
    "output_class",
]

#: Output kinds that come back as an owned vector layer.
VECTOR_OUTPUT_KINDS: frozenset[str] = frozenset({"outputVector"})
#: Output kinds that come back as several owned vector layers, in order.
MULTI_OUTPUT_KINDS: frozenset[str] = frozenset({"outputMultilayer"})
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


#: Every character a provider may name a parameter with that no file name may
#: carry. A model names the destinations Processing derives for its children
#: after the child and its output - ``native:centroids_1:CENTROIDS`` - so the
#: colon and the upper case are the normal case, not the hostile one.
_UNSAFE_IN_NAME = re.compile(r"[^a-z0-9_]+")

#: Device names a file may not be called on Windows, whatever the extension.
_RESERVED_NAMES: frozenset[str] = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{index}" for index in range(1, 10)}
    | {f"lpt{index}" for index in range(1, 10)}
)


def _destination_name(parameter: ParameterInfo) -> str:
    """Keep provider-supplied names and extensions within the run directory.

    The provider's name is *translated*, not refused: a registered algorithm
    names a destination ``OUTPUT`` and a model names it after the child that
    writes it (``native:centroids_1:CENTROIDS``), and neither is a file name
    this SDK writes untouched. Every run of characters outside
    ``[a-z0-9_]`` becomes one ``_``, which leaves no separator, no leading
    dot and no name that escapes the run directory. What is still refused is
    what translation cannot make safe: a name that translates to nothing, a
    Windows device name, and an extension outside ``[A-Za-z0-9]``.

    Two provider names can translate alike; ``plan_destinations`` refuses that
    collision rather than letting one output overwrite another. A name that
    carries a path separator is not translated but refused: no provider
    composes one, so it is a caller reaching out of the run directory, and
    answering it with a benign name would hide that.
    """
    if "/" in parameter.name or "\\" in parameter.name:
        raise ValueError(
            "an allocated destination has an unsafe provider-defined name or extension"
        )
    name = _UNSAFE_IN_NAME.sub("_", parameter.name.lower()).strip("_")[:128]
    extension = parameter.extension or DEFAULT_EXTENSIONS.get(parameter.kind, "out")
    if (
        not name
        or name in _RESERVED_NAMES
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
    """``vector``, ``layers``, ``file``, ``directory`` or ``value`` for one
    output name."""
    for output in info.outputs:
        if output.name == name:
            if output.kind in VECTOR_OUTPUT_KINDS:
                return "vector"
            if output.kind in MULTI_OUTPUT_KINDS:
                return "layers"
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

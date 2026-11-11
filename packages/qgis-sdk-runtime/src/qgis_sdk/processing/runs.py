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
from dataclasses import replace
from pathlib import Path
from xml.etree import ElementTree

from qgis_sdk.models import (
    AlgorithmInfo,
    AlgorithmRun,
    FileRef,
    OutputInfo,
    ParameterInfo,
    QgisSdkAlgorithmRejectedError,
    TypedRun,
)


def _destination_name_tail1(**values):
    name = values["name"]
    parameter = values["parameter"]
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
#: The output kind a model's destination parameter exposes, for the run's
#: conversion: a sink is a vector file, a folder is a directory, and every
#: other destination is a file.
DESTINATION_OUTPUT_KINDS: dict[str, str] = {
    "sink": "outputVector",
    "vectorDestination": "outputVector",
    "folderDestination": "outputFolder",
}

#: Extension per destination kind when the registry names none.
DEFAULT_EXTENSIONS: dict[str, str] = {
    "sink": "gpkg",
    "vectorDestination": "gpkg",
    "rasterDestination": "tif",
    "pointCloudDestination": "las",
    "vectorTileDestination": "mbtiles",
    "fileDestination": "out",
}


def _is_local_destination(value: object) -> bool:
    """Whether a destination names a path this machine writes.

    A URI names somewhere else and a pipe hands the bytes to another process;
    neither is a file the run can stage.
    """
    if not isinstance(value, str) or not value:
        return False
    return "://" not in value and "|" not in value


def declared_model_outputs(model_file: Path) -> dict[str, str]:
    """What a ``.model3`` document says each exposed output is, by description.

    A model file records its exposed outputs under ``outputs``, each naming
    the child, the child's output and the designer's description. A loaded
    model may answer neither: this Processing derives the destinations from
    the children and hands them back without their descriptions, so the
    document is read for what the designer wrote. Every entry is keyed by the
    ``child:output`` destination the run answers under and by the model
    output's own name, because either can be that name.

    A model file this reader cannot parse answers nothing at all: the naming
    rule then falls back to the child's own name, which is still a true name
    for an output the model does not describe.
    """
    try:
        root = ElementTree.parse(model_file).getroot()
    except (OSError, ElementTree.ParseError):
        return {}
    declared: dict[str, str] = {}
    for section in root.iter("Option"):
        if section.get("name") != "outputs" or section.get("type") != "Map":
            continue
        for entry in section.findall("Option"):
            name = entry.get("name") or ""
            fields = {
                option.get("name"): option.get("value") or ""
                for option in entry.findall("Option")
            }
            description = fields.get("description") or ""
            if not name or not description:
                continue
            declared[name] = description
            child = fields.get("child_id") or ""
            output = fields.get("output_name") or name
            if child:
                declared[f"{child}:{output}"] = description
    return declared


def model_output_names(
    info: AlgorithmInfo,
    descriptions: Mapping[str, str] | None = None,
) -> tuple[AlgorithmInfo, dict[str, str]]:
    """A model's outputs, named the way version 2 of the format derives them.

    A model exposes a *child* output, and the child names it after itself
    (``CENTROIDS``); version 2 of the format names the exposed output after
    its description instead - ``Centroids`` becomes ``centroids`` and
    ``Report`` becomes ``report`` - because the child's name belongs to the
    child that writes it. A loaded model describes those outputs twice: as
    output definitions, whose description is often empty and whose name is
    the destination's, and as the destination parameters the format derives,
    whose description is the designer's. The description decides, the tail of
    the child output's name is the fallback, and the mapping answers both the
    description the caller reads (an ``AlgorithmInfo`` whose outputs carry
    the derived names) and the names a run answers under.

    ``descriptions`` is what the loaded model itself declares - keyed by an
    output's own name or by the ``child:output`` destination it exposes - and
    it is the source that survives a QGIS which drops descriptions from the
    parameter definitions. It wins over both.
    """
    declared_text = dict(descriptions or {})

    def derived(label: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")

    def tail(name: str) -> str:
        return name.rsplit(":", 1)[-1].lower()

    names: dict[str, str] = {}
    for output in info.outputs:
        text = declared_text.get(output.name, output.label)
        names[output.name] = derived(text) or tail(output.name)
    # The destination parameter is the same output seen from the run's side,
    # and its description is the one the designer wrote, so it wins.
    for parameter in info.parameters:
        if not parameter.destination:
            continue
        text = declared_text.get(parameter.name, parameter.label)
        names[parameter.name] = (
            derived(text) or names.get(parameter.name) or tail(parameter.name)
        )
    taken: set[str] = set()
    for key, candidate in list(names.items()):
        base = candidate
        suffix = 2
        while candidate in taken:
            candidate = f"{base}_{suffix}"
            suffix += 1
        taken.add(candidate)
        names[key] = candidate
    declared = {output.name for output in info.outputs}
    described = [replace(output, name=names[output.name]) for output in info.outputs]
    for parameter in info.parameters:
        if not parameter.destination:
            continue
        candidate = names[parameter.name]
        if candidate in {output.name for output in described}:
            continue
        described.append(
            OutputInfo(
                name=candidate,
                kind=DESTINATION_OUTPUT_KINDS.get(parameter.kind, "outputFile"),
                label=parameter.label,
            )
        )
        declared.add(candidate)
    return replace(info, outputs=tuple(described)), names


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
        elif _is_local_destination(value):
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
    return _destination_name_tail1(**{**globals(), **locals()})


def destination_path(run_directory: Path, parameter: ParameterInfo) -> Path:
    """Place a qualified allocated destination directly in the run directory."""
    return run_directory / _destination_name(parameter)


def _output_kind_class(kind: str) -> str:
    """The result class a declared output kind produces."""
    if kind in VECTOR_OUTPUT_KINDS:
        return "vector"
    if kind in MULTI_OUTPUT_KINDS:
        return "layers"
    if kind == "outputFolder":
        return "directory"
    if kind in FILE_OUTPUT_KINDS:
        return "file"
    return "value"


def _destination_class(kind: str) -> str:
    """The result class a declared destination parameter produces."""
    if kind in ("sink", "vectorDestination"):
        return "vector"
    if kind == "folderDestination":
        return "directory"
    return "file"


def output_class(info: AlgorithmInfo, name: str) -> str:
    """``vector``, ``layers``, ``file``, ``directory`` or ``value`` for one
    output name."""
    for output in info.outputs:
        if output.name == name:
            return _output_kind_class(output.kind)
    parameter = info.parameter(name)
    if parameter is not None and parameter.destination:
        return _destination_class(parameter.kind)
    return "value"

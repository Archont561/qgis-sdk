"""Destination planning: validate allocated names and plan new local files."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from pathlib import Path

from qgis_sdk.models import (
    AlgorithmInfo,
    FileRef,
    ParameterInfo,
    QgisSdkAlgorithmRejectedError,
)

from ._names import destination_name

__all__ = ["plan_destinations"]


def _is_local_destination(value: object) -> bool:
    """Whether a destination names a path this machine writes.

    A URI names somewhere else and a pipe hands the bytes to another process;
    neither is a file the run can stage.
    """
    if not isinstance(value, str) or not value:
        return False
    return "://" not in value and "|" not in value


def _allocated_names(info: AlgorithmInfo, params: Mapping[str, object]) -> None:
    """Refuse two implicit destinations that translate to the same file name."""
    allocated: set[str] = set()
    for parameter in info.parameters:
        if not parameter.destination or params.get(parameter.name) is not None:
            continue
        try:
            relative = destination_name(parameter).lower()
        except ValueError as error:
            raise QgisSdkAlgorithmRejectedError(info.id, [str(error)]) from error
        if relative in allocated:
            raise QgisSdkAlgorithmRejectedError(
                info.id, ["allocated destination names collide"]
            )
        allocated.add(relative)


def _explicit_destinations(
    info: AlgorithmInfo, params: Mapping[str, object]
) -> list[tuple[ParameterInfo, object]]:
    """At most one destination may be published safely in a single run."""
    supplied = [
        (parameter, params[parameter.name])
        for parameter in info.parameters
        if parameter.destination and params.get(parameter.name) is not None
    ]
    if len(supplied) > 1:
        raise QgisSdkAlgorithmRejectedError(
            info.id, ["at most one explicit destination can be published safely"]
        )
    return supplied


def _destination_file(
    value: object,
    parameter: ParameterInfo,
    resolve_file: Callable[[FileRef], Path],
    info: AlgorithmInfo,
) -> Path:
    """A FileRef or a local string path; never a URI or a pipe."""
    if isinstance(value, FileRef):
        return resolve_file(value)
    if _is_local_destination(value):
        return Path(value)
    raise QgisSdkAlgorithmRejectedError(
        info.id, [f"{parameter.name} must be a new local file destination"]
    )


def _check_vector_file(parameter: ParameterInfo, path: Path, algorithm_id: str) -> None:
    """Only new GeoJSON and GeoPackage vector files are publishable."""
    if parameter.kind not in {
        "sink",
        "vectorDestination",
    } or path.suffix.lower() not in {".geojson", ".gpkg"}:
        raise QgisSdkAlgorithmRejectedError(
            algorithm_id,
            [f"{parameter.name} supports only new GeoJSON or GeoPackage vector files"],
        )


def _new_vector_path(path: Path, parameter: ParameterInfo, algorithm_id: str) -> Path:
    """Resolve an existing parent and refuse a path that is already taken."""
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
            algorithm_id, [f"{parameter.name} cannot be published safely: {error}"]
        ) from error
    except (OSError, RuntimeError) as error:
        raise QgisSdkAlgorithmRejectedError(
            algorithm_id, [f"{parameter.name} destination cannot be verified"]
        ) from error
    return path


def plan_destinations(
    info: AlgorithmInfo,
    params: Mapping[str, object],
    resolve_file: Callable[[FileRef], Path],
) -> dict[str, Path]:
    """Validate allocated names and plan at most one new local vector file."""
    _allocated_names(info, params)
    result: dict[str, Path] = {}
    for parameter, value in _explicit_destinations(info, params):
        path = _destination_file(value, parameter, resolve_file, info)
        _check_vector_file(parameter, path, info.id)
        result[parameter.name] = _new_vector_path(path, parameter, info.id)
    return result

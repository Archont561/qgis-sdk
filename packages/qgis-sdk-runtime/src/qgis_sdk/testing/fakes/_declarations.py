"""In-memory service fakes: the same contracts the native adapters implement.

Fakes exist so pure tests can exercise a workflow without QGIS, and so the
contract suite can hold a fake and the future native adapter to identical
expectations. They are not emulators: they store what the contract
observes and no more.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from qgis_sdk.core import ResourceScope
from qgis_sdk.models import (
    LAYER_KINDS,
    AlgorithmRun,
    Catalogue,
    FileRef,
    GeometryType,
    validate_parameters,
)
from qgis_sdk.processing.runs import output_class, plan_destinations
from qgis_sdk.testing.project import FakeProject

if TYPE_CHECKING:
    from qgis_sdk.testing.fakes._layers import FakeLayers

if TYPE_CHECKING:
    from qgis_sdk.files import FilesService
ScriptedOutputs = Mapping[str, object] | Callable[[AlgorithmRun], Mapping[str, object]]
ScriptedModelOutputs = (
    Mapping[str, object]
    | Callable[[FileRef, Mapping[str, object]], Mapping[str, object]]
)


@dataclass(frozen=True, slots=True)
class FakeAlgorithmSetup:
    """The collaborators one ``FakeAlgorithms`` backend is built from."""

    layers: FakeLayers
    scope: ResourceScope
    catalogue: Catalogue | None = None
    files: FilesService | None = None
    workers: Any | None = None


@dataclass(frozen=True, slots=True)
class DeclaredOutput:
    """What one ``AlgorithmRequest`` type produces, as a vector dataset."""

    request_type: type
    source: Path
    name: str
    geometry_type: GeometryType
    field_names: Sequence[str]
    crs: str | None = None


@dataclass(frozen=True, slots=True)
class VectorLayerDeclaration:
    """One vector dataset a ``FakeLayers`` backend can open."""

    source: Path
    name: str
    geometry_type: GeometryType
    field_names: Sequence[str]
    crs: str | None = None
    dataset_path: Path | None = None


@dataclass(frozen=True, slots=True)
class OtherLayerDeclaration:
    """One mesh, point-cloud, tile or scene dataset a ``FakeLayers`` can open."""

    source: Path
    name: str
    kind: str
    crs: str | None = None
    dataset_path: Path | None = None
    detail: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ConnectionDeclaration:
    """One registered connection and the schemas it browses to."""

    name: str
    provider: str = "ogr"
    auth_config: str | None = None
    schemas: Sequence[str] = ()
    valid: bool = True
    message: str | None = None
    accepts_auth: bool = True


@dataclass(frozen=True, slots=True)
class TableDeclaration:
    """One table or view inside a declared connection."""

    connection: str
    name: str
    provider: str = "ogr"
    schema: str = ""
    kind: str = "vector"
    geometries: Sequence[str] = ()
    fields: Sequence[str] = ()
    crs: str | None = None


def validate_run(algorithms, info, run) -> None:
    """Validate the params and layer inputs exactly as the host would."""
    validate_parameters(info, run.params)
    plan_destinations(
        info,
        run.params,
        lambda ref: algorithms._file_service().resolve(ref, operation="write"),
    )
    for parameter in info.parameters:
        value = run.params.get(parameter.name)
        if value is None or parameter.kind not in LAYER_KINDS:
            continue
        # Same rule as the native adapter: an owned layer id, a ref, or
        # an existing path; anything else is an unknown layer.
        if isinstance(value, str) and not Path(value).exists():
            algorithms._layers.layer(value)


def _open_vector_output(algorithms, value):
    return algorithms._layers.open_vector(value)


def _grant_directory_output(algorithms, value):
    return algorithms._file_service().grant_directory(value)


def _grant_file_output(algorithms, value):
    return algorithms._file_service().grant_file(value)


_PATH_OUTPUTS = {
    "vector": _open_vector_output,
    "directory": _grant_directory_output,
    "file": _grant_file_output,
}


def _path_output(algorithms, kind, value):
    resolver = _PATH_OUTPUTS.get(kind)
    return resolver(algorithms, value) if resolver is not None else value


def _output_value(algorithms, info, name, value):
    kind = output_class(info, name)
    if isinstance(value, Path):
        return _path_output(algorithms, kind, value)
    if kind == "layers" and isinstance(value, (list, tuple)):
        return tuple(
            algorithms._layers.open_vector(item) if isinstance(item, Path) else item
            for item in value
        )
    return value


def resolve_outputs(algorithms, info, answer):
    return {
        name: _output_value(algorithms, info, name, value)
        for name, value in answer.items()
    }


__all__ = [
    "FakeProject",
]

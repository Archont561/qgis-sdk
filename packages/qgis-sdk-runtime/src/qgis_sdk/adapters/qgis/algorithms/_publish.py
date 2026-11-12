"""Turning a Processing answer into an SDK result: validation and publishing.

A provider's answer is not trusted: the staged vector is re-checked (independent
file, expected driver, no sidecars), the write grant is re-checked, and only then
is the destination hard-linked into place, so a destination that already exists
is refused rather than overwritten. ``convert_outputs`` is the other half - the
answer's values as layers, refs or plain scalars.

``buffer`` and ``centroid`` live here because they are the two algorithms the
adapter runs itself rather than through a declared provider, and both go through
the same staging the publishing half verifies.

This module is a leaf: the only thing it needs from its siblings is the shape of
``NativeAlgorithms`` in an annotation, and that is imported for the type checker
alone so the two do not import each other.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from qgis.core import QgsVectorLayer

from qgis_sdk.models import (
    BufferRequest,
    CentroidRequest,
    FileRef,
    QgisSdkAlgorithmFailedError,
)
from qgis_sdk.processing.runs import (
    output_class,
)

from ._values import plain, require_metric_projected_crs

if TYPE_CHECKING:
    from ._native import NativeAlgorithms


def _publish_facts(request: PublishRequest) -> PublishFacts:
    name, destination = next(iter(request.explicit.items()))
    return PublishFacts(
        algorithm=request.algorithm,
        raw=request.raw,
        params=request.params,
        stage=request.stage,
        name=name,
        destination=destination,
        partial=request.staged[name],
    )


def _require_valid_answer(facts: PublishFacts) -> None:
    if not isinstance(facts.raw, Mapping):
        raise QgisSdkAlgorithmFailedError(
            facts.algorithm, "the provider returned invalid outputs"
        )
    value = facts.raw.get(facts.name)
    if not staged_vector_is_sound(facts.stage, value, facts.partial):
        raise QgisSdkAlgorithmFailedError(
            facts.algorithm, "the provider did not produce the staged vector file"
        )


def _require_independent(facts: PublishFacts) -> None:
    try:
        independent = facts.partial.stat().st_nlink == 1
    except OSError as error:
        raise QgisSdkAlgorithmFailedError(
            facts.algorithm, "the staged vector file cannot be verified"
        ) from error
    if not independent:
        raise QgisSdkAlgorithmFailedError(
            facts.algorithm, "the staged vector file is not an independent file"
        )


def _vector_driver(facts: PublishFacts) -> str | None:
    probe = QgsVectorLayer(str(facts.partial), "export validation", "ogr")
    valid = probe.isValid()
    driver = probe.dataProvider().storageType() if valid else None
    del probe
    if not valid:
        raise QgisSdkAlgorithmFailedError(
            facts.algorithm, "the staged vector file is not readable"
        )
    return driver


def _require_vector_format(facts: PublishFacts, driver: str | None) -> None:
    expected = {".gpkg": "GPKG", ".geojson": "GeoJSON"}[
        facts.destination.suffix.lower()
    ]
    if driver != expected:
        raise QgisSdkAlgorithmFailedError(
            facts.algorithm, "the staged vector file has an unexpected format"
        )


def _require_no_sidecars(facts: PublishFacts) -> None:
    try:
        staged_files = set(facts.stage.iterdir())
    except OSError as error:
        raise QgisSdkAlgorithmFailedError(
            facts.algorithm, "the output staging directory cannot be verified"
        ) from error
    if staged_files != {facts.partial}:
        raise QgisSdkAlgorithmFailedError(
            facts.algorithm, "the staged output has unsupported sidecars"
        )


def _require_still_granted(owner: NativeAlgorithms, facts: PublishFacts) -> None:
    owner._scope.ensure_open()
    value = facts.params.get(facts.name)
    if (
        isinstance(value, FileRef)
        and owner._resolve(value, "write") != facts.destination
    ):
        raise QgisSdkAlgorithmFailedError(
            facts.algorithm, "the output write grant changed during processing"
        )


def _hardlink(facts: PublishFacts) -> None:
    try:
        facts.destination.hardlink_to(facts.partial)
    except FileExistsError as error:
        raise QgisSdkAlgorithmFailedError(
            facts.algorithm, "the destination already exists; choose a new file"
        ) from error
    except OSError as error:
        raise QgisSdkAlgorithmFailedError(
            facts.algorithm,
            "cannot safely publish the output; hard-link support is required",
        ) from error


def publish_explicit(
    owner: NativeAlgorithms, request: PublishRequest
) -> dict[str, Any]:
    facts = _publish_facts(request)
    _require_valid_answer(facts)
    _require_independent(facts)
    driver = _vector_driver(facts)
    _require_vector_format(facts, driver)
    _require_no_sidecars(facts)
    _require_still_granted(owner, facts)
    _hardlink(facts)
    result = dict(facts.raw)
    result[facts.name] = str(facts.destination)
    return result


def _vector_output(owner, value, _kind, _info):
    if not isinstance(value, str) or not value:
        return plain(value)
    return owner._layers.open_vector(Path(value))


def _layers_output(owner, value, _kind, info):
    if not isinstance(value, (list, tuple)):
        return plain(value)
    if not all(isinstance(item, str) and item for item in value):
        raise QgisSdkAlgorithmFailedError(
            info.id, ["the provider returned invalid outputs"]
        )
    return tuple(owner._layers.open_vector(Path(item)) for item in value)


def _file_output(owner, value, kind, _info):
    if not isinstance(value, str) or not value:
        return plain(value)
    return _file_output_ref(owner, Path(value), kind)


def _file_output_ref(owner, path: Path, kind: str) -> object:
    """A readable ref for what the run wrote; the path itself without a
    files service (a bare standalone runtime)."""
    if not path.exists() or owner._files is None:
        return str(path)
    if kind == "directory":
        return owner._files.grant_directory(path)
    return owner._files.grant_file(path, operations=("read",))


_OUTPUT_CONVERTERS = {
    "vector": _vector_output,
    "layers": _layers_output,
    "file": _file_output,
    "directory": _file_output,
}


def convert_outputs(owner, info, raw) -> dict[str, object]:
    return {name: _convert_one(owner, info, name, value) for name, value in raw.items()}


def _convert_one(owner, info, name, value):
    kind = output_class(info, name)
    converter = _OUTPUT_CONVERTERS.get(kind)
    if converter is None:
        return plain(value)
    return converter(owner, value, kind, info)


def _reproject_parameters(source, request: BufferRequest, reprojected: Path):
    return {
        "INPUT": source,
        "TARGET_CRS": request.working_crs,
        "OUTPUT": str(reprojected),
    }


def _buffer_run_parameters(reprojected: Path, request: BufferRequest, output: Path):
    return {
        "INPUT": str(reprojected),
        "DISTANCE": request.distance_metres,
        "SEGMENTS": 8,
        "END_CAP_STYLE": 0,
        "JOIN_STYLE": 0,
        "MITER_LIMIT": 2.0,
        "DISSOLVE": False,
        "OUTPUT": str(output),
    }


def buffer(
    owner: NativeAlgorithms, processing, request: BufferRequest, run_directory: Path
) -> Path:
    """Reproject into the caller's working CRS, then buffer in metres."""
    source = owner._layers._qgs_layer(request.layer_id)
    require_metric_projected_crs(request.working_crs, "buffer")
    reprojected = run_directory / "reprojected.gpkg"
    output = run_directory / "buffer.gpkg"
    processing.run(
        "native:reprojectlayer", _reproject_parameters(source, request, reprojected)
    )
    processing.run(
        "native:buffer", _buffer_run_parameters(reprojected, request, output)
    )
    # The intermediate is this execution's own scaffolding, not a result.
    reprojected.unlink(missing_ok=True)
    return output


def centroid(
    owner: NativeAlgorithms, processing, request: CentroidRequest, run_directory: Path
) -> Path:
    """Replace geometries with centroids; no distance, so no working CRS."""
    source = owner._layers._qgs_layer(request.layer_id)
    output = run_directory / "centroid.gpkg"
    processing.run("native:centroids", {"INPUT": source, "OUTPUT": str(output)})
    return output


def staged_vector_is_sound(stage: object, value: object, partial: Path) -> bool:
    """Whether the provider's answer is the staged vector file the graph expects.

    Four things have to hold: the run was staged, the provider answered a path,
    that path is the staged one, and it is a real file rather than a link to
    somebody else's.
    """
    if stage is None or not isinstance(value, str):
        return False
    if Path(value) != partial:
        return False
    return not partial.is_symlink() and partial.is_file()


@dataclass(frozen=True, slots=True)
class PublishRequest:
    algorithm: str
    raw: Mapping[str, Any]
    params: Mapping[str, object]
    explicit: Mapping[str, Path]
    staged: Mapping[str, Path]
    stage: Path | None


@dataclass(frozen=True, slots=True)
class PublishFacts:
    algorithm: str
    raw: Mapping[str, Any]
    params: Mapping[str, object]
    stage: Path | None
    name: str
    destination: Path
    partial: Path

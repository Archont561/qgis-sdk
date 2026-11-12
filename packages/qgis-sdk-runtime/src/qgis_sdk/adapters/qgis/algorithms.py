"""PyQGIS-backed ``Algorithms``: QGIS Processing, into new temporary outputs.

Native module: nothing on the pure side may import it. Two things here are worth
knowing before reading the code.

**The chained buffer.** ``native:buffer`` measures in the layer's own units, so
buffering a WGS 84 layer would silently interpret ``distance_metres`` as degrees.
The adapter therefore reprojects the source into the caller's working CRS first
and buffers there. The caller states the CRS; the adapter never picks one, and it
refuses a working CRS that is geographic or whose units are not metres rather
than converting behind the caller's back (decision-19).

**Output ownership.** Omitted destinations are allocated in a run directory;
a qualified named vector destination is staged beside its destination and
published without replacement. Cleanup is best-effort and limited to the
SDK-owned directories. Registered Processing providers are trusted code and
may modify inputs or write elsewhere; their side effects are not sandboxed or
rolled back by this adapter.

Reading cancellation and progress is ``invoke``'s job at phase boundaries. This
adapter deliberately does not claim to abort a native operation mid-flight: a
feedback bridge that raises inside QGIS's own loop has not been qualified here.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from qgis.core import Qgis, QgsApplication, QgsCoordinateReferenceSystem, QgsVectorLayer

from qgis_sdk.batch import batch_body, batch_items
from qgis_sdk.core import ResourceScope
from qgis_sdk.jobs import JobHandle, JobService
from qgis_sdk.models import (
    LAYER_KINDS,
    AlgorithmInfo,
    AlgorithmRequest,
    AlgorithmRun,
    BufferRequest,
    CentroidRequest,
    FileRef,
    ProviderInfo,
    QgisSdkAlgorithmFailedError,
    QgisSdkAlgorithmNotFoundError,
    QgisSdkAlgorithmRejectedError,
    QgisSdkLayerNotFoundError,
    QgisSdkUnsupportedCapabilityError,
    RunResult,
    TypedRun,
    VectorLayerInfo,
    validate_parameters,
)
from qgis_sdk.processing.runs import (
    coerce_run,
    declared_model_outputs,
    destination_path,
    model_output_names,
    output_class,
    plan_destinations,
)

from .layers import NativeLayers

if TYPE_CHECKING:
    from qgis_sdk.files import FilesService

__all__ = ["AlgorithmWiring", "NativeAlgorithms"]

METRES_ONLY: str = "metres"


class _ProcessingReady:
    """Whether the Processing framework was initialised in this process."""

    def __init__(self) -> None:
        self.ready = False


_processing_ready = _ProcessingReady()


def _processing():
    """Import the Processing framework, initialising it once per process.

    ``from qgis import processing`` is only the shim; the framework itself is the
    plugin, which has to be on ``sys.path`` and initialised. QGIS Desktop does
    both at startup. A headless embedder that has only set the prefix gets the
    plugin directory appended here once, which is the same path QGIS's own
    startup uses.
    """
    try:
        from processing.core.Processing import Processing
    except ImportError:
        plugins = Path(QgsApplication.prefixPath()) / "share" / "qgis" / "python"
        for candidate in (plugins / "plugins",):
            if candidate.is_dir() and str(candidate) not in sys.path:
                sys.path.append(str(candidate))
        try:
            from processing.core.Processing import Processing
        except ImportError as error:
            raise QgisSdkUnsupportedCapabilityError("processing") from error
    if not _processing_ready.ready:
        Processing.initialize()
        _processing_ready.ready = True
    from qgis import processing

    return processing


def _declared_outputs(model: Any) -> dict[str, str]:
    """What a loaded model declares about its exposed outputs, by description.

    ``modelOutputDefinitions`` is the designer's own map, so it survives a
    Processing that answers the derived destination parameters without
    carrying their descriptions. Each entry is keyed twice - by the model
    output's name and by the ``child:output`` destination the run answers
    under - because either can be the name a run produces.
    """
    declared: dict[str, str] = {}
    definitions = getattr(model, "modelOutputDefinitions", None)
    if definitions is None:
        return declared
    for name, output in dict(definitions() or {}).items():
        text = output.description() if hasattr(output, "description") else ""
        if not text:
            continue
        declared[str(name)] = text
        child = output.childId() if hasattr(output, "childId") else ""
        child_output = (
            output.childOutputName() if hasattr(output, "childOutputName") else ""
        )
        if child:
            declared[f"{child}:{child_output or name}"] = text
            declared[f"{child}:{name}"] = text
    return declared


def _staged_vector_is_sound(stage: object, value: object, partial: Path) -> bool:
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
class AlgorithmWiring:
    """The host objects one ``NativeAlgorithms`` backend borrows.

    One record instead of six keyword parameters: the layers, scope, working
    directory, files service and worker backend are the same facts a Desktop
    context and a contract-test fixture assemble, and passing them as a record
    is what keeps the two call sites from drifting apart.
    """

    layers: NativeLayers
    scope: ResourceScope
    working_directory: Path | None = None
    files: FilesService | None = None
    workers: Any | None = None


@dataclass(frozen=True, slots=True)
class _RunRequest:
    info: AlgorithmInfo
    params: Mapping[str, object]
    target: Any
    label: str
    rename: Mapping[str, str] | None = None


@dataclass(frozen=True, slots=True)
class _NativeParams:
    info: AlgorithmInfo
    params: Mapping[str, object]
    run_directory: Path
    staged: Mapping[str, Path]


@dataclass(frozen=True, slots=True)
class _PublishRequest:
    algorithm: str
    raw: Mapping[str, Any]
    params: Mapping[str, object]
    explicit: Mapping[str, Path]
    staged: Mapping[str, Path]
    stage: Path | None


@dataclass(frozen=True, slots=True)
class _PublishFacts:
    algorithm: str
    raw: Mapping[str, Any]
    params: Mapping[str, object]
    stage: Path | None
    name: str
    destination: Path
    partial: Path


@dataclass(slots=True)
class _RunStage:
    owner: NativeAlgorithms
    request: _RunRequest
    explicit: Mapping[str, Path]
    processing: Any
    run_directory: Path
    stage: Path | None = None
    staged: dict[str, Path] = field(default_factory=dict)

    def execute(self) -> dict[str, object]:
        self._stage_outputs()
        raw = self._call_processing()
        if self.explicit:
            raw = self._publish(raw)
        if self.request.rename:
            raw = _rename_outputs(raw, self.request.rename)
        return _convert_outputs(self.owner, self.request.info, raw)

    def _stage_outputs(self) -> None:
        if not self.explicit:
            return
        name, destination = next(iter(self.explicit.items()))
        try:
            self.stage = Path(
                tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent)
            )
        except OSError as error:
            raise QgisSdkAlgorithmFailedError(
                self.request.label, "cannot create the output staging directory"
            ) from error
        self.staged[name] = self.stage / destination.name

    def _call_processing(self) -> Mapping[str, Any]:
        native = _native_parameters(
            self.owner,
            _NativeParams(
                info=self.request.info,
                params=self.request.params,
                run_directory=self.run_directory,
                staged=self.staged,
            ),
        )
        try:
            return self.processing.run(self.request.target, native)
        except Exception as error:
            raise QgisSdkAlgorithmFailedError(self.request.label, str(error)) from error

    def _publish(self, raw: Mapping[str, Any]) -> dict[str, Any]:
        return _publish_explicit(
            self.owner,
            _PublishRequest(
                algorithm=self.request.label,
                raw=raw,
                params=self.request.params,
                explicit=self.explicit,
                staged=self.staged,
                stage=self.stage,
            ),
        )

    def cleanup(self) -> None:
        if self.stage is not None:
            shutil.rmtree(self.stage, ignore_errors=True)


def _load_model(owner: NativeAlgorithms, model: FileRef) -> Any:
    from qgis.core import QgsProcessingModelAlgorithm

    loaded = QgsProcessingModelAlgorithm()
    try:
        loaded_from_file = loaded.fromFile(str(owner._resolve(model, "read")))
    except Exception as error:
        raise QgisSdkAlgorithmFailedError(model.name, str(error)) from error
    if not loaded_from_file:
        raise QgisSdkAlgorithmFailedError(
            model.name, f"{model.name} is not a model file this QGIS can load"
        )
    return loaded


def _model_run_request(
    owner: NativeAlgorithms,
    loaded: Any,
    model: FileRef,
    params: Mapping[str, object] | None,
) -> _RunRequest:
    from .catalogue import algorithm_info

    declared = {
        **declared_model_outputs(owner._resolve(model, "read")),
        **_declared_outputs(loaded),
    }
    info, output_names = model_output_names(algorithm_info(loaded, "model"), declared)
    return _RunRequest(
        info=info,
        params=dict(params or {}),
        target=loaded,
        label=model.name,
        rename=output_names,
    )


def _new_run_directory(owner: NativeAlgorithms, label: str) -> Path:
    run_directory = owner._root / f"run-{owner._runs}"
    try:
        run_directory.mkdir()
    except OSError as error:
        raise QgisSdkAlgorithmFailedError(
            label, "cannot create a new run directory"
        ) from error
    return run_directory


def _run_described(owner: NativeAlgorithms, request: _RunRequest) -> RunResult:
    validate_parameters(request.info, request.params)
    explicit = plan_destinations(
        request.info, request.params, lambda ref: owner._resolve(ref, "write")
    )
    processing = _processing()
    owner._runs += 1
    run_directory = _new_run_directory(owner, request.label)
    stage = _RunStage(
        owner=owner,
        request=request,
        explicit=explicit,
        processing=processing,
        run_directory=run_directory,
    )
    try:
        outputs = stage.execute()
    except BaseException:
        shutil.rmtree(run_directory, ignore_errors=True)
        raise
    finally:
        stage.cleanup()
    return RunResult(algorithm=request.label, outputs=outputs)


def _rename_outputs(
    raw: Mapping[str, Any], rename: Mapping[str, str]
) -> dict[str, Any]:
    lowered = {key.lower(): value for key, value in rename.items()}
    return {lowered.get(key.lower(), key): value for key, value in raw.items()}


def _native_parameters(owner: NativeAlgorithms, ctx: _NativeParams) -> dict[str, Any]:
    native: dict[str, Any] = {}
    for parameter in ctx.info.parameters:
        value = ctx.params.get(parameter.name)
        if parameter.destination:
            native[parameter.name] = _destination_value(owner, ctx, parameter, value)
            continue
        if value is None:
            continue
        native[parameter.name] = _input_value(owner, parameter, value)
    return native


def _destination_value(owner: NativeAlgorithms, ctx: _NativeParams, parameter, value):
    if parameter.name in ctx.staged:
        return str(ctx.staged[parameter.name])
    if value is None:
        return str(destination_path(ctx.run_directory, parameter))
    raise QgisSdkAlgorithmRejectedError(
        ctx.info.id, [f"{parameter.name} was not safely staged"]
    )


def _input_value(owner: NativeAlgorithms, parameter, value):
    if parameter.kind in LAYER_KINDS:
        return _layer_input(owner, value)
    if parameter.kind == "multilayer" and isinstance(value, (list, tuple)):
        return [_layer_input(owner, item) for item in value]
    if isinstance(value, FileRef):
        return str(owner._resolve(value, "read"))
    return value


def _layer_input(owner: NativeAlgorithms, value: object) -> Any:
    """An owned layer id, a readable ref, or an existing source string."""
    if isinstance(value, FileRef):
        return str(owner._resolve(value, "read"))
    if not isinstance(value, str):
        return value
    try:
        return owner._layers._qgs_layer(value)
    except QgisSdkLayerNotFoundError:
        if Path(value).exists() or "://" in value or "|" in value:
            return value
        raise


def _publish_facts(request: _PublishRequest) -> _PublishFacts:
    name, destination = next(iter(request.explicit.items()))
    return _PublishFacts(
        algorithm=request.algorithm,
        raw=request.raw,
        params=request.params,
        stage=request.stage,
        name=name,
        destination=destination,
        partial=request.staged[name],
    )


def _require_valid_answer(facts: _PublishFacts) -> None:
    if not isinstance(facts.raw, Mapping):
        raise QgisSdkAlgorithmFailedError(
            facts.algorithm, "the provider returned invalid outputs"
        )
    value = facts.raw.get(facts.name)
    if not _staged_vector_is_sound(facts.stage, value, facts.partial):
        raise QgisSdkAlgorithmFailedError(
            facts.algorithm, "the provider did not produce the staged vector file"
        )


def _require_independent(facts: _PublishFacts) -> None:
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


def _vector_driver(facts: _PublishFacts) -> str | None:
    probe = QgsVectorLayer(str(facts.partial), "export validation", "ogr")
    valid = probe.isValid()
    driver = probe.dataProvider().storageType() if valid else None
    del probe
    if not valid:
        raise QgisSdkAlgorithmFailedError(
            facts.algorithm, "the staged vector file is not readable"
        )
    return driver


def _require_vector_format(facts: _PublishFacts, driver: str | None) -> None:
    expected = {".gpkg": "GPKG", ".geojson": "GeoJSON"}[
        facts.destination.suffix.lower()
    ]
    if driver != expected:
        raise QgisSdkAlgorithmFailedError(
            facts.algorithm, "the staged vector file has an unexpected format"
        )


def _require_no_sidecars(facts: _PublishFacts) -> None:
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


def _require_still_granted(owner: NativeAlgorithms, facts: _PublishFacts) -> None:
    owner._scope.ensure_open()
    value = facts.params.get(facts.name)
    if (
        isinstance(value, FileRef)
        and owner._resolve(value, "write") != facts.destination
    ):
        raise QgisSdkAlgorithmFailedError(
            facts.algorithm, "the output write grant changed during processing"
        )


def _hardlink(facts: _PublishFacts) -> None:
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


def _publish_explicit(
    owner: NativeAlgorithms, request: _PublishRequest
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
        return _plain(value)
    return owner._layers.open_vector(Path(value))


def _layers_output(owner, value, _kind, info):
    if not isinstance(value, (list, tuple)):
        return _plain(value)
    if not all(isinstance(item, str) and item for item in value):
        raise QgisSdkAlgorithmFailedError(
            info.id, ["the provider returned invalid outputs"]
        )
    return tuple(owner._layers.open_vector(Path(item)) for item in value)


def _file_output(owner, value, kind, _info):
    if not isinstance(value, str) or not value:
        return _plain(value)
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


def _convert_outputs(owner, info, raw) -> dict[str, object]:
    return {name: _convert_one(owner, info, name, value) for name, value in raw.items()}


def _convert_one(owner, info, name, value):
    kind = output_class(info, name)
    converter = _OUTPUT_CONVERTERS.get(kind)
    if converter is None:
        return _plain(value)
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


def _buffer(
    owner: NativeAlgorithms, processing, request: BufferRequest, run_directory: Path
) -> Path:
    """Reproject into the caller's working CRS, then buffer in metres."""
    source = owner._layers._qgs_layer(request.layer_id)
    _require_metric_projected_crs(request.working_crs, "buffer")
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


def _centroid(
    owner: NativeAlgorithms, processing, request: CentroidRequest, run_directory: Path
) -> Path:
    """Replace geometries with centroids; no distance, so no working CRS."""
    source = owner._layers._qgs_layer(request.layer_id)
    output = run_directory / "centroid.gpkg"
    processing.run("native:centroids", {"INPUT": source, "OUTPUT": str(output)})
    return output


class NativeAlgorithms:
    """Run registered operations through QGIS Processing.

    ``working_directory`` is where temporary outputs go. The caller may supply
    one (a test asserting what is left behind does) - in that case the directory
    is not removed on scope close, because the runtime does not own it.
    """

    def __init__(self, wiring: AlgorithmWiring) -> None:
        self._layers = wiring.layers
        self._scope = wiring.scope
        self._files = wiring.files
        self._owns_root = wiring.working_directory is None
        root = (
            Path(tempfile.mkdtemp(prefix="qgis-sdk-algorithms-"))
            if wiring.working_directory is None
            else Path(wiring.working_directory)
        )
        root.mkdir(parents=True, exist_ok=True)
        self._root = root
        self._runs = 0
        self._jobs = JobService(wiring.scope, workers=wiring.workers)
        wiring.scope.on_close(self._release)

    # -- the registry -------------------------------------------------------

    def providers(self) -> tuple[ProviderInfo, ...]:
        self._scope.ensure_open()
        return self._catalogue().providers

    def list(self, provider: str | None = None) -> tuple[AlgorithmInfo, ...]:
        self._scope.ensure_open()
        catalogue = self._catalogue()
        return (
            catalogue.algorithms
            if provider is None
            else catalogue.by_provider(provider)
        )

    def describe(self, algorithm_id: str) -> AlgorithmInfo:
        """Describe one algorithm straight from the live registry."""
        self._scope.ensure_open()
        _processing()
        from .catalogue import algorithm_info

        algorithm = QgsApplication.processingRegistry().algorithmById(algorithm_id)
        if algorithm is None:
            raise QgisSdkAlgorithmNotFoundError(algorithm_id)
        return algorithm_info(algorithm, algorithm.provider().id())

    def _catalogue(self):
        """The registry read in full; cheap enough to read per call."""
        from .catalogue import read_catalogue

        return read_catalogue()

    # -- the generic run ----------------------------------------------------

    def run(
        self,
        request: AlgorithmRun | TypedRun | str,
        params: Mapping[str, object] | None = None,
    ) -> RunResult:
        """Run any registered algorithm into new outputs under a run directory."""
        self._scope.ensure_open()
        run = coerce_run(request, params)
        return _run_described(
            self,
            _RunRequest(
                info=self.describe(run.algorithm),
                params=run.params,
                target=run.algorithm,
                label=run.algorithm,
            ),
        )

    def run_model(
        self, model: FileRef, params: Mapping[str, object] | None = None
    ) -> RunResult:
        """Load one ``.model3`` model file and run it like a registered one.

        The model describes itself (its parameters and the destination-backed
        outputs ``updateDestinationParameters`` derives), so the run follows
        the same staging, validation and output conversion path as
        :meth:`run` and the outputs come back as the kinds the registry
        describes for that model.
        """
        self._scope.ensure_open()
        if not isinstance(model, FileRef):
            raise QgisSdkAlgorithmRejectedError(
                "run_model",
                ["a model is a FileRef the host minted, not a path (decision-20)"],
            )
        _processing()
        loaded = _load_model(self, model)
        return _run_described(self, _model_run_request(self, loaded, model, params))

    def batch(self, runs: Sequence[AlgorithmRun | TypedRun | str]) -> JobHandle:
        """Submit the batch as one job through this backend's job service."""
        self._scope.ensure_open()
        return self._jobs.bind(batch_body(self)).delay(runs=batch_items(runs))

    @property
    def jobs(self) -> JobService:
        """The job service ``batch`` submits through."""
        return self._jobs

    # -- the hand-written predecessors --------------------------------------

    def execute(self, request: AlgorithmRequest) -> VectorLayerInfo:
        """Run one request into a new output layer and describe that layer."""
        self._scope.ensure_open()
        processing = _processing()
        self._runs += 1
        run_directory = self._root / f"run-{self._runs}"
        run_directory.mkdir()
        try:
            if isinstance(request, BufferRequest):
                output = _buffer(self, processing, request, run_directory)
            elif isinstance(request, CentroidRequest):
                output = _centroid(self, processing, request, run_directory)
            else:
                raise QgisSdkAlgorithmRejectedError(
                    "execute", [f"unsupported request {type(request).__name__}"]
                )
        except BaseException:
            # decision-19: an incomplete output is removed before the caller sees
            # the failure, so a caller never has to know this directory exists.
            shutil.rmtree(run_directory, ignore_errors=True)
            raise
        return self._layers.open_vector(output)

    def _resolve(self, ref: FileRef, operation: str) -> Path:
        if self._files is None:
            raise QgisSdkAlgorithmRejectedError(
                "run", ["this runtime has no files service to resolve a FileRef with"]
            )
        return self._files.resolve(ref, operation=operation)

    def _release(self) -> None:
        """Remove this runtime's temporary tree; a caller's directory stays."""
        if self._owns_root:
            shutil.rmtree(self._root, ignore_errors=True)


def _plain(value: Any) -> object:
    """A scalar output as Python: QGIS hands numbers, strings and booleans
    over already; anything else is kept only by its text."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    return str(value)


def _require_metric_projected_crs(authid: str, request: str) -> None:
    """Refuse a working CRS a distance cannot honestly be measured in."""
    crs = QgsCoordinateReferenceSystem(authid)
    if not crs.isValid():
        raise QgisSdkAlgorithmRejectedError(
            request, [f"working_crs {authid!r} is not a known CRS"]
        )
    if crs.isGeographic():
        raise QgisSdkAlgorithmRejectedError(
            request,
            [
                f"working_crs {authid!r} is geographic; a distance there would be degrees"
            ],
        )
    if crs.mapUnits() != Qgis.DistanceUnit.Meters:
        raise QgisSdkAlgorithmRejectedError(
            request,
            [
                f"working_crs {authid!r} is not in {METRES_ONLY}; distance_metres would be wrong"
            ],
        )

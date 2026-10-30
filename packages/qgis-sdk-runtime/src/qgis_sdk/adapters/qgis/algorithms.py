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
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

from qgis.core import Qgis, QgsApplication, QgsCoordinateReferenceSystem, QgsVectorLayer

from qgis_sdk.core import ResourceScope
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
    destination_path,
    output_class,
    plan_destinations,
)

from .layers import NativeLayers

if TYPE_CHECKING:
    from qgis_sdk.files import FilesService

__all__ = ["NativeAlgorithms"]

METRES_ONLY: str = "metres"
_PROCESSING_READY = False


def _processing():
    """Import the Processing framework, initialising it once per process.

    ``from qgis import processing`` is only the shim; the framework itself is the
    plugin, which has to be on ``sys.path`` and initialised. QGIS Desktop does
    both at startup. A headless embedder that has only set the prefix gets the
    plugin directory appended here once, which is the same path QGIS's own
    startup uses.
    """
    global _PROCESSING_READY
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
    if not _PROCESSING_READY:
        Processing.initialize()
        _PROCESSING_READY = True
    from qgis import processing

    return processing


class NativeAlgorithms:
    """Run registered operations through QGIS Processing.

    ``working_directory`` is where temporary outputs go. The caller may supply
    one (a test asserting what is left behind does) - in that case the directory
    is not removed on scope close, because the runtime does not own it.
    """

    def __init__(
        self,
        layers: NativeLayers,
        scope: ResourceScope,
        *,
        working_directory: Path | None = None,
        files: FilesService | None = None,
    ) -> None:
        self._layers = layers
        self._scope = scope
        self._files = files
        self._owns_root = working_directory is None
        root = (
            Path(tempfile.mkdtemp(prefix="qgis-sdk-algorithms-"))
            if working_directory is None
            else Path(working_directory)
        )
        root.mkdir(parents=True, exist_ok=True)
        self._root = root
        self._runs = 0
        scope.on_close(self._release)

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
        info = self.describe(run.algorithm)
        validate_parameters(info, run.params)
        explicit = plan_destinations(
            info, run.params, lambda ref: self._resolve(ref, "write")
        )
        processing = _processing()
        self._runs += 1
        run_directory = self._root / f"run-{self._runs}"
        try:
            run_directory.mkdir()
        except OSError as error:
            raise QgisSdkAlgorithmFailedError(
                run.algorithm, "cannot create a new run directory"
            ) from error
        stage: Path | None = None
        try:
            staged: dict[str, Path] = {}
            if explicit:
                name, destination = next(iter(explicit.items()))
                try:
                    stage = Path(
                        tempfile.mkdtemp(
                            prefix=f".{destination.name}.", dir=destination.parent
                        )
                    )
                except OSError as error:
                    raise QgisSdkAlgorithmFailedError(
                        run.algorithm, "cannot create the output staging directory"
                    ) from error
                staged[name] = stage / destination.name
            native_params = self._native_parameters(
                info, run.params, run_directory, staged
            )
            try:
                raw = processing.run(run.algorithm, native_params)
            except Exception as error:  # QgsProcessingException and friends
                raise QgisSdkAlgorithmFailedError(run.algorithm, str(error)) from error
            if explicit:
                raw = self._publish_explicit(
                    run.algorithm, raw, run.params, explicit, staged, stage
                )
            outputs = self._convert_outputs(info, raw)
        except BaseException:
            shutil.rmtree(run_directory, ignore_errors=True)
            raise
        finally:
            if stage is not None:
                shutil.rmtree(stage, ignore_errors=True)
        return RunResult(algorithm=run.algorithm, outputs=outputs)

    def _publish_explicit(
        self,
        algorithm: str,
        raw: Mapping[str, Any],
        params: Mapping[str, object],
        explicit: Mapping[str, Path],
        staged: Mapping[str, Path],
        stage: Path | None,
    ) -> dict[str, Any]:
        """Publish only the single verified file, without replacing a name."""
        name, destination = next(iter(explicit.items()))
        partial = staged[name]
        if not isinstance(raw, Mapping):
            raise QgisSdkAlgorithmFailedError(
                algorithm, "the provider returned invalid outputs"
            )
        value = raw.get(name)
        if (
            stage is None
            or not isinstance(value, str)
            or Path(value) != partial
            or partial.is_symlink()
            or not partial.is_file()
        ):
            raise QgisSdkAlgorithmFailedError(
                algorithm, "the provider did not produce the staged vector file"
            )
        try:
            independent = partial.stat().st_nlink == 1
        except OSError as error:
            raise QgisSdkAlgorithmFailedError(
                algorithm, "the staged vector file cannot be verified"
            ) from error
        if not independent:
            raise QgisSdkAlgorithmFailedError(
                algorithm, "the staged vector file is not an independent file"
            )
        probe = QgsVectorLayer(str(partial), "export validation", "ogr")
        valid = probe.isValid()
        driver = probe.dataProvider().storageType() if valid else None
        del probe
        if not valid:
            raise QgisSdkAlgorithmFailedError(
                algorithm, "the staged vector file is not readable"
            )
        expected = {".gpkg": "GPKG", ".geojson": "GeoJSON"}[destination.suffix.lower()]
        if driver != expected:
            raise QgisSdkAlgorithmFailedError(
                algorithm, "the staged vector file has an unexpected format"
            )
        try:
            staged_files = set(stage.iterdir())
        except OSError as error:
            raise QgisSdkAlgorithmFailedError(
                algorithm, "the output staging directory cannot be verified"
            ) from error
        if staged_files != {partial}:
            raise QgisSdkAlgorithmFailedError(
                algorithm, "the staged output has unsupported sidecars"
            )
        self._scope.ensure_open()
        value = params.get(name)
        if isinstance(value, FileRef) and self._resolve(value, "write") != destination:
            raise QgisSdkAlgorithmFailedError(
                algorithm, "the output write grant changed during processing"
            )
        try:
            destination.hardlink_to(partial)
        except FileExistsError as error:
            raise QgisSdkAlgorithmFailedError(
                algorithm, "the destination already exists; choose a new file"
            ) from error
        except OSError as error:
            raise QgisSdkAlgorithmFailedError(
                algorithm,
                "cannot safely publish the output; hard-link support is required",
            ) from error
        result = dict(raw)
        result[name] = str(destination)
        return result

    def _native_parameters(
        self,
        info: AlgorithmInfo,
        params: Mapping[str, object],
        run_directory: Path,
        staged: Mapping[str, Path],
    ) -> dict[str, Any]:
        """Owned layer ids become layer handles, refs become paths, missing
        destinations are allocated; everything else is passed as given."""
        native: dict[str, Any] = {}
        for parameter in info.parameters:
            value = params.get(parameter.name)
            if parameter.destination:
                if parameter.name in staged:
                    native[parameter.name] = str(staged[parameter.name])
                elif value is None:
                    native[parameter.name] = str(
                        destination_path(run_directory, parameter)
                    )
                else:
                    raise QgisSdkAlgorithmRejectedError(
                        info.id, [f"{parameter.name} was not safely staged"]
                    )
                continue
            if value is None:
                continue
            if parameter.kind in LAYER_KINDS:
                native[parameter.name] = self._layer_input(value)
            elif parameter.kind == "multilayer" and isinstance(value, (list, tuple)):
                native[parameter.name] = [self._layer_input(item) for item in value]
            elif isinstance(value, FileRef):
                native[parameter.name] = str(self._resolve(value, "read"))
            else:
                native[parameter.name] = value
        return native

    def _layer_input(self, value: object) -> Any:
        """An owned layer id, a readable ref, or an existing source string."""
        if isinstance(value, FileRef):
            return str(self._resolve(value, "read"))
        if not isinstance(value, str):
            return value
        try:
            return self._layers._qgs_layer(value)
        except QgisSdkLayerNotFoundError:
            if Path(value).exists() or "://" in value or "|" in value:
                return value
            raise

    def _resolve(self, ref: FileRef, operation: str) -> Path:
        if self._files is None:
            raise QgisSdkAlgorithmRejectedError(
                "run", ["this runtime has no files service to resolve a FileRef with"]
            )
        return self._files.resolve(ref, operation=operation)

    def _convert_outputs(
        self, info: AlgorithmInfo, raw: Mapping[str, Any]
    ) -> dict[str, object]:
        outputs: dict[str, object] = {}
        for name, value in raw.items():
            kind = output_class(info, name)
            if kind == "vector" and isinstance(value, str) and value:
                outputs[name] = self._layers.open_vector(Path(value))
            elif kind in ("file", "directory") and isinstance(value, str) and value:
                outputs[name] = self._file_output(Path(value), kind)
            else:
                outputs[name] = _plain(value)
        return outputs

    def _file_output(self, path: Path, kind: str) -> object:
        """A readable ref for what the run wrote; the path itself without a
        files service (a bare standalone runtime)."""
        if not path.exists() or self._files is None:
            return str(path)
        if kind == "directory":
            return self._files.grant_directory(path)
        return self._files.grant_file(path, operations=("read",))

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
                output = self._buffer(processing, request, run_directory)
            elif isinstance(request, CentroidRequest):
                output = self._centroid(processing, request, run_directory)
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

    def _buffer(self, processing, request: BufferRequest, run_directory: Path) -> Path:
        """Reproject into the caller's working CRS, then buffer in metres."""
        source = self._layers._qgs_layer(request.layer_id)
        _require_metric_projected_crs(request.working_crs, "buffer")
        reprojected = run_directory / "reprojected.gpkg"
        processing.run(
            "native:reprojectlayer",
            {
                "INPUT": source,
                "TARGET_CRS": request.working_crs,
                "OUTPUT": str(reprojected),
            },
        )
        output = run_directory / "buffer.gpkg"
        processing.run(
            "native:buffer",
            {
                "INPUT": str(reprojected),
                "DISTANCE": request.distance_metres,
                "SEGMENTS": 8,
                "END_CAP_STYLE": 0,
                "JOIN_STYLE": 0,
                "MITER_LIMIT": 2.0,
                "DISSOLVE": False,
                "OUTPUT": str(output),
            },
        )
        # The intermediate is this execution's own scaffolding, not a result.
        reprojected.unlink(missing_ok=True)
        return output

    def _centroid(
        self, processing, request: CentroidRequest, run_directory: Path
    ) -> Path:
        """Replace geometries with centroids; no distance, so no working CRS."""
        source = self._layers._qgs_layer(request.layer_id)
        output = run_directory / "centroid.gpkg"
        processing.run("native:centroids", {"INPUT": source, "OUTPUT": str(output)})
        return output

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

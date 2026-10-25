"""PyQGIS-backed ``Algorithms``: QGIS Processing, into new temporary outputs.

Native module: nothing on the pure side may import it. Two things here are worth
knowing before reading the code.

**The chained buffer.** ``native:buffer`` measures in the layer's own units, so
buffering a WGS 84 layer would silently interpret ``distance_metres`` as degrees.
The adapter therefore reprojects the source into the caller's working CRS first
and buffers there. The caller states the CRS; the adapter never picks one, and it
refuses a working CRS that is geographic or whose units are not metres rather
than converting behind the caller's back (decision-19).

**Outputs are new files.** No step writes to the source dataset: the source is
passed to Processing as an input, and every output is a file under this
execution's working directory. The produced file is handed to ``NativeLayers``,
so the output is a layer this runtime owns exactly like any other - which is also
what makes adding it to the project possible later. A run that fails deletes its
own directory before re-raising, so no partial output survives an exception.

Reading cancellation and progress is ``invoke``'s job at phase boundaries. This
adapter deliberately does not claim to abort a native operation mid-flight: a
feedback bridge that raises inside QGIS's own loop has not been qualified here.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

from qgis.core import Qgis, QgsApplication, QgsCoordinateReferenceSystem

from qgis_sdk.core import ResourceScope
from qgis_sdk.models import (
    AlgorithmRequest,
    BufferRequest,
    CentroidRequest,
    QgisSdkAlgorithmRejectedError,
    QgisSdkUnsupportedCapabilityError,
    VectorLayerInfo,
)

from .layers import NativeLayers

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
    ) -> None:
        self._layers = layers
        self._scope = scope
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

"""PyQGIS-backed raster reads: bands, statistics, a point sample and an export.

Native module: importing it needs a QGIS installation, so nothing on the pure
side may import it (``tests/test_pure_imports.py`` guards that). ``QgsRasterLayer``
handles never cross this boundary; the answers are
:class:`~qgis_sdk.models.layers.RasterLayerInfo`,
:class:`~qgis_sdk.models.layers.RasterStatistics`,
:class:`~qgis_sdk.models.layers.RasterSample` and
:class:`~qgis_sdk.models.layers.RasterExport`.

Three translations are worth stating, because each is a place a version of QGIS
could answer differently and the pure side must not inherit that.

*The band's data type becomes a name, not a number.* ``Qgis.DataType`` is an
enum whose Python spelling differs between the PyQt versions a QGIS 3.x and a
QGIS 4.x build ship, so the name is looked up from the enum itself rather than
assumed.

*A band with no no-data value answers ``None``.* GDAL reports a missing
``GDAL_NODATA`` tag as NaN through QGIS, so NaN is translated once, here, and
never reaches a page as a number that is not equal to itself.

*Statistics are taken over the whole band.* The provider's own ``sampleSize``
default caps a statistics pass at a quarter of a million cells, which would make
``valid_count`` silently a sample of a large raster; asking for every cell costs
the scan and keeps the two counts adding up to the band's size.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsCoordinateTransformContext,
    QgsPointXY,
    QgsProject,
    QgsRasterFileWriter,
    QgsRasterLayer,
    QgsRectangle,
)

import qgis_sdk.exports as export_policy
from qgis_sdk.core import ResourceScope
from qgis_sdk.models import (
    RASTER_EXPORT_DRIVERS,
    CanvasExtent,
    CanvasPoint,
    QgisSdkExportFailedError,
    QgisSdkLayerNotFoundError,
    QgisSdkRasterBandError,
    QgisSdkUnsupportedCapabilityError,
    RasterExport,
    RasterLayerInfo,
    RasterSample,
    RasterStatistics,
)


class _CcState:
    """A mutable record shared by the phases of one long function."""

    def __init__(_cc_self, **values):
        _cc_self.__dict__.update(values)


class _CcReturn:
    """An early return travelling out of a phase."""

    def __init__(_cc_self, value):
        _cc_self.value = value


def _cc_export_raster_p1(_s):
    _s.self._scope.ensure_open()
    _s.layer = _s.self._require(_s.layer_id)
    _s.plan = export_policy.plan_export(
        _s.destination, overwrite=_s.overwrite, drivers=RASTER_EXPORT_DRIVERS
    )
    _s.plan = export_policy.protect_source(
        _s.plan, _s.self._export_sources[_s.layer_id]
    )
    _s.provider = _s.layer.dataProvider()


def _cc_export_raster_p2(_s):

    def write(partial: Path) -> None:
        writer = QgsRasterFileWriter(str(partial))
        writer.setOutputFormat(_s.plan.driver)
        result = writer.writeRaster(
            _pipe(_s.provider),
            _s.layer.width(),
            _s.layer.height(),
            _s.layer.extent(),
            _s.layer.crs(),
            QgsCoordinateTransformContext(),
        )
        # ``NoError`` is 0 under every spelling of the enum across the
        # versions this adapter supports, so the check does not name it.
        if int(result) != 0:
            raise QgisSdkExportFailedError(
                str(_s.plan.destination), f"raster writer error {int(result)}"
            )
        _close_writer(writer)

    _s.write = write


def _cc_export_raster_p3(_s):

    export_policy.run_export(_s.plan, _s.write)
    return _CcReturn(RasterExport(path=str(_s.plan.destination), driver=_s.plan.driver))


def _statistics_facts1(band, stats, total, valid):
    return RasterStatistics(
        band=band,
        minimum=float(stats.minimumValue),
        maximum=float(stats.maximumValue),
        mean=float(stats.mean),
        std_dev=float(stats.stdDev),
        valid_count=valid,
        no_data_count=max(total - valid, 0),
    )


__all__ = ["NativeRasters"]


class NativeRasters:
    """Open local rasters through GDAL and read their bands.

    Ownership: every raster this runtime opens is released when the owner scope
    closes, and every operation is refused afterwards rather than returning a
    stale reference (decision-20).
    """

    def __init__(self, scope: ResourceScope) -> None:
        self._scope = scope
        self._rasters: dict[str, QgsRasterLayer] = {}
        self._export_sources: dict[str, export_policy.SourceIdentity | None] = {}
        scope.on_close(self._release)

    def open_raster(self, source: Path) -> RasterLayerInfo:
        """Open a local dataset with GDAL and describe the resulting raster."""
        self._scope.ensure_open()
        layer = QgsRasterLayer(str(source), Path(source).stem, "gdal")
        if not layer.isValid():
            raise QgisSdkLayerNotFoundError(str(source))
        self._rasters[layer.id()] = layer
        self._export_sources[layer.id()] = _capture_source(layer)
        return _describe(layer)

    def list_layers(self) -> tuple[RasterLayerInfo, ...]:
        """Return opened rasters in the order they were opened."""
        self._scope.ensure_open()
        return tuple(_describe(layer) for layer in self._rasters.values())

    def raster(self, layer_id: str) -> RasterLayerInfo:
        """Return the description of one opened raster."""
        self._scope.ensure_open()
        return _describe(self._require(layer_id))

    def statistics(self, layer_id: str, band: int) -> RasterStatistics:
        """Compute one band's statistics over every cell of the band."""
        self._scope.ensure_open()
        layer = self._require(layer_id)
        _require_band(layer, band)
        provider = layer.dataProvider()
        stats = provider.bandStatistics(
            band, Qgis.RasterBandStatistic.All, QgsRectangle(), 0
        )
        total = layer.width() * layer.height()
        valid = int(stats.elementCount)
        if valid <= 0:
            # No cell carries a value: "no data" and "all zeros" are different
            # answers, so the four numbers stay None rather than becoming zero.
            return RasterStatistics(
                band=band,
                minimum=None,
                maximum=None,
                mean=None,
                std_dev=None,
                valid_count=0,
                no_data_count=total,
            )
        return _statistics_facts1(band, stats, total, valid)

    def sample(
        self, layer_id: str, point: CanvasPoint, *, band: int | None = None
    ) -> RasterSample:
        """Read each band (or one band) at ``point``, transforming it if needed."""
        self._scope.ensure_open()
        layer = self._require(layer_id)
        bands = range(1, layer.bandCount() + 1) if band is None else (band,)
        for number in bands:
            _require_band(layer, number)
        x, y = _in_raster_crs(layer, point)
        provider = layer.dataProvider()
        values: list[float | None] = []
        for number in bands:
            value, ok = provider.sample(QgsPointXY(x, y), number)
            values.append(float(value) if ok else None)
        answer = CanvasPoint(x=x, y=y, crs=_authid(layer))
        return RasterSample(point=answer, values=tuple(values))

    def export_raster(
        self, layer_id: str, destination: Path, *, overwrite: bool = False
    ) -> RasterExport:
        "Write the raster with ``QgsRasterFileWriter`` under the shared policy.\n\n        The writer targets a staged path, so a half-written GeoTIFF never\n        appears at the destination. The shared policy checks the source before\n        writing and immediately before committing.\n"
        _s = _CcState(
            self=self, layer_id=layer_id, destination=destination, overwrite=overwrite
        )
        for _p in (_cc_export_raster_p1, _cc_export_raster_p2, _cc_export_raster_p3):
            _r = _p(_s)
            if isinstance(_r, _CcReturn):
                return _r.value
        return None

    def _qgs_raster(self, layer_id: str) -> QgsRasterLayer:
        """Hand the native handle to a sibling adapter in this package.

        Package-internal: the documented handoff between ``NativeRasters`` and
        ``NativeProject``, which must add the very layer instance this adapter
        owns. Author and bridge code use the contract, never this.
        """
        self._scope.ensure_open()
        return self._require(layer_id)

    def knows(self, layer_id: str) -> bool:
        """Whether this adapter opened ``layer_id`` (package-internal probe)."""
        return layer_id in self._rasters

    def _require(self, layer_id: str) -> QgsRasterLayer:
        try:
            return self._rasters[layer_id]
        except KeyError:
            raise QgisSdkLayerNotFoundError(layer_id) from None

    def _release(self) -> None:
        """Drop this runtime's references; the scope closes exactly once."""
        self._rasters.clear()
        self._export_sources.clear()


def _pipe(provider: Any) -> Any:
    """Build the one-element pipe ``writeRaster`` copies from."""
    from qgis.core import QgsRasterPipe

    pipe = QgsRasterPipe()
    if not pipe.set(provider.clone()):
        raise QgisSdkUnsupportedCapabilityError(
            "raster", "the provider does not support the raster writer's pipe"
        )
    return pipe


def _close_writer(writer: Any) -> None:
    """Let the writer release its dataset before the staged file is committed."""
    close = getattr(writer, "close", None)
    if close is not None:
        close()


def _require_band(layer: QgsRasterLayer, band: int) -> None:
    if not 1 <= band <= layer.bandCount():
        raise QgisSdkRasterBandError(layer.id(), band, layer.bandCount())


def _authid(layer: QgsRasterLayer) -> str | None:
    return layer.crs().authid() or None


def _in_raster_crs(layer: QgsRasterLayer, point: CanvasPoint) -> tuple[float, float]:
    """Return the point's coordinates in the raster's CRS, reprojecting if asked."""
    target = layer.crs()
    if point.crs is None or point.crs == (target.authid() or None):
        return point.x, point.y
    source = QgsCoordinateReferenceSystem(point.crs)
    if not source.isValid():
        raise QgisSdkUnsupportedCapabilityError(
            "crs", f"{point.crs!r} is not a CRS this host can resolve"
        )
    transform = QgsCoordinateTransform(source, target, QgsProject.instance())
    moved = transform.transform(QgsPointXY(point.x, point.y))
    return moved.x(), moved.y()


def _capture_source(layer: QgsRasterLayer) -> export_policy.SourceIdentity | None:
    """Identify only a direct local dataset; leave others unexportable."""
    try:
        source = layer.source()
        if not source or "://" in source:
            return None
        return export_policy.capture_source(Path(source))
    except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
        return None


def _data_type_name(value: Any) -> str:
    """Spell ``Qgis.DataType`` member ``value`` by its name."""
    for name in dir(Qgis.DataType):
        if name.startswith("_"):
            continue
        try:
            if int(getattr(Qgis.DataType, name)) == int(value):
                return name
        except (TypeError, ValueError):
            continue
    return f"type-{int(value)}"


def _describe(layer: QgsRasterLayer) -> RasterLayerInfo:
    """Translate a native raster into the QGIS-free description."""
    provider = layer.dataProvider()
    no_data: list[float | None] = []
    data_types: list[str] = []
    for band in range(1, layer.bandCount() + 1):
        data_types.append(_data_type_name(provider.dataType(band)))
        value = float(provider.sourceNoDataValue(band))
        # GDAL reports a band with no ``GDAL_NODATA`` tag as NaN through QGIS.
        no_data.append(None if math.isnan(value) else value)
    extent = layer.extent()
    return RasterLayerInfo(
        id=layer.id(),
        name=layer.name(),
        band_count=layer.bandCount(),
        data_types=tuple(data_types),
        no_data=tuple(no_data),
        extent=CanvasExtent(
            x_min=extent.xMinimum(),
            y_min=extent.yMinimum(),
            x_max=extent.xMaximum(),
            y_max=extent.yMaximum(),
            crs=None,
        ),
        resolution=(
            float(layer.rasterUnitsPerPixelX()),
            float(layer.rasterUnitsPerPixelY()),
        ),
        crs=_authid(layer),
    )

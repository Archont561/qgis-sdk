"""A ``Rasters`` backend over datasets declared in the test."""

from __future__ import annotations

import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import qgis_sdk.exports as export_policy
from qgis_sdk._published import REQUIRED, published
from qgis_sdk.core import ResourceScope
from qgis_sdk.models import (
    RASTER_EXPORT_DRIVERS,
    CanvasExtent,
    CanvasPoint,
    QgisSdkLayerNotFoundError,
    QgisSdkRasterBandError,
    QgisSdkUnsupportedCapabilityError,
    RasterExport,
    RasterLayerInfo,
    RasterSample,
    RasterStatistics,
)

from ._register import register_dataset

__all__ = ["FakeRasters"]

#: A band with no declared statistics: no valid cell, so every value is ``None``
#: rather than a zero, which is the distinction
#: :class:`~qgis_sdk.models.layers.RasterStatistics` exists to keep.
_EMPTY_STATISTICS = (None, None, None, None)


class _FakeRastersMixin1:
    _CC_SPECS_register_1 = (
        ("self", REQUIRED, REQUIRED, "positional"),
        ("source", Path, REQUIRED, "positional"),
        ("name", str, REQUIRED, "keyword"),
        ("extent", CanvasExtent, REQUIRED, "keyword"),
        ("band_count", int, 1, "keyword"),
        ("data_types", Sequence[str] | None, None, "keyword"),
        ("no_data", Sequence[float | None] | None, None, "keyword"),
        ("resolution", tuple[float, float], (1.0, 1.0), "keyword"),
        ("crs", str | None, None, "keyword"),
        ("values", Sequence[float | None] | None, None, "keyword"),
        ("holes", Sequence[tuple[float, float]], (), "keyword"),
        ("statistics", Mapping[int, RasterStatistics] | None, None, "keyword"),
        ("dataset_path", Path | None, None, "keyword"),
    )

    @published(_CC_SPECS_register_1, returns=type(None))
    def register(_published_values):
        """Declare a raster dataset, and what reading it answers.

        ``values`` is one sampled value per band, returned for a point inside
        ``extent``; ``holes`` names the points a band is empty at, standing in
        for the pixel grid this fake does not have. ``statistics`` is declared
        by band number, and a band left out answers :data:`_EMPTY_STATISTICS`.
        ``dataset_path`` models a container: the file the export copies, when it
        differs from ``source``.
        """
        register_dataset(_published_values)

    def open_raster(self, source: Path) -> RasterLayerInfo:
        """Return a new raster for a declared dataset."""
        self._scope.ensure_open()
        declared = self._datasets.get(str(source))
        if declared is None:
            raise QgisSdkLayerNotFoundError(str(source))
        template: RasterLayerInfo = declared["info"]
        info = RasterLayerInfo(
            id=f"raster-{len(self._rasters) + 1}",
            name=template.name,
            band_count=template.band_count,
            data_types=template.data_types,
            no_data=template.no_data,
            extent=template.extent,
            resolution=template.resolution,
            crs=template.crs,
        )
        self._rasters[info.id] = info
        values = self._values.pop(template.id)
        self._values[info.id] = values
        holes = self._holes.pop(template.id, frozenset())
        self._holes[info.id] = holes
        statistics = self._statistics.pop(template.id, {})
        self._statistics[info.id] = statistics
        path = Path(declared["source"])
        captured = export_policy.capture_source(path, allow_virtual=True)
        self._export_sources[info.id] = captured
        self._sources[info.id] = captured.path if captured is not None else path
        return info

    def list_layers(self) -> tuple[RasterLayerInfo, ...]:
        """Return opened rasters in the order they were opened."""
        self._scope.ensure_open()
        return tuple(self._rasters.values())

    def raster(self, layer_id: str) -> RasterLayerInfo:
        """Return one opened raster."""
        self._scope.ensure_open()
        return self._require(layer_id)

    def statistics(self, layer_id: str, band: int) -> RasterStatistics:
        """Return the declared statistics of one band."""
        self._scope.ensure_open()
        info = self._require(layer_id)
        self._require_band(info, band)
        declared = self._statistics[layer_id].get(band)
        if declared is not None:
            return declared
        minimum, maximum, mean, std_dev = _EMPTY_STATISTICS
        return RasterStatistics(
            band=band,
            minimum=minimum,
            maximum=maximum,
            mean=mean,
            std_dev=std_dev,
            valid_count=0,
            no_data_count=0,
        )

    def sample(
        self, layer_id: str, point: CanvasPoint, *, band: int | None = None
    ) -> RasterSample:
        """Answer the declared value for a point inside the raster's box."""
        self._scope.ensure_open()
        info = self._require(layer_id)
        if point.crs is not None and info.crs is not None and point.crs != info.crs:
            raise QgisSdkUnsupportedCapabilityError(
                "reprojection",
                f"this backend has no CRS database, so it cannot transform a "
                f"{point.crs} point into {info.crs}; pass the point in the "
                "raster's own CRS or sample through the native backend",
            )
        bands = range(1, info.band_count + 1) if band is None else (band,)
        inside = (
            info.extent.x_min <= point.x <= info.extent.x_max
            and info.extent.y_min <= point.y <= info.extent.y_max
            and (point.x, point.y) not in self._holes[layer_id]
        )
        values: list[float | None] = []
        for number in bands:
            self._require_band(info, number)
            declared = self._values[layer_id][number - 1] if inside else None
            values.append(None if declared is None else float(declared))
        # The answer names the CRS it landed in, exactly as the native adapter
        # does, so a page never has to remember which one it asked in.
        answer = CanvasPoint(x=point.x, y=point.y, crs=info.crs)
        return RasterSample(point=answer, values=tuple(values))

    def export_raster(
        self, layer_id: str, destination: Path, *, overwrite: bool = False
    ) -> RasterExport:
        """Copy the declared dataset to ``destination`` under the shared policy."""
        self._scope.ensure_open()
        self._require(layer_id)
        plan = export_policy.plan_export(
            destination, overwrite=overwrite, drivers=RASTER_EXPORT_DRIVERS
        )
        plan = export_policy.protect_source(plan, self._export_sources[layer_id])
        source = self._sources[layer_id]

        def write(partial: Path) -> None:
            if source.is_file():
                shutil.copyfile(source, partial)
            else:
                partial.write_bytes(b"")

        export_policy.run_export(plan, write)
        return RasterExport(path=str(plan.destination), driver=plan.driver)

    def opened_layers(self) -> tuple[str, ...]:
        """Return the ids this backend opened (package-internal probe)."""
        return tuple(self._rasters)

    def _require(self, layer_id: str) -> RasterLayerInfo:
        try:
            return self._rasters[layer_id]
        except KeyError:
            raise QgisSdkLayerNotFoundError(layer_id) from None

    def _require_band(self, info: RasterLayerInfo, band: int) -> None:
        if not 1 <= band <= info.band_count:
            raise QgisSdkRasterBandError(info.id, band, info.band_count)

    def _release(self) -> None:
        """Drop this runtime's references; the scope closes exactly once."""
        self._rasters.clear()
        self._sources.clear()
        self._export_sources.clear()
        self._values.clear()
        self._holes.clear()
        self._statistics.clear()


class FakeRasters(_FakeRastersMixin1):
    """A ``Rasters`` backend over datasets declared in the test.

    The fake carries an owner scope like every real backend, so a pure test can
    prove the same disposal rules the native adapter must honour.
    """

    def __init__(self, scope: ResourceScope) -> None:
        self._scope = scope
        self._datasets: dict[str, dict[str, Any]] = {}
        self._rasters: dict[str, RasterLayerInfo] = {}
        self._sources: dict[str, Path] = {}
        self._export_sources: dict[str, export_policy.SourceIdentity | None] = {}
        self._values: dict[str, tuple[float | None, ...]] = {}
        self._holes: dict[str, frozenset[tuple[float, float]]] = {}
        self._statistics: dict[str, dict[int, RasterStatistics]] = {}
        scope.on_close(self._release)

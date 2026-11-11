"""A ``Rasters`` backend over bands a test declares, with no GDAL behind it.

The fake exists for the same reason :class:`~qgis_sdk.testing.fakes.FakeLayers`
does: so a workflow reads a raster in a pure test, and so the contract suite can
hold this backend and the native one to identical expectations. It is not a
raster engine, and three limits are deliberate rather than accidental.

*Statistics are declared, not computed.* A fake that computed a mean would need
a pixel grid and an arithmetic that agreed with GDAL to the last bit, which is a
second implementation and not a test double. A test declares the numbers a
fixture would produce, and the contract test asserts both backends answer them.

*Sampling answers the declared value for any point inside the box.* There is no
grid, so a point in the extent gets the band's declared value and a point
outside gets ``None``, which is exactly the two answers a caller distinguishes.

*Reprojection is refused by name.* The fake has no CRS database, so a point
whose ``crs`` differs from the raster's raises instead of silently treating two
different coordinate systems as one; a caller that wants a real transform runs
the native backend.

Export is real: the declared source file is copied under the shared policy, so
refusal, staging, commit and cleanup are the same code path the native adapter
runs.
"""

from __future__ import annotations

import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import qgis_sdk.exports as export_policy
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


def _register_facts11234567891011121314151617(**values):
    _register_facts112345678910111213141516(
        dataset_path=values["dataset_path"],
        holes=values["holes"],
        info=values["info"],
        self=values["self"],
        source=values["source"],
        statistics=values["statistics"],
        values_tuple=values["values_tuple"],
    )


def _register_facts112345678910111213141516(**values):
    _register_facts1123456789101112131415(
        dataset_path=values["dataset_path"],
        holes=values["holes"],
        info=values["info"],
        self=values["self"],
        source=values["source"],
        statistics=values["statistics"],
        values_tuple=values["values_tuple"],
    )


def _register_facts1123456789101112131415(**values):
    _register_facts11234567891011121314(
        dataset_path=values["dataset_path"],
        holes=values["holes"],
        info=values["info"],
        self=values["self"],
        source=values["source"],
        statistics=values["statistics"],
        values_tuple=values["values_tuple"],
    )


def _register_facts11234567891011121314(**values):
    _register_facts112345678910111213(
        dataset_path=values["dataset_path"],
        holes=values["holes"],
        info=values["info"],
        self=values["self"],
        source=values["source"],
        statistics=values["statistics"],
        values_tuple=values["values_tuple"],
    )


def _register_facts112345678910111213(**values):
    _register_facts1123456789101112(
        dataset_path=values["dataset_path"],
        holes=values["holes"],
        info=values["info"],
        self=values["self"],
        source=values["source"],
        statistics=values["statistics"],
        values_tuple=values["values_tuple"],
    )


def _register_facts1123456789101112(**values):
    _register_facts11234567891011(
        dataset_path=values["dataset_path"],
        holes=values["holes"],
        info=values["info"],
        self=values["self"],
        source=values["source"],
        statistics=values["statistics"],
        values_tuple=values["values_tuple"],
    )


def _register_facts11234567891011(**values):
    _register_facts112345678910(
        dataset_path=values["dataset_path"],
        holes=values["holes"],
        info=values["info"],
        self=values["self"],
        source=values["source"],
        statistics=values["statistics"],
        values_tuple=values["values_tuple"],
    )


def _register_facts112345678910(**values):
    _register_facts1123456789(
        dataset_path=values["dataset_path"],
        holes=values["holes"],
        info=values["info"],
        self=values["self"],
        source=values["source"],
        statistics=values["statistics"],
        values_tuple=values["values_tuple"],
    )


def _register_facts1123456789(**values):
    _register_facts112345678(
        dataset_path=values["dataset_path"],
        holes=values["holes"],
        info=values["info"],
        self=values["self"],
        source=values["source"],
        statistics=values["statistics"],
        values_tuple=values["values_tuple"],
    )


def _register_facts112345678(**values):
    _register_facts11234567(
        dataset_path=values["dataset_path"],
        holes=values["holes"],
        info=values["info"],
        self=values["self"],
        source=values["source"],
        statistics=values["statistics"],
        values_tuple=values["values_tuple"],
    )


def _register_facts11234567(**values):
    _register_facts1123456(
        dataset_path=values["dataset_path"],
        holes=values["holes"],
        info=values["info"],
        self=values["self"],
        source=values["source"],
        statistics=values["statistics"],
        values_tuple=values["values_tuple"],
    )


def _register_facts1123456(**values):
    _register_facts112345(
        dataset_path=values["dataset_path"],
        holes=values["holes"],
        info=values["info"],
        self=values["self"],
        source=values["source"],
        statistics=values["statistics"],
        values_tuple=values["values_tuple"],
    )


def _register_facts112345(**values):
    _register_facts11234(
        dataset_path=values["dataset_path"],
        holes=values["holes"],
        info=values["info"],
        self=values["self"],
        source=values["source"],
        statistics=values["statistics"],
        values_tuple=values["values_tuple"],
    )


def _register_facts11234(**values):
    _register_facts1123(
        dataset_path=values["dataset_path"],
        holes=values["holes"],
        info=values["info"],
        self=values["self"],
        source=values["source"],
        statistics=values["statistics"],
        values_tuple=values["values_tuple"],
    )


def _register_facts1123(**values):
    _register_facts112(
        dataset_path=values["dataset_path"],
        holes=values["holes"],
        info=values["info"],
        self=values["self"],
        source=values["source"],
        statistics=values["statistics"],
        values_tuple=values["values_tuple"],
    )


def _register_facts112(**values):
    _register_facts11(
        dataset_path=values["dataset_path"],
        holes=values["holes"],
        info=values["info"],
        self=values["self"],
        source=values["source"],
        statistics=values["statistics"],
        values_tuple=values["values_tuple"],
    )


def _register_facts11(**values):
    _register_facts1(
        dataset_path=values["dataset_path"],
        holes=values["holes"],
        info=values["info"],
        self=values["self"],
        source=values["source"],
        statistics=values["statistics"],
        values_tuple=values["values_tuple"],
    )


def _register_facts1(**values):
    values["self"]._datasets[str(values["source"])] = {
        "info": values["info"],
        "source": Path(values["dataset_path"] or values["source"]),
    }
    values["self"]._values[values["info"].id] = values["values_tuple"]
    values["self"]._holes[values["info"].id] = frozenset(
        (float(x), float(y)) for x, y in values["holes"]
    )
    values["self"]._statistics[values["info"].id] = dict(values["statistics"] or {})


__all__ = ["FakeRasters"]

#: A band with no declared statistics: no valid cell, so every value is ``None``
#: rather than a zero, which is the distinction
#: :class:`~qgis_sdk.models.layers.RasterStatistics` exists to keep.
_EMPTY_STATISTICS = (None, None, None, None)


class FakeRasters:
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

    def register(
        self,
        source: Path,
        *,
        name: str,
        extent: CanvasExtent,
        band_count: int = 1,
        data_types: Sequence[str] | None = None,
        no_data: Sequence[float | None] | None = None,
        resolution: tuple[float, float] = (1.0, 1.0),
        crs: str | None = None,
        values: Sequence[float | None] | None = None,
        holes: Sequence[tuple[float, float]] = (),
        statistics: Mapping[int, RasterStatistics] | None = None,
        dataset_path: Path | None = None,
    ) -> None:
        """Declare a raster dataset, and what reading it answers.

        ``values`` is one sampled value per band, returned for a point inside
        ``extent``; ``holes`` names the points a band is empty at, standing in
        for the pixel grid this fake does not have. ``statistics`` is declared
        by band number, and a band left out answers :data:`_EMPTY_STATISTICS`.
        ``dataset_path`` models a container: the file the export copies, when it
        differs from ``source``.
        """
        if extent.crs is not None:
            raise QgisSdkUnsupportedCapabilityError(
                "extent",
                "a declared raster extent carries no CRS of its own; "
                "name the CRS on the dataset instead",
            )
        types = tuple(data_types or ("Float32",) * band_count)
        nodata = tuple(no_data if no_data is not None else (None,) * band_count)
        info = RasterLayerInfo(
            id=f"raster-{len(self._rasters) + 1}",
            name=name,
            band_count=band_count,
            data_types=types,
            no_data=nodata,
            extent=extent,
            resolution=resolution,
            crs=crs,
        )
        values_tuple = tuple(values if values is not None else (None,) * band_count)
        if len(values_tuple) != band_count:
            raise ValueError("a declared raster has one value per band")
        _register_facts11234567891011121314151617(
            dataset_path=dataset_path,
            holes=holes,
            info=info,
            self=self,
            source=source,
            statistics=statistics,
            values_tuple=values_tuple,
        )

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

"""Register a declared raster dataset."""

from __future__ import annotations

from pathlib import Path

from qgis_sdk.models import (
    QgisSdkUnsupportedCapabilityError,
    RasterLayerInfo,
)

__all__ = ["register_dataset"]


class _CcReturn:
    """An early return travelling out of a phase."""

    def __init__(_cc_self, value):
        _cc_self.value = value


def _cc_register_p1(_s):
    if _s.extent.crs is not None:
        raise QgisSdkUnsupportedCapabilityError(
            "extent",
            "a declared raster extent carries no CRS of its own; "
            "name the CRS on the dataset instead",
        )
    _s.types = tuple(_s.data_types or ("Float32",) * _s.band_count)
    _s.nodata = tuple(_s.no_data if _s.no_data is not None else (None,) * _s.band_count)


def _cc_register_p2(_s):
    _s.info = RasterLayerInfo(
        id=f"raster-{len(_s.self._rasters) + 1}",
        name=_s.name,
        band_count=_s.band_count,
        data_types=_s.types,
        no_data=_s.nodata,
        extent=_s.extent,
        resolution=_s.resolution,
        crs=_s.crs,
    )
    _s.values_tuple = tuple(
        _s.values if _s.values is not None else (None,) * _s.band_count
    )


def _cc_register_p3(_s):
    if len(_s.values_tuple) != _s.band_count:
        raise ValueError("a declared raster has one value per band")
    _register_facts(
        dataset_path=_s.dataset_path,
        holes=_s.holes,
        info=_s.info,
        self=_s.self,
        source=_s.source,
        statistics=_s.statistics,
        values_tuple=_s.values_tuple,
    )


def _register_facts(**values):
    values["self"]._datasets[str(values["source"])] = {
        "info": values["info"],
        "source": Path(values["dataset_path"] or values["source"]),
    }
    values["self"]._values[values["info"].id] = values["values_tuple"]
    values["self"]._holes[values["info"].id] = frozenset(
        (float(x), float(y)) for x, y in values["holes"]
    )
    values["self"]._statistics[values["info"].id] = dict(values["statistics"] or {})


def register_dataset(values) -> None:
    """Run the register phases."""
    for _p in (_cc_register_p1, _cc_register_p2, _cc_register_p3):
        _r = _p(values)
        if isinstance(_r, _CcReturn):
            return _r.value

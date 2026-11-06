"""Real GDAL rasters: bands, statistics and samples from a GeoTIFF.

Opt-in under ``QGIS_SDK_NATIVE_SERVICES=1``. The shared contract suite already
holds the fake and the adapter to one answer; these tests prove the parts only
GDAL can answer - that the fixture really is a GeoTIFF, that its band is read as
the type the file declares, that a statistics pass covers the band rather than a
sample of it, and that a sample reprojects a point the caller sent in another CRS.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import conftest
import pytest
from qgis_sdk.models.canvas import CanvasPoint

pytestmark = pytest.mark.qgis

if TYPE_CHECKING:
    Services = conftest.Services


def _raster(services: Services):
    assert services.rasters is not None and services.open_raster is not None
    return services.rasters, services.rasters.raster(services.open_raster())


def test_the_fixture_is_a_geotiff_read_by_gdal(native_services: Services) -> None:
    from qgis.core import QgsRasterLayer

    _, info = _raster(native_services)

    assert native_services.raster_dataset is not None
    layer = QgsRasterLayer(str(native_services.raster_dataset), "source", "gdal")
    assert layer.isValid()
    assert info.band_count == layer.bandCount()
    assert info.data_types == (conftest.RASTER_DATA_TYPE,)


def test_statistics_cover_every_cell_of_the_band(native_services: Services) -> None:
    rasters, info = _raster(native_services)

    stats = rasters.statistics(info.id, 1)

    assert stats.valid_count + stats.no_data_count == 6
    assert stats.valid_count == conftest.RASTER_VALID_CELLS
    assert stats.mean == pytest.approx(conftest.RASTER_MEAN)


def test_a_point_in_another_crs_is_reprojected_into_the_raster(
    native_services: Services,
) -> None:
    """A caller that asks in WGS 84 projected coordinates gets the same cell."""
    from qgis.core import (
        QgsCoordinateReferenceSystem,
        QgsCoordinateTransform,
        QgsPointXY,
        QgsProject,
    )

    rasters, info = _raster(native_services)
    transform = QgsCoordinateTransform(
        QgsCoordinateReferenceSystem(conftest.FIXTURE_CRS),
        QgsCoordinateReferenceSystem("EPSG:3857"),
        QgsProject.instance(),
    )
    moved = transform.transform(
        QgsPointXY(conftest.RASTER_VALUE_POINT.x, conftest.RASTER_VALUE_POINT.y)
    )

    sample = rasters.sample(
        info.id, CanvasPoint(x=moved.x(), y=moved.y(), crs="EPSG:3857")
    )

    assert sample.values == pytest.approx((conftest.RASTER_VALUE,))
    assert sample.point.crs == conftest.FIXTURE_CRS


def test_an_export_is_a_geotiff_gdal_can_open(
    native_services: Services, tmp_path
) -> None:
    from qgis.core import QgsRasterLayer

    rasters, info = _raster(native_services)
    destination = tmp_path / "exported.tif"

    exported = rasters.export_raster(info.id, destination)

    assert exported.driver == "GTiff"
    reopened = QgsRasterLayer(str(destination), "exported", "gdal")
    assert reopened.isValid()
    assert reopened.bandCount() == info.band_count
    box = reopened.extent()
    assert box.xMinimum() == pytest.approx(info.extent.x_min)
    assert box.yMinimum() == pytest.approx(info.extent.y_min)
    assert box.xMaximum() == pytest.approx(info.extent.x_max)
    assert box.yMaximum() == pytest.approx(info.extent.y_max)

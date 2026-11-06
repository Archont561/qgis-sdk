"""Contract: raster reads, on the checked-in grid both backends declare.

The fixture is a three-by-two ASCII grid (``elevation.asc``): one value per cell,
one no-data hole, a box from 21.0 to 21.3 east and 52.0 to 52.2 north, and one
value per pixel of 0.1 degrees. The native backend converts it to a GeoTIFF
before the tests run and the fake declares the same numbers, so every assertion
here is a statement about *both* backends or about neither.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import conftest
import pytest
from qgis_sdk.models import (
    QgisSdkExportRefusedError,
    QgisSdkLayerNotFoundError,
    QgisSdkRasterBandError,
    QgisSdkUnsupportedCapabilityError,
    RasterLayerInfo,
    VectorLayerInfo,
)
from qgis_sdk.models.canvas import CanvasPoint

if TYPE_CHECKING:
    Services = conftest.Services

pytestmark = pytest.mark.usefixtures("services")


def _raster(services: Services) -> tuple[object, RasterLayerInfo]:
    """Open the fixture raster and return ``(service, info)``."""
    rasters = services.rasters
    assert rasters is not None, "this backend has not joined the raster contract"
    assert services.open_raster is not None
    layer_id = services.open_raster()
    return rasters, rasters.raster(layer_id)


def test_opening_the_fixture_describes_its_bands(services: Services) -> None:
    _, info = _raster(services)

    assert info.kind == "raster"
    assert info.name == conftest.RASTER_NAME
    assert info.band_count == conftest.RASTER_BAND_COUNT
    assert info.data_types == (conftest.RASTER_DATA_TYPE,)
    assert info.no_data == (conftest.RASTER_NO_DATA,)
    assert info.crs == conftest.FIXTURE_CRS
    # A grid's corner is a sum of cell sizes, so the box is compared to the
    # precision the file states rather than bit for bit.
    for corner in ("x_min", "y_min", "x_max", "y_max"):
        assert getattr(info.extent, corner) == pytest.approx(
            getattr(conftest.RASTER_EXTENT, corner)
        )
    assert info.extent.crs is None
    assert info.resolution == pytest.approx(conftest.RASTER_RESOLUTION)


def test_a_raster_extent_carries_no_crs_of_its_own(services: Services) -> None:
    """The raster names its CRS once, in ``crs``; the box would be a second copy."""
    _, info = _raster(services)

    assert info.extent.crs is None


def test_a_band_can_be_measured(services: Services) -> None:
    rasters, info = _raster(services)

    stats = rasters.statistics(info.id, 1)

    assert stats.band == 1
    assert stats.minimum == pytest.approx(conftest.RASTER_MINIMUM)
    assert stats.maximum == pytest.approx(conftest.RASTER_MAXIMUM)
    assert stats.mean == pytest.approx(conftest.RASTER_MEAN)
    assert stats.std_dev == pytest.approx(conftest.RASTER_STD_DEV)
    # The two counts add up to the cells the band covers: three by two.
    assert stats.valid_count == conftest.RASTER_VALID_CELLS
    assert stats.no_data_count == conftest.RASTER_NO_DATA_CELLS
    assert stats.valid_count + stats.no_data_count == 6


def test_a_band_outside_the_raster_is_refused_by_name(services: Services) -> None:
    rasters, info = _raster(services)

    with pytest.raises(QgisSdkRasterBandError) as error:
        rasters.statistics(info.id, conftest.RASTER_BAND_COUNT + 1)

    assert error.value.band == conftest.RASTER_BAND_COUNT + 1
    assert error.value.band_count == conftest.RASTER_BAND_COUNT


def test_a_point_inside_a_cell_answers_that_cell(services: Services) -> None:
    rasters, info = _raster(services)

    sample = rasters.sample(info.id, conftest.RASTER_VALUE_POINT)

    assert sample.values == pytest.approx((conftest.RASTER_VALUE,))
    assert sample.point.crs == conftest.FIXTURE_CRS


def test_a_point_on_the_hole_answers_nothing_for_that_band(
    services: Services,
) -> None:
    """A hole is not a zero: "no data" and "all zeros" are different answers."""
    rasters, info = _raster(services)

    sample = rasters.sample(info.id, conftest.RASTER_HOLE_POINT)

    assert sample.values == (None,)


def test_a_point_outside_the_raster_answers_nothing(services: Services) -> None:
    rasters, info = _raster(services)

    sample = rasters.sample(
        info.id, CanvasPoint(x=0.0, y=0.0, crs=conftest.FIXTURE_CRS)
    )

    assert sample.values == (None,)


def test_one_band_can_be_sampled_alone(services: Services) -> None:
    rasters, info = _raster(services)

    sample = rasters.sample(info.id, conftest.RASTER_VALUE_POINT, band=1)

    assert len(sample.values) == 1


def test_sampling_band_zero_is_refused(services: Services) -> None:
    rasters, info = _raster(services)

    with pytest.raises(QgisSdkRasterBandError):
        rasters.sample(info.id, conftest.RASTER_VALUE_POINT, band=0)


def test_an_unopened_raster_is_refused_by_name(services: Services) -> None:
    rasters = services.rasters
    assert rasters is not None

    with pytest.raises(QgisSdkLayerNotFoundError):
        rasters.raster("no-such-raster")

    with pytest.raises(QgisSdkLayerNotFoundError):
        rasters.open_raster(services.dataset.with_name("absent.tif"))


def test_a_vector_layer_id_is_not_a_raster(services: Services) -> None:
    """A raster call is not a vector call, and says so by name."""
    rasters = services.rasters
    assert rasters is not None
    vector = services.layers.open_vector(services.dataset)

    with pytest.raises(QgisSdkLayerNotFoundError):
        rasters.raster(vector.id)


def test_layers_lists_both_kinds_with_their_kinds(services: Services) -> None:
    """``Layers.list_layers`` answers every kind, each carrying its discriminator."""
    rasters = services.rasters
    assert rasters is not None and services.open_raster is not None
    vector = services.layers.open_vector(services.dataset)
    raster_id = services.open_raster()

    listed = services.layers.list_layers()

    kinds = {info.id: info.kind for info in listed}
    assert kinds[vector.id] == "vector"
    assert kinds[raster_id] == "raster"
    assert isinstance(services.layers.layer(vector.id), VectorLayerInfo)
    assert isinstance(services.layers.layer(raster_id), RasterLayerInfo)


def test_a_vector_only_method_refuses_a_raster_by_name(services: Services) -> None:
    rasters = services.rasters
    assert rasters is not None and services.open_raster is not None
    raster_id = services.open_raster()

    with pytest.raises(QgisSdkUnsupportedCapabilityError) as error:
        services.layers.selection(raster_id)

    assert error.value.capability == raster_id


def test_a_raster_exports_to_a_new_file(services: Services) -> None:
    rasters, info = _raster(services)
    assert services.project_directory is not None
    destination = services.project_directory() / "elevation-export.tif"

    exported = rasters.export_raster(info.id, destination)

    assert exported.driver == "GTiff"
    assert exported.path == str(destination)
    assert destination.is_file()


def test_an_export_refuses_to_replace_a_file_without_permission(
    services: Services,
) -> None:
    rasters, info = _raster(services)
    assert services.project_directory is not None
    destination = services.project_directory() / "elevation-export.tif"
    rasters.export_raster(info.id, destination)

    with pytest.raises(QgisSdkExportRefusedError):
        rasters.export_raster(info.id, destination)

    replaced = rasters.export_raster(info.id, destination, overwrite=True)
    assert replaced.path == str(destination)


def test_an_export_refuses_an_unknown_suffix(services: Services) -> None:
    rasters, info = _raster(services)
    assert services.project_directory is not None

    with pytest.raises(QgisSdkExportRefusedError) as error:
        rasters.export_raster(info.id, services.project_directory() / "out.xyz")

    assert "unsupported format" in str(error.value)

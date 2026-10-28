"""Real OGR exports: the written file is a faithful, re-openable copy.

Opt-in under ``QGIS_SDK_NATIVE_SERVICES=1``: the fake copies bytes, so only
QGIS can prove that an export carries every feature and the source CRS, in
both formats the policy admits, and that a GeoPackage write leaves no journal
behind.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import conftest
import pytest
from qgis_sdk.models import BufferRequest, QgisSdkExportRefusedError

pytestmark = pytest.mark.qgis

if TYPE_CHECKING:
    from .conftest import Services


def _feature_count(path: Path) -> int:
    from qgis.core import QgsVectorLayer

    layer = QgsVectorLayer(str(path), path.stem, "ogr")
    assert layer.isValid(), path
    return layer.featureCount()


@pytest.mark.parametrize("suffix", [".geojson", ".gpkg"])
def test_the_export_reopens_with_every_feature_and_the_source_crs(
    native_services: Services, tmp_path: Path, suffix: str
) -> None:
    info = native_services.layers.open_vector(native_services.dataset)
    destination = tmp_path / f"exported{suffix}"

    export = native_services.layers.export_vector(info.id, destination)

    reopened = native_services.layers.open_vector(Path(export.path))
    assert reopened.geometry_type == info.geometry_type
    assert reopened.crs == info.crs
    assert set(reopened.field_names) >= set(info.field_names)
    assert _feature_count(destination) == _feature_count(native_services.dataset)
    assert sorted(p.name for p in tmp_path.iterdir()) == [destination.name]


@pytest.mark.parametrize("destination_is_source", [True, False])
def test_a_virtual_dataset_with_an_indirect_source_is_refused(
    native_services: Services, tmp_path: Path, destination_is_source: bool
) -> None:
    source = tmp_path / "points.geojson"
    source.write_bytes(native_services.dataset.read_bytes())
    vrt = tmp_path / "virtual.vrt"
    vrt.write_text(
        '<OGRVRTDataSource><OGRVRTLayer name="points">'
        '<SrcDataSource relativeToVRT="1">points.geojson</SrcDataSource>'
        "</OGRVRTLayer></OGRVRTDataSource>",
        encoding="utf-8",
    )
    info = native_services.layers.open_vector(vrt)
    original = source.read_bytes()
    inode = source.stat().st_ino

    destination = source if destination_is_source else tmp_path / "other.geojson"
    with pytest.raises(QgisSdkExportRefusedError, match="source"):
        native_services.layers.export_vector(info.id, destination, overwrite=True)

    assert source.read_bytes() == original
    assert source.stat().st_ino == inode
    if not destination_is_source:
        assert not destination.exists()


def test_a_local_shapefile_can_be_exported_without_changing_its_files(
    native_services: Services, tmp_path: Path
) -> None:
    from qgis.core import (
        QgsCoordinateTransformContext,
        QgsVectorFileWriter,
        QgsVectorLayer,
    )

    fixture = QgsVectorLayer(str(native_services.dataset), "source", "ogr")
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "ESRI Shapefile"
    source = tmp_path / "source.shp"
    error, *_ = QgsVectorFileWriter.writeAsVectorFormatV3(
        fixture, str(source), QgsCoordinateTransformContext(), options
    )
    assert error == QgsVectorFileWriter.WriterError.NoError
    before = {path.name: path.read_bytes() for path in tmp_path.glob("source.*")}
    info = native_services.layers.open_vector(source)

    result = native_services.layers.export_vector(info.id, tmp_path / "export.geojson")

    assert Path(result.path).is_file()
    assert {
        path.name: path.read_bytes() for path in tmp_path.glob("source.*")
    } == before


def test_a_processing_output_can_be_exported(
    native_services: Services, tmp_path: Path
) -> None:
    info = native_services.layers.open_vector(native_services.dataset)
    output = native_services.algorithms.execute(
        BufferRequest(
            layer_id=info.id, distance_metres=250.0, working_crs=conftest.WORKING_CRS
        )
    )

    export = native_services.layers.export_vector(output.id, tmp_path / "buffer.gpkg")

    assert _feature_count(Path(export.path)) == _feature_count(native_services.dataset)
    assert native_services.layers.open_vector(Path(export.path)).geometry_type == (
        "polygon"
    )

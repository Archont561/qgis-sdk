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


class _CcState:
    """A mutable record shared by the phases of one long function."""

    def __init__(_cc_self, **values):
        _cc_self.__dict__.update(values)


class _CcReturn:
    """An early return travelling out of a phase."""

    def __init__(_cc_self, value):
        _cc_self.value = value


class _CcBreak:
    """A loop break travelling out of a phase."""


class _CcContinue:
    """A loop continue travelling out of a phase."""


def _cc_test_a_local_sha_p1(_s):
    from qgis.core import (
        QgsCoordinateTransformContext,
        QgsVectorFileWriter,
        QgsVectorLayer,
    )

    _s.QgsCoordinateTransformContext = QgsCoordinateTransformContext
    _s.QgsVectorFileWriter = QgsVectorFileWriter
    _s.QgsVectorLayer = QgsVectorLayer

    _s.fixture = _s.QgsVectorLayer(str(_s.native_services.dataset), "source", "ogr")
    _s.options = _s.QgsVectorFileWriter.SaveVectorOptions()
    _s.options.driverName = "ESRI Shapefile"
    _s.source = _s.tmp_path / "source.shp"


def _cc_test_a_local_sha_p2(_s):
    _s.error, *_s._ = _s.QgsVectorFileWriter.writeAsVectorFormatV3(
        _s.fixture, str(_s.source), _s.QgsCoordinateTransformContext(), _s.options
    )
    assert _s.error == _s.QgsVectorFileWriter.WriterError.NoError
    _s.before = {path.name: path.read_bytes() for path in _s.tmp_path.glob("source.*")}
    _s.info = _s.native_services.layers.open_vector(_s.source)

    _s.result = _s.native_services.layers.export_vector(
        _s.info.id, _s.tmp_path / "export.geojson"
    )

    assert Path(_s.result.path).is_file()


def _cc_test_a_local_sha_p3(_s):
    assert {
        path.name: path.read_bytes() for path in _s.tmp_path.glob("source.*")
    } == _s.before


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
    _s = _CcState(native_services=native_services, tmp_path=tmp_path)
    for _p in (
        _cc_test_a_local_sha_p1,
        _cc_test_a_local_sha_p2,
        _cc_test_a_local_sha_p3,
    ):
        _r = _p(_s)
        if isinstance(_r, _CcReturn):
            return _r.value
    return None


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

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
from qgis_sdk.models import BufferRequest

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

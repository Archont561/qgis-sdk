"""A vector tile layer's data source is a typed URI, not a path (TASK-91).

The two fixes this module pins were both found by opening a real file: a layer
whose data source is a bare path never gets a provider, and a point cloud opened
with the provider's *library* name instead of its registry key never gets one
either. Both failures look like a broken file - the layer comes back invalid and
the service reports the source as missing - so they are asserted here, where the
message says which one it was.

Skips unless the QGIS bindings are importable, like every ``*_native`` module.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import layer_kind_fixtures as fixture_files
import pytest

pytestmark = pytest.mark.qgis

try:
    from qgis.core import QgsDataSourceUri, QgsVectorTileLayer
except ImportError as error:  # pragma: no cover - depends on the host
    pytest.skip(f"the vector tile source needs QGIS: {error}", allow_module_level=True)

from qgis_sdk.core import ResourceScope
from qgis_sdk.models import QgisSdkUnsupportedCapabilityError


def test_a_vector_tile_source_names_its_type_and_its_path(tmp_path: Path) -> None:
    """``type=mbtiles&url=...`` is what the layer reads a provider key out of."""
    from qgis_sdk.adapters.qgis.layers import _vector_tile_source

    tiles = fixture_files.write_vector_tiles(tmp_path / "basemap.mbtiles")

    uri = _vector_tile_source(tiles)

    # The value is percent-encoded on the way out and decoded on the way in, so
    # the assertion is the round trip rather than the bytes: a temp directory
    # with a space in its name has to survive both halves.
    parsed = QgsDataSourceUri()
    parsed.setEncodedUri(uri)
    assert parsed.param("type") == "mbtiles"
    assert parsed.param("url") == str(tiles)
    layer = QgsVectorTileLayer(uri, tiles.stem)
    assert layer.isValid(), layer.error().message() if layer.error() else uri


def test_a_path_a_tile_provider_cannot_open_is_refused_by_suffix(
    tmp_path: Path,
) -> None:
    """A raster handed to the tile service is refused, not reported as missing."""
    scope = ResourceScope()
    from qgis_sdk.adapters.qgis import NativeLayers

    layers = NativeLayers(scope)
    raster = tmp_path / "elevation.asc"
    raster.write_text("ncols 1\nnrows 1\n", encoding="utf-8")

    with pytest.raises(QgisSdkUnsupportedCapabilityError) as error:
        layers.open_vector_tile(raster)

    assert ".asc" in str(error.value)
    scope.close()


def test_a_point_cloud_opens_with_the_key_its_provider_registers(
    tmp_path: Path, qgis_app: Any
) -> None:
    """The registry answers ``pdal``; ``pointcloud`` is the library, not a key."""
    from qgis_sdk.adapters.qgis import NativeLayers

    scope = ResourceScope()
    layers = NativeLayers(scope)
    cloud = fixture_files.write_point_cloud(tmp_path / "survey.las")

    info = layers.open_point_cloud(cloud)

    assert info.kind == "point_cloud"
    assert info.point_count == len(fixture_files.POINT_CLOUD_POINTS)
    assert "Z" in info.attribute_names
    scope.close()

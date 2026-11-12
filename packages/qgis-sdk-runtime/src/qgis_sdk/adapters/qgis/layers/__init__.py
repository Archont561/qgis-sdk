"""PyQGIS-backed layer service.

Native module: importing it needs a QGIS installation, so nothing on the pure
side may import it (``tests/test_pure_imports.py`` guards that). The adapter
returns :class:`~qgis_sdk.models.layers.LayerInfo` values - a
:class:`~qgis_sdk.models.layers.VectorLayerInfo`, one of the five other kinds
this module opens itself, or, when a sibling ``NativeRasters`` opened it, a
:class:`~qgis_sdk.models.layers.RasterLayerInfo` - and never a PyQGIS handle.
"""

from __future__ import annotations

from ._layers import NativeLayers

__all__ = ["NativeLayers"]

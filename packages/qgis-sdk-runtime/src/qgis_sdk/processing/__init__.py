"""Typed access to QGIS Processing (decision-64).

``qgis_sdk.processing.native``, ``.qgis``, ``.gdal``, ``.p3d`` and ``.pdal``
are generated from the pinned QGIS 4: one ``...Params`` TypedDict, one
``...Result`` TypedDict and one keyword-only request class per algorithm.
``CATALOGUE`` is the description they were generated from; a host whose
registry differs is described by ``ctx.algorithms.describe``. A project
with other providers generates its own package with
``qgis-sdk processing generate``.
"""

from __future__ import annotations

from .snapshot import CORE_PROVIDERS, core_catalogue, load_catalogue
from .types import Destination, Extent, LayerRef, PointValue, RangeValue

__all__ = [
    "CORE_PROVIDERS",
    "Destination",
    "Extent",
    "LayerRef",
    "PointValue",
    "RangeValue",
    "core_catalogue",
    "load_catalogue",
]

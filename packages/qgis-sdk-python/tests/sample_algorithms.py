"""A sample provider the runtime tests share.

The same shape ``examples/simple/simple/algorithms.py`` has - a distance
operation that needs an explicit working CRS and a geometric one that does not
- declared here so the runtime's own tests depend on no example code.
"""

from __future__ import annotations

from qgis_sdk.core import AlgorithmContext
from qgis_sdk.models import (
    BufferRequest,
    CentroidRequest,
    CrsInput,
    LayerInput,
    Metres,
    VectorLayerInfo,
)
from qgis_sdk.providers import Provider

__all__ = ["buffer_layer", "centroid_layer", "sample_provider"]

sample_provider = Provider(id="sample", title="Sample tools")


@sample_provider.algorithm(
    id="buffer", title="Buffer a layer in an explicit working CRS", group="Geometry"
)
def buffer_layer(
    ctx: AlgorithmContext,
    layer_id: LayerInput,
    distance_metres: Metres,
    working_crs: CrsInput,
) -> VectorLayerInfo:
    """Buffer ``layer_id`` by ``distance_metres`` inside ``working_crs``."""
    return ctx.algorithms.execute(
        BufferRequest(
            layer_id=layer_id,
            distance_metres=distance_metres,
            working_crs=working_crs,
        )
    )


@sample_provider.algorithm(
    id="centroid", title="Replace geometries with centroids", group="Geometry"
)
def centroid_layer(ctx: AlgorithmContext, layer_id: LayerInput) -> VectorLayerInfo:
    """Replace each geometry of ``layer_id`` with its centroid, in a new layer."""
    return ctx.algorithms.execute(CentroidRequest(layer_id=layer_id))

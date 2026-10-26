"""The operations the reference workflow runs (decision-19).

Two of them, deliberately: a distance operation that forces an explicit
projected working CRS and metres, and a geometric one that needs neither. That
pair is what keeps "explicit units" from being a blanket rule the SDK applies
to every possible operation - decision-19 requires a projected CRS *where the
operation has a distance*, not everywhere.

The functions are thin on purpose (decision-42). Request validation lives in
the models, the conversion to Processing parameters lives in the native
adapter, and this layer only binds typed inputs to the produced layer through
the injected service. That is the mapping TASK-14 asks for, and it is why the
same functions run against the in-memory double in a QGIS-free test.
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

__all__ = ["buffer_layer", "centroid_layer", "reference_provider"]

# One provider owns the workflow's operations, the way one app owns its routes.
reference_provider = Provider(id="reference", title="Reference plugin")


@reference_provider.algorithm(
    id="buffer", title="Buffer a layer in an explicit working CRS", group="Geometry"
)
def buffer_layer(
    ctx: AlgorithmContext,
    layer_id: LayerInput,
    distance_metres: Metres,
    working_crs: CrsInput,
) -> VectorLayerInfo:
    """Buffer ``layer_id`` by ``distance_metres`` inside ``working_crs``.

    The request refuses an empty CRS or a non-positive distance before anything
    runs; the native service refuses a geographic or non-metre CRS.
    """
    return ctx.algorithms.execute(
        BufferRequest(
            layer_id=layer_id,
            distance_metres=distance_metres,
            working_crs=working_crs,
        )
    )


@reference_provider.algorithm(
    id="centroid", title="Replace geometries with centroids", group="Geometry"
)
def centroid_layer(ctx: AlgorithmContext, layer_id: LayerInput) -> VectorLayerInfo:
    """Replace each geometry of ``layer_id`` with its centroid, in a new layer."""
    return ctx.algorithms.execute(CentroidRequest(layer_id=layer_id))

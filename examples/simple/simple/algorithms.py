"""The Processing algorithms this plugin owns (decision-19, decision-42).

Two of them, deliberately: a distance operation that forces an explicit
projected working CRS and metres, and a geometric one that needs neither. That
pair is what keeps "explicit units" from being a blanket rule the SDK applies
to every possible operation - decision-19 requires a projected CRS *where the
operation has a distance*, not everywhere.

The functions are thin on purpose. Request validation lives in the SDK models,
the conversion to Processing parameters lives in the SDK's native adapter, and
this module only binds typed inputs to the produced layer through the injected
service. That is why the same functions run against the in-memory double in a
QGIS-free test, and why they live here rather than in the runtime: what a
plugin computes is the plugin's.

The two also show both spellings of a Processing call (decision-64): the
buffer keeps the hand-written ``BufferRequest`` with its CRS policy, the
centroid runs the generated ``native.Centroids`` request through the generic
``ctx.algorithms.run`` that reaches any registered algorithm.
"""

from __future__ import annotations

from qgis_sdk.core import AlgorithmContext
from qgis_sdk.models import (
    BufferRequest,
    CrsInput,
    LayerInput,
    Metres,
    VectorLayerInfo,
)
from qgis_sdk.processing import native
from qgis_sdk.providers import Provider

__all__ = ["buffer_layer", "centroid_layer", "provider"]

#: One provider owns the plugin's operations, the way one app owns its routes;
#: the toolbox shows them as ``simple:buffer`` and ``simple:centroid``.
provider = Provider(id="simple", title="Simple")


@provider.algorithm(
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


@provider.algorithm(
    id="centroid", title="Replace geometries with centroids", group="Geometry"
)
def centroid_layer(ctx: AlgorithmContext, layer_id: LayerInput) -> VectorLayerInfo:
    """Replace each geometry of ``layer_id`` with its centroid, in a new layer.

    ``native.Centroids`` is generated from the QGIS registry; the omitted
    ``output`` is allocated by the run and comes back as an owned layer.
    """
    return ctx.algorithms.run(native.Centroids(input=layer_id)).vector("OUTPUT")

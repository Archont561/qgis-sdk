"""The operations the reference workflow runs (decision-19).

Two of them, deliberately: a distance operation that forces an explicit
projected working CRS and metres, and a geometric one that needs neither. That
pair is what keeps "explicit units" from being a blanket rule the SDK applies
to every possible operation - decision-19 requires a projected CRS *where the
operation has a distance*, not everywhere.

The classes are thin on purpose. Request validation lives in the models, the
conversion to Processing parameters lives in the native adapter, and this layer
only binds a typed request to a typed result through the injected service. That
is the mapping TASK-14 asks for, and it is why the same classes run against the
in-memory double in a QGIS-free test.
"""

from __future__ import annotations

from dataclasses import dataclass

from qgis_sdk.algorithms import algorithm
from qgis_sdk.core import AlgorithmContext
from qgis_sdk.models import BufferRequest, CentroidRequest, VectorLayerInfo

__all__ = ["BufferLayer", "BufferResult", "CentroidLayer", "CentroidResult"]


@dataclass(frozen=True, slots=True)
class BufferResult:
    """The buffered output: a new layer, never the source layer restyled."""

    output: VectorLayerInfo


@dataclass(frozen=True, slots=True)
class CentroidResult:
    """The centroid output: a new layer, never the source layer restyled."""

    output: VectorLayerInfo


@algorithm(id="reference.buffer", title="Buffer a layer in an explicit working CRS")
class BufferLayer:
    """Turn one ``BufferRequest`` into its buffered output layer."""

    def __init__(self, ctx: AlgorithmContext) -> None:
        self.ctx = ctx

    def run(self, inputs: BufferRequest) -> BufferResult:
        """Run the buffered operation the request describes."""
        return BufferResult(output=self.ctx.algorithms.execute(inputs))


@algorithm(id="reference.centroid", title="Replace geometries with centroids")
class CentroidLayer:
    """Turn one ``CentroidRequest`` into its centroid output layer."""

    def __init__(self, ctx: AlgorithmContext) -> None:
        self.ctx = ctx

    def run(self, inputs: CentroidRequest) -> CentroidResult:
        """Run the centroid operation the request describes."""
        return CentroidResult(output=self.ctx.algorithms.execute(inputs))

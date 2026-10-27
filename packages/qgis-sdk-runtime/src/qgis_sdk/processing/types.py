"""Value aliases the generated Processing modules annotate with.

They name what a parameter accepts on the SDK side of the boundary, not what
QGIS stores: an owned layer id, a path or a :class:`FileRef` where QGIS wants
a layer; ``None`` for a destination the backend should allocate.
"""

from __future__ import annotations

from qgis_sdk.models import FileRef

__all__ = ["Destination", "Extent", "LayerRef", "PointValue", "RangeValue"]

#: A layer input: the id of a layer this runtime owns, a dataset path, or a ref.
LayerRef = str | FileRef
#: Where an output goes: a path or a writable ref, or ``None`` to have the
#: backend allocate one under the run directory.
Destination = str | FileRef | None
#: ``"xmin,xmax,ymin,ymax [crs]"`` as QGIS writes it, or the four numbers.
Extent = str | tuple[float, float, float, float]
#: ``"x,y [crs]"`` or the two numbers.
PointValue = str | tuple[float, float]
#: ``(lower, upper)``.
RangeValue = tuple[float, float]

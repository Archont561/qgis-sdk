"""Typed requests for the operations the reference workflow may run.

Every request carries the values decision-19 requires to be explicit: which
layer, how far, in which working CRS. Nothing here imports QGIS, so a request
can be built and refused in a pure test - and the same value is what the native
adapter converts into Processing parameters.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .errors import QgisSdkAlgorithmRejectedError


def _refuse(request: str, reasons: list[str]) -> None:
    """Raise once for every reason, so a caller fixes the whole request at once."""
    if reasons:
        raise QgisSdkAlgorithmRejectedError(request, reasons)


@dataclass(frozen=True, slots=True)
class BufferRequest:
    """Buffer one layer by a distance in metres inside an explicit working CRS.

    ``working_crs`` is required and must name a projected CRS whose units are
    metres; the native backend is what can prove that, because deciding whether
    an authority code is projected needs a CRS database. What pure code can
    insist on is that the caller supplied it at all: an empty value means the
    distance would be interpreted in whatever CRS the layer happens to have,
    which is the silent-degrees failure decision-19 rejects.
    """

    layer_id: str
    distance_metres: float
    working_crs: str

    def __post_init__(self) -> None:
        reasons: list[str] = []
        if not self.layer_id.strip():
            reasons.append("layer_id is required")
        if not math.isfinite(self.distance_metres) or self.distance_metres <= 0:
            reasons.append("distance_metres must be a positive finite number")
        if not self.working_crs.strip():
            reasons.append(
                "working_crs is required; a distance without a stated CRS is ambiguous"
            )
        _refuse("buffer", reasons)


@dataclass(frozen=True, slots=True)
class CentroidRequest:
    """Replace each geometry with its centroid; no distance, so no working CRS."""

    layer_id: str

    def __post_init__(self) -> None:
        _refuse("centroid", [] if self.layer_id.strip() else ["layer_id is required"])


# The operations the reference workflow may request. The native adapter
# dispatches on these types, so an unknown request cannot reach Processing.
AlgorithmRequest = BufferRequest | CentroidRequest

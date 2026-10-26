"""Markers that say what an input *means* to a host, not what it stores.

An annotation already carries a type, and the type is enough to render a text
box or a spin box. It is not enough to render the right *widget*: a ``str`` may
be free text or a vector layer the user picks from the canvas, and a ``float``
may be an arbitrary number or a distance whose unit the host should show. The
markers ride along in ``Annotated`` metadata so the wire schema keeps describing
the stored value while the host learns the intent (TASK-39).

The usual spelling is the alias (decision-42): ``layer: LayerInput``,
``crs: CrsInput``, ``distance: Metres``. The explicit form stays available for
a bounded distance or a reader who wants to see the stored type -
``Annotated[float, MetresParameter(minimum=1.0)]`` - and describes identically.

The markers are plain frozen values: equality is by type and bounds, so a test
can assert which marker a parameter carries without importing QGIS.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

__all__ = [
    "CrsInput",
    "CrsParameter",
    "LayerInput",
    "LayerParameter",
    "Metres",
    "MetresParameter",
]


@dataclass(frozen=True, slots=True)
class LayerParameter:
    """The input receives a vector layer chosen by the user."""


@dataclass(frozen=True, slots=True)
class CrsParameter:
    """The input receives a coordinate reference system chosen by the user."""


@dataclass(frozen=True, slots=True)
class MetresParameter:
    """The input is a distance in metres, so the host may label and bound it."""

    minimum: float = 0.0
    maximum: float | None = None


LayerInput = Annotated[str, LayerParameter()]
"""A vector layer id the host fills from a layer picker."""

CrsInput = Annotated[str, CrsParameter()]
"""An authority code (``EPSG:3857``) the host fills from a CRS picker."""

Metres = Annotated[float, MetresParameter()]
"""A distance in metres, labelled as such and bounded at zero by the host."""

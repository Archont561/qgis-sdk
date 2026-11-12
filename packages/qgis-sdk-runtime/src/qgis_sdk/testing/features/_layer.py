"""One layer's rows: the ids, their attributes and their geometries."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from qgis_sdk.models import Geometry

__all__ = ["FakeLayer", "point_coordinates"]

_WKT_POINT = re.compile(
    r"\s*POINT\s*\(\s*(?P<x>-?\d+(?:\.\d+)?)\s+(?P<y>-?\d+(?:\.\d+)?)\s*\)\s*",
    re.IGNORECASE,
)


def point_coordinates(geometry: Geometry | None) -> tuple[float, float] | None:
    """Read the two numbers of a WKT point, or ``None`` for anything else."""
    if geometry is None or geometry.geometry_type != "point":
        return None
    match = _WKT_POINT.match(geometry.value)
    if match is None:
        return None
    return float(match.group("x")), float(match.group("y"))


@dataclass
class FakeLayer:
    """One layer's rows: the ids, their attributes and their geometries.

    ``geometries`` is keyed by feature id and then by encoding. The fake does
    not convert between encodings - that is a geometry engine's job, and a fake
    that approximated it would let a round-trip test pass for a conversion QGIS
    would have refused - so a test declares the encodings it wants to read back
    and asking for another one is refused by name.
    """

    fields: tuple[str, ...]
    rows: dict[int, dict[str, Any]] = field(default_factory=dict)
    geometries: dict[int, dict[str, Geometry]] = field(default_factory=dict)
    editable: bool = True
    #: ``False`` models a provider that writes row by row, so a commit that
    #: fails halfway leaves the rows it already wrote behind (decision-54).
    atomic: bool = True
    #: Bumped on every commit; a session that began earlier sees it change.
    revision: int = 0

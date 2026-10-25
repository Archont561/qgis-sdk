"""QGIS-free description of a vector layer the runtime has opened."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

GeometryType = Literal["point", "line", "polygon", "none"]


@dataclass(frozen=True, slots=True)
class VectorLayerInfo:
    """What pure code may know about an opened vector layer.

    Native handles never cross this boundary. ``id`` is the runtime-owned
    reference, and the remaining fields are the values the reference workflow
    validates before it applies an operation or a style (decision-19).
    """

    id: str
    name: str
    geometry_type: GeometryType
    field_names: tuple[str, ...]
    crs: str | None


@dataclass(frozen=True, slots=True)
class VectorExport:
    """What an explicit export produced: the file written and its format.

    ``path`` is the destination the caller named, as a string so the value
    crosses the bridge unchanged; ``driver`` is the OGR driver the suffix
    selected (``GeoJSON`` or ``GPKG``).
    """

    path: str
    driver: str

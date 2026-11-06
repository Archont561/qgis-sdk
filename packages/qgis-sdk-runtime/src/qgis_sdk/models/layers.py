"""QGIS-free descriptions of the layers and rasters the runtime has opened.

decision-54 point 3 makes a layer *kinded*: a vector layer and a raster layer are
two descriptions a page draws differently, not one description with half its
fields empty. Four choices are deliberate.

*``kind`` is a field, not a test.* A page that receives a layer asks
``info.kind`` and gets ``"vector"`` or ``"raster"``; it never guesses from which
fields happen to be ``None``, and the two types stay independently readable.

*The two descriptions do not inherit from each other.* A shared base class would
tempt a caller to treat ``VectorLayerInfo`` as "a layer" and pass it where a
raster is expected; two sibling types make the union the only shared thing, and
:data:`LayerInfo` is where a caller that genuinely means "either" says so.

*A raster's box is the canvas's box.* :class:`~.
qgis_sdk.models.canvas.CanvasExtent` already carries four finite, ordered numbers
and refuses a box whose corners are the wrong way round, so a raster extent and a
canvas extent are one value a page can pass to ``canvas.zoom_to`` unchanged. The
box's ``crs`` is left ``None`` because the raster's own ``crs`` field says it
once.

*Statistics and samples are band-scoped values.* A band is named by its number
(``1``-based, as QGIS and GDAL name it), never by an object, so a fake and a
native raster answer the same numbers.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from qgis_sdk.models.canvas import (
    CANVAS_EXTENT,
    CANVAS_POINT,
    CanvasExtent,
    CanvasPoint,
)

__all__ = [
    "LAYER_KIND_NAMES",
    "RASTER_EXPORT_DRIVERS",
    "RASTER_LAYER_INFO",
    "RASTER_SAMPLE",
    "RASTER_STATISTICS",
    "LayerInfo",
    "LayerKind",
    "RasterExport",
    "RasterLayerInfo",
    "RasterSample",
    "RasterStatistics",
    "VectorExport",
    "VectorLayerInfo",
    "layer_info",
]

#: The kinds ``Layers.list_layers`` may return. Ordered as the wire enum reads.
LAYER_KIND_NAMES: tuple[str, ...] = ("vector", "raster")

#: The raster drivers :meth:`Rasters.export_raster` can write, by the suffix the
#: caller names. GeoTIFF is the one every GDAL build carries; COG is the
#: cloud-optimised variant of the same bytes and is offered because it is the
#: format a published raster is expected in.
RASTER_EXPORT_DRIVERS: dict[str, str] = {
    ".tif": "GTiff",
    ".tiff": "GTiff",
    ".nc": "netCDF",
}

LayerKind = Literal["vector", "raster"]

GeometryType = Literal["point", "line", "polygon", "none"]


def _is_number(value: Any) -> bool:
    """Whether ``value`` is a real, finite number (``bool`` is not a number)."""
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


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
    kind: Literal["vector"] = "vector"

    def to_wire(self) -> dict[str, Any]:
        """Return the transport representation of this description.

        ``kind`` is always present, so a page reads one discriminator for both
        kinds and never has to try a field to find out what it holds.
        """
        return {
            "kind": self.kind,
            "id": self.id,
            "name": self.name,
            "geometry_type": self.geometry_type,
            "field_names": list(self.field_names),
            "crs": self.crs,
        }

    @classmethod
    def from_wire(cls, value: Mapping[str, Any]) -> VectorLayerInfo:
        """Read one description, refusing a field it does not know."""
        known = {"kind", "id", "name", "geometry_type", "field_names", "crs"}
        unknown = set(value) - known
        if unknown:
            raise ValueError(f"a VectorLayerInfo has no field {min(unknown)!r}")
        return cls(
            id=value["id"],
            name=value["name"],
            geometry_type=value["geometry_type"],
            field_names=tuple(value["field_names"]),
            crs=value.get("crs"),
        )


@dataclass(frozen=True, slots=True)
class RasterLayerInfo:
    """What pure code may know about an opened raster layer (TASK-87).

    ``data_types`` and ``no_data`` are per band, in band order, so
    ``data_types[band - 1]`` is the type of the band a number names - the two
    tuples are exactly ``band_count`` long, which is refused rather than
    tolerated when it is not. ``extent`` is the raster's own box; its ``crs`` is
    ``None`` because :attr:`crs` already says which CRS the numbers are in.
    """

    id: str
    name: str
    band_count: int
    data_types: tuple[str, ...]
    no_data: tuple[float | None, ...]
    extent: CanvasExtent
    #: ``(x, y)`` map units per pixel. Declared variadic because a fixed-length
    #: tuple has no JSON equivalent (the declaration contract), and checked to
    #: be exactly two in ``__post_init__``.
    resolution: tuple[float, ...]
    crs: str | None
    kind: Literal["raster"] = "raster"

    def __post_init__(self) -> None:
        if not isinstance(self.band_count, int) or isinstance(self.band_count, bool):
            raise TypeError("band_count is an integer")
        if self.band_count < 1:
            raise ValueError(f"band_count is at least 1, not {self.band_count}")
        for name in ("data_types", "no_data"):
            values = getattr(self, name)
            if len(values) != self.band_count:
                raise ValueError(
                    f"{name} has one entry per band ({self.band_count}), "
                    f"not {len(values)}"
                )
        for data_type in self.data_types:
            if not isinstance(data_type, str) or not data_type:
                raise ValueError("a band data type is a nonempty string")
        for value in self.no_data:
            if value is not None and not _is_number(value):
                raise ValueError("a no-data value is a finite number or None")
        if len(self.resolution) != 2:
            raise ValueError("resolution is (x, y)")
        for value in self.resolution:
            if not _is_number(value) or value <= 0:
                raise ValueError("a pixel size is a finite positive number")
        if self.extent.crs is not None:
            raise ValueError(
                "a raster extent carries no CRS of its own; the raster names it"
            )
        if self.crs is not None and (not isinstance(self.crs, str) or not self.crs):
            raise ValueError("crs is a nonempty string or None")

    def to_wire(self) -> dict[str, Any]:
        """Return the transport representation of this description."""
        return {
            "kind": self.kind,
            "id": self.id,
            "name": self.name,
            "band_count": self.band_count,
            "data_types": list(self.data_types),
            "no_data": list(self.no_data),
            "extent": self.extent.to_wire(),
            "resolution": list(self.resolution),
            "crs": self.crs,
        }

    @classmethod
    def from_wire(cls, value: Mapping[str, Any]) -> RasterLayerInfo:
        """Read one description, refusing a field it does not know."""
        known = {
            "kind",
            "id",
            "name",
            "band_count",
            "data_types",
            "no_data",
            "extent",
            "resolution",
            "crs",
        }
        unknown = set(value) - known
        if unknown:
            raise ValueError(f"a RasterLayerInfo has no field {min(unknown)!r}")
        return cls(
            id=value["id"],
            name=value["name"],
            band_count=value["band_count"],
            data_types=tuple(value["data_types"]),
            no_data=tuple(value["no_data"]),
            extent=CanvasExtent.from_wire(value["extent"]),
            resolution=tuple(value["resolution"]),
            crs=value.get("crs"),
        )


#: Either kind of layer. A caller that needs one kind narrows with
#: ``isinstance``, and a caller that needs a vector layer asks
#: :func:`layer_info` for it, which refuses a raster by name.
LayerInfo = VectorLayerInfo | RasterLayerInfo


def layer_info(info: LayerInfo) -> dict[str, Any]:
    """Return the wire shape of either kind.

    One function rather than two calls at every site: a handler that answers
    ``layers.list`` holds a union and must not branch on it to serialize it.
    """
    return info.to_wire()


@dataclass(frozen=True, slots=True)
class VectorExport:
    """What an explicit export produced: the file written and its format.

    ``path`` is the destination the caller named, as a string so the value
    crosses the bridge unchanged; ``driver`` is the OGR driver the suffix
    selected (``GeoJSON`` or ``GPKG``).
    """

    path: str
    driver: str


@dataclass(frozen=True, slots=True)
class RasterExport:
    """What a raster export produced: the file written and its GDAL driver."""

    path: str
    driver: str

    def to_wire(self) -> dict[str, Any]:
        return {"path": self.path, "driver": self.driver}


@dataclass(frozen=True, slots=True)
class RasterStatistics:
    """One band's statistics, computed over the band's valid cells.

    ``valid_count`` and ``no_data_count`` add up to the cells the band covers;
    a band with no valid cell answers ``None`` for the four values rather than a
    zero, because "no data" and "all zeros" are different answers.
    """

    band: int
    minimum: float | None
    maximum: float | None
    mean: float | None
    std_dev: float | None
    valid_count: int
    no_data_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.band, int) or isinstance(self.band, bool):
            raise TypeError("band is an integer")
        if self.band < 1:
            raise ValueError(f"band is 1-based, not {self.band}")
        values = (self.minimum, self.maximum, self.mean, self.std_dev)
        if any(value is None for value in values) and not all(
            value is None for value in values
        ):
            raise ValueError(
                "a band with no valid cell has no minimum, maximum, mean or "
                "standard deviation; a band with one has all four"
            )
        for value in values:
            if value is not None and not _is_number(value):
                raise ValueError("a statistic is a finite number or None")
        for name in ("valid_count", "no_data_count"):
            count = getattr(self, name)
            if not isinstance(count, int) or isinstance(count, bool) or count < 0:
                raise ValueError(f"{name} is a non-negative integer")

    def to_wire(self) -> dict[str, Any]:
        return {
            "band": self.band,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "mean": self.mean,
            "std_dev": self.std_dev,
            "valid_count": self.valid_count,
            "no_data_count": self.no_data_count,
        }


@dataclass(frozen=True, slots=True)
class RasterSample:
    """What one point sampled: the point in the raster's CRS, and one value per band.

    A band whose pixel at that point is no-data, or outside the raster, answers
    ``None`` for that band - a sample never invents a zero for a hole.
    """

    point: CanvasPoint
    values: tuple[float | None, ...]

    def __post_init__(self) -> None:
        if not self.values:
            raise ValueError("a sample has one value per band")
        for value in self.values:
            if value is not None and not _is_number(value):
                raise ValueError("a sampled value is a finite number or None")

    def to_wire(self) -> dict[str, Any]:
        return {"point": self.point.to_wire(), "values": list(self.values)}


# ---------------------------------------------------------------------------
# The wire shapes the generated TypeScript types come from
# ---------------------------------------------------------------------------

RASTER_LAYER_INFO: dict[str, Any] = {
    "type": "object",
    "title": "RasterLayerInfo",
    "properties": {
        "kind": {"enum": ["raster"]},
        "id": {"type": "string"},
        "name": {"type": "string"},
        "band_count": {"type": "integer", "minimum": 1},
        "data_types": {"type": "array", "items": {"type": "string"}},
        "no_data": {
            "type": "array",
            "items": {"anyOf": [{"type": "number"}, {"type": "null"}]},
        },
        "extent": CANVAS_EXTENT,
        "resolution": {"type": "array", "items": {"type": "number"}},
        "crs": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    },
    "required": [
        "kind",
        "id",
        "name",
        "band_count",
        "data_types",
        "no_data",
        "extent",
        "resolution",
        "crs",
    ],
    "additionalProperties": False,
}

#: One sample result: the point and one value per band, ``null`` where the
#: pixel is a hole or outside the raster.
RASTER_SAMPLE: dict[str, Any] = {
    "type": "object",
    "title": "RasterSample",
    "properties": {
        "point": CANVAS_POINT,
        "values": {
            "type": "array",
            "items": {"anyOf": [{"type": "number"}, {"type": "null"}]},
        },
    },
    "required": ["point", "values"],
    "additionalProperties": False,
}

RASTER_STATISTICS: dict[str, Any] = {
    "type": "object",
    "title": "RasterStatistics",
    "properties": {
        "band": {"type": "integer", "minimum": 1},
        "minimum": {"anyOf": [{"type": "number"}, {"type": "null"}]},
        "maximum": {"anyOf": [{"type": "number"}, {"type": "null"}]},
        "mean": {"anyOf": [{"type": "number"}, {"type": "null"}]},
        "std_dev": {"anyOf": [{"type": "number"}, {"type": "null"}]},
        "valid_count": {"type": "integer", "minimum": 0},
        "no_data_count": {"type": "integer", "minimum": 0},
    },
    "required": [
        "band",
        "minimum",
        "maximum",
        "mean",
        "std_dev",
        "valid_count",
        "no_data_count",
    ],
    "additionalProperties": False,
}

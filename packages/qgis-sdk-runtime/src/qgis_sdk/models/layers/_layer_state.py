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
    CanvasExtent,
)


class _CcState:
    """A mutable record shared by the phases of one long function."""

    def __init__(_cc_self, **values):
        _cc_self.__dict__.update(values)


class _CcReturn:
    """An early return travelling out of a phase."""

    def __init__(_cc_self, value):
        _cc_self.value = value


def _cc_post_init___tail_p1(_s):
    _s.self = _s.values["self"]
    for name in ("data_types", "no_data"):
        _s.name = name
        _s.values = getattr(_s.self, _s.name)
        if len(_s.values) != _s.self.band_count:
            raise ValueError(
                f"{_s.name} has one entry per band ({_s.self.band_count}), not {len(_s.values)}"
            )
    for data_type in _s.self.data_types:
        _s.data_type = data_type
        if not isinstance(_s.data_type, str) or not _s.data_type:
            raise ValueError("a band data type is a nonempty string")


def _cc_post_init___tail_p2(_s):
    for value in _s.self.no_data:
        _s.value = value
        if _s.value is not None and not is_number(_s.value):
            raise ValueError("a no-data value is a finite number or None")
    if len(_s.self.resolution) != 2:
        raise ValueError("resolution is (x, y)")


def _cc_post_init___tail_p3(_s):
    for value in _s.self.resolution:
        _s.value = value
        if not is_number(_s.value) or _s.value <= 0:
            raise ValueError("a pixel size is a finite positive number")
    if _s.self.extent.crs is not None:
        raise ValueError(
            "a raster extent carries no CRS of its own; the raster names it"
        )


def _cc_post_init___tail_p4(_s):
    if _s.self.crs is not None and (
        not isinstance(_s.self.crs, str) or not _s.self.crs
    ):
        raise ValueError("crs is a nonempty string or None")


def _post_init___tail2(**values):
    _s = _CcState(values=values)
    for _p in (
        _cc_post_init___tail_p1,
        _cc_post_init___tail_p2,
        _cc_post_init___tail_p3,
        _cc_post_init___tail_p4,
    ):
        _r = _p(_s)
        if isinstance(_r, _CcReturn):
            return _r.value
    return None


def post_init___tail1(**values):
    self = values["self"]
    values = (self.minimum, self.maximum, self.mean, self.std_dev)
    if any(value is None for value in values) and not all(
        value is None for value in values
    ):
        raise ValueError(
            "a band with no valid cell has no minimum, maximum, mean or "
            "standard deviation; a band with one has all four"
        )
    for value in values:
        if value is not None and not is_number(value):
            raise ValueError("a statistic is a finite number or None")
    for name in ("valid_count", "no_data_count"):
        count = getattr(self, name)
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise ValueError(f"{name} is a non-negative integer")


LAYER_KIND_NAMES: tuple[str, ...] = (
    "vector",
    "raster",
    "mesh",
    "point_cloud",
    "vector_tile",
    "annotation",
    "tiled_scene",
)
RASTER_EXPORT_DRIVERS: dict[str, str] = {
    ".tif": "GTiff",
    ".tiff": "GTiff",
    ".nc": "netCDF",
}
LayerKind = Literal[
    "vector",
    "raster",
    "mesh",
    "point_cloud",
    "vector_tile",
    "annotation",
    "tiled_scene",
]
GeometryType = Literal["point", "line", "polygon", "none"]


def is_number(value: Any) -> bool:
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
        _post_init___tail2(**{**globals(), **locals()})

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


def check_count(name: str, value: Any) -> None:
    """A count is a whole number, and never negative."""
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{name} is an integer")
    if value < 0:
        raise ValueError(f"{name} is at least 0, not {value}")


def check_text(name: str, value: Any) -> None:
    """A name is a nonempty string."""
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} is a nonempty string")


def check_crs(crs: Any) -> None:
    """A CRS is an authority code or ``None``, never an object."""
    if crs is not None and (not isinstance(crs, str) or not crs):
        raise ValueError("crs is a nonempty string or None")


def check_extent(extent: Any) -> None:
    """A layer's box is a canvas box that names no CRS of its own."""
    if not isinstance(extent, CanvasExtent):
        raise TypeError("extent is a CanvasExtent")
    if extent.crs is not None:
        raise ValueError("an extent here carries no CRS of its own; crs names it")

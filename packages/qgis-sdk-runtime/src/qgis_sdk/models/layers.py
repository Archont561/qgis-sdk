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
        if _s.value is not None and not _is_number(_s.value):
            raise ValueError("a no-data value is a finite number or None")
    if len(_s.self.resolution) != 2:
        raise ValueError("resolution is (x, y)")


def _cc_post_init___tail_p3(_s):
    for value in _s.self.resolution:
        _s.value = value
        if not _is_number(_s.value) or _s.value <= 0:
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


def _post_init___tail1(**values):
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
        if value is not None and not _is_number(value):
            raise ValueError("a statistic is a finite number or None")
    for name in ("valid_count", "no_data_count"):
        count = getattr(self, name)
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise ValueError(f"{name} is a non-negative integer")


__all__ = [
    "ANNOTATION_LAYER_INFO",
    "LAYER_INFO_NAMES",
    "LAYER_INFO_SCHEMAS",
    "LAYER_KIND_NAMES",
    "MESH_LAYER_INFO",
    "POINT_CLOUD_LAYER_INFO",
    "RASTER_EXPORT_DRIVERS",
    "RASTER_LAYER_INFO",
    "RASTER_SAMPLE",
    "RASTER_STATISTICS",
    "TILED_SCENE_LAYER_INFO",
    "VECTOR_TILE_LAYER_INFO",
    "AnnotationLayerInfo",
    "LayerInfo",
    "LayerKind",
    "MeshLayerInfo",
    "PointCloudLayerInfo",
    "RasterExport",
    "RasterLayerInfo",
    "RasterSample",
    "RasterStatistics",
    "TiledSceneLayerInfo",
    "VectorExport",
    "VectorLayerInfo",
    "VectorTileLayerInfo",
    "layer_info",
    "layer_kind_of",
]

#: The kinds ``Layers.list_layers`` may return. Ordered as the wire enum reads:
#: the two that have been here since 0.10.0 first, then the five TASK-91 adds,
#: so a page that switched on the first two keeps its meaning and the new ones
#: append to the list rather than reshuffling it.
LAYER_KIND_NAMES: tuple[str, ...] = (
    "vector",
    "raster",
    "mesh",
    "point_cloud",
    "vector_tile",
    "annotation",
    "tiled_scene",
)

#: The raster drivers :meth:`Rasters.export_raster` can write, by the suffix the
#: caller names. GeoTIFF is the one every GDAL build carries; COG is the
#: cloud-optimised variant of the same bytes and is offered because it is the
#: format a published raster is expected in.
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


# ---------------------------------------------------------------------------
# The five kinds TASK-91 adds (decision-54 point 4)
# ---------------------------------------------------------------------------
#
# Each of these answers the numbers *its own* kind has, and nothing borrowed
# from a kind it is not: a mesh has vertices and faces, a point cloud has points
# and attributes, a vector tile layer has a source type and a zoom range, an
# annotation layer has items, and a 3D tiled scene has a box. A single
# "everything optional" description would have let a page read a raster's
# ``band_count`` off a mesh and get ``None`` instead of a refusal, which is the
# shape decision-54 point 3 deliberately rejected for vector and raster.
#
# Two choices are shared with the raster: a count is a whole number that is
# never negative, and ``crs`` is an authority code or ``None``, never an object.


def _check_count(name: str, value: Any) -> None:
    """A count is a whole number, and never negative."""
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{name} is an integer")
    if value < 0:
        raise ValueError(f"{name} is at least 0, not {value}")


def _check_text(name: str, value: Any) -> None:
    """A name is a nonempty string."""
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} is a nonempty string")


def _check_crs(crs: Any) -> None:
    """A CRS is an authority code or ``None``, never an object."""
    if crs is not None and (not isinstance(crs, str) or not crs):
        raise ValueError("crs is a nonempty string or None")


def _check_extent(extent: Any) -> None:
    """A layer's box is a canvas box that names no CRS of its own."""
    if not isinstance(extent, CanvasExtent):
        raise TypeError("extent is a CanvasExtent")
    if extent.crs is not None:
        raise ValueError("an extent here carries no CRS of its own; crs names it")


@dataclass(frozen=True, slots=True)
class MeshLayerInfo:
    """What pure code may know about an opened mesh layer.

    A mesh is a surface of vertices and faces with datasets - water depth,
    velocity - grouped by the provider. ``group_count`` is how many dataset
    groups the mesh declares, and zero is a legal answer: a mesh with geometry
    and no result stored on it is a mesh, not a broken one.
    """

    id: str
    name: str
    #: Vertices in the mesh's own geometry, as the provider counts them.
    vertex_count: int
    #: Faces (triangles or quads) the mesh is built from.
    face_count: int
    #: Dataset groups the provider declares: one per quantity it carries.
    group_count: int
    crs: str | None
    kind: Literal["mesh"] = "mesh"

    def __post_init__(self) -> None:
        for name in ("vertex_count", "face_count", "group_count"):
            _check_count(name, getattr(self, name))
        _check_crs(self.crs)

    def to_wire(self) -> dict[str, Any]:
        """Return the transport representation of this description."""
        return {
            "kind": self.kind,
            "id": self.id,
            "name": self.name,
            "vertex_count": self.vertex_count,
            "face_count": self.face_count,
            "group_count": self.group_count,
            "crs": self.crs,
        }

    @classmethod
    def from_wire(cls, value: Mapping[str, Any]) -> MeshLayerInfo:
        """Read one description, refusing a field it does not know."""
        known = {
            "kind",
            "id",
            "name",
            "vertex_count",
            "face_count",
            "group_count",
            "crs",
        }
        unknown = set(value) - known
        if unknown:
            raise ValueError(f"a MeshLayerInfo has no field {min(unknown)!r}")
        return cls(
            id=value["id"],
            name=value["name"],
            vertex_count=value["vertex_count"],
            face_count=value["face_count"],
            group_count=value["group_count"],
            crs=value.get("crs"),
        )


@dataclass(frozen=True, slots=True)
class PointCloudLayerInfo:
    """What pure code may know about an opened point cloud layer.

    ``point_count`` is the whole cloud, including the points a subset string
    hides: it is the size of the dataset, not of the current view. The
    attributes are the ones the file declares, in the file's own order, so a
    page can offer them as columns without reading a point.
    """

    id: str
    name: str
    point_count: int
    attribute_names: tuple[str, ...]
    crs: str | None
    kind: Literal["point_cloud"] = "point_cloud"

    def __post_init__(self) -> None:
        _check_count("point_count", self.point_count)
        for attribute in self.attribute_names:
            _check_text("an attribute name", attribute)
        _check_crs(self.crs)

    def to_wire(self) -> dict[str, Any]:
        """Return the transport representation of this description."""
        return {
            "kind": self.kind,
            "id": self.id,
            "name": self.name,
            "point_count": self.point_count,
            "attribute_names": list(self.attribute_names),
            "crs": self.crs,
        }

    @classmethod
    def from_wire(cls, value: Mapping[str, Any]) -> PointCloudLayerInfo:
        """Read one description, refusing a field it does not know."""
        known = {"kind", "id", "name", "point_count", "attribute_names", "crs"}
        unknown = set(value) - known
        if unknown:
            raise ValueError(f"a PointCloudLayerInfo has no field {min(unknown)!r}")
        return cls(
            id=value["id"],
            name=value["name"],
            point_count=value["point_count"],
            attribute_names=tuple(value["attribute_names"]),
            crs=value.get("crs"),
        )


@dataclass(frozen=True, slots=True)
class VectorTileLayerInfo:
    """What pure code may know about an opened vector tile layer.

    A vector tile layer is a *source*: a template URL a client fetches tiles
    from, plus the zoom range the source declares. What this description does
    **not** carry is the source path, deliberately: a tile URL routinely holds a
    token (a ``?key=`` query, a signed storage URL), and a description travels to
    a page, a log and a bug report. ``source_type`` - ``xyz``, ``mbtiles`` -
    names the shape of the source without repeating its credentials, which is
    the same rule TASK-92 applies to authentication (ids and names, never
    secrets).
    """

    id: str
    name: str
    #: The provider's own spelling of the source shape: ``xyz``, ``mbtiles``.
    source_type: str
    #: The lowest zoom the source declares tiles for.
    min_zoom: int
    #: The highest zoom the source declares tiles for.
    max_zoom: int
    crs: str | None
    kind: Literal["vector_tile"] = "vector_tile"

    def __post_init__(self) -> None:
        _check_text("source_type", self.source_type)
        for name in ("min_zoom", "max_zoom"):
            _check_count(name, getattr(self, name))
        if self.min_zoom > self.max_zoom:
            raise ValueError(
                f"a zoom range starts below it ends: {self.min_zoom} to {self.max_zoom}"
            )
        _check_crs(self.crs)

    def to_wire(self) -> dict[str, Any]:
        """Return the transport representation of this description."""
        return {
            "kind": self.kind,
            "id": self.id,
            "name": self.name,
            "source_type": self.source_type,
            "min_zoom": self.min_zoom,
            "max_zoom": self.max_zoom,
            "crs": self.crs,
        }

    @classmethod
    def from_wire(cls, value: Mapping[str, Any]) -> VectorTileLayerInfo:
        """Read one description, refusing a field it does not know."""
        known = {
            "kind",
            "id",
            "name",
            "source_type",
            "min_zoom",
            "max_zoom",
            "crs",
        }
        unknown = set(value) - known
        if unknown:
            raise ValueError(f"a VectorTileLayerInfo has no field {min(unknown)!r}")
        return cls(
            id=value["id"],
            name=value["name"],
            source_type=value["source_type"],
            min_zoom=value["min_zoom"],
            max_zoom=value["max_zoom"],
            crs=value.get("crs"),
        )


@dataclass(frozen=True, slots=True)
class AnnotationLayerInfo:
    """What pure code may know about an annotation layer.

    An annotation layer has no dataset behind it: it is a bag of items a user or
    a plugin drew in the project, and the only thing to say about it at this
    level is how many. The items themselves are ``QgsAnnotationItem`` handles
    and stay native until a later task models them.
    """

    id: str
    name: str
    item_count: int
    crs: str | None
    kind: Literal["annotation"] = "annotation"

    def __post_init__(self) -> None:
        _check_count("item_count", self.item_count)
        _check_crs(self.crs)

    def to_wire(self) -> dict[str, Any]:
        """Return the transport representation of this description."""
        return {
            "kind": self.kind,
            "id": self.id,
            "name": self.name,
            "item_count": self.item_count,
            "crs": self.crs,
        }

    @classmethod
    def from_wire(cls, value: Mapping[str, Any]) -> AnnotationLayerInfo:
        """Read one description, refusing a field it does not know."""
        known = {"kind", "id", "name", "item_count", "crs"}
        unknown = set(value) - known
        if unknown:
            raise ValueError(f"an AnnotationLayerInfo has no field {min(unknown)!r}")
        return cls(
            id=value["id"],
            name=value["name"],
            item_count=value["item_count"],
            crs=value.get("crs"),
        )


@dataclass(frozen=True, slots=True)
class TiledSceneLayerInfo:
    """What pure code may know about an opened 3D tiled scene.

    A tiled scene is a hierarchy of tiles in a 3D CRS, and QGIS counts none of
    them cheaply: the index hands out a root tile and asks what its children
    are, so "how many tiles" is a walk, not a field. What *is* cheap and true is
    where the scene sits, so that is what the description carries - the box, in
    the scene's own CRS. ``crs`` names the 3D system the numbers are in
    (``EPSG:4978`` for an ECEF scene).
    """

    id: str
    name: str
    extent: CanvasExtent
    crs: str | None
    kind: Literal["tiled_scene"] = "tiled_scene"

    def __post_init__(self) -> None:
        _check_extent(self.extent)
        _check_crs(self.crs)

    def to_wire(self) -> dict[str, Any]:
        """Return the transport representation of this description."""
        return {
            "kind": self.kind,
            "id": self.id,
            "name": self.name,
            "extent": self.extent.to_wire(),
            "crs": self.crs,
        }

    @classmethod
    def from_wire(cls, value: Mapping[str, Any]) -> TiledSceneLayerInfo:
        """Read one description, refusing a field it does not know."""
        known = {"kind", "id", "name", "extent", "crs"}
        unknown = set(value) - known
        if unknown:
            raise ValueError(f"a TiledSceneLayerInfo has no field {min(unknown)!r}")
        return cls(
            id=value["id"],
            name=value["name"],
            extent=CanvasExtent.from_wire(value["extent"]),
            crs=value.get("crs"),
        )


#: Every kind is either a vector, a raster, or one of the five above. A caller
#: that needs one kind narrows with ``isinstance``; a caller that serializes
#: whatever it holds asks :func:`layer_info`, which dispatches on the object and
#: so cannot drift from the union.
LayerInfo = (
    VectorLayerInfo
    | RasterLayerInfo
    | MeshLayerInfo
    | PointCloudLayerInfo
    | VectorTileLayerInfo
    | AnnotationLayerInfo
    | TiledSceneLayerInfo
)


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
        _post_init___tail1(**{**globals(), **locals()})

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


def _layer_schema(kind: str, title: str, properties: dict[str, Any]) -> dict[str, Any]:
    """One layer description's JSON schema: ``kind`` first, ``crs`` last.

    Built rather than repeated seven times so a page's validation and a host's
    declaration cannot disagree about which fields are required.
    """
    fields = {"kind": {"enum": [kind]}, **properties, "crs": _NULLABLE_STRING}
    return {
        "type": "object",
        "title": title,
        "properties": fields,
        "required": list(fields),
        "additionalProperties": False,
    }


def layer_kind_of(schema: Mapping[str, Any]) -> str:
    """The kind a layer description's schema is for, read from the schema."""
    return str(schema["properties"]["kind"]["enum"][0])


#: A field that is a string or ``null``: an authority code, a CRS, a name the
#: provider did not give.
_NULLABLE_STRING: dict[str, Any] = {"anyOf": [{"type": "string"}, {"type": "null"}]}


MESH_LAYER_INFO: dict[str, Any] = _layer_schema(
    "mesh",
    "MeshLayerInfo",
    {
        "id": {"type": "string"},
        "name": {"type": "string"},
        "vertex_count": {"type": "integer", "minimum": 0},
        "face_count": {"type": "integer", "minimum": 0},
        "group_count": {"type": "integer", "minimum": 0},
    },
)

POINT_CLOUD_LAYER_INFO: dict[str, Any] = _layer_schema(
    "point_cloud",
    "PointCloudLayerInfo",
    {
        "id": {"type": "string"},
        "name": {"type": "string"},
        "point_count": {"type": "integer", "minimum": 0},
        "attribute_names": {"type": "array", "items": {"type": "string"}},
    },
)

VECTOR_TILE_LAYER_INFO: dict[str, Any] = _layer_schema(
    "vector_tile",
    "VectorTileLayerInfo",
    {
        "id": {"type": "string"},
        "name": {"type": "string"},
        "source_type": {"type": "string"},
        "min_zoom": {"type": "integer", "minimum": 0},
        "max_zoom": {"type": "integer", "minimum": 0},
    },
)

ANNOTATION_LAYER_INFO: dict[str, Any] = _layer_schema(
    "annotation",
    "AnnotationLayerInfo",
    {
        "id": {"type": "string"},
        "name": {"type": "string"},
        "item_count": {"type": "integer", "minimum": 0},
    },
)

TILED_SCENE_LAYER_INFO: dict[str, Any] = _layer_schema(
    "tiled_scene",
    "TiledSceneLayerInfo",
    {
        "id": {"type": "string"},
        "name": {"type": "string"},
        "extent": CANVAS_EXTENT,
    },
)

#: Every layer description, by kind. The coverage map, the host catalogue and
#: the model tests read this one table instead of each keeping a list that can
#: fall out of step with :data:`LAYER_KIND_NAMES`.
LAYER_INFO_SCHEMAS: dict[str, dict[str, Any]] = {
    "vector": {
        "type": "object",
        "title": "VectorLayerInfo",
        "properties": {
            "kind": {"enum": ["vector"]},
            "id": {"type": "string"},
            "name": {"type": "string"},
            "geometry_type": {"enum": ["point", "line", "polygon", "none"]},
            "field_names": {"type": "array", "items": {"type": "string"}},
            "crs": _NULLABLE_STRING,
        },
        "required": ["kind", "id", "name", "geometry_type", "field_names", "crs"],
        "additionalProperties": False,
    },
    "raster": RASTER_LAYER_INFO,
    "mesh": MESH_LAYER_INFO,
    "point_cloud": POINT_CLOUD_LAYER_INFO,
    "vector_tile": VECTOR_TILE_LAYER_INFO,
    "annotation": ANNOTATION_LAYER_INFO,
    "tiled_scene": TILED_SCENE_LAYER_INFO,
}

#: The TypeScript name each kind's description is declared under.
LAYER_INFO_NAMES: dict[str, str] = {
    kind: str(schema["title"]) for kind, schema in LAYER_INFO_SCHEMAS.items()
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

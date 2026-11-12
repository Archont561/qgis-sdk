from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from qgis_sdk.models.canvas import (
    CanvasExtent,
)

from ._layer_state import (
    RasterLayerInfo,
    VectorLayerInfo,
    check_count,
    check_crs,
    check_extent,
    check_text,
)


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
            check_count(name, getattr(self, name))
        check_crs(self.crs)

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
        check_count("point_count", self.point_count)
        for attribute in self.attribute_names:
            check_text("an attribute name", attribute)
        check_crs(self.crs)

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
        check_text("source_type", self.source_type)
        for name in ("min_zoom", "max_zoom"):
            check_count(name, getattr(self, name))
        if self.min_zoom > self.max_zoom:
            raise ValueError(
                f"a zoom range starts below it ends: {self.min_zoom} to {self.max_zoom}"
            )
        check_crs(self.crs)

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
        check_count("item_count", self.item_count)
        check_crs(self.crs)

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
        check_extent(self.extent)
        check_crs(self.crs)

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

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from qgis_sdk.models.canvas import (
    CANVAS_EXTENT,
    CANVAS_POINT,
    CanvasPoint,
)

from ._layer_state import is_number, post_init___tail1


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
        post_init___tail1(**{**globals(), **locals()})

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
            if value is not None and not is_number(value):
                raise ValueError("a sampled value is a finite number or None")

    def to_wire(self) -> dict[str, Any]:
        return {"point": self.point.to_wire(), "values": list(self.values)}


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
LAYER_INFO_NAMES: dict[str, str] = {
    kind: str(schema["title"]) for kind, schema in LAYER_INFO_SCHEMAS.items()
}
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

"""The JSON Schemas of the curated host surface: pages, layers, fetch and algorithms."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from qgis_sdk.bridge.authority import FILE_REF
from qgis_sdk.models.blobs import BLOB_REF
from qgis_sdk.models.features import (
    FEATURE_PAGE,
    GEOMETRY_ENCODINGS,
    MAX_FEATURE_PAGE,
)
from qgis_sdk.models.layers import LAYER_INFO_SCHEMAS

DEFAULT_PAGE = 50
MAX_PAGE = 200
BLOB_CHUNK_BYTES = 64 * 1024
MAX_LAYOUT_DPI = 1200
GUI = "gui"
WORKER = "worker"


def object(properties: Mapping[str, Any], required: Sequence[str] = ()) -> dict:
    schema: dict[str, Any] = {
        "type": "object",
        "properties": dict(properties),
        "additionalProperties": False,
    }
    if required:
        schema["required"] = list(required)
    return schema


def array(items: Mapping[str, Any]) -> dict:
    return {"type": "array", "items": items}


VECTOR_LAYER_INFO = LAYER_INFO_SCHEMAS["vector"]
RASTER_LAYER_INFO = LAYER_INFO_SCHEMAS["raster"]
MESH_LAYER_INFO = LAYER_INFO_SCHEMAS["mesh"]
POINT_CLOUD_LAYER_INFO = LAYER_INFO_SCHEMAS["point_cloud"]
VECTOR_TILE_LAYER_INFO = LAYER_INFO_SCHEMAS["vector_tile"]
ANNOTATION_LAYER_INFO = LAYER_INFO_SCHEMAS["annotation"]
TILED_SCENE_LAYER_INFO = LAYER_INFO_SCHEMAS["tiled_scene"]
LAYER_INFO: dict[str, Any] = {
    "anyOf": [LAYER_INFO_SCHEMAS[kind] for kind in LAYER_INFO_SCHEMAS]
}
PAGE_REQUEST = object(
    {
        "limit": {"type": "integer", "minimum": 1, "maximum": MAX_PAGE},
        "cursor": {"type": "string", "pattern": "[0-9]+"},
    }
)
_NOTHING = {"type": "null"}
_TEXT_OR_NULL = {"anyOf": [{"type": "string"}, {"type": "null"}]}
HTTP_HEADER = object(
    {"name": {"type": "string"}, "value": {"type": "string"}},
    required=("name", "value"),
)
HTTP_HEADER["title"] = "HttpHeader"
FETCH_METHODS = ("GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")
MAX_FETCH_TIMEOUT_SECONDS = 300
FETCH_REQUEST = object(
    {
        "url": {"type": "string"},
        "method": {"enum": list(FETCH_METHODS)},
        "headers": array(HTTP_HEADER),
        "body": {"type": "string"},
        "timeout_seconds": {
            "type": "number",
            "minimum": 0.1,
            "maximum": MAX_FETCH_TIMEOUT_SECONDS,
        },
        "auth_config": {"type": "string"},
    },
    required=("url",),
)
FETCH_RESPONSE = object(
    {
        "url": {"type": "string"},
        "status_code": {"type": "integer"},
        "reason": {"type": "string"},
        "headers": array(HTTP_HEADER),
        "text": _TEXT_OR_NULL,
        "base64": _TEXT_OR_NULL,
    },
    required=("url", "status_code", "reason", "headers", "text", "base64"),
)
_SCALAR = {
    "anyOf": [
        {"type": "string"},
        {"type": "number"},
        {"type": "boolean"},
        {"type": "null"},
    ]
}
PROVIDER_INFO = object(
    {
        "id": {"type": "string"},
        "label": {"type": "string"},
        "version": {"type": "string"},
    },
    required=("id", "label", "version"),
)
PROVIDER_INFO["title"] = "ProviderInfo"
ALGORITHM_SUMMARY = object(
    {
        "id": {"type": "string"},
        "provider": {"type": "string"},
        "name": {"type": "string"},
        "label": {"type": "string"},
        "group": {"type": "string"},
        "deprecated": {"type": "boolean"},
    },
    required=("id", "provider", "name", "label", "group", "deprecated"),
)
ALGORITHM_SUMMARY["title"] = "AlgorithmSummary"
PARAMETER_INFO = object(
    {
        "name": {"type": "string"},
        "kind": {"type": "string"},
        "label": {"type": "string"},
        "description": {"type": "string"},
        "optional": {"type": "boolean"},
        "advanced": {"type": "boolean"},
        "hidden": {"type": "boolean"},
        "destination": {"type": "boolean"},
        "required": {"type": "boolean"},
        "default_json": _TEXT_OR_NULL,
        "options": array({"type": "string"}),
        "multiple": {"type": "boolean"},
        "number_type": _TEXT_OR_NULL,
        "minimum": {"anyOf": [{"type": "number"}, {"type": "null"}]},
        "maximum": {"anyOf": [{"type": "number"}, {"type": "null"}]},
        "extension": _TEXT_OR_NULL,
    },
    required=(
        "name",
        "kind",
        "label",
        "description",
        "optional",
        "advanced",
        "hidden",
        "destination",
        "required",
        "default_json",
        "options",
        "multiple",
        "number_type",
        "minimum",
        "maximum",
        "extension",
    ),
)
PARAMETER_INFO["title"] = "ParameterInfo"
OUTPUT_INFO = object(
    {
        "name": {"type": "string"},
        "kind": {"type": "string"},
        "label": {"type": "string"},
    },
    required=("name", "kind", "label"),
)
OUTPUT_INFO["title"] = "OutputInfo"
ALGORITHM_INFO = object(
    {
        "id": {"type": "string"},
        "provider": {"type": "string"},
        "name": {"type": "string"},
        "label": {"type": "string"},
        "group": {"type": "string"},
        "group_id": {"type": "string"},
        "help": {"type": "string"},
        "deprecated": {"type": "boolean"},
        "parameters": array(PARAMETER_INFO),
        "outputs": array(OUTPUT_INFO),
    },
    required=(
        "id",
        "provider",
        "name",
        "label",
        "group",
        "group_id",
        "help",
        "deprecated",
        "parameters",
        "outputs",
    ),
)
ALGORITHM_INFO["title"] = "AlgorithmInfo"
RUN_REQUEST = object(
    {
        "algorithm_id": {"type": "string"},
        "params": {"type": "object"},
    },
    required=("algorithm_id", "params"),
)
RUN_OUTPUT = object(
    {
        "name": {"type": "string"},
        "kind": {"enum": ["vector", "layers", "file", "value"]},
        "layer": VECTOR_LAYER_INFO,
        "layers": array(VECTOR_LAYER_INFO),
        "file": FILE_REF,
        "value": _SCALAR,
    },
    required=("name", "kind"),
)
RUN_OUTPUT["title"] = "RunOutput"
RUN_RESULT = object(
    {"algorithm": {"type": "string"}, "outputs": array(RUN_OUTPUT)},
    required=("algorithm", "outputs"),
)
RUN_RESULT["title"] = "RunResult"
RUN_MODEL_REQUEST = object(
    {"model": FILE_REF, "params": {"type": "object"}},
    required=("model", "params"),
)
RUN_MODEL_REQUEST["title"] = "RunModelRequest"
BATCH_REQUEST = object({"runs": array(RUN_REQUEST)}, required=("runs",))
BATCH_REQUEST["title"] = "BatchRequest"
BATCH_RESULT = object({"results": array(RUN_RESULT)}, required=("results",))
BATCH_RESULT["title"] = "BatchResult"


def page(items: Sequence[Any], cursor: str | None, truncated: bool) -> dict:
    """Shape one page, with the cursor only when something is left."""
    body: dict[str, Any] = {"items": list(items), "truncated": truncated}
    if truncated:
        body["next_cursor"] = cursor
    return body


def page_result(items: Mapping[str, Any]) -> dict:
    return object(
        {
            "items": array(items),
            "truncated": {"type": "boolean"},
            "next_cursor": {"type": "string"},
        },
        required=("items", "truncated"),
    )


BLOB_REQUEST = object(
    {
        "blob": BLOB_REF,
        "offset": {"type": "integer", "minimum": 0},
        "length": {
            "type": "integer",
            "minimum": 1,
            "maximum": BLOB_CHUNK_BYTES,
        },
    },
    required=("blob",),
)
BLOB_CHUNK = object(
    {
        "offset": {"type": "integer", "minimum": 0},
        "length": {"type": "integer", "minimum": 0},
        "size": {"type": "integer", "minimum": 0},
        "media_type": {"type": "string"},
        "checksum": {"type": "string"},
        "data_base64": {"type": "string"},
        "next_offset": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
    },
    required=(
        "offset",
        "length",
        "size",
        "media_type",
        "checksum",
        "data_base64",
        "next_offset",
    ),
)
BLOB_CHUNK["title"] = "BlobChunk"
FEATURE_QUERY = object(
    {
        "layer_id": {"type": "string"},
        "limit": {"type": "integer", "minimum": 1, "maximum": MAX_FEATURE_PAGE},
        "cursor": {"type": "string", "pattern": "[0-9]+"},
        "expression": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "bbox": {
            "anyOf": [
                {
                    "type": "array",
                    "items": {"type": "number"},
                },
                {"type": "null"},
            ]
        },
        "ids": {
            "anyOf": [
                {"type": "array", "items": {"type": "integer"}},
                {"type": "null"},
            ]
        },
        "encoding": {"enum": list(GEOMETRY_ENCODINGS)},
        "with_geometry": {"type": "boolean"},
    },
    required=("layer_id",),
)
FEATURE_QUERY["title"] = "FeaturePageRequest"
FEATURE_PAGE_RESULT = FEATURE_PAGE
FEATURE_REQUEST = object(
    {
        "layer_id": {"type": "string"},
        "feature_id": {"type": "integer"},
        "encoding": {"enum": list(GEOMETRY_ENCODINGS)},
    },
    required=("layer_id", "feature_id"),
)
FEATURE_REQUEST["title"] = "FeatureRequest"
EXPRESSION_REQUEST = object(
    {
        "text": {"type": "string"},
        "layer_id": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "feature_id": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
    },
    required=("text",),
)
EXPRESSION_REQUEST["title"] = "ExpressionRequest"
EDIT_BEGIN_REQUEST = object({"layer_id": {"type": "string"}}, required=("layer_id",))

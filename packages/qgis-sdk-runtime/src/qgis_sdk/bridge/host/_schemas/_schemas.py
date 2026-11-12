from __future__ import annotations

from qgis_sdk.bridge.authority import FILE_REF
from qgis_sdk.models.features import (
    GEOMETRY,
)
from qgis_sdk.models.layouts import LAYOUT_FORMATS

from ._builders import EDIT_BEGIN_REQUEST, MAX_LAYOUT_DPI, array, object

EDIT_BEGIN_REQUEST["title"] = "EditBeginRequest"
EDIT_SESSION_RESULT = object(
    {"session_id": {"type": "string"}, "layer_id": {"type": "string"}},
    required=("session_id", "layer_id"),
)
EDIT_SESSION_RESULT["title"] = "EditSessionInfo"
EDIT_ADD_REQUEST = object(
    {
        "session_id": {"type": "string"},
        "attributes": {"type": "object", "additionalProperties": True},
        "geometry": {"anyOf": [GEOMETRY, {"type": "null"}]},
    },
    required=("session_id", "attributes"),
)
EDIT_ADD_REQUEST["title"] = "EditAddRequest"
EDIT_ADD_RESULT = object(
    {"feature_id": {"type": "integer"}, "pending": {"type": "integer"}},
    required=("feature_id", "pending"),
)
EDIT_ADD_RESULT["title"] = "EditAddResult"
EDIT_UPDATE_REQUEST = object(
    {
        "session_id": {"type": "string"},
        "feature_id": {"type": "integer"},
        "attributes": {"anyOf": [{"type": "object"}, {"type": "null"}]},
        "geometry": {"anyOf": [GEOMETRY, {"type": "null"}]},
    },
    required=("session_id", "feature_id"),
)
EDIT_UPDATE_REQUEST["title"] = "EditUpdateRequest"
EDIT_DELETE_REQUEST = object(
    {"session_id": {"type": "string"}, "feature_id": {"type": "integer"}},
    required=("session_id", "feature_id"),
)
EDIT_DELETE_REQUEST["title"] = "EditDeleteRequest"
EDIT_SESSION_REQUEST = object(
    {"session_id": {"type": "string"}}, required=("session_id",)
)
EDIT_SESSION_REQUEST["title"] = "EditSessionRequest"
EDIT_PENDING_RESULT = object(
    {"session_id": {"type": "string"}, "pending": {"type": "integer"}},
    required=("session_id", "pending"),
)
EDIT_PENDING_RESULT["title"] = "EditPendingResult"
LOAD_LAYOUT_TEMPLATE_REQUEST = object({"file": FILE_REF}, required=("file",))
LOAD_LAYOUT_TEMPLATE_REQUEST["title"] = "LoadLayoutTemplateRequest"
_LAYOUT_RENDER_SETTINGS = {
    "dpi": {"type": "integer", "minimum": 1, "maximum": MAX_LAYOUT_DPI},
    "rasterize": {"type": "boolean"},
    "georeference": {"type": "boolean"},
}
EXPORT_LAYOUT_REQUEST = object(
    {
        "layout": {"type": "string"},
        "format": {"enum": sorted(LAYOUT_FORMATS)},
        "destination": FILE_REF,
        **_LAYOUT_RENDER_SETTINGS,
        "overwrite": {"type": "boolean"},
    },
    required=("layout",),
)
EXPORT_LAYOUT_REQUEST["title"] = "ExportLayoutRequest"
ATLAS_LAYOUT_REQUEST = object(
    {
        "layout": {"type": "string"},
        "format": {"enum": sorted(LAYOUT_FORMATS)},
        "pattern": {"type": "string"},
        **_LAYOUT_RENDER_SETTINGS,
        "overwrite": {"type": "boolean"},
    },
    required=("layout",),
)
ATLAS_LAYOUT_REQUEST["title"] = "AtlasLayoutRequest"
LAYOUT_EXPORT_RESULT = object(
    {
        "file": FILE_REF,
        "format": {"enum": sorted(LAYOUT_FORMATS)},
        "pages": {"type": "integer", "minimum": 1},
        "bytes": {"type": "integer", "minimum": 0},
    },
    required=("file", "format", "pages", "bytes"),
)
LAYOUT_EXPORT_RESULT["title"] = "LayoutExport"
ATLAS_PAGE_RESULT = object(
    {
        "index": {"type": "integer", "minimum": 1},
        "feature_id": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
        "file": FILE_REF,
    },
    required=("index", "feature_id", "file"),
)
ATLAS_PAGE_RESULT["title"] = "AtlasPage"
ATLAS_EXPORT_RESULT = object(
    {
        "directory": FILE_REF,
        "format": {"enum": sorted(LAYOUT_FORMATS)},
        "pages": array(ATLAS_PAGE_RESULT),
    },
    required=("directory", "format", "pages"),
)
ATLAS_EXPORT_RESULT["title"] = "AtlasExport"

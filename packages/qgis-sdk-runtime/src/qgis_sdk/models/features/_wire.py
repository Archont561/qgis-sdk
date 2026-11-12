"""The wire shapes the generated TypeScript types come from."""

from __future__ import annotations

from typing import Any

from ._geometry import GEOMETRY_ENCODINGS, GEOMETRY_TYPES

__all__ = [
    "EDIT_OUTCOME",
    "EXPRESSION_CHECK",
    "EXPRESSION_OUTCOME",
    "FEATURE",
    "FEATURE_PAGE",
    "FEATURE_QUERY",
    "GEOMETRY",
]

GEOMETRY: dict[str, Any] = {
    "type": "object",
    "title": "Geometry",
    "properties": {
        "encoding": {"enum": list(GEOMETRY_ENCODINGS)},
        "value": {"type": "string"},
        "geometry_type": {"enum": list(GEOMETRY_TYPES)},
        "crs": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "part_count": {"type": "integer", "minimum": 0},
        "vertex_count": {"type": "integer", "minimum": 0},
        "is_empty": {"type": "boolean"},
    },
    "required": ["encoding", "value", "geometry_type"],
    "additionalProperties": False,
}

FEATURE: dict[str, Any] = {
    "type": "object",
    "title": "Feature",
    "properties": {
        "id": {"type": "integer"},
        "attributes": {"type": "object", "additionalProperties": True},
        "geometry": {"anyOf": [GEOMETRY, {"type": "null"}]},
    },
    "required": ["id", "attributes"],
    "additionalProperties": False,
}

FEATURE_QUERY: dict[str, Any] = {
    "type": "object",
    "title": "FeatureQuery",
    "properties": {
        "limit": {"type": "integer", "minimum": 1},
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
    "additionalProperties": False,
}

FEATURE_PAGE: dict[str, Any] = {
    "type": "object",
    "title": "FeaturePage",
    "properties": {
        "items": {"type": "array", "items": FEATURE},
        "truncated": {"type": "boolean"},
        "next_cursor": {"type": "string"},
        "total": {"type": "integer", "minimum": 0},
    },
    "required": ["items", "truncated"],
    "additionalProperties": False,
}

EXPRESSION_OUTCOME: dict[str, Any] = {
    "type": "object",
    "title": "ExpressionOutcome",
    "properties": {
        "valid": {"type": "boolean"},
        "value": {"type": ["string", "number", "boolean", "null", "array", "object"]},
        "message": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    },
    "required": ["valid", "message"],
    "additionalProperties": False,
}

EDIT_OUTCOME: dict[str, Any] = {
    "type": "object",
    "title": "EditOutcome",
    "properties": {
        "applied": {"type": "integer", "minimum": 0},
        "feature_ids": {"type": "array", "items": {"type": "integer"}},
        "committed": {"type": "boolean"},
    },
    "required": ["applied", "feature_ids", "committed"],
    "additionalProperties": False,
}

EXPRESSION_CHECK: dict[str, Any] = {
    "type": "object",
    "title": "ExpressionCheck",
    "properties": {
        "valid": {"type": "boolean"},
        "message": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "referenced_columns": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["valid", "message", "referenced_columns"],
    "additionalProperties": False,
}

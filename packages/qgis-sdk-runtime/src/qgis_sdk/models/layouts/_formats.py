"""The format tables and wire schemas of print layouts and atlases.

Pure data: the export format table, the atlas pattern defaults and the JSON
schemas a page reads. The dataclasses that carry these shapes live in
:mod:`._records`; this module holds only what is shared by name.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

__all__ = [
    "ATLAS_EXPORT",
    "ATLAS_INFO",
    "ATLAS_PAGE",
    "ATLAS_TOKENS",
    "DEFAULT_ATLAS_PATTERN",
    "LAYOUT_EXPORT",
    "LAYOUT_FORMATS",
    "LAYOUT_INFO",
    "LAYOUT_SUFFIXES",
    "SINGLE_PAGE_FORMATS",
]

#: Export format name -> the suffix the file gets. The table lives here, not in
#: an adapter, so the fake, the native exporter and the ``layouts.export`` host
#: operation refuse the same format and write the same suffix.
LAYOUT_FORMATS: Mapping[str, str] = {"pdf": ".pdf", "png": ".png", "svg": ".svg"}

#: Destination suffix (lower-case) -> format name, the direction the export
#: policy reads: ``plan_export`` looks a destination's suffix up in a table and
#: answers the driver, which for a layout is the format it was written in.
LAYOUT_SUFFIXES: Mapping[str, str] = {
    suffix: name for name, suffix in LAYOUT_FORMATS.items()
}

#: The formats that hold one page. A PDF holds as many as the layout has.
SINGLE_PAGE_FORMATS = frozenset({"png", "svg"})

#: The default atlas file name pattern. Index only, because a coverage feature's
#: id need not be unique across a project and a pattern naming one is a caller's
#: decision, not the default.
DEFAULT_ATLAS_PATTERN = "page-{index:03d}"

#: The placeholders an atlas pattern may use: ``index`` is zero-based and
#: ``feature_id`` is the coverage feature's own id.
ATLAS_TOKENS = ("index", "feature_id")


def check_format(format: str) -> str:
    """Return ``format`` if it is one this SDK exports, or refuse it by name."""
    if format not in LAYOUT_FORMATS:
        known = ", ".join(sorted(LAYOUT_FORMATS))
        raise ValueError(f"a layout exports to {known}, not {format!r}")
    return format


#: The wire shape of one layout. ``atlas`` is present and ``null`` rather than
#: omitted: a page that had to tell "no atlas" from "a field the host forgot"
#: would otherwise guess.
ATLAS_INFO: dict[str, Any] = {
    "type": "object",
    "title": "AtlasInfo",
    "properties": {
        "enabled": {"type": "boolean"},
        "coverage_layer": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "filename_expression": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    },
    "required": ["enabled", "coverage_layer", "filename_expression"],
    "additionalProperties": False,
}

LAYOUT_INFO: dict[str, Any] = {
    "type": "object",
    "title": "LayoutInfo",
    "properties": {
        "id": {"type": "string"},
        "name": {"type": "string"},
        "page_count": {"type": "integer", "minimum": 1},
        "atlas": {"anyOf": [ATLAS_INFO, {"type": "null"}]},
    },
    "required": ["id", "name", "page_count", "atlas"],
    "additionalProperties": False,
}

LAYOUT_EXPORT: dict[str, Any] = {
    "type": "object",
    "title": "LayoutExport",
    "properties": {
        "path": {"type": "string"},
        "format": {"enum": sorted(LAYOUT_FORMATS)},
        "pages": {"type": "integer", "minimum": 1},
        "bytes": {"type": "integer", "minimum": 0},
    },
    "required": ["path", "format", "pages", "bytes"],
    "additionalProperties": False,
}

ATLAS_PAGE: dict[str, Any] = {
    "type": "object",
    "title": "AtlasPage",
    "properties": {
        "index": {"type": "integer", "minimum": 1},
        "feature_id": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
        "path": {"type": "string"},
    },
    "required": ["index", "feature_id", "path"],
    "additionalProperties": False,
}

ATLAS_EXPORT: dict[str, Any] = {
    "type": "object",
    "title": "AtlasExport",
    "properties": {
        "directory": {"type": "string"},
        "format": {"enum": sorted(LAYOUT_FORMATS)},
        "pages": {"type": "array", "items": ATLAS_PAGE},
    },
    "required": ["directory", "format", "pages"],
    "additionalProperties": False,
}

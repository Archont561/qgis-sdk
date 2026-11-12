from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ._renderers import COLOUR_SCHEMA, NULLABLE_STRING, NUMBER, RENDERERS
from ._symbols import (
    GRADUATED_MODES,
    MARKER_SHAPES,
    RENDERER_KIND_NAMES,
    STYLE_FORMATS,
    STYLE_MANAGER_KINDS,
)


def _schema(title: str, kind: str, properties: Mapping[str, Any]) -> dict[str, Any]:
    """One wire object: its discriminator first, then its own fields."""
    return {
        "type": "object",
        "title": title,
        "properties": {"kind": {"enum": [kind]}, **properties},
        "required": ["kind", *properties],
        "additionalProperties": False,
    }


MARKER_SYMBOL = _schema(
    "MarkerSymbol",
    "marker",
    {
        "color": COLOUR_SCHEMA,
        "size": NUMBER,
        "shape": {"enum": list(MARKER_SHAPES)},
        "outline_color": COLOUR_SCHEMA,
        "outline_width": NUMBER,
    },
)
LINE_SYMBOL = _schema(
    "LineSymbol",
    "line",
    {"color": COLOUR_SCHEMA, "width": NUMBER},
)
FILL_SYMBOL = _schema(
    "FillSymbol",
    "fill",
    {
        "color": COLOUR_SCHEMA,
        "outline_color": COLOUR_SCHEMA,
        "outline_width": NUMBER,
    },
)
SYMBOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "marker": MARKER_SYMBOL,
    "line": LINE_SYMBOL,
    "fill": FILL_SYMBOL,
}
SYMBOL: dict[str, Any] = {
    "anyOf": [SYMBOL_SCHEMAS[kind] for kind in SYMBOL_SCHEMAS],
}
CATEGORY: dict[str, Any] = {
    "type": "object",
    "title": "Category",
    "properties": {
        "value": {"type": "string"},
        "label": {"type": "string"},
        "symbol": SYMBOL,
    },
    "required": ["value", "label", "symbol"],
    "additionalProperties": False,
}
GRADUATED_CLASS: dict[str, Any] = {
    "type": "object",
    "title": "GraduatedClass",
    "properties": {
        "lower": NUMBER,
        "upper": NUMBER,
        "label": {"type": "string"},
        "symbol": SYMBOL,
    },
    "required": ["lower", "upper", "label", "symbol"],
    "additionalProperties": False,
}
RULE: dict[str, Any] = {
    "type": "object",
    "title": "Rule",
    "properties": {
        "filter": {"type": "string"},
        "label": {"type": "string"},
        "enabled": {"type": "boolean"},
        "symbol": SYMBOL,
    },
    "required": ["filter", "label", "enabled", "symbol"],
    "additionalProperties": False,
}
SINGLE_SYMBOL_RENDERER = _schema(
    "SingleSymbolRenderer", "single_symbol", {"symbol": SYMBOL}
)
CATEGORIZED_RENDERER = _schema(
    "CategorizedRenderer",
    "categorized",
    {"field": {"type": "string"}, "categories": {"type": "array", "items": CATEGORY}},
)
GRADUATED_RENDERER = _schema(
    "GraduatedRenderer",
    "graduated",
    {
        "field": {"type": "string"},
        "mode": {"enum": list(GRADUATED_MODES)},
        "classes": {"type": "array", "items": GRADUATED_CLASS},
    },
)
RULE_BASED_RENDERER = _schema(
    "RuleBasedRenderer", "rule_based", {"rules": {"type": "array", "items": RULE}}
)
RENDERER_SCHEMAS: dict[str, dict[str, Any]] = {
    "single_symbol": SINGLE_SYMBOL_RENDERER,
    "categorized": CATEGORIZED_RENDERER,
    "graduated": GRADUATED_RENDERER,
    "rule_based": RULE_BASED_RENDERER,
}
RENDERER: dict[str, Any] = {
    "anyOf": [RENDERER_SCHEMAS[kind] for kind in RENDERER_SCHEMAS]
}
LABELLING: dict[str, Any] = {
    "type": "object",
    "title": "Labelling",
    "properties": {
        "enabled": {"type": "boolean"},
        "field": NULLABLE_STRING,
        "size": NUMBER,
        "color": COLOUR_SCHEMA,
    },
    "required": ["enabled", "field", "size", "color"],
    "additionalProperties": False,
}
STYLE_ENTRY: dict[str, Any] = {
    "type": "object",
    "title": "StyleEntry",
    "properties": {
        "name": {"type": "string"},
        "kind": {"enum": list(STYLE_MANAGER_KINDS)},
    },
    "required": ["name", "kind"],
    "additionalProperties": False,
}
STYLE_TEXT: dict[str, Any] = {
    "type": "object",
    "title": "StyleText",
    "properties": {
        "format": {"enum": list(STYLE_FORMATS)},
        "text": {"type": "string"},
    },
    "required": ["format", "text"],
    "additionalProperties": False,
}
RENDERER_NAMES: dict[str, str] = {
    kind: str(schema["title"]) for kind, schema in RENDERER_SCHEMAS.items()
}
SYMBOL_NAMES: dict[str, str] = {
    kind: str(schema["title"]) for kind, schema in SYMBOL_SCHEMAS.items()
}
RENDERER_MODELS: tuple[Any, ...] = tuple(
    RENDERERS[kind] for kind in RENDERER_KIND_NAMES
)

"""JSON Schema generation for inputs and results, and the parameter-kind rules."""

from __future__ import annotations

from ._kinds import WIRE_KIND_KEYWORD, resolve_kind
from ._schemas import _schema as _schema
from ._schemas import object_schema, resolve_hints, schema_for
from ._validate import (
    check_field_parents,
    keyword_inputs,
    require_plain_method,
    require_self_first,
)

__all__ = [
    "WIRE_KIND_KEYWORD",
    "check_field_parents",
    "keyword_inputs",
    "object_schema",
    "require_plain_method",
    "require_self_first",
    "resolve_hints",
    "resolve_kind",
    "schema_for",
]

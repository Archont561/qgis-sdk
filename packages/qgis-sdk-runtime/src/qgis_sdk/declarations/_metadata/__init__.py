"""Metadata: ids and titles, derived or given, and how a class or function carries them."""

from __future__ import annotations

from ._declared import declared_metadata
from ._metadata import (
    WIRES_ATTRIBUTE,
    Metadata,
    T,
    attach_describe,
    class_decorator,
    class_metadata,
    declare_class,
    declared_function_metadata,
    derive_id,
    derive_title,
    function_metadata,
    mark_class,
    mark_function,
    metadata,
    method_metadata,
    validate_given,
)

__all__ = [
    "WIRES_ATTRIBUTE",
    "Metadata",
    "T",
    "attach_describe",
    "class_decorator",
    "class_metadata",
    "declare_class",
    "declared_function_metadata",
    "declared_metadata",
    "derive_id",
    "derive_title",
    "function_metadata",
    "mark_class",
    "mark_function",
    "metadata",
    "method_metadata",
    "validate_given",
]

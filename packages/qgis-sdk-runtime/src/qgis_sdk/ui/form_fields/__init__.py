"""Module form_fields_orig."""

from __future__ import annotations

from ._coerce_values import coerce_values
from ._coercion import (
    coerce,
    coerce_value,
    label_for,
)
from ._fields import (
    FieldSpec,
    form_fields,
    schema_fields,
)

__all__ = [
    "FieldSpec",
    "coerce",
    "coerce_value",
    "coerce_values",
    "form_fields",
    "label_for",
    "schema_fields",
]

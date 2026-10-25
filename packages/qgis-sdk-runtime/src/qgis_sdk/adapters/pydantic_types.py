"""Pydantic-specific field annotations for the optional adapter boundary."""

from __future__ import annotations

import math
from typing import Annotated

from qgis_sdk.models import MAX_SAFE_INTEGER, QgisSdkOptionalDependencyError

from ._pydantic_compat import OPTIONAL_PYDANTIC_PROVISIONING_HINT

try:
    from pydantic import BeforeValidator, Field
except ImportError as error:
    raise QgisSdkOptionalDependencyError(
        "pydantic", OPTIONAL_PYDANTIC_PROVISIONING_HINT
    ) from error


def _normalize_integral_safe_number(value: object) -> object:
    """Accept JSON integer values written with an integral floating token."""
    if (
        type(value) is float
        and math.isfinite(value)
        and value.is_integer()
        and abs(value) <= MAX_SAFE_INTEGER
    ):
        return int(value)
    return value


SafeJsonInteger = Annotated[
    int,
    Field(ge=-MAX_SAFE_INTEGER, le=MAX_SAFE_INTEGER),
    BeforeValidator(_normalize_integral_safe_number),
]

__all__ = ["MAX_SAFE_INTEGER", "SafeJsonInteger"]

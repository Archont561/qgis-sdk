"""The numeric check every canvas model makes, in one place."""

from __future__ import annotations

import math
from typing import Any

__all__ = ["is_number"]


def is_number(value: Any) -> bool:
    """Whether ``value`` is a real, finite number (``bool`` is not a number).

    Args:
        value: The value a canvas model was handed.

    Returns:
        Whether it is a number that can be drawn.
    """

    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )

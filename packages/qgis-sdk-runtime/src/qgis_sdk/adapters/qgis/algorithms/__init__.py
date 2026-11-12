"""Module algorithms."""

from __future__ import annotations

from ._native import (
    NativeAlgorithms,
)
from ._wiring import (
    AlgorithmWiring,
    processing,
)

__all__ = [
    "AlgorithmWiring",
    "NativeAlgorithms",
    "processing",
]

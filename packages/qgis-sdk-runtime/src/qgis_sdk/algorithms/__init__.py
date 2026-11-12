"""Module algorithms."""

from __future__ import annotations

from ._declaration import (
    ALGORITHM_ATTRIBUTE,
    CRS_PARAMETER,
    LAYER_PARAMETER,
    METRES_PARAMETER,
    AlgorithmDeclaration,
    AlgorithmDescription,
    describe_algorithm,
    describe_declared_algorithm,
    input_refusal,
    parameter_kind,
)
from ._invocation import (
    invoke,
)

__all__ = [
    "ALGORITHM_ATTRIBUTE",
    "CRS_PARAMETER",
    "LAYER_PARAMETER",
    "METRES_PARAMETER",
    "AlgorithmDeclaration",
    "AlgorithmDescription",
    "describe_algorithm",
    "describe_declared_algorithm",
    "input_refusal",
    "invoke",
    "parameter_kind",
]

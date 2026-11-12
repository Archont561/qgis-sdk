"""Module processing."""

from __future__ import annotations

from ._catalogue import (
    AlgorithmInfo,
    AlgorithmRun,
    Catalogue,
    ProviderInfo,
    output_kind_for,
    output_kinds,
    validate_parameters,
)
from ._runs import (
    RunResult,
    TypedRun,
)
from ._validation_state import (
    DESTINATION_KINDS,
    LAYER_KINDS,
    AlgorithmResult,
    FolderOutput,
    FolderOutputParameter,
    HtmlOutput,
    HtmlOutputParameter,
    MultipleLayers,
    OutputInfo,
    OutputKind,
    ParameterInfo,
)

__all__ = [
    "DESTINATION_KINDS",
    "LAYER_KINDS",
    "AlgorithmInfo",
    "AlgorithmResult",
    "AlgorithmRun",
    "Catalogue",
    "FolderOutput",
    "FolderOutputParameter",
    "HtmlOutput",
    "HtmlOutputParameter",
    "MultipleLayers",
    "OutputInfo",
    "OutputKind",
    "ParameterInfo",
    "ProviderInfo",
    "RunResult",
    "TypedRun",
    "output_kind_for",
    "output_kinds",
    "validate_parameters",
]

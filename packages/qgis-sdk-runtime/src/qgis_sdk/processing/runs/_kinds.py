"""Output kinds and their result classes."""

from __future__ import annotations

from qgis_sdk.models import AlgorithmInfo

__all__ = [
    "DEFAULT_EXTENSIONS",
    "DESTINATION_OUTPUT_KINDS",
    "FILE_OUTPUT_KINDS",
    "MULTI_OUTPUT_KINDS",
    "VECTOR_OUTPUT_KINDS",
    "output_class",
]

#: Output kinds that come back as an owned vector layer.
VECTOR_OUTPUT_KINDS: frozenset[str] = frozenset({"outputVector"})
#: Output kinds that come back as several owned vector layers, in order.
MULTI_OUTPUT_KINDS: frozenset[str] = frozenset({"outputMultilayer"})
#: Output kinds that come back as a file ref (a directory ref for folders).
FILE_OUTPUT_KINDS: frozenset[str] = frozenset(
    {
        "outputRaster",
        "outputFile",
        "outputFolder",
        "outputHtml",
        "outputPointCloud",
        "outputVectorTile",
    }
)
#: The output kind a model's destination parameter exposes, for the run's
#: conversion: a sink is a vector file, a folder is a directory, and every
#: other destination is a file.
DESTINATION_OUTPUT_KINDS: dict[str, str] = {
    "sink": "outputVector",
    "vectorDestination": "outputVector",
    "folderDestination": "outputFolder",
}

#: Extension per destination kind when the registry names none.
DEFAULT_EXTENSIONS: dict[str, str] = {
    "sink": "gpkg",
    "vectorDestination": "gpkg",
    "rasterDestination": "tif",
    "pointCloudDestination": "las",
    "vectorTileDestination": "mbtiles",
    "fileDestination": "out",
}


def _output_kind_class(kind: str) -> str:
    """The result class a declared output kind produces."""
    if kind in VECTOR_OUTPUT_KINDS:
        return "vector"
    if kind in MULTI_OUTPUT_KINDS:
        return "layers"
    if kind == "outputFolder":
        return "directory"
    if kind in FILE_OUTPUT_KINDS:
        return "file"
    return "value"


def _destination_class(kind: str) -> str:
    """The result class a declared destination parameter produces."""
    if kind in ("sink", "vectorDestination"):
        return "vector"
    if kind == "folderDestination":
        return "directory"
    return "file"


def output_class(info: AlgorithmInfo, name: str) -> str:
    """``vector``, ``layers``, ``file``, ``directory`` or ``value`` for one
    output name."""
    for output in info.outputs:
        if output.name == name:
            return _output_kind_class(output.kind)
    parameter = info.parameter(name)
    if parameter is not None and parameter.destination:
        return _destination_class(parameter.kind)
    return "value"

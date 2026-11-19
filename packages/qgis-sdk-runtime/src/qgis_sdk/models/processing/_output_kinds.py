"""The result kinds a declared output may name, and how a run reports each one."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Annotated, Any, get_args, get_origin

from qgis_sdk.models.files import FileRef
from qgis_sdk.models.layers import RasterLayerInfo, VectorLayerInfo

from ._validation_state import (
    FolderOutputParameter,
    HtmlOutputParameter,
    MultipleLayers,
    OutputKind,
)

__all__ = ["output_kind_for", "output_kinds"]


_OUTPUT_KINDS: tuple[OutputKind, ...] = (
    OutputKind(
        "outputVector",
        None,
        (VectorLayerInfo,),
        "QgsProcessingOutputVectorLayer",
        "the VectorLayerInfo of the layer it produced",
        (VectorLayerInfo,),
    ),
    OutputKind(
        "outputRaster",
        None,
        (RasterLayerInfo,),
        "QgsProcessingOutputRasterLayer",
        "the RasterLayerInfo of the raster it produced",
        (RasterLayerInfo,),
    ),
    OutputKind(
        "outputFile",
        None,
        (FileRef,),
        "QgsProcessingOutputFile",
        "the FileRef of the file it produced",
        (FileRef,),
    ),
    OutputKind(
        "outputFolder",
        FolderOutputParameter,
        (FileRef,),
        "QgsProcessingOutputFolder",
        "the FolderOutput ref of the folder it produced",
        (FileRef,),
    ),
    OutputKind(
        "outputNumber",
        None,
        (int, float),
        "QgsProcessingOutputNumber",
        "the number it produced",
        (int, float),
    ),
    OutputKind(
        "outputString",
        None,
        (str,),
        "QgsProcessingOutputString",
        "the string it produced",
        (str,),
    ),
    OutputKind(
        "outputBoolean",
        None,
        (bool,),
        "QgsProcessingOutputBoolean",
        "the boolean it produced",
        (bool,),
    ),
    OutputKind(
        "outputHtml",
        HtmlOutputParameter,
        (FileRef,),
        "QgsProcessingOutputHtml",
        "the HtmlOutput ref of the report it produced",
        (FileRef,),
    ),
    OutputKind(
        "outputMultilayer",
        None,
        (MultipleLayers,),
        "QgsProcessingOutputMultipleLayers",
        "the MultipleLayers it produced",
        (tuple,),
    ),
)


def output_kinds() -> Mapping[str, OutputKind]:
    """Every declared result kind, by its QGIS output type id."""
    return MappingProxyType({kind.name: kind for kind in _OUTPUT_KINDS})


def output_kind_for(annotation: Any) -> OutputKind | None:
    """The kind one declared result annotation names, or ``None``.

    A plain stored type names its kind directly (``VectorLayerInfo``,
    ``FileRef``, a scalar, ``MultipleLayers``); the two ``FileRef`` collisions
    are spelled as markers (``FolderOutput``, ``HtmlOutput``).

    Args:
        annotation: The declared result annotation.
    """
    base = annotation
    markers: tuple[Any, ...] = ()
    if get_origin(annotation) is Annotated:
        base, *markers = get_args(annotation)
    for kind in _OUTPUT_KINDS:
        if kind.marker is not None and any(
            isinstance(marker, kind.marker) for marker in markers
        ):
            return kind
    for kind in _OUTPUT_KINDS:
        if kind.marker is None and any(
            base is stored or base == stored for stored in kind.stored
        ):
            return kind
    return None

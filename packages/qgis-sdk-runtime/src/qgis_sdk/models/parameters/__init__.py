"""Markers that say what an input *means* to a host, not what it stores.

An annotation already carries a type, and the type is enough to render a text
box or a spin box. It is not enough to render the right *widget*: a ``str`` may
be free text or a vector layer the user picks from the canvas, and a ``float``
may be an arbitrary number or a distance whose unit the host should show. The
markers ride along in ``Annotated`` metadata so the wire schema keeps describing
the stored value while the host learns the intent.

The usual spelling is the alias (decision-42): ``layer: LayerInput``,
``crs: CrsInput``, ``distance: Metres``, ``source: FileInput(filters=(\"*.gpkg\",))``,
``folder: DirectoryInput()``, ``attribute: FieldInput(of=\"layer\")``,
``weight: Range(0.0, 1.0)``, ``fill: Colour()``, ``mode: Literal[\"fast\", \"safe\"]``.
The explicit form stays available for a reader who wants to see the stored
type - ``Annotated[float, MetresParameter(minimum=1.0)]`` - and describes
identically.

A kind is complete across hosts or it does not exist (decision-46 point 1):\n:class:`ParameterKind` names, for each kind, the marker, the stored types, the
widget family ``qgis_sdk.ui`` draws, the Processing parameter the provider
adapter builds and the value a handler receives. :func:`parameter_kinds` is the
one table every describer and adapter reads, so a kind missing a face is a
test failure here, never a surprise in a host.

The markers are plain frozen values: equality is by type and attributes, so a
test can assert which marker a parameter carries without importing QGIS.
"""

from __future__ import annotations

from ._kinds import ParameterKind, parameter_kinds
from ._markers import (
    COLOUR_PATTERN,
    LAYER_KINDS_FOR_INPUT,
    AnnotationInput,
    AnyLayerInput,
    Colour,
    ColourParameter,
    CrsInput,
    CrsParameter,
    DirectoryInput,
    DirectoryParameter,
    FieldInput,
    FieldParameter,
    FileInput,
    FileParameter,
    LayerInput,
    LayerParameter,
    MeshInput,
    Metres,
    MetresParameter,
    PointCloudInput,
    Range,
    RangeParameter,
    RasterInput,
    TiledSceneInput,
    VectorTileInput,
)

__all__ = [
    "COLOUR_PATTERN",
    "LAYER_KINDS_FOR_INPUT",
    "AnnotationInput",
    "AnyLayerInput",
    "Colour",
    "ColourParameter",
    "CrsInput",
    "CrsParameter",
    "DirectoryInput",
    "DirectoryParameter",
    "FieldInput",
    "FieldParameter",
    "FileInput",
    "FileParameter",
    "LayerInput",
    "LayerParameter",
    "MeshInput",
    "Metres",
    "MetresParameter",
    "ParameterKind",
    "PointCloudInput",
    "Range",
    "RangeParameter",
    "RasterInput",
    "TiledSceneInput",
    "VectorTileInput",
    "parameter_kinds",
]

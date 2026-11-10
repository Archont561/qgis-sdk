"""A declared parameter kind, turned into the widget the toolbox shows.

Every input was already mapped to a kind when the provider declared it
(``qgis_sdk.algorithms``), so this module only has to translate a kind into a
``QgsProcessingParameter``: the class the kind registry names, plus whatever
extra a particular kind needs on top - the layer a field belongs to, the filter
a file picker shows, the bounds of a range. An input that could not be mapped
never reached here, which is why there is no fallback widget.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any, get_args, get_origin

from qgis.core import (
    Qgis,
    QgsProcessingParameterFile,
    QgsProcessingParameterMapLayer,
    QgsProcessingParameterNumber,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterVectorLayer,
)

from qgis_sdk.algorithms import CRS_PARAMETER, LAYER_PARAMETER, METRES_PARAMETER
from qgis_sdk.declarations import QgisSdkDeclarationError
from qgis_sdk.models import (
    ColourParameter,
    FieldParameter,
    FileParameter,
    LayerParameter,
    MetresParameter,
    RangeParameter,
    parameter_kinds,
)

from ._tables import _LAYER_SOURCE_TYPES, _PARAMETER_CLASSES


def _marker(annotation: Any, marker_type: type) -> Any:
    """The marker of this type on an input's annotation, or ``None``."""
    if get_origin(annotation) is not Annotated:
        return None
    return next(
        (m for m in get_args(annotation)[1:] if isinstance(m, marker_type)), None
    )


def _number_type(bounds: RangeParameter) -> Any:
    """An integer range stays an integer spin box; anything else is a double."""
    integral = isinstance(bounds.minimum, int) and isinstance(bounds.maximum, int)
    return (
        QgsProcessingParameterNumber.Integer
        if integral
        else QgsProcessingParameterNumber.Double
    )


def _build_layer(cls: type, name: str, annotation: Any) -> Any:
    """A layer input names its kind, and the kind decides what the toolbox offers.

    A dedicated class where Processing has one, a map-layer parameter narrowed to
    that kind's source type where it does not - never a filter the parameter can
    ignore.
    """
    wanted = (_marker(annotation, LayerParameter) or LayerParameter()).kind
    if wanted == "vector":
        return QgsProcessingParameterVectorLayer(name, name)
    if wanted == "raster":
        return QgsProcessingParameterRasterLayer(name, name)
    parameter = QgsProcessingParameterMapLayer(name, name)
    source_type = _LAYER_SOURCE_TYPES.get(wanted)
    if source_type is not None:
        parameter.setDataTypes([getattr(Qgis.ProcessingSourceType, source_type)])
    return parameter


def _build_metres(cls: type, name: str, annotation: Any) -> Any:
    """A metre input is a double that says so, bounded by what the marker allows."""
    metres = _marker(annotation, MetresParameter) or MetresParameter()
    parameter = cls(
        name,
        f"{name} (metres)",
        type=QgsProcessingParameterNumber.Double,
        minValue=metres.minimum,
    )
    if metres.maximum is not None:
        parameter.setMaximum(metres.maximum)
    return parameter


def _build_file(cls: type, name: str, annotation: Any) -> Any:
    filters = (_marker(annotation, FileParameter) or FileParameter()).filters
    return cls(
        name,
        name,
        behavior=QgsProcessingParameterFile.Behavior.File,
        fileFilter=";;".join(_qt_filter(glob) for glob in filters),
    )


def _build_directory(cls: type, name: str, annotation: Any) -> Any:
    return cls(name, name, behavior=QgsProcessingParameterFile.Behavior.Folder)


def _build_field(cls: type, name: str, annotation: Any) -> Any:
    return cls(
        name, name, parentLayerParameterName=_marker(annotation, FieldParameter).of
    )


def _build_range(cls: type, name: str, annotation: Any) -> Any:
    bounds = _marker(annotation, RangeParameter)
    return cls(
        name,
        name,
        type=_number_type(bounds),
        minValue=bounds.minimum,
        maxValue=bounds.maximum,
    )


def _build_colour(cls: type, name: str, annotation: Any) -> Any:
    """A colour input offers opacity only when the kind stores an alpha channel."""
    colour = _marker(annotation, ColourParameter) or ColourParameter()
    return cls(name, name, opacityEnabled=colour.alpha)


def _build_enum(cls: type, name: str, annotation: Any) -> Any:
    return cls(name, name, options=list(get_args(annotation)))


def _build_integer(cls: type, name: str, annotation: Any) -> Any:
    return cls(name, name, type=QgsProcessingParameterNumber.Integer)


def _build_number(cls: type, name: str, annotation: Any) -> Any:
    return cls(name, name, type=QgsProcessingParameterNumber.Double)


def _build_plain(cls: type, name: str, annotation: Any) -> Any:
    """A kind whose parameter takes nothing beyond its class and its label."""
    return cls(name, name)


#: What each declared kind adds to the class the kind registry names. The plain
#: kinds share `_build_plain`, so this table names thirteen kinds in ten rows.
_BUILDERS: dict[str, Callable[[type, str, Any], Any]] = {
    LAYER_PARAMETER: _build_layer,
    METRES_PARAMETER: _build_metres,
    CRS_PARAMETER: _build_plain,
    "file": _build_file,
    "directory": _build_directory,
    "field": _build_field,
    "range": _build_range,
    "colour": _build_colour,
    "enum": _build_enum,
    "string": _build_plain,
    "integer": _build_integer,
    "number": _build_number,
    "boolean": _build_plain,
}


def _parameter(kind: str, name: str, annotation: Any = None) -> Any:
    """Build the Processing parameter a declared kind deserves."""
    build = _BUILDERS.get(kind)
    if build is None:
        raise QgisSdkDeclarationError(f"unsupported parameter kind {kind!r}")
    return build(
        _PARAMETER_CLASSES[parameter_kinds()[kind].processing], name, annotation
    )


def _qt_filter(glob: str) -> str:
    """Spell one author glob the way a Qt file dialog lists it: ``CSV (*.csv)``."""
    stem, dot, extension = glob.rpartition(".")
    label = extension.upper() if stem == "*" and dot else glob
    return f"{label} ({glob})"

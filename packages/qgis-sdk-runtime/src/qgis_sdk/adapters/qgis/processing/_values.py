"""A value the dialog holds, read back as the keyword the handler expects.

The other half of `_parameters`: that module turns a declaration into a widget,
this one turns the widget's value into the typed input the author's function
was declared with. A file or directory picked in the dialog is a native picker
result, so it is granted through the host authority (decision-20) and the
handler receives the ``FileRef``, never the path the dialog held.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, get_args

from qgis.core import Qgis, QgsProcessingContext, QgsProcessingException
from qgis.PyQt.QtGui import QColor

from qgis_sdk.algorithms import (
    CRS_PARAMETER,
    LAYER_PARAMETER,
    METRES_PARAMETER,
    AlgorithmDescription,
)
from qgis_sdk.bridge.authority import FilePolicy
from qgis_sdk.declarations import QgisSdkDeclarationError
from qgis_sdk.models import ColourParameter, LayerParameter, RangeParameter

from ._parameters import _marker
from ._services import rasters_of


@dataclass(frozen=True, slots=True)
class _Picked:
    """One dialog value, the declaration that says how to read it, and the run it belongs to."""

    algorithm: Any
    bridge: Any
    description: AlgorithmDescription
    name: str
    kind: str
    parameters: dict
    context: QgsProcessingContext
    #: Refs minted for this run, revoked when it ends.
    minted: list[str]

    @property
    def annotation(self) -> Any:
        """What the input was annotated with, which is what its readers inspect."""
        return self.description.annotations[self.name]


def _read_text(picked: _Picked) -> str:
    return picked.algorithm.parameterAsString(
        picked.parameters, picked.name, picked.context
    )


def _read_integer(picked: _Picked) -> int:
    return picked.algorithm.parameterAsInt(
        picked.parameters, picked.name, picked.context
    )


def _read_number(picked: _Picked) -> float:
    return picked.algorithm.parameterAsDouble(
        picked.parameters, picked.name, picked.context
    )


def _read_boolean(picked: _Picked) -> bool:
    return picked.algorithm.parameterAsBool(
        picked.parameters, picked.name, picked.context
    )


def _read_crs(picked: _Picked) -> str:
    return picked.algorithm.parameterAsCrs(
        picked.parameters, picked.name, picked.context
    ).authid()


def _read_range(picked: _Picked) -> Any:
    """An integer range is read as an integer; anything else as a double."""
    bounds = _marker(picked.annotation, RangeParameter)
    integral = isinstance(bounds.minimum, int) and isinstance(bounds.maximum, int)
    return _read_integer(picked) if integral else _read_number(picked)


def _hex_rgba(colour: QColor, *, alpha: bool) -> str:
    """Spell a QColor the way the colour kind stores it: ``#RRGGBBAA``."""
    rgb = colour.name(QColor.NameFormat.HexRgb)
    return f"{rgb}{colour.alpha():02x}" if alpha else rgb


def _read_colour(picked: _Picked) -> str:
    """The colour kind stores its value as text, opaque unless the marker says otherwise."""
    declared = _marker(picked.annotation, ColourParameter)
    colour = picked.algorithm.parameterAsColor(
        picked.parameters, picked.name, picked.context
    )
    return _hex_rgba(colour, alpha=declared is None or declared.alpha)


def _read_enum(picked: _Picked) -> Any:
    """An enum value is the selected option, not the index the dialog stores."""
    chosen = picked.algorithm.parameterAsEnum(
        picked.parameters, picked.name, picked.context
    )
    return get_args(picked.annotation)[chosen]


def _picked_path(picked: _Picked) -> str:
    """The path the dialog holds, refused by name when the author left it empty."""
    path = picked.algorithm.parameterAsFile(
        picked.parameters, picked.name, picked.context
    )
    if not path:
        raise QgsProcessingException(f"{picked.name} requires a {picked.kind}")
    return path


def _read_file(picked: _Picked) -> Any:
    """Grant the picked file, so the handler receives the ref and not the path."""
    ref = picked.bridge.authority.grant_file(
        picked.bridge.binding, _picked_path(picked), FilePolicy(source="picker")
    )
    picked.minted.append(ref.id)
    return ref


def _read_directory(picked: _Picked) -> Any:
    """Grant the picked folder, so the handler receives the ref and not the path."""
    ref = picked.bridge.authority.grant_directory(
        picked.bridge.binding, _picked_path(picked), source="picker"
    )
    picked.minted.append(ref.id)
    return ref


def _opened_raster(picked: _Picked) -> str:
    raster = picked.algorithm.parameterAsRasterLayer(
        picked.parameters, picked.name, picked.context
    )
    if raster is None:
        raise QgsProcessingException(f"{picked.name} requires a raster layer")
    return rasters_of(picked.bridge).open_raster(Path(raster.source())).id


def _opened_vector(picked: _Picked) -> str:
    layer = picked.algorithm.parameterAsVectorLayer(
        picked.parameters, picked.name, picked.context
    )
    if layer is None:
        raise QgsProcessingException(f"{picked.name} requires a vector layer")
    return picked.bridge.layers.open_vector(Path(layer.source())).id


def _opened_either(picked: _Picked) -> str:
    """One parameter class lists both kinds, so the picked layer's type decides."""
    layer = picked.algorithm.parameterAsMapLayer(
        picked.parameters, picked.name, picked.context
    )
    if layer is None:
        raise QgsProcessingException(f"{picked.name} requires a map layer")
    if layer.type() == Qgis.LayerType.Raster:
        return rasters_of(picked.bridge).open_raster(Path(layer.source())).id
    return picked.bridge.layers.open_vector(Path(layer.source())).id


def _read_layer(picked: _Picked) -> str:
    """Re-open the picked layer through the service that owns that kind.

    The SDK owns the layers it opened, so the picked layer is re-opened through
    the same service the rest of the bridge uses - the raster service when the
    input asked for a raster.
    """
    wanted = (_marker(picked.annotation, LayerParameter) or LayerParameter()).kind
    if wanted == "raster":
        return _opened_raster(picked)
    if wanted == "any":
        return _opened_either(picked)
    return _opened_vector(picked)


#: How a value of each declared kind is read back out of the dialog. Kinds that
#: share a reading share a row: a field and a string are both text, and a
#: distance and a number are both doubles.
_READERS: dict[str, Callable[[_Picked], Any]] = {
    "file": _read_file,
    "directory": _read_directory,
    "field": _read_text,
    "range": _read_range,
    "colour": _read_colour,
    "enum": _read_enum,
    LAYER_PARAMETER: _read_layer,
    METRES_PARAMETER: _read_number,
    CRS_PARAMETER: _read_crs,
    "string": _read_text,
    "integer": _read_integer,
    "number": _read_number,
    "boolean": _read_boolean,
}


def read(picked: _Picked) -> Any:
    """Read one dialog value the way its declared kind is spelled."""
    reader = _READERS.get(picked.kind)
    if reader is None:
        raise QgisSdkDeclarationError(f"unsupported parameter kind {picked.kind!r}")
    return reader(picked)


def values_of(
    algorithm: Any,
    description: AlgorithmDescription,
    parameters: dict,
    context: QgsProcessingContext,
    minted: list[str],
) -> dict:
    """Turn every value the dialog holds into the keyword the handler receives."""
    return {
        name: read(
            _Picked(
                algorithm,
                algorithm.bridge,
                description,
                name,
                kind,
                parameters,
                context,
                minted,
            )
        )
        for name, kind in description.kinds.items()
    }

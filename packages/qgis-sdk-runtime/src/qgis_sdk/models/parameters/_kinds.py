"""The kinds table: one row per input kind, with the face it shows each host.

A kind is complete across hosts or it does not exist (decision-46 point 1):
:class:`ParameterKind` names, for each kind, the marker, the stored types, the
widget family ``qgis_sdk.ui`` draws, the Processing parameter the provider
adapter builds and the value a handler receives. :func:`parameter_kinds` is the
one table every describer and adapter reads, so a kind missing a face is a
test failure here, never a surprise in a host.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from qgis_sdk.models.files import FileRef

from ._markers import (
    ColourParameter,
    CrsParameter,
    DirectoryParameter,
    FieldParameter,
    FileParameter,
    LayerParameter,
    MetresParameter,
    RangeParameter,
)

__all__ = ["ParameterKind", "parameter_kinds"]


@dataclass(frozen=True, slots=True)
class ParameterKind:
    """One kind, with the face it shows to each host.

    ``marker`` is the ``Annotated`` extra that selects the kind (``None`` for
    the primitives and for ``enum``, which ``Literal`` selects); ``stored`` the
    annotation bases the marker fits; ``widget`` the family ``qgis_sdk.ui``
    draws; ``processing`` the ``QgsProcessingParameter*`` class the provider
    adapter builds; ``expected`` and ``accepted`` what a handler receives,
    spelled for a refusal and for ``isinstance``.
    """

    name: str
    marker: type | None
    stored: tuple[Any, ...]
    widget: str
    processing: str
    expected: str
    accepted: tuple[type, ...]
    refusal: str = field(default="")

    def annotation(self, marker: Any) -> dict[str, Any]:
        """The ``x-qgis-sdk`` object the describer puts on the wire."""
        payload: dict[str, Any] = {"kind": self.name}
        if isinstance(marker, FileParameter) and marker.filters:
            payload["filters"] = list(marker.filters)
        if isinstance(marker, FieldParameter):
            payload["of"] = marker.of
        if isinstance(marker, RangeParameter) and marker.step is not None:
            payload["step"] = marker.step
        if isinstance(marker, ColourParameter) and not marker.alpha:
            payload["alpha"] = False
        if isinstance(marker, LayerParameter) and marker.kind != "vector":
            payload["layer_kind"] = marker.kind
        return payload


_KINDS: tuple[ParameterKind, ...] = (
    ParameterKind(
        "layer",
        LayerParameter,
        (str,),
        widget="layer",
        processing="QgsProcessingParameterVectorLayer",
        expected="a str layer id",
        accepted=(str,),
        refusal="a layer input must be a str layer id",
    ),
    ParameterKind(
        "crs",
        CrsParameter,
        (str,),
        widget="crs",
        processing="QgsProcessingParameterCrs",
        expected="a str authority code",
        accepted=(str,),
        refusal="a CRS input must be a str authority code",
    ),
    ParameterKind(
        "metres",
        MetresParameter,
        (float, int),
        widget="metres",
        processing="QgsProcessingParameterNumber",
        expected="a number of metres",
        accepted=(int, float),
        refusal="a metres input must be a number",
    ),
    ParameterKind(
        "file",
        FileParameter,
        (FileRef,),
        widget="file",
        processing="QgsProcessingParameterFile",
        expected="a FileRef",
        accepted=(FileRef,),
        refusal="a file input stores a FileRef: use FileInput(filters=...)",
    ),
    ParameterKind(
        "directory",
        DirectoryParameter,
        (FileRef,),
        widget="directory",
        processing="QgsProcessingParameterFile",
        expected="a directory FileRef",
        accepted=(FileRef,),
        refusal="a directory input stores a FileRef: use DirectoryInput()",
    ),
    ParameterKind(
        "field",
        FieldParameter,
        (str,),
        widget="field",
        processing="QgsProcessingParameterField",
        expected="a str field name",
        accepted=(str,),
        refusal="a field input must be a str field name",
    ),
    ParameterKind(
        "range",
        RangeParameter,
        (float, int),
        widget="range",
        processing="QgsProcessingParameterNumber",
        expected="a number within the range",
        accepted=(int, float),
        refusal="a range must be a number",
    ),
    ParameterKind(
        "colour",
        ColourParameter,
        (str,),
        widget="colour",
        processing="QgsProcessingParameterColor",
        expected="a #RRGGBB or #RRGGBBAA colour",
        accepted=(str,),
        refusal="a colour input must be a str",
    ),
    ParameterKind(
        "enum",
        None,
        (),
        widget="choice",
        processing="QgsProcessingParameterEnum",
        expected="one of the choices",
        accepted=(str,),
    ),
    ParameterKind(
        "string",
        None,
        (str,),
        widget="text",
        processing="QgsProcessingParameterString",
        expected="a str",
        accepted=(str,),
    ),
    ParameterKind(
        "integer",
        None,
        (int,),
        widget="integer",
        processing="QgsProcessingParameterNumber",
        expected="an int",
        accepted=(int,),
    ),
    ParameterKind(
        "number",
        None,
        (float,),
        widget="number",
        processing="QgsProcessingParameterNumber",
        expected="a number",
        accepted=(int, float),
    ),
    ParameterKind(
        "boolean",
        None,
        (bool,),
        widget="boolean",
        processing="QgsProcessingParameterBoolean",
        expected="a bool",
        accepted=(bool,),
    ),
)

_BY_NAME: Mapping[str, ParameterKind] = MappingProxyType({k.name: k for k in _KINDS})


def parameter_kinds() -> Mapping[str, ParameterKind]:
    """Every kind in registry order, read-only; markers first, primitives last."""
    return _BY_NAME

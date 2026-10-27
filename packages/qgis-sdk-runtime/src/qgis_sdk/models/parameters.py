"""Markers that say what an input *means* to a host, not what it stores.

An annotation already carries a type, and the type is enough to render a text
box or a spin box. It is not enough to render the right *widget*: a ``str`` may
be free text or a vector layer the user picks from the canvas, and a ``float``
may be an arbitrary number or a distance whose unit the host should show. The
markers ride along in ``Annotated`` metadata so the wire schema keeps describing
the stored value while the host learns the intent.

The usual spelling is the alias (decision-42): ``layer: LayerInput``,
``crs: CrsInput``, ``distance: Metres``, ``source: FileInput(filters=("*.gpkg",))``,
``folder: DirectoryInput()``, ``attribute: FieldInput(of="layer")``,
``weight: Range(0.0, 1.0)``, ``fill: Colour()``, ``mode: Literal["fast", "safe"]``.
The explicit form stays available for a reader who wants to see the stored
type - ``Annotated[float, MetresParameter(minimum=1.0)]`` - and describes
identically.

A kind is complete across hosts or it does not exist (decision-46 point 1):
:class:`ParameterKind` names, for each kind, the marker, the stored types, the
widget family ``qgis_sdk.ui`` draws, the Processing parameter the provider
adapter builds and the value a handler receives. :func:`parameter_kinds` is the
one table every describer and adapter reads, so a kind missing a face is a
test failure here, never a surprise in a host.

The markers are plain frozen values: equality is by type and attributes, so a
test can assert which marker a parameter carries without importing QGIS.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Annotated, Any

from .files import FileRef

__all__ = [
    "COLOUR_PATTERN",
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
    "Metres",
    "MetresParameter",
    "ParameterKind",
    "Range",
    "RangeParameter",
    "parameter_kinds",
]

#: ``#RRGGBB`` or ``#RRGGBBAA``, the one colour spelling every host reads back.
COLOUR_PATTERN = re.compile(r"\A#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?\Z")


@dataclass(frozen=True, slots=True)
class LayerParameter:
    """The input receives a vector layer chosen by the user."""


@dataclass(frozen=True, slots=True)
class CrsParameter:
    """The input receives a coordinate reference system chosen by the user."""


@dataclass(frozen=True, slots=True)
class MetresParameter:
    """The input is a distance in metres, so the host may label and bound it."""

    minimum: float = 0.0
    maximum: float | None = None


@dataclass(frozen=True, slots=True)
class FileParameter:
    """The input is one existing file the user picked; the handler gets a ref.

    ``filters`` are globs (``*.gpkg``) in the order the picker offers them.
    """

    filters: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        filters = tuple(self.filters)
        for pattern in filters:
            if not isinstance(pattern, str) or "*" not in pattern:
                raise ValueError(
                    f"a file filter is a glob such as '*.gpkg', not {pattern!r}"
                )
        object.__setattr__(self, "filters", filters)


@dataclass(frozen=True, slots=True)
class DirectoryParameter:
    """The input is an existing directory the user picked; the handler gets a ref."""


@dataclass(frozen=True, slots=True)
class FieldParameter:
    """The input is an attribute field of the layer input named by ``of``."""

    of: str

    def __post_init__(self) -> None:
        if not isinstance(self.of, str) or not self.of.isidentifier():
            raise ValueError(
                "a field input names the layer input it belongs to: of='layer'"
            )


@dataclass(frozen=True, slots=True)
class RangeParameter:
    """The input is a number the host bounds between ``minimum`` and ``maximum``."""

    minimum: float
    maximum: float
    step: float | None = None

    def __post_init__(self) -> None:
        if not (self.minimum < self.maximum):
            raise ValueError(
                f"a range puts its minimum {self.minimum!r} below its maximum "
                f"{self.maximum!r}"
            )
        if self.step is not None and not (self.step > 0):
            raise ValueError("a step is positive")


@dataclass(frozen=True, slots=True)
class ColourParameter:
    """The input is a colour, stored as ``#RRGGBB`` or ``#RRGGBBAA``."""

    alpha: bool = True


LayerInput = Annotated[str, LayerParameter()]
"""A vector layer id the host fills from a layer picker."""

CrsInput = Annotated[str, CrsParameter()]
"""An authority code (``EPSG:3857``) the host fills from a CRS picker."""

Metres = Annotated[float, MetresParameter()]
"""A distance in metres, labelled as such and bounded at zero by the host."""


def FileInput(*, filters: Iterable[str] = ()) -> Any:
    """One existing file, offered through ``filters``; the handler gets a FileRef."""
    return Annotated[FileRef, FileParameter(filters=tuple(filters))]


def DirectoryInput() -> Any:
    """One existing directory; the handler gets a directory FileRef."""
    return Annotated[FileRef, DirectoryParameter()]


def FieldInput(*, of: str) -> Any:
    """An attribute field name of the layer input called ``of``."""
    return Annotated[str, FieldParameter(of=of)]


def Range(minimum: float, maximum: float, *, step: float | None = None) -> Any:
    """A number between ``minimum`` and ``maximum``; ints stay ints."""
    stored = int if isinstance(minimum, int) and isinstance(maximum, int) else float
    return Annotated[
        stored, RangeParameter(minimum=minimum, maximum=maximum, step=step)
    ]


def Colour(*, alpha: bool = True) -> Any:
    """A colour the host picks with its colour button, stored as hex."""
    return Annotated[str, ColourParameter(alpha=alpha)]


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

"""The Processing catalogue and the generic run (decision-64).

QGIS describes every algorithm its registry holds: parameters with a type id,
a label, a default, options; outputs with a type id. These models are that
description with the QGIS objects removed, so the same catalogue can be read
by the native adapter, shipped as a snapshot, emitted as typed modules and
sent over the bridge. ``kind`` values are QGIS's own type ids (``source``,
``sink``, ``number``, ``outputVector`` ...) rather than an SDK vocabulary:
the catalogue must describe a provider the SDK has never seen.

Three request and result shapes live here too:

* :class:`AlgorithmRun` - an algorithm id and a parameter mapping, the
  ``processing.run`` shape a generated ``TypedDict`` types.
* :class:`TypedRun` - the base of the generated request classes
  (``native.Buffer(input=..., distance=...)``), which carry the QGIS names of
  their fields and turn into an :class:`AlgorithmRun`.
* :class:`RunResult` - what a run produced, by output name: an owned vector
  layer, a file ref for everything on disk the SDK cannot open as a layer
  yet, or a scalar.

:func:`validate_parameters` is the one validation applied before any data is
read, in the fake and in the native adapter alike.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields
from typing import Annotated, Any

from qgis_sdk.models.errors import (
    QgisSdkAlgorithmRejectedError,
)
from qgis_sdk.models.files import FileRef
from qgis_sdk.models.layers import RasterLayerInfo, VectorLayerInfo


def is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


class CcState:
    """A mutable record shared by the phases of one long function."""

    def __init__(_cc_self, **values):
        _cc_self.__dict__.update(values)


class CcReturn:
    """An early return travelling out of a phase."""

    def __init__(_cc_self, value):
        _cc_self.value = value


class _CcBreak:
    """A loop break travelling out of a phase."""


class _CcContinue:
    """A loop continue travelling out of a phase."""


def _cc_validate_paramet_p1(_s):
    _s.reasons.append(f"{_s.parameter.name} must be a boolean")


def _cc_validate_paramet_p2(_s):
    _s.reasons.append(f"{_s.parameter.name} must be a number")


def _cc_validate_paramet_p3(_s):
    _s.choices = (
        _s.value if _s.parameter.multiple and isinstance(_s.value, list) else [_s.value]
    )


def _cc_validate_paramet_p4(_s):
    for choice in _s.choices:
        _s.choice = choice
        _s.valid = (
            isinstance(_s.choice, int)
            and not isinstance(_s.choice, bool)
            and 0 <= _s.choice < len(_s.parameter.options)
        ) or (isinstance(_s.choice, str) and _s.choice in _s.parameter.options)
        if not _s.valid:
            _s.reasons.append(
                f"{_s.parameter.name} must be one of "
                f"{', '.join(_s.parameter.options)} (or its index)"
            )
            break


def _cc_validate_paramet_p5(_s):
    _s.value = _s.params.get(_s.parameter.name)
    if _s.value is None:
        # Absent and explicit None are the same thing: not given.
        if _s.parameter.required:
            _s.reasons.append(f"{_s.parameter.name} is required")
        return _CcContinue()
    _s.kind = _s.parameter.kind


_CC_KIND_CHECKS = (
    (
        lambda state: state.kind == "boolean" and not isinstance(state.value, bool),
        (_cc_validate_paramet_p1,),
    ),
    (
        lambda state: state.kind in _NUMBER_KINDS and not is_number(state.value),
        (_cc_validate_paramet_p2,),
    ),
    (
        lambda state: state.kind == "enum" and state.parameter.options,
        (_cc_validate_paramet_p3, _cc_validate_paramet_p4),
    ),
)


def _cc_validate_paramet_p6(_s):
    """Run the checker for the value's kind, chosen from a dispatch table."""
    for matches, phases in _CC_KIND_CHECKS:
        if matches(_s):
            for phase in phases:
                result = phase(_s)
                if isinstance(result, CcReturn):
                    return result
            break
    return None


def cc_validate_paramet_p7(_s):
    _s.reasons: list[str] = []
    for name in _s.params:
        _s.name = name
        if _s.info.parameter(_s.name) is None:
            _s.reasons.append(f"{_s.name} is not a parameter of {_s.info.id}")


def cc_validate_paramet_p8(_s):
    for parameter in _s.info.parameters:
        _s.parameter = parameter
        _a = None
        for _p in (_cc_validate_paramet_p5, _cc_validate_paramet_p6):
            _r = _p(_s)
            if isinstance(_r, CcReturn):
                return _r
            if isinstance(_r, (_CcBreak, _CcContinue)):
                _a = _r
                break
        if isinstance(_a, _CcBreak):
            break
        if isinstance(_a, _CcContinue):
            continue


def cc_validate_paramet_p9(_s):
    if _s.reasons:
        raise QgisSdkAlgorithmRejectedError(_s.info.id, _s.reasons)


DESTINATION_KINDS: tuple[str, ...] = (
    "sink",
    "vectorDestination",
    "rasterDestination",
    "fileDestination",
    "folderDestination",
    "pointCloudDestination",
    "vectorTileDestination",
)
LAYER_KINDS: tuple[str, ...] = (
    "source",
    "raster",
    "vector",
    "layer",
    "mesh",
    "pointcloud",
)
_NUMBER_KINDS = frozenset({"number", "distance", "area", "scale", "duration", "band"})
_JSON_SCALARS = (str, int, float, bool, type(None))


def _is_json(value: object) -> bool:
    if isinstance(value, _JSON_SCALARS):
        return True
    if isinstance(value, (list, tuple)):
        return all(_is_json(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(k, str) and _is_json(v) for k, v in value.items())
    return False


@dataclass(frozen=True, slots=True)
class ParameterInfo:
    """One parameter as the registry describes it.

    ``default`` is JSON only: a QGIS default the reader could not express as
    JSON (a CRS object, a date) arrives as ``None``, and the parameter is still
    not required when the registry says it has a default (``has_default``).
    """

    name: str
    kind: str
    label: str = ""
    description: str = ""
    optional: bool = False
    advanced: bool = False
    hidden: bool = False
    destination: bool = False
    default: Any = None
    has_default: bool | None = None
    options: tuple[str, ...] = ()
    multiple: bool = False
    number_type: str | None = None
    minimum: float | None = None
    maximum: float | None = None
    extension: str | None = None

    def __post_init__(self) -> None:
        if not _is_json(self.default):
            raise ValueError(
                f"parameter {self.name!r}: a default must be JSON, not "
                f"{type(self.default).__name__}"
            )
        if isinstance(self.default, list):
            object.__setattr__(self, "default", list(self.default))
        object.__setattr__(self, "options", tuple(self.options))
        if self.has_default is None:
            object.__setattr__(self, "has_default", self.default is not None)
        if self.kind in DESTINATION_KINDS and not self.destination:
            object.__setattr__(self, "destination", True)

    @property
    def required(self) -> bool:
        """Whether a run must supply this parameter."""
        return not (self.optional or self.destination or self.has_default)

    def to_dict(self) -> dict[str, Any]:
        """The JSON shape; fields at their default are left out to keep a
        catalogue of several hundred algorithms readable and small."""
        data: dict[str, Any] = {"name": self.name, "kind": self.kind}
        for f in fields(self):
            if f.name in ("name", "kind"):
                continue
            value = getattr(self, f.name)
            if f.name == "options":
                if value:
                    data["options"] = list(value)
            elif f.name == "has_default":
                if value != (self.default is not None):
                    data["has_default"] = value
            elif value != f.default:
                data[f.name] = value
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ParameterInfo:
        known = {f.name for f in fields(cls)}
        values = {k: v for k, v in data.items() if k in known}
        if "options" in values:
            values["options"] = tuple(values["options"])
        return cls(**values)


@dataclass(frozen=True, slots=True)
class OutputInfo:
    """One declared output: its name and QGIS output type id."""

    name: str
    kind: str
    label: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = {"name": self.name, "kind": self.kind}
        if self.label:
            data["label"] = self.label
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> OutputInfo:
        return cls(name=data["name"], kind=data["kind"], label=data.get("label", ""))


@dataclass(frozen=True, slots=True)
class FolderOutputParameter:
    """Marker: the ``FileRef`` result is the folder the algorithm produced.

    ``FileRef`` alone means one file (``outputFile``); the marker selects
    ``outputFolder`` the way :class:`~qgis_sdk.models.parameters.FolderParameter`
    selects a folder input. The usual spelling is the alias (decision-42):
    ``def run(ctx) -> FolderOutput: ...``.
    """


@dataclass(frozen=True, slots=True)
class HtmlOutputParameter:
    """Marker: the ``FileRef`` result is the algorithm's HTML report.

    The usual spelling is the alias: ``def run(ctx) -> HtmlOutput: ...``.
    """


FolderOutput = Annotated[FileRef, FolderOutputParameter()]
HtmlOutput = Annotated[FileRef, HtmlOutputParameter()]
MultipleLayers = tuple[VectorLayerInfo, ...]
AlgorithmResult = (
    VectorLayerInfo
    | RasterLayerInfo
    | FileRef
    | float
    | str
    | bool
    | tuple[VectorLayerInfo, ...]
)


@dataclass(frozen=True, slots=True)
class OutputKind:
    """One declared result kind, with the face it shows to each host.

    ``name`` is the QGIS output type id the registry reports (``outputVector``,
    ``outputRaster`` ...), ``marker`` the ``Annotated`` extra that selects the
    kind where a plain spelling would collide (``None`` where the stored type
    names the kind on its own), ``stored`` the annotations the kind accepts,
    ``processing`` the ``QgsProcessingOutput*`` class the provider adapter
    declares, and ``accepted`` what ``invoke`` checks the handler's result
    against. :func:`output_kinds` is the one table every describer and adapter
    reads, so a kind missing a face is a test failure here, never a surprise
    in a host.
    """

    name: str
    marker: type | None
    stored: tuple[Any, ...]
    processing: str
    result: str
    accepted: tuple[type, ...]

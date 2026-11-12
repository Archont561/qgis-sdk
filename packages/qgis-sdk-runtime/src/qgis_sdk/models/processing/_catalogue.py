from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from types import MappingProxyType
from typing import Annotated, Any, get_args, get_origin

from qgis_sdk.models.errors import (
    QgisSdkAlgorithmNotFoundError,
    QgisSdkAlgorithmRejectedError,
)
from qgis_sdk.models.files import FileRef
from qgis_sdk.models.layers import RasterLayerInfo, VectorLayerInfo

from ._validation_state import (
    CcReturn,
    CcState,
    FolderOutputParameter,
    HtmlOutputParameter,
    MultipleLayers,
    OutputInfo,
    OutputKind,
    ParameterInfo,
    cc_validate_paramet_p7,
    cc_validate_paramet_p8,
    cc_validate_paramet_p9,
)

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


@dataclass(frozen=True, slots=True)
class AlgorithmInfo:
    """One algorithm: identity, help, parameters and outputs."""

    id: str
    provider: str
    name: str
    label: str
    group: str = ""
    group_id: str = ""
    help: str = ""
    parameters: tuple[ParameterInfo, ...] = ()
    outputs: tuple[OutputInfo, ...] = ()
    deprecated: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "parameters", tuple(self.parameters))
        object.__setattr__(self, "outputs", tuple(self.outputs))

    def parameter(self, name: str) -> ParameterInfo | None:
        for parameter in self.parameters:
            if parameter.name == name:
                return parameter
        return None

    @property
    def inputs(self) -> tuple[ParameterInfo, ...]:
        return tuple(p for p in self.parameters if not p.destination)

    @property
    def destinations(self) -> tuple[ParameterInfo, ...]:
        return tuple(p for p in self.parameters if p.destination)

    @property
    def required(self) -> tuple[ParameterInfo, ...]:
        return tuple(p for p in self.parameters if p.required)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "provider": self.provider,
            "name": self.name,
            "label": self.label,
            "group": self.group,
            "group_id": self.group_id,
            "help": self.help,
        }
        if self.deprecated:
            data["deprecated"] = True
        data["parameters"] = [p.to_dict() for p in self.parameters]
        data["outputs"] = [o.to_dict() for o in self.outputs]
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> AlgorithmInfo:
        return cls(
            id=data["id"],
            provider=data["provider"],
            name=data["name"],
            label=data["label"],
            group=data.get("group", ""),
            group_id=data.get("group_id", ""),
            help=data.get("help", ""),
            deprecated=bool(data.get("deprecated", False)),
            parameters=tuple(
                ParameterInfo.from_dict(p) for p in data.get("parameters", ())
            ),
            outputs=tuple(OutputInfo.from_dict(o) for o in data.get("outputs", ())),
        )


@dataclass(frozen=True, slots=True)
class ProviderInfo:
    """One registered provider."""

    id: str
    label: str = ""
    version: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ProviderInfo:
        return cls(
            id=data["id"], label=data.get("label", ""), version=data.get("version", "")
        )


@dataclass(frozen=True, slots=True)
class Catalogue:
    """Every provider and algorithm one registry held, as plain data."""

    qgis_version: str
    providers: tuple[ProviderInfo, ...] = ()
    algorithms: tuple[AlgorithmInfo, ...] = ()
    _index: dict[str, AlgorithmInfo] = field(
        default_factory=dict, init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "providers", tuple(self.providers))
        object.__setattr__(self, "algorithms", tuple(self.algorithms))
        self._index.update({a.id: a for a in self.algorithms})

    def algorithm(self, algorithm_id: str) -> AlgorithmInfo:
        """The algorithm with this id, or ``QgisSdkAlgorithmNotFoundError``."""
        try:
            return self._index[algorithm_id]
        except KeyError:
            raise QgisSdkAlgorithmNotFoundError(algorithm_id) from None

    def __contains__(self, algorithm_id: object) -> bool:
        return algorithm_id in self._index

    def by_provider(self, provider_id: str) -> tuple[AlgorithmInfo, ...]:
        return tuple(a for a in self.algorithms if a.provider == provider_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "qgis_version": self.qgis_version,
            "providers": [p.to_dict() for p in self.providers],
            "algorithms": [a.to_dict() for a in self.algorithms],
        }

    def to_json(self) -> str:
        """One algorithm per line: diffs by algorithm, a tenth of the indented size."""

        def dump(value: object) -> str:
            return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

        lines = [
            "{",
            f'"qgis_version":{dump(self.qgis_version)},',
            f'"providers":{dump([p.to_dict() for p in self.providers])},',
            '"algorithms":[',
        ]
        lines.extend(
            dump(a.to_dict()) + ("," if i + 1 < len(self.algorithms) else "")
            for i, a in enumerate(self.algorithms)
        )
        lines.extend(["]", "}", ""])
        return "\n".join(lines)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Catalogue:
        return cls(
            qgis_version=str(data.get("qgis_version", "")),
            providers=tuple(
                ProviderInfo.from_dict(p) for p in data.get("providers", ())
            ),
            algorithms=tuple(
                AlgorithmInfo.from_dict(a) for a in data.get("algorithms", ())
            ),
        )

    @classmethod
    def from_json(cls, text: str) -> Catalogue:
        return cls.from_dict(json.loads(text))


def validate_parameters(info: AlgorithmInfo, params: Mapping[str, object]) -> None:
    """Refuse a parameter mapping the registry's description cannot accept.

    Every problem is reported in one error, and no value is quoted in the
    reasons (``QgisSdkAlgorithmRejectedError`` is loggable as-is). What is
    checked is what pure code can know from the catalogue: unknown names,
    missing required inputs, numbers, booleans and enum choices. Layer and
    file existence are the backend's to check.
    """
    _s = CcState(**locals())
    for _p in (
        cc_validate_paramet_p7,
        cc_validate_paramet_p8,
        cc_validate_paramet_p9,
    ):
        _r = _p(_s)
        if isinstance(_r, CcReturn):
            return _r.value
    return None


@dataclass(frozen=True, slots=True)
class AlgorithmRun:
    """A request by algorithm id and parameter mapping, as ``processing.run`` takes."""

    algorithm: str
    params: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        reasons: list[str] = []
        if self.algorithm.count(":") != 1 or not all(self.algorithm.split(":")):
            reasons.append("an algorithm id has the form provider:name")
        if not all(isinstance(key, str) for key in self.params):
            reasons.append("parameter names are strings")
        if reasons:
            raise QgisSdkAlgorithmRejectedError(self.algorithm, reasons)
        object.__setattr__(self, "params", dict(self.params))

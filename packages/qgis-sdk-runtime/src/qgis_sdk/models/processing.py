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

import json
from collections.abc import Iterator, Mapping
from dataclasses import asdict, dataclass, field, fields
from typing import Any, ClassVar

from .errors import QgisSdkAlgorithmNotFoundError, QgisSdkAlgorithmRejectedError
from .files import FileRef
from .layers import VectorLayerInfo

__all__ = [
    "DESTINATION_KINDS",
    "LAYER_KINDS",
    "AlgorithmInfo",
    "AlgorithmRun",
    "Catalogue",
    "OutputInfo",
    "ParameterInfo",
    "ProviderInfo",
    "RunResult",
    "TypedRun",
    "validate_parameters",
]

#: Parameter kinds that name an output location. Left out of a run, the
#: backend allocates one under the run directory.
DESTINATION_KINDS: tuple[str, ...] = (
    "sink",
    "vectorDestination",
    "rasterDestination",
    "fileDestination",
    "folderDestination",
    "pointCloudDestination",
    "vectorTileDestination",
)
#: Parameter kinds that take one layer: an owned layer id, a path or a ref.
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


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def validate_parameters(info: AlgorithmInfo, params: Mapping[str, object]) -> None:
    """Refuse a parameter mapping the registry's description cannot accept.

    Every problem is reported in one error, and no value is quoted in the
    reasons (``QgisSdkAlgorithmRejectedError`` is loggable as-is). What is
    checked is what pure code can know from the catalogue: unknown names,
    missing required inputs, numbers, booleans and enum choices. Layer and
    file existence are the backend's to check.
    """
    reasons: list[str] = []
    for name in params:
        if info.parameter(name) is None:
            reasons.append(f"{name} is not a parameter of {info.id}")
    for parameter in info.parameters:
        value = params.get(parameter.name)
        if value is None:
            # Absent and explicit None are the same thing: not given.
            if parameter.required:
                reasons.append(f"{parameter.name} is required")
            continue
        kind = parameter.kind
        if kind == "boolean" and not isinstance(value, bool):
            reasons.append(f"{parameter.name} must be a boolean")
        elif kind in _NUMBER_KINDS and not _is_number(value):
            reasons.append(f"{parameter.name} must be a number")
        elif kind == "enum" and parameter.options:
            choices = (
                value if parameter.multiple and isinstance(value, list) else [value]
            )
            for choice in choices:
                valid = (
                    isinstance(choice, int)
                    and not isinstance(choice, bool)
                    and 0 <= choice < len(parameter.options)
                ) or (isinstance(choice, str) and choice in parameter.options)
                if not valid:
                    reasons.append(
                        f"{parameter.name} must be one of "
                        f"{', '.join(parameter.options)} (or its index)"
                    )
                    break
    if reasons:
        raise QgisSdkAlgorithmRejectedError(info.id, reasons)


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


class TypedRun:
    """Base of the generated request classes.

    A generated class is a frozen dataclass whose fields are the algorithm's
    parameters under Python names; ``algorithm`` is the id and ``_names`` maps
    each field to its QGIS name. ``params()`` keeps only the fields that were
    given (``None`` is "not given": QGIS applies the default, or the backend
    allocates the destination).
    """

    algorithm: ClassVar[str]
    _names: ClassVar[Mapping[str, str]]

    def params(self) -> dict[str, object]:
        values: dict[str, object] = {}
        for field_name, qgis_name in type(self)._names.items():
            value = getattr(self, field_name)
            if value is not None:
                values[qgis_name] = value
        return values

    def to_run(self) -> AlgorithmRun:
        return AlgorithmRun(type(self).algorithm, self.params())


@dataclass(frozen=True, slots=True)
class RunResult:
    """What one run produced, by output name.

    Vector destinations come back as owned :class:`VectorLayerInfo`; rasters,
    files, folders and HTML reports as :class:`FileRef` (readable by the
    plugin that ran the algorithm); numbers, strings and booleans as they are.
    """

    algorithm: str
    outputs: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "outputs", dict(self.outputs))

    def __getitem__(self, name: str) -> object:
        return self.outputs[name]

    def __iter__(self) -> Iterator[str]:
        return iter(self.outputs)

    def __len__(self) -> int:
        return len(self.outputs)

    def value(self, name: str) -> object:
        return self.outputs[name]

    def vector(self, name: str) -> VectorLayerInfo:
        value = self.outputs[name]
        if not isinstance(value, VectorLayerInfo):
            raise KeyError(f"output {name!r} of {self.algorithm} is not a vector layer")
        return value

    def file(self, name: str) -> FileRef:
        value = self.outputs[name]
        if not isinstance(value, FileRef):
            raise KeyError(f"output {name!r} of {self.algorithm} is not a file")
        return value

    def to_wire(self) -> dict[str, Any]:
        """The bridge shape: outputs as a list of tagged entries.

        A list of ``{name, kind, ...}`` records is a wire shape every generator
        can type, where a map keyed by output name is not (the same reason
        HTTP headers cross as pairs).
        """
        outputs: list[dict[str, Any]] = []
        for name, value in self.outputs.items():
            if isinstance(value, VectorLayerInfo):
                layer = asdict(value)
                layer["field_names"] = list(value.field_names)
                outputs.append({"name": name, "kind": "vector", "layer": layer})
            elif isinstance(value, FileRef):
                outputs.append({"name": name, "kind": "file", "file": value.to_wire()})
            else:
                outputs.append({"name": name, "kind": "value", "value": value})
        return {"algorithm": self.algorithm, "outputs": outputs}

    @classmethod
    def from_wire(cls, data: Mapping[str, Any]) -> RunResult:
        outputs: dict[str, object] = {}
        for entry in data.get("outputs", ()):
            name, kind = entry["name"], entry.get("kind")
            if kind == "vector":
                layer = dict(entry["layer"])
                layer["field_names"] = tuple(layer.get("field_names", ()))
                outputs[name] = VectorLayerInfo(**layer)
            elif kind == "file":
                outputs[name] = FileRef.from_wire(entry["file"])
            else:
                outputs[name] = entry.get("value")
        return cls(algorithm=data["algorithm"], outputs=outputs)

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from typing import Any

from qgis_sdk.models.errors import (
    QgisSdkAlgorithmNotFoundError,
    QgisSdkAlgorithmRejectedError,
)

from ._validation_state import (
    CcReturn,
    CcState,
    OutputInfo,
    ParameterInfo,
    cc_validate_paramet_p7,
    cc_validate_paramet_p8,
    cc_validate_paramet_p9,
)


@dataclass(frozen=True, slots=True)
class AlgorithmInfo:
    """One algorithm: identity, help, parameters and outputs.

    Attributes:
        id: The ``provider:name`` id ``run`` takes.
        provider: The provider that registered it.
        name: Its own name within the provider.
        label: The name the toolbox shows.
        group: The toolbox group it is listed under.
        group_id: The group's stable id, for ordering.
        help: The algorithm's own help text.
        parameters: One entry per input, in the registry's order.
        outputs: One entry per declared output.
        deprecated: Whether the registry marks it as deprecated.
    """

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
        """Return the named parameter's description, or ``None`` if it has none.

        Args:
            name: The parameter name to read.
        """
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
        """Read this value from a plain mapping.

        Args:
            data: The mapping the catalogue carries.
        """
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
    """One registered provider.

    Attributes:
        id: The provider's id, as an algorithm id quotes it.
        label: The name the toolbox shows.
        version: The provider's own version string.
    """

    id: str
    label: str = ""
    version: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ProviderInfo:
        """Read this value from a plain mapping.

        Args:
            data: The mapping the catalogue carries.
        """
        return cls(
            id=data["id"], label=data.get("label", ""), version=data.get("version", "")
        )


@dataclass(frozen=True, slots=True)
class Catalogue:
    """Every provider and algorithm one registry held, as plain data.

    Attributes:
        qgis_version: The QGIS build the snapshot was read from.
        providers: Every provider the registry held.
        algorithms: Every algorithm, across all providers.
        _index: The id lookup built on load.
    """

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
        """The algorithm with this id, or ``QgisSdkAlgorithmNotFoundError``.

        Args:
            algorithm_id: The ``provider:name`` id to look up.
        """
        try:
            return self._index[algorithm_id]
        except KeyError:
            raise QgisSdkAlgorithmNotFoundError(algorithm_id) from None

    def __contains__(self, algorithm_id: object) -> bool:
        """Whether the catalogue holds this id.

        Args:
            algorithm_id: The id to test for.
        """
        return algorithm_id in self._index

    def by_provider(self, provider_id: str) -> tuple[AlgorithmInfo, ...]:
        """Every algorithm one provider registered, in catalogue order.

        Args:
            provider_id: The provider to narrow to.
        """
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
        """Read this value from a plain mapping.

        Args:
            data: The mapping the catalogue carries.
        """
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
        """Read this value from its JSON text.

        Args:
            text: The JSON document to read.
        """
        return cls.from_dict(json.loads(text))


def validate_parameters(info: AlgorithmInfo, params: Mapping[str, object]) -> None:
    """Refuse a parameter mapping the registry's description cannot accept.

    Every problem is reported in one error, and no value is quoted in the
    reasons (``QgisSdkAlgorithmRejectedError`` is loggable as-is). What is
    checked is what pure code can know from the catalogue: unknown names,
    missing required inputs, numbers, booleans and enum choices. Layer and
    file existence are the backend's to check.

    Args:
        info: The algorithm's registry description.
        params: The mapping the caller asked to run with.
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
    """A request by algorithm id and parameter mapping, as ``processing.run`` takes.

    Attributes:
        algorithm: The ``provider:name`` id to run.
        params: The parameter mapping, by parameter name.
    """

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

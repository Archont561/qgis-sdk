from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import asdict, dataclass, field
from typing import Any, ClassVar

from qgis_sdk.models.files import FileRef
from qgis_sdk.models.layers import VectorLayerInfo

from ._catalogue import AlgorithmRun


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
    plugin that ran the algorithm); numbers, strings and booleans as they are;
    a multiple-layers output as a tuple of :class:`VectorLayerInfo`, in the
    order the registry listed them.
    """

    algorithm: str
    outputs: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "outputs", dict(self.outputs))

    def __getitem__(self, name: str) -> object:
        try:
            return self.outputs[name]
        except KeyError:
            # A run's outputs are named by the algorithm that produced them,
            # and a caller guessing a name learns what the run did answer
            # rather than only what it did not.
            raise KeyError(
                f"{name!r} is not an output of {self.algorithm}; it answered "
                f"{sorted(self.outputs)}"
            ) from None

    def __iter__(self) -> Iterator[str]:
        return iter(self.outputs)

    def __len__(self) -> int:
        return len(self.outputs)

    def value(self, name: str) -> object:
        return self[name]

    def vector(self, name: str) -> VectorLayerInfo:
        value = self[name]
        if not isinstance(value, VectorLayerInfo):
            raise KeyError(f"output {name!r} of {self.algorithm} is not a vector layer")
        return value

    def layers(self, name: str) -> tuple[VectorLayerInfo, ...]:
        value = self[name]
        if not isinstance(value, tuple) or not all(
            isinstance(item, VectorLayerInfo) for item in value
        ):
            raise KeyError(f"output {name!r} of {self.algorithm} is not layers")
        return value

    def file(self, name: str) -> FileRef:
        value = self[name]
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
            elif isinstance(value, tuple) and all(
                isinstance(item, VectorLayerInfo) for item in value
            ):
                layers = []
                for item in value:
                    layer = asdict(item)
                    layer["field_names"] = list(item.field_names)
                    layers.append(layer)
                outputs.append({"name": name, "kind": "layers", "layers": layers})
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
            elif kind == "layers":
                rebuilt = []
                for layer in entry.get("layers", ()):
                    layer = dict(layer)
                    layer["field_names"] = tuple(layer.get("field_names", ()))
                    rebuilt.append(VectorLayerInfo(**layer))
                outputs[name] = tuple(rebuilt)
            elif kind == "file":
                outputs[name] = FileRef.from_wire(entry["file"])
            else:
                outputs[name] = entry.get("value")
        return cls(algorithm=data["algorithm"], outputs=outputs)


RunResult.__qgis_sdk_schema__ = {  # type: ignore[attr-defined]
    "type": "object",
    "properties": {
        "algorithm": {"type": "string"},
        "outputs": {"type": "array", "items": {"type": "object"}},
    },
    "required": ["algorithm", "outputs"],
    "additionalProperties": False,
}

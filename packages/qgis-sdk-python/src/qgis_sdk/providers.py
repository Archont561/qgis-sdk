"""A provider owns a set of algorithms, the way an app owns its routes.

Declaring one is the whole setup step:

```python
provider = Provider(id="reference", title="Reference plugin")


@provider.algorithm(id="buffer", title="Buffer", group="Geometry")
class BufferLayer:
    def run(self, inputs: BufferRequest) -> BufferResult: ...
```

Registration is validated when it happens, not when the algorithm first runs: the
class has to describe (one typed ``run``, a representable request), every request
field has to map to a host parameter, and the id has to be unique inside the
provider. A mistake therefore fails at import time, which is where a plugin author
can still see it.

The provider is also what makes an algorithm *visible*: the QGIS adapter turns a
provider into a ``QgsProcessingProvider`` and each registration into a
``QgsProcessingAlgorithm``, so ``provider:algorithm`` appears in the toolbox. This
module stays QGIS-free; only the adapter knows about the toolbox.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, fields
from typing import Annotated, Any, TypeVar, get_args, get_origin

from qgis_sdk.algorithms import (
    _ALGORITHM_ATTRIBUTE,
    AlgorithmDescription,
    describe_algorithm,
)
from qgis_sdk.declarations import (
    QgisSdkDeclarationError,
    canonical_json,
    class_metadata,
    mark_class,
    metadata,
    resolve_hints,
    validate_given,
)
from qgis_sdk.models import CrsInput, LayerInput, Metres

__all__ = [
    "LAYER_PARAMETER",
    "METRES_PARAMETER",
    "Provider",
    "ProviderDescription",
    "RegisteredAlgorithm",
    "parameter_kinds",
]

T = TypeVar("T")

LAYER_PARAMETER = "layer"
"""Kind of a field the host fills with a vector layer."""

METRES_PARAMETER = "metres"
"""Kind of a field that is a distance in metres."""

_PRIMITIVE_KINDS: dict[Any, str] = {
    str: "string",
    bool: "boolean",
    int: "integer",
    float: "number",
}
_SUPPORTED = "layer, crs, metres, string, integer, number or boolean"


def _refuse(owner: str, name: str, detail: str) -> QgisSdkDeclarationError:
    return QgisSdkDeclarationError(
        f"{owner}.{name}: {detail}; use Annotated markers ({_SUPPORTED})"
    )


def _kind(owner: str, name: str, annotation: Any) -> str:
    """Map one annotated field onto a host parameter kind, or refuse it."""
    base, markers = annotation, ()
    if get_origin(annotation) is Annotated:
        base, *markers = get_args(annotation)
    for marker in markers:
        if isinstance(marker, LayerInput):
            if base is not str:
                raise _refuse(owner, name, "a layer field must be a str layer id")
            return LAYER_PARAMETER
        if isinstance(marker, CrsInput):
            if base is not str:
                raise _refuse(owner, name, "a CRS field must be a str authority code")
            return "crs"
        if isinstance(marker, Metres):
            if base not in (float, int):
                raise _refuse(owner, name, "a metres field must be a number")
            return METRES_PARAMETER
        raise _refuse(owner, name, f"unknown parameter marker {marker!r}")
    kind = _PRIMITIVE_KINDS.get(base)
    if kind is None:
        raise _refuse(owner, name, f"cannot express {base!r} as a host parameter")
    return kind


def parameter_kinds(inputs_type: Any) -> tuple[tuple[str, str], ...]:
    """Return ``(field name, kind)`` for a request dataclass, in field order.

    This is the whole host-parameter contract: a field is either a marked layer,
    a marked CRS, a marked distance in metres, or a plain primitive. Anything else
    is refused here so that no adapter has to invent a widget at run time.
    """
    if not inspect.isclass(inputs_type):
        raise QgisSdkDeclarationError(
            f"request {inputs_type!r} must be a dataclass type to become parameters"
        )
    hints = resolve_hints(inputs_type, f"{inputs_type.__name__} request")
    return tuple(
        (
            field.name,
            _kind(inputs_type.__name__, field.name, hints.get(field.name, field.type)),
        )
        for field in fields(inputs_type)
    )


@dataclass(frozen=True)
class RegisteredAlgorithm:
    """One algorithm as its provider knows it: description, group, parameters."""

    description: AlgorithmDescription
    group: str | None
    parameters: tuple[tuple[str, str], ...]

    def to_dict(self) -> dict[str, Any]:
        """Return the transport view, including the request's parameter kinds."""
        return {
            **self.description.to_dict(),
            "group": self.group,
            "parameters": {name: kind for name, kind in self.parameters},
        }


@dataclass(frozen=True)
class ProviderDescription:
    """A provider and its algorithms, with the ids a host will register."""

    id: str
    title: str
    algorithms: tuple[RegisteredAlgorithm, ...]
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        """Return the transport representation; ids are ``provider:algorithm``."""
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "title": self.title,
            "algorithms": [
                {
                    **registered.to_dict(),
                    "qualified_id": f"{self.id}:{registered.description.id}",
                }
                for registered in self.algorithms
            ],
        }

    def to_json(self) -> str:
        """The canonical JSON form shared by every description."""
        return canonical_json(self.to_dict())


class Provider:
    """A named collection of algorithms, registered at definition time."""

    def __init__(self, *, id: str, title: str) -> None:
        declared = metadata(id, title)
        self._id = declared.id
        self._title = declared.title
        self._registered: dict[str, RegisteredAlgorithm] = {}
        self._classes: dict[str, type] = {}

    @property
    def id(self) -> str:
        """Return the provider id hosts prefix their algorithm ids with."""
        return self._id

    @property
    def title(self) -> str:
        """Return the human-readable provider title."""
        return self._title

    def algorithm(
        self,
        cls: type[T] | None = None,
        /,
        *,
        id: str | None = None,
        title: str | None = None,
        group: str | None = None,
    ) -> Any:
        """Register a decorated-by-this-call algorithm class on the provider.

        The class is described immediately, so a missing ``run``, an
        uninspectable request or a field no host could render all fail here
        rather than during the first execution. ``@provider.algorithm`` alone
        derives the id and title from the class name, as ``@algorithm`` does.
        """

        validate_given(id, title)
        if group is not None and (not isinstance(group, str) or not group.strip()):
            raise QgisSdkDeclarationError(
                f"{id if id is not None else 'algorithm'}: group must be a nonempty string"
            )

        def decorate(cls: type[T]) -> type[T]:
            if not inspect.isclass(cls):
                raise QgisSdkDeclarationError("@provider.algorithm requires a class")
            declared = class_metadata(cls, id, title)
            if declared.id in self._registered:
                raise QgisSdkDeclarationError(
                    f"{self._id}: duplicate algorithm id {declared.id!r}"
                )
            if _ALGORITHM_ATTRIBUTE in vars(cls):
                raise QgisSdkDeclarationError(
                    f"{declared.id}: already declared; register it on one provider"
                )
            mark_class(cls, _ALGORITHM_ATTRIBUTE, declared, "@provider.algorithm")
            try:
                described = describe_algorithm(cls)
                parameters = parameter_kinds(described.inputs_type)
            except QgisSdkDeclarationError:
                # Leave the class as it was: a refused registration must not
                # half-declare an algorithm that describe_algorithm would accept.
                delattr(cls, _ALGORITHM_ATTRIBUTE)
                raise
            self._registered[declared.id] = RegisteredAlgorithm(
                described, group, parameters
            )
            self._classes[declared.id] = cls
            return cls

        if cls is None:
            return decorate
        return decorate(cls)

    @property
    def algorithms(self) -> tuple[type, ...]:
        """Return the registered classes in registration order."""
        return tuple(self._classes.values())

    def class_for(self, algorithm_id: str) -> type:
        """Return the class registered under ``algorithm_id``."""
        try:
            return self._classes[algorithm_id]
        except KeyError:
            raise QgisSdkDeclarationError(
                f"{self._id}: no algorithm {algorithm_id!r} is registered"
            ) from None

    def describe(self) -> ProviderDescription:
        """Return the provider's structure without constructing an algorithm."""
        return ProviderDescription(
            id=self._id, title=self._title, algorithms=tuple(self._registered.values())
        )

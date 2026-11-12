"""A provider owns a set of algorithms, the way an app owns its routes.

Declaring one is the whole setup step (decision-42):

```python
tools = Provider(id="field_tools", title="Field tools")


@tools.algorithm(title="Buffer in a projected CRS", group="Geometry")
def buffer(
    ctx: AlgorithmContext, layer: LayerInput, distance: Metres, crs: CrsInput
) -> VectorLayerInfo: ...
```

Registration is validated when it happens, not when the algorithm first runs:
the function has to take the ``AlgorithmContext`` first, every input has to map
to a host parameter kind, the result has to be one declared output kind - the
produced layer or raster, a ``FileRef``, a ``FolderOutput`` or ``HtmlOutput``
ref, a number, a string, a boolean or ``MultipleLayers`` - and the id has to
be unique inside the provider. A mistake therefore fails at import time,
which is where a plugin author can still see it.

An application owns a provider through ``app.add_provider(tools)``.
``PluginRuntime.start()`` registers them with the host's Processing registry
when the context carries one (``ctx.processing``), so ``field_tools:buffer``
appears in the toolbox, the modeler and ``processing.run``; ``unload()``
removes them. Outside QGIS the same application registers nothing. This module stays
QGIS-free; only the adapter knows about the toolbox.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from qgis_sdk.algorithms import (
    ALGORITHM_ATTRIBUTE,
    CRS_PARAMETER,
    LAYER_PARAMETER,
    METRES_PARAMETER,
    AlgorithmDeclaration,
    AlgorithmDescription,
    describe_declared_algorithm,
)
from qgis_sdk.declarations import (
    QgisSdkDeclarationError,
    canonical_json,
    derive_id,
    derive_title,
    mark_function,
    metadata,
    register_predicate_describer,
    validate_given,
)


class _CcState:
    """A mutable record shared by the phases of one long function."""

    def __init__(_cc_self, **values):
        _cc_self.__dict__.update(values)


class _CcReturn:
    """An early return travelling out of a phase."""

    def __init__(_cc_self, value):
        _cc_self.value = value


def _cc_algorithm_p1(_s):
    validate_given(_s.id, _s.title)
    if _s.group is not None and (not isinstance(_s.group, str) or not _s.group.strip()):
        raise QgisSdkDeclarationError(
            f"{_s.id if _s.id is not None else 'algorithm'}: group must be a nonempty string"
        )


def _cc_algorithm_decorate(_s, function: T) -> T:
    if inspect.isclass(function):
        raise QgisSdkDeclarationError(
            "@provider.algorithm declares a function, not a class: write "
            "`@provider.algorithm def name(ctx: AlgorithmContext, ...) -> "
            "VectorLayerInfo` (the class form was removed; see the 0.6.0 "
            "migration notes)"
        )
    if not inspect.isfunction(function):
        raise QgisSdkDeclarationError("@provider.algorithm requires a function")
    declared = _s.self._declaration(function, _s.id, _s.title, _s.group)
    if declared.id in _s.self._described:
        raise QgisSdkDeclarationError(
            f"{_s.self._id}: duplicate algorithm id {declared.id!r}"
        )
    if ALGORITHM_ATTRIBUTE in vars(function):
        raise QgisSdkDeclarationError(
            f"{declared.qualified_id}: already declared; "
            "declare a function on one provider"
        )
    # Described before it is marked: a refused function keeps no marker,
    # so it cannot describe as an algorithm while registered nowhere.
    described = describe_declared_algorithm(function, declared)
    mark_function(function, ALGORITHM_ATTRIBUTE, declared, "@provider.algorithm")
    _s.self._described[declared.id] = described
    _s.self._functions[declared.id] = function
    return function


def _cc_algorithm_p2(_s):
    def decorate(function):
        return _cc_algorithm_decorate(_s, function)

    _s.decorate = decorate


def _cc_algorithm_p3(_s):

    if _s.function is None:
        return _CcReturn(_s.decorate)
    return _CcReturn(_s.decorate(_s.function))


__all__ = [
    "CRS_PARAMETER",
    "LAYER_PARAMETER",
    "METRES_PARAMETER",
    "Provider",
    "ProviderDescription",
]

T = TypeVar("T", bound=Callable[..., Any])


@dataclass(frozen=True)
class ProviderDescription:
    """A provider and its algorithms, with the ids a host will register."""

    id: str
    title: str
    algorithms: tuple[AlgorithmDescription, ...]
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        """Return the transport representation; ids are ``provider:algorithm``."""
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "title": self.title,
            "algorithms": [described.to_dict() for described in self.algorithms],
        }

    def to_json(self) -> str:
        """The canonical JSON form shared by every description."""
        return canonical_json(self.to_dict())


class Provider:
    """A named collection of algorithm functions, registered at definition time."""

    def __init__(self, *, id: str, title: str) -> None:
        declared = metadata(id, title)
        self._id = declared.id
        self._title = declared.title
        self._described: dict[str, AlgorithmDescription] = {}
        self._functions: dict[str, Callable[..., Any]] = {}

    @property
    def id(self) -> str:
        """Return the provider id hosts prefix their algorithm ids with."""
        return self._id

    @property
    def title(self) -> str:
        """Return the human-readable provider title."""
        return self._title

    def __repr__(self) -> str:
        return f"Provider(id={self._id!r}, title={self._title!r})"

    def algorithm(
        self,
        function: T | None = None,
        /,
        *,
        id: str | None = None,
        title: str | None = None,
        group: str | None = None,
    ) -> Any:
        "Declare ``function`` as one of this provider's algorithms.\n\n        The function is described immediately, so a missing context\n        parameter, an input no host could render or a result that is not a\n        declared output kind all fail here rather than during the first\n        execution. Nothing is\n        wrapped: it gains ``describe()`` and a test calls the original function\n        with a fake context.\n\n        ``@provider.algorithm`` alone derives the id and title from the\n        function name. The derived id is the plain snake_case name - the\n        provider is its namespace and refuses a duplicate - so the toolbox\n        shows ``field_tools:buffer`` rather than a hashed suffix.\n"
        _s = _CcState(self=self, function=function, id=id, title=title, group=group)
        for _p in (_cc_algorithm_p1, _cc_algorithm_p2, _cc_algorithm_p3):
            _r = _p(_s)
            if isinstance(_r, _CcReturn):
                return _r.value
        return None

    def _declaration(
        self,
        function: Callable[..., Any],
        id: str | None,
        title: str | None,
        group: str | None,
    ) -> AlgorithmDeclaration:
        name = getattr(function, "__name__", None)
        if id is None:
            if not isinstance(name, str):
                raise QgisSdkDeclarationError(
                    f"{self._id}: cannot derive an id without a name; pass id= explicitly"
                )
            id = derive_id(name)
        if title is None:
            if not isinstance(name, str):
                raise QgisSdkDeclarationError(
                    f"{id}: cannot derive a title without a name; pass title= explicitly"
                )
            title = derive_title(name)
        validated = metadata(id, title)
        return AlgorithmDeclaration(
            id=validated.id, title=validated.title, provider_id=self._id, group=group
        )

    @property
    def algorithms(self) -> tuple[Callable[..., Any], ...]:
        """Return the declared functions in declaration order."""
        return tuple(self._functions.values())

    def function_for(self, algorithm_id: str) -> Callable[..., Any]:
        """Return the function declared under ``algorithm_id``."""
        try:
            return self._functions[algorithm_id]
        except KeyError:
            raise QgisSdkDeclarationError(
                f"{self._id}: no algorithm {algorithm_id!r} is registered"
            ) from None

    def describe(self) -> ProviderDescription:
        """Return the provider's structure without calling an algorithm."""
        return ProviderDescription(
            id=self._id, title=self._title, algorithms=tuple(self._described.values())
        )


register_predicate_describer(
    lambda value: isinstance(value, Provider), Provider.describe
)

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
to a host parameter kind, the result has to be the produced layer, and the id
has to be unique inside the provider. A mistake therefore fails at import time,
which is where a plugin author can still see it.

A ``@plugin`` class lists the providers it owns in ``providers = [tools]``.
``PluginRuntime.start()`` registers them with the host's Processing registry
when the context carries one (``ctx.processing``), so ``field_tools:buffer``
appears in the toolbox, the modeler and ``processing.run``; ``unload()``
removes them. Outside QGIS the same class registers nothing. This module stays
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
    validate_given,
)

__all__ = [
    "CRS_PARAMETER",
    "LAYER_PARAMETER",
    "METRES_PARAMETER",
    "PROVIDERS_ATTRIBUTE",
    "Provider",
    "ProviderDescription",
    "declared_providers",
]

T = TypeVar("T", bound=Callable[..., Any])

PROVIDERS_ATTRIBUTE = "providers"
"""The class attribute a ``@plugin`` class lists its providers in."""


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
        """Declare ``function`` as one of this provider's algorithms.

        The function is described immediately, so a missing context
        parameter, an input no host could render or a result that is not a
        layer all fail here rather than during the first execution. Nothing is
        wrapped or injected: a test calls the function with a fake context.

        ``@provider.algorithm`` alone derives the id and title from the
        function name. The derived id is the plain snake_case name - the
        provider is its namespace and refuses a duplicate - so the toolbox
        shows ``field_tools:buffer`` rather than a hashed suffix.
        """
        validate_given(id, title)
        if group is not None and (not isinstance(group, str) or not group.strip()):
            raise QgisSdkDeclarationError(
                f"{id if id is not None else 'algorithm'}: group must be a nonempty string"
            )

        def decorate(function: T) -> T:
            if inspect.isclass(function):
                raise QgisSdkDeclarationError(
                    "@provider.algorithm declares a function, not a class: write "
                    "`@provider.algorithm def name(ctx: AlgorithmContext, ...) -> "
                    "VectorLayerInfo` (the class form was removed; see the 0.6.0 "
                    "migration notes)"
                )
            if not inspect.isfunction(function):
                raise QgisSdkDeclarationError("@provider.algorithm requires a function")
            declared = self._declaration(function, id, title, group)
            if declared.id in self._described:
                raise QgisSdkDeclarationError(
                    f"{self._id}: duplicate algorithm id {declared.id!r}"
                )
            if ALGORITHM_ATTRIBUTE in vars(function):
                raise QgisSdkDeclarationError(
                    f"{declared.qualified_id}: already declared; "
                    "declare a function on one provider"
                )
            # Described before it is marked: a refused function keeps no marker,
            # so it cannot describe as an algorithm while registered nowhere.
            described = describe_declared_algorithm(function, declared)
            mark_function(
                function, ALGORITHM_ATTRIBUTE, declared, "@provider.algorithm"
            )
            self._described[declared.id] = described
            self._functions[declared.id] = function
            return function

        if function is None:
            return decorate
        return decorate(function)

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


def declared_providers(plugin_class: type) -> tuple[Provider, ...]:
    """Return the providers a ``@plugin`` class lists, validated.

    ``providers`` is optional; when present it is a list or tuple of
    :class:`Provider` instances with distinct ids. Anything else is refused
    naming the class, so a typo (``providers = tools``) fails when the runtime
    is built rather than registering nothing in silence.
    """
    listed = getattr(plugin_class, PROVIDERS_ATTRIBUTE, None)
    if listed is None:
        return ()
    name = getattr(plugin_class, "__name__", repr(plugin_class))
    if not isinstance(listed, (list, tuple)) or not all(
        isinstance(provider, Provider) for provider in listed
    ):
        raise QgisSdkDeclarationError(
            f"{name}.{PROVIDERS_ATTRIBUTE} must be a list of Provider instances"
        )
    seen: dict[str, Provider] = {}
    for provider in listed:
        if provider.id in seen:
            raise QgisSdkDeclarationError(
                f"{name}.{PROVIDERS_ATTRIBUTE}: provider id {provider.id!r} is "
                "listed twice"
            )
        seen[provider.id] = provider
    return tuple(listed)

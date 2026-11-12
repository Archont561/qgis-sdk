"""The exported type names, decided before anything is rendered."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from qgis_sdk.models.errors import QgisSdkBridgeError

from qgis_sdk_tools.generate._contract import _shape, is_open_map
from qgis_sdk_tools.generate._emit import (
    check_supported,
    inline_type,
    inline_validator,
    pascal,
)
from qgis_sdk_tools.generate._names import declared_name


def _titled(schema: Mapping[str, Any], name: str) -> str:
    """The name a titled object declares for itself, wherever it appears.

    A branded reference reads as ``FileRef``, not as the field path it happened
    to be declared under first.
    """
    if "title" not in schema:
        return name
    return declared_name(schema["title"], name, kind="title", action=name)


class Naming:
    """One name per object schema, walked out before the first line is rendered.

    Naming has to finish first: a parent's field type is the child's name, so
    rendering while descending would point the parent at a name not yet chosen.
    Identity, not equality, decides whether two schemas are the same type - the
    same dict declared twice is one exported interface.
    """

    def __init__(self) -> None:
        self._objects: list[tuple[str, Mapping[str, Any]]] = []
        self._names: dict[int, str] = {}

    @property
    def objects(self) -> list[tuple[str, Mapping[str, Any]]]:
        """The named object schemas, in the order they were first declared."""
        return self._objects

    def declare(self, schema: Mapping[str, Any], name: str) -> str:
        """Name every object below ``schema`` before anything is rendered.

        Naming has to finish first: a parent's field type is the child's name, so
        rendering as we descend would point the parent at a name not yet chosen.
        """
        check_supported(schema, path=name)
        self.register(schema, name)
        return name

    def register(self, schema: Mapping[str, Any], name: str) -> None:
        """Name ``schema`` itself, then everything declared inside it."""
        self._name_object(schema, name)
        for key, item in (schema.get("properties") or {}).items():
            self.register(item, f"{name}{pascal(str(key))}")
        if isinstance(schema.get("items"), Mapping):
            self.register(schema["items"], f"{name}Item")
        for position, branch in enumerate(schema.get("anyOf", []) or []):
            self._name_branch(branch, f"{name}{position}", union=name)

    def _name_object(self, schema: Mapping[str, Any], name: str) -> None:
        """Give one object schema its exported name, unless it already has one."""
        if schema.get("type") != "object" or is_open_map(schema):
            return
        if id(schema) in self._names:
            return
        name = _titled(schema, name)
        if self._twin_of(schema, name):
            return
        self._names[id(schema)] = name
        self._objects.append((name, schema))

    def _twin_of(self, schema: Mapping[str, Any], name: str) -> bool:
        """Point this site at the type already carrying ``name``, or refuse it."""
        twin = next(
            (item for existing, item in self._objects if existing == name), None
        )
        if twin is None:
            return False
        if _shape(twin) != _shape(schema):
            raise QgisSdkBridgeError(
                f"{name}: two declarations would generate the same type name; "
                "rename one of the actions"
            )
        # The same branded object declared twice (two file inputs are both
        # ``FileRef``): one exported type, both sites point at it.
        self._names[id(schema)] = name
        return True

    def _name_branch(self, branch: Mapping[str, Any], name: str, *, union: str) -> None:
        """Name one object branch of a union, or explain why it has no name."""
        if branch.get("type") != "object" or is_open_map(branch):
            # A non-object branch, or an open map, renders inline.
            return
        if "title" in branch:
            # A titled object in a union is a declaration of its own - the
            # nullable geometry of a feature, say - so it is registered under
            # its title and the union renders as ``Geometry | null``.
            self.register(branch, name)
            return
        raise QgisSdkBridgeError(
            f"{union}: an untitled object inside a union has no generated type; "
            "give it a title or declare it as its own dataclass"
        )

    def name_for(self, schema: Mapping[str, Any]) -> str | None:
        """Return the registered name of an object schema, if it has one."""
        return self._names.get(id(schema))

    # -- rendering -----------------------------------------------------

    def type_name(self, schema: Mapping[str, Any], fallback: str) -> str:
        # ``fallback`` sits unused in the signature on purpose: a caller passes
        # the name it would give an unnamed object, but a schema that reaches
        # here unnamed is rendered inline instead. The generator travels with the
        # render so a union of titled objects keeps its interfaces - without it
        # ``layers.get`` answered ``Record<string, unknown> | Record<string, unknown>``
        # and a page could not read a field off the reply it just validated.
        return self.name_for(schema) or inline_type(schema, self)

    def accepts(self, schema: Mapping[str, Any]) -> str:
        """Return the predicate ``call`` should use for this value.

        A named object schema becomes its generated validator; anything else
        (``null``, a bare string, an enum) becomes an inline predicate, wrapped in
        a lambda because ``call`` takes a function either way.
        """
        name = self.name_for(schema)
        if name is not None:
            return name
        # The generator travels with the predicate for the same reason it does
        # with the type: a union of titled objects validated as ``isRecord`` and
        # nothing else, so `layers.get` accepted a reply with no `kind` at all.
        # The lambda carries ``strict`` itself, with the same default a named
        # validator has, because `call` hands it the flag for a request and
        # nothing for a response.
        predicate = inline_validator(schema, "candidate", self)
        return f"(candidate: unknown, strict = false) => {predicate}"

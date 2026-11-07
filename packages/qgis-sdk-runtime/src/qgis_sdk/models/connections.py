"""Registered data-source connections and authentication configurations.

decision-54 point 4 asks for ``connections`` - the provider connection registry
QGIS itself keeps in its settings - to be browsable and openable from a plugin,
with ``auth`` as configuration **ids, never secrets**. This module is where that
promise is enforced by construction:

* **A description carries no credential.** :class:`ConnectionInfo` answers the
  registry key, the provider that owns it and the *id* of the attached QGIS
  authentication configuration. The connection's URI is not a description: for
  a password-authenticated connection it is exactly where a password lives, so
  it never crosses this boundary. A password, a username, an expanded
  ``authcfg`` token and a decrypted configuration are refused by these models
  as fields that do not exist.
* **An authentication configuration is an id and a name.** That is what QGIS's
  own "base configs (not decrypted data)" answer contains, and it is all a page
  needs to show which configuration a connection uses. The secret half lives in
  the authentication database and is spent by QGIS, not read by this SDK.
* **A browse item is a table, a view or a schema.** ``kind`` names which one,
  the same discriminator pattern the layer kinds and renderers use, and
  ``geometries`` reuses the layer vocabulary (``point``, ``line``, ``polygon``,
  ``none``) so a page speaks one language about both.
* **A test is a verdict and, if not, why.** The :class:`ConnectionTest` shape is
  :class:`~qgis_sdk.models.features.ExpressionCheck`'s: a valid answer carries
  no message, an invalid one says why.

Everything here is frozen and validated at construction. The native adapter
redacts before it builds one of these; the wire schema refuses anything else.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, get_args

from qgis_sdk.models.layers import GeometryType

__all__ = [
    "AUTH_CONFIGURATION",
    "CONNECTION_INFO",
    "CONNECTION_ITEM",
    "CONNECTION_ITEM_KINDS",
    "CONNECTION_TEST",
    "ITEM_GEOMETRIES",
    "AuthConfiguration",
    "ConnectionInfo",
    "ConnectionItem",
    "ConnectionTest",
    "auth_configuration_from_wire",
    "connection_info_from_wire",
    "connection_item_from_wire",
    "connection_test_from_wire",
]

#: The geometries a browse item may name, in the layer vocabulary. A table with
#: several geometry columns carries several names.
ITEM_GEOMETRIES: tuple[str, ...] = get_args(GeometryType)

#: What a browse entry is. ``schema`` entries are browsed further; the rest are
#: opened (``raster`` by name refusal - see the service docs). Precedence when a
#: provider reports several flags for one table: a materialised view is a view,
#: a view is a view even when it has geometry, and a foreign table keeps its
#: place last.
CONNECTION_ITEM_KINDS: tuple[str, ...] = (
    "schema",
    "vector",
    "aspatial",
    "raster",
    "view",
    "materialized_view",
    "foreign",
)


def _non_empty(value: str, what: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"a connection's {what} is not empty")
    return value


@dataclass(frozen=True, slots=True)
class ConnectionInfo:
    """One registered connection: its name, its provider and nothing secret.

    ``auth_config`` is the id of the QGIS authentication configuration the
    connection spends - seven characters that reference a secret, never the
    secret itself. ``None`` means the connection authenticates some other way
    (a local file, a service file, a password QGIS stores in its own settings),
    and this description says which rather than exposing which.
    """

    name: str
    provider: str
    auth_config: str | None = None

    def __post_init__(self) -> None:
        _non_empty(self.name, "name")
        _non_empty(self.provider, "provider")
        if self.auth_config is not None:
            _non_empty(self.auth_config, "auth_config")

    def to_wire(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "provider": self.provider,
            "auth_config": self.auth_config,
        }

    @classmethod
    def from_wire(cls, value: Any) -> ConnectionInfo:
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise TypeError("a connection description is an object")
        auth_config = value.get("auth_config")
        return cls(
            name=str(value["name"]),
            provider=str(value["provider"]),
            auth_config=None if auth_config is None else str(auth_config),
        )


@dataclass(frozen=True, slots=True)
class ConnectionItem:
    """One entry of a connection's browse: a schema, a table or a view.

    ``schema`` is empty for backends that have no schemas (a GeoPackage is one
    file) and named for the ones that do. ``geometries`` names the geometry
    columns in the layer vocabulary, empty for a schema entry or an aspatial
    table.
    """

    name: str
    schema: str
    kind: str
    geometries: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _non_empty(self.name, "name")
        if not isinstance(self.schema, str):
            raise TypeError("a browse item's schema is a string")
        if self.kind not in CONNECTION_ITEM_KINDS:
            raise ValueError(
                f"a browse item kind is one of {', '.join(CONNECTION_ITEM_KINDS)}, "
                f"not {self.kind!r}"
            )
        for geometry in self.geometries:
            if geometry not in ITEM_GEOMETRIES:
                raise ValueError(
                    f"a browse item geometry is one of {', '.join(ITEM_GEOMETRIES)}, "
                    f"not {geometry!r}"
                )
        if self.kind == "schema" and (self.schema or self.geometries):
            raise ValueError("a schema entry has no schema of its own and no geometry")

    def to_wire(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "schema": self.schema,
            "kind": self.kind,
            "geometries": list(self.geometries),
        }

    @classmethod
    def from_wire(cls, value: Any) -> ConnectionItem:
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise TypeError("a browse item is an object")
        return cls(
            name=str(value["name"]),
            schema=str(value["schema"]),
            kind=str(value["kind"]),
            geometries=tuple(str(g) for g in value.get("geometries", ())),
        )


@dataclass(frozen=True, slots=True)
class ConnectionTest:
    """The answer to "does this connection open": a verdict and, if not, why.

    The shape is :class:`ExpressionCheck`'s, because the question is the same
    shape: one boolean a page can show, and a message only when it is false.
    The message is the provider's own refusal, already free of the connection's
    URI (a refusal string can quote what it refused).
    """

    valid: bool
    message: str | None = None

    def __post_init__(self) -> None:
        if self.valid and self.message is not None:
            raise ValueError("a valid connection carries no message")
        if not self.valid and not self.message:
            raise ValueError("an invalid connection says why")

    def to_wire(self) -> dict[str, Any]:
        return {"valid": self.valid, "message": self.message}

    @classmethod
    def from_wire(cls, value: Any) -> ConnectionTest:
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise TypeError("a connection test is an object")
        message = value.get("message")
        return cls(
            valid=bool(value["valid"]),
            message=None if message is None else str(message),
        )


@dataclass(frozen=True, slots=True)
class AuthConfiguration:
    """One authentication configuration: the id it is spent by and its name.

    Nothing else is modelled on purpose. A configuration's method, its URI and
    its secret live in the authentication database and are spent by QGIS when a
    connection opens; a page names them, it never reads them.
    """

    id: str
    name: str

    def __post_init__(self) -> None:
        _non_empty(self.id, "id")
        _non_empty(self.name, "name")

    def to_wire(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name}

    @classmethod
    def from_wire(cls, value: Any) -> AuthConfiguration:
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise TypeError("an auth configuration is an object")
        return cls(id=str(value["id"]), name=str(value["name"]))


# -- the wire shapes ----------------------------------------------------------

_NULLABLE_STRING: dict[str, Any] = {"anyOf": [{"type": "string"}, {"type": "null"}]}


def _object(
    title: str, properties: Mapping[str, Any], required: tuple[str, ...]
) -> dict[str, Any]:
    return {
        "type": "object",
        "title": title,
        "properties": dict(properties),
        "required": list(required),
        "additionalProperties": False,
    }


CONNECTION_INFO = _object(
    "ConnectionInfo",
    {
        "name": {"type": "string", "pattern": r".*\S.*"},
        "provider": {"type": "string", "pattern": r".*\S.*"},
        "auth_config": _NULLABLE_STRING,
    },
    ("name", "provider", "auth_config"),
)

CONNECTION_ITEM = _object(
    "ConnectionItem",
    {
        "name": {"type": "string", "pattern": r".*\S.*"},
        "schema": {"type": "string"},
        "kind": {"enum": list(CONNECTION_ITEM_KINDS)},
        "geometries": {"type": "array", "items": {"enum": list(ITEM_GEOMETRIES)}},
    },
    ("name", "schema", "kind", "geometries"),
)

CONNECTION_TEST = _object(
    "ConnectionTest",
    {
        "valid": {"type": "boolean"},
        "message": _NULLABLE_STRING,
    },
    ("valid", "message"),
)

AUTH_CONFIGURATION = _object(
    "AuthConfiguration",
    {
        "id": {"type": "string", "pattern": r".*\S.*"},
        "name": {"type": "string", "pattern": r".*\S.*"},
    },
    ("id", "name"),
)


def connection_info_from_wire(value: Any) -> ConnectionInfo:
    """Return the connection ``value`` describes."""
    return ConnectionInfo.from_wire(value)


def connection_item_from_wire(value: Any) -> ConnectionItem:
    """Return the browse item ``value`` describes."""
    return ConnectionItem.from_wire(value)


def connection_test_from_wire(value: Any) -> ConnectionTest:
    """Return the connection test ``value`` describes."""
    return ConnectionTest.from_wire(value)


def auth_configuration_from_wire(value: Any) -> AuthConfiguration:
    """Return the auth configuration ``value`` describes."""
    return AuthConfiguration.from_wire(value)

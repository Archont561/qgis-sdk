"""Description objects: what a described plugin, action or stream serialises to."""

import json
from dataclasses import dataclass, field
from typing import (
    Any,
    Protocol,
    runtime_checkable,
)

from qgis_sdk.declarations._contract import PLUGIN_DESCRIPTION_SCHEMA_VERSION


def canonical_json(value: Any) -> str:
    """The one JSON form every description and fingerprint uses.

    Sorted keys and compact separators make two equal descriptions two equal
    strings, and ``allow_nan=False`` keeps a nonfinite number from becoming a
    token no JSON parser accepts.
    """
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _json_copy(value: Any) -> Any:
    """Return an independent JSON-compatible copy, refusing nonfinite numbers."""
    return json.loads(json.dumps(value, allow_nan=False))


@runtime_checkable
class Description(Protocol):
    """What every description object offers, whatever it describes.

    ``PluginDescription``, ``AlgorithmDescription``, ``JobDescription`` and
    ``ProviderDescription`` all satisfy it; generators and the bridge consume
    this shape rather than one of the concrete types.
    """

    @property
    def id(self) -> str: ...

    @property
    def title(self) -> str: ...

    @property
    def schema_version(self) -> int: ...

    def to_dict(self) -> dict[str, Any]: ...

    def to_json(self) -> str: ...


@dataclass(frozen=True)
class ActionDescription:
    """Serializable action structure; handler is a binding name, not a callable."""

    id: str
    title: str
    handler: str
    request: dict[str, Any]
    result: dict[str, Any]
    # UI bindings are introspection metadata, not part of the bridge contract.
    bindings: tuple[Any, ...] = field(default=(), repr=False, compare=False)
    wires: tuple[Any, ...] = field(default=(), repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        """Return the unchanged bridge representation (without UI bindings)."""
        return _json_copy(
            {
                "id": self.id,
                "title": self.title,
                "handler": self.handler,
                "request": self.request,
                "result": self.result,
            }
        )


@dataclass(frozen=True)
class StreamDescription:
    """Serializable stream structure: a request in, declared event kinds out.

    ``events`` maps each declared kind to the schema of its payload. There is no
    ``result``: the reply to a subscription is the protocol's acknowledgement,
    not something an author declares (decision-28).
    """

    id: str
    title: str
    handler: str
    request: dict[str, Any]
    events: dict[str, dict[str, Any]]
    wires: tuple[Any, ...] = field(default=(), repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        """Return the unchanged stream wire representation."""
        return _json_copy(
            {
                "id": self.id,
                "title": self.title,
                "handler": self.handler,
                "request": self.request,
                "events": self.events,
            }
        )


@dataclass(frozen=True)
class PluginDescription:
    """Version 1 description, independent of SDK and future bridge versions."""

    id: str
    title: str
    actions: tuple[ActionDescription, ...]
    schema_version: int = PLUGIN_DESCRIPTION_SCHEMA_VERSION
    streams: tuple[StreamDescription, ...] = ()
    # Unified introspection may attach host bindings without altering the wire.
    bindings: Any = field(default=None, repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        """Return the transport representation."""
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "title": self.title,
            "actions": [action.to_dict() for action in self.actions],
            "streams": [item.to_dict() for item in self.streams],
        }

    def to_json(self) -> str:
        """Produce canonical key ordering with no nonfinite JSON numbers."""
        return canonical_json(self.to_dict())

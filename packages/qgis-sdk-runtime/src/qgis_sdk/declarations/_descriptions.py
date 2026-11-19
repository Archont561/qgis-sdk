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

    Args:
        value: The JSON-compatible structure to serialise.

    Returns:
        Its canonical JSON text.

    Raises:
        ValueError: ``value`` holds a nonfinite number, or something that is not
            JSON at all.
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
    def id(self) -> str:
        """The identifier the thing is invoked or subscribed to by."""

    @property
    def title(self) -> str:
        """The label a host shows for it."""

    @property
    def schema_version(self) -> int:
        """The description schema the object speaks."""

    def to_dict(self) -> dict[str, Any]:
        """The transport representation, ready to be serialised."""

    def to_json(self) -> str:
        """The transport representation as canonical JSON."""


@dataclass(frozen=True)
class ActionDescription:
    """Serializable action structure; handler is a binding name, not a callable.

    Attributes:
        id: The identifier the action is invoked by, unique within its plugin.
        title: The label a host shows for it, in a menu or a button.
        handler: The name of the binding that receives the call. It is a name
            rather than a callable, so the description stays serialisable and a
            generated client can name the same operation.
        request: The JSON schema of the arguments the action takes.
        result: The JSON schema of the value it returns.
        bindings: The UI bindings it was declared with, as introspection
            metadata. Not part of the wire representation.
        wires: The wires it declared, in the same sense as ``bindings``.
    """

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

    Attributes:
        id: The identifier the stream is subscribed to by.
        title: The label a host shows for it.
        handler: The name of the binding that receives the subscription.
        request: The JSON schema of what the subscriber sends to open it.
        events: Each declared event kind, mapped to the JSON schema of its
            payload.
        wires: The wires it declared, as introspection metadata rather than as
            part of the wire representation.
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
    """Version 1 description, independent of SDK and future bridge versions.

    Attributes:
        id: The plugin's identifier, which its actions are namespaced under.
        title: The label a host shows for the plugin.
        actions: Every action the plugin declares, in declaration order.
        schema_version: The description schema the object speaks, so a host can
            refuse one it does not know rather than misread it.
        streams: Every stream the plugin declares.
        bindings: Host bindings attached by unified introspection. They are
            carried alongside the wire representation, not inside it.
    """

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

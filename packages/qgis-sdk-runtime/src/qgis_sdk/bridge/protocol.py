"""The versioned bridge envelope, and the JSON rules behind it.

An envelope is the only thing that crosses the transport: the protocol version,
a call id, an operation id and a payload. It names no Python object, no
attribute path and no view - the host knows which view is calling from the
transport it owns, so a claim inside the payload cannot change who the caller is
(decision-9, decision-18).

The protocol version is deliberately not the package version. A wire break bumps
it, a package release does not, and the two languages agree on it the way they
agree on ``PLUGIN_DESCRIPTION_SCHEMA_VERSION``.

Subscriptions (``kind: "subscribe"``) did not bump it. A subscription is a call
a client chooses to make, and the host only sends frames for a subscription that
client opened, so a client which never subscribes still sees nothing but replies
to its own calls. The ordering, buffering and termination rules that go with
those frames live in :mod:`qgis_sdk.bridge.streams`.

Version 2 added ``kind: "ack"`` (decision-59 point 3): a client acknowledges
each stream frame it delivered, and the host keeps at most
:data:`~qgis_sdk.bridge.streams.MAX_IN_FLIGHT_FRAMES` frames ahead of the
acknowledgement before it stops advancing the source. A version-1 client never
sends one, so the host could not tell a slow consumer from a dead one and had no
answer but a bounded queue and a ``gap``; that is a wire change, not a package
release, and it moved this number and nothing else.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from qgis_sdk.declarations import STREAM_EVENT_KINDS
from qgis_sdk.models.errors import QgisSdkBridgeError, QgisSdkBridgeProtocolError

BRIDGE_PROTOCOL_VERSION = 2

#: Ceiling for one message, in bytes of JSON (decision-59 point 1). A payload
#: above it is not truncated and not sent: the producer hands over a
#: ``BlobRef`` instead (``HostAuthority.inline_or_blob``), and the dispatcher
#: refuses a reply that still exceeds the ceiling rather than shipping a
#: message a page was never designed to parse.
MAX_INLINE_BYTES = 256 * 1024

#: Version of the curated host surface (:mod:`qgis_sdk.bridge.host`). It is
#: advertised in the handshake and carried by the generated TypeScript module, so
#: a page can tell which host surface it is talking to before its first call.
#: Additive changes only: a breaking rename is a new version, and the protocol
#: version is untouched by it because the envelope did not change.
HOST_SCHEMA_VERSION = 1

MAX_CALL_ID_LENGTH = 128
MAX_WIRE_DEPTH = 32


_OPERATION_ID = re.compile(r"[a-zA-Z][a-zA-Z0-9_.-]*")


class BridgeErrorCode(str, Enum):
    """Codes a failure reply may carry.

    A client switches on these, never on the message text: the text is for a
    human reading a log, the code is the contract.
    """

    UNKNOWN_OPERATION = "unknown_operation"
    NOT_AUTHORIZED = "not_authorized"
    STALE_GENERATION = "stale_generation"
    INVALID_PAYLOAD = "invalid_payload"
    INVALID_MESSAGE = "invalid_bridge_message"
    INVALID_PROTOCOL = "invalid_protocol"
    NOT_SERIALIZABLE = "not_serializable"
    OPERATION_FAILED = "operation_failed"
    CANCELLED = "cancelled"
    LIMIT_EXCEEDED = "limit_exceeded"
    INVALID_RESULT = "invalid_result"
    # Refusals an operation raises itself: the handle or grant a call
    # named is not usable by this view, and the view can act on which.
    UNKNOWN_HANDLE = "unknown_handle"
    STALE_HANDLE = "stale_handle"
    GRANT_REFUSED = "grant_refused"


def to_wire(value: Any, *, depth: int = 0) -> Any:
    """Return a JSON-safe copy of ``value``, or refuse it.

    Only JSON primitives, lists and string-keyed mappings survive. Refusing here,
    at the boundary, is what makes "no raw Qt/QGIS object crosses the wire" a
    property of the code instead of a rule authors are asked to remember.
    """
    if depth > MAX_WIRE_DEPTH:
        raise QgisSdkBridgeError(f"value is nested deeper than {MAX_WIRE_DEPTH}")
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise QgisSdkBridgeError("non-finite floats have no JSON representation")
        return value
    if isinstance(value, Mapping):
        copy: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise QgisSdkBridgeError(f"mapping key {key!r} is not a string")
            copy[key] = to_wire(item, depth=depth + 1)
        return copy
    if isinstance(value, (list, tuple)):
        return [to_wire(item, depth=depth + 1) for item in value]
    raise QgisSdkBridgeError(f"{type(value).__name__} is not wire-serializable")


@dataclass(frozen=True, slots=True)
class BridgeOperation:
    """One operation a view may call, declared rather than discovered.

    The id is the allowlist entry: there is no ``getattr`` path, no dotted
    attribute walk and no way to reach a Python callable that was not declared
    here with a handler.

    ``request`` and ``result`` are the schemas the declaration already produced.
    They are carried here so the allowlist, the handshake and the generated
    client all read one object (decision-26): a host that validates inputs
    against a different shape than the one it advertises has a contract that
    only looks like a contract. An operation registered by hand may leave both
    out, and is then described by its id and title alone.

    A stream declares ``events`` instead of ``result`` (decision-28): a map from
    event kind to the schema of that kind's payload. An operation answers with a
    result or streams events, never both.
    """

    id: str
    title: str
    request: Mapping[str, Any] | None = None
    result: Mapping[str, Any] | None = None
    events: Mapping[str, Mapping[str, Any]] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not _OPERATION_ID.fullmatch(self.id):
            raise QgisSdkBridgeError(
                f"Invalid operation id {self.id!r}: use a letter followed by "
                "letters, digits, _, . or -"
            )
        if not isinstance(self.title, str) or not self.title.strip():
            raise QgisSdkBridgeError(f"{self.id}: title must be a nonempty string")
        for name in ("request", "result"):
            schema = getattr(self, name)
            if schema is not None and not isinstance(schema, Mapping):
                raise QgisSdkBridgeError(
                    f"{self.id}: {name} must be a schema object or None"
                )
        if self.events is not None:
            self._check_events(self.events)

    def _check_events(self, events: Any) -> None:
        if self.result is not None:
            raise QgisSdkBridgeError(
                f"{self.id}: an operation declares a result or events, not both"
            )
        if not isinstance(events, Mapping):
            raise QgisSdkBridgeError(f"{self.id}: events must be a mapping")
        if not events:
            raise QgisSdkBridgeError(
                f"{self.id}: a stream declares at least one event kind"
            )
        for kind, schema in events.items():
            if kind not in STREAM_EVENT_KINDS:
                raise QgisSdkBridgeError(
                    f"{self.id}: {kind!r} is not a stream event kind"
                )
            if not isinstance(schema, Mapping):
                raise QgisSdkBridgeError(
                    f"{self.id}: events.{kind} must be a schema object"
                )

    def to_dict(self) -> dict[str, Any]:
        """Return the advertised description of this operation."""
        described: dict[str, Any] = {"id": self.id, "title": self.title}
        if self.request is not None:
            described["request"] = to_wire(self.request)
        if self.result is not None:
            described["result"] = to_wire(self.result)
        if self.events is not None:
            described["events"] = to_wire(self.events)
        return described


@dataclass(frozen=True, slots=True)
class InvokeEnvelope:
    """A parsed invocation: the only request shape the dispatcher accepts."""

    call_id: str
    operation: str
    payload: Mapping[str, Any]

    @classmethod
    def parse(cls, raw: Any) -> InvokeEnvelope:
        """Validate ``raw`` as an invocation, refusing anything else.

        Every refusal is a :class:`QgisSdkBridgeProtocolError`; the dispatcher
        catches it and answers with the call id when one can be read, so a
        malformed envelope still correlates instead of hanging the view.
        """
        if not isinstance(raw, Mapping):
            raise QgisSdkBridgeProtocolError("An invocation must be an object")
        protocol = raw.get("protocol")
        if protocol != BRIDGE_PROTOCOL_VERSION:
            raise QgisSdkBridgeProtocolError(
                f"Unsupported bridge protocol: {protocol!r}; "
                f"this host speaks {BRIDGE_PROTOCOL_VERSION}"
            )
        call_id = peek_call_id(raw)
        if call_id is None:
            raise QgisSdkBridgeProtocolError(
                f"call_id must be a nonempty string of at most "
                f"{MAX_CALL_ID_LENGTH} characters"
            )
        operation = raw.get("operation")
        if not isinstance(operation, str) or not operation:
            raise QgisSdkBridgeProtocolError("operation must be a nonempty string")
        payload = raw.get("payload", {})
        if not isinstance(payload, Mapping):
            raise QgisSdkBridgeProtocolError("payload must be an object")
        return cls(call_id=call_id, operation=operation, payload=payload)


def peek_call_id(raw: Any) -> str | None:
    """Return a usable call id from ``raw``, or ``None``.

    Used on both sides of validation: a refusal about an unsupported protocol or
    an unknown operation still has to name the call it refuses.
    """
    if not isinstance(raw, Mapping):
        return None
    call_id = raw.get("call_id")
    if not isinstance(call_id, str) or not call_id:
        return None
    if len(call_id) > MAX_CALL_ID_LENGTH:
        return None
    return call_id


def success(call_id: str, value: Any) -> dict[str, Any]:
    """Build a success reply, refusing a value that cannot cross the wire."""
    return {
        "protocol": BRIDGE_PROTOCOL_VERSION,
        "call_id": call_id,
        "ok": True,
        "value": to_wire(value),
    }


def failure(call_id: str, code: BridgeErrorCode, message: str) -> dict[str, Any]:
    """Build a failure reply: a code the client switches on, and a message."""
    return {
        "protocol": BRIDGE_PROTOCOL_VERSION,
        "call_id": call_id,
        "ok": False,
        "error": {"code": code.value, "message": message[:200]},
    }

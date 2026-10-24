"""The narrow endpoint every bridge call passes through.

One dispatcher owns one view's traffic. It decides, in this order, whether a
call is allowed to exist at all: protocol, session generation, authorization,
allowlist, payload, handler, and finally a reply that is itself JSON-safe
(decision-9, decision-18).

Two choices are deliberate.

*Authorization runs before the allowlist lookup.* A caller that is not allowed
to do a thing should not learn whether the host could have done it, so a
forbidden call and an unknown call are answered with different codes only when
the caller is authorized to learn the difference.

*A handler that raises does not raise into the transport.* Its failure becomes
an error reply carrying the same call id, because an exception crossing Qt's
boundary loses the correlation and leaves the view waiting for a reply that
never arrives. Messages from :class:`QgisSdkError` are forwarded - they are
written for users and name no host objects - while anything else is replaced by
a fixed message, since an unexpected exception can carry paths, handles or
native repr into a web view.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from qgis_sdk.bridge.protocol import (
    BRIDGE_PROTOCOL_VERSION,
    BridgeErrorCode,
    BridgeOperation,
    InvokeEnvelope,
    failure,
    peek_call_id,
    success,
    to_wire,
)
from qgis_sdk.models.errors import (
    QgisSdkBridgeError,
    QgisSdkBridgeProtocolError,
    QgisSdkError,
)


@dataclass(frozen=True, slots=True)
class ViewBinding:
    """The trusted identity of one view, minted by the host.

    Nothing here is read from the payload. A client that sends its own view id
    or generation is not disagreeing with the host, it is being ignored.
    """

    view_id: str
    origin: str
    generation: int


Handler = Callable[[Mapping[str, Any]], Any]
Authorizer = Callable[[ViewBinding, str], bool]


class Dispatcher:
    """Route allowlisted operations for one host, per view generation."""

    def __init__(
        self,
        *,
        description: Mapping[str, Any] | None = None,
        authorize: Authorizer | None = None,
    ) -> None:
        self._description = None if description is None else to_wire(description)
        self._authorize = authorize
        self._handlers: dict[str, Handler] = {}
        self._operations: dict[str, BridgeOperation] = {}
        self._generation = 0

    @property
    def generation(self) -> int:
        """The runtime generation every live binding must match."""
        return self._generation

    def register(self, operation: BridgeOperation, handler: Handler) -> None:
        """Allowlist one operation and bind it to its handler."""
        if operation.id in self._handlers:
            raise QgisSdkBridgeError(f"duplicate operation id {operation.id!r}")
        if not callable(handler):
            raise QgisSdkBridgeError(f"{operation.id}: handler must be callable")
        self._operations[operation.id] = operation
        self._handlers[operation.id] = handler

    def operations(self) -> tuple[BridgeOperation, ...]:
        """Return the allowlisted operations in id order."""
        return tuple(self._operations[key] for key in sorted(self._operations))

    def bind(self, *, view_id: str, origin: str) -> ViewBinding:
        """Mint the binding for a view that just connected."""
        if not isinstance(view_id, str) or not view_id.strip():
            raise QgisSdkBridgeError("view_id must be a nonempty string")
        if not isinstance(origin, str) or not origin.strip():
            raise QgisSdkBridgeError("origin must be a nonempty string")
        return ViewBinding(view_id=view_id, origin=origin, generation=self._generation)

    def advance_generation(self) -> int:
        """Start a new runtime generation, invalidating every existing binding.

        Called when the plugin runtime is replaced. A view that reconnects gets a
        fresh binding; a view that keeps using the old one is refused with
        ``stale_generation`` rather than served state from a runtime that no
        longer exists.
        """
        self._generation += 1
        return self._generation

    def handshake(self, *, view_id: str, origin: str) -> tuple[ViewBinding, dict]:
        """Bind a view and return the reply that completes the handshake.

        The reply carries the protocol version, the generation the view must
        present later through the host (never through the payload), and the
        plugin description so the frontend can render forms without a second
        call.
        """
        binding = self.bind(view_id=view_id, origin=origin)
        reply = {
            "protocol": BRIDGE_PROTOCOL_VERSION,
            "generation": binding.generation,
            "plugin": self._description,
            "operations": [operation.to_dict() for operation in self.operations()],
        }
        return binding, to_wire(reply)

    def dispatch(
        self,
        binding: ViewBinding,
        raw: Mapping[str, Any],
        *,
        cancelled: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        """Answer one invocation with a reply, never with an exception."""
        call_id = peek_call_id(raw) or ""
        try:
            envelope = InvokeEnvelope.parse(raw)
        except QgisSdkBridgeProtocolError as error:
            return failure(call_id, BridgeErrorCode.INVALID_MESSAGE, str(error))
        call_id = envelope.call_id

        if binding.generation != self._generation:
            return failure(
                call_id,
                BridgeErrorCode.STALE_GENERATION,
                "This view belongs to a runtime generation that no longer exists",
            )
        if not self._is_authorized(binding, envelope.operation):
            return failure(
                call_id,
                BridgeErrorCode.NOT_AUTHORIZED,
                "This view is not authorized for that operation",
            )
        handler = self._handlers.get(envelope.operation)
        if handler is None:
            return failure(
                call_id,
                BridgeErrorCode.UNKNOWN_OPERATION,
                f"No operation {envelope.operation!r} is exposed by this plugin",
            )
        if cancelled is not None and cancelled():
            return failure(
                call_id, BridgeErrorCode.CANCELLED, "The operation was cancelled"
            )
        try:
            payload = to_wire(envelope.payload)
        except QgisSdkBridgeError as error:
            return failure(call_id, BridgeErrorCode.INVALID_PAYLOAD, str(error))

        try:
            value = handler(payload)
        except QgisSdkError as error:
            return failure(call_id, BridgeErrorCode.OPERATION_FAILED, str(error))
        except Exception:  # noqa: BLE001 - a reply must always be produced
            return failure(
                call_id,
                BridgeErrorCode.OPERATION_FAILED,
                "The operation failed; the host recorded the details",
            )
        try:
            return success(call_id, value)
        except QgisSdkBridgeError as error:
            return failure(call_id, BridgeErrorCode.NOT_SERIALIZABLE, str(error))

    def _is_authorized(self, binding: ViewBinding, operation: str) -> bool:
        if self._authorize is None:
            return False
        return bool(self._authorize(binding, operation))

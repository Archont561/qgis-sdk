"""The narrow endpoint every bridge call passes through.

One dispatcher owns one view's traffic. It decides, in this order, whether a
call is allowed to exist at all: protocol, session generation, authorization,
allowlist, payload, handler, and finally a reply that is itself JSON-safe
(decision-9, decision-18). Subscriptions are decided in the same order and stop
at the same place: opening one is a call, and the frames that follow belong to
the view and generation that opened it.

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

The dispatcher is driven, never threaded. :meth:`pump` is what the Qt adapter
calls on a timer to collect the frames waiting for a view, so ordering and
bounded buffering are decided by ordinary code that a test can run in a loop,
not by whatever the transport happens to do with a callback.
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
from qgis_sdk.bridge.streams import (
    MAX_FRAMES_PER_PUMP,
    MAX_SUBSCRIPTIONS_PER_VIEW,
    DisposalRequest,
    StreamEventType,
    StreamSource,
    Subscription,
    SubscriptionRequest,
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
        self._streams: dict[str, StreamSource] = {}
        self._operations: dict[str, BridgeOperation] = {}
        self._subscriptions: dict[str, Subscription] = {}
        self._counter = 0
        self._generation = 0

    @property
    def generation(self) -> int:
        """The runtime generation every live binding must match."""
        return self._generation

    def register(self, operation: BridgeOperation, handler: Handler) -> None:
        """Allowlist one operation and bind it to its handler."""
        if operation.id in self._handlers or operation.id in self._streams:
            raise QgisSdkBridgeError(f"duplicate operation id {operation.id!r}")
        if not callable(handler):
            raise QgisSdkBridgeError(f"{operation.id}: handler must be callable")
        self._operations[operation.id] = operation
        self._handlers[operation.id] = handler

    def register_stream(
        self, operation: BridgeOperation, factory: StreamSource
    ) -> None:
        """Allowlist one streaming operation and its source factory.

        The factory is called once per subscription with the already-checked
        payload and returns an iterator of events. Nothing about it is reachable
        from the wire: the view names an operation id, never a callable.

        A factory may return ``None`` instead, for a stream a host pushes into
        with :meth:`emit` rather than allows to be pulled - a Qt task reporting
        progress, for instance. Such a subscription ends when it is disposed or
        when its buffer overruns, never by itself.
        """
        if operation.id in self._handlers or operation.id in self._streams:
            raise QgisSdkBridgeError(f"duplicate operation id {operation.id!r}")
        if not callable(factory):
            raise QgisSdkBridgeError(f"{operation.id}: factory must be callable")
        self._operations[operation.id] = operation
        self._streams[operation.id] = factory

    def operations(self) -> tuple[BridgeOperation, ...]:
        """Return the allowlisted operations in id order."""
        return tuple(self._operations[key] for key in sorted(self._operations))

    def subscriptions(self) -> tuple[Subscription, ...]:
        """Return the live subscriptions in id order, for tests and teardown."""
        return tuple(self._subscriptions[key] for key in sorted(self._subscriptions))

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
        longer exists. Subscriptions die with the generation: their sources are
        closed, so a generator's ``finally`` block still runs, and no frame is
        delivered to a view that can no longer be trusted to interpret it.
        """
        self._dispose_all()
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
        """Answer one call with a reply, never with an exception.

        ``kind`` selects the call: an invocation by default, a subscription or
        its disposal otherwise. The three share the same refusals, so a
        subscription can never be opened through a path an invocation cannot
        take.
        """
        call_id = peek_call_id(raw) or ""
        kind = raw.get("kind", "invoke") if isinstance(raw, Mapping) else "invoke"
        if kind == "subscribe":
            return self._subscribe(binding, raw, cancelled=cancelled)
        if kind == "unsubscribe":
            return self._unsubscribe(binding, raw)
        if kind != "invoke":
            return failure(
                call_id,
                BridgeErrorCode.INVALID_MESSAGE,
                f"Unknown call kind {kind!r}",
            )
        try:
            envelope = InvokeEnvelope.parse(raw)
        except QgisSdkBridgeProtocolError as error:
            return failure(call_id, BridgeErrorCode.INVALID_MESSAGE, str(error))
        call_id = envelope.call_id

        refusal = self._refuse(binding, envelope.operation)
        if refusal is not None:
            return refusal(call_id)
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

    def pump(
        self, binding: ViewBinding, *, limit: int = MAX_FRAMES_PER_PUMP
    ) -> list[dict[str, Any]]:
        """Collect the frames waiting for ``binding``'s view, oldest first.

        Only the view and generation that opened a subscription can collect its
        frames. A stale binding gets nothing at all - not even a terminal frame -
        because delivering state to a runtime that no longer exists is exactly
        what the generation check is for.
        """
        frames: list[dict[str, Any]] = []
        for subscription in self.subscriptions():
            if (
                subscription.view_id != binding.view_id
                or subscription.generation != binding.generation
            ):
                continue
            subscription.pull(limit)
            frames.extend(subscription.drain(limit))
        self._forget_drained()
        return frames

    def emit(
        self,
        subscription_id: str,
        payload: Any,
        *,
        kind: StreamEventType = StreamEventType.DATA,
    ) -> bool:
        """Push one event into an open subscription.

        This is the adapter's entry point for events that are not produced by
        pulling - a Qt task's progress signal, for instance. A full queue is
        reported to the client as a ``gap`` instead of being absorbed silently.
        """
        subscription = self._subscriptions.get(subscription_id)
        if subscription is None:
            return False
        return subscription.emit(payload, kind=kind)

    def dispose(self, binding: ViewBinding) -> int:
        """Close every subscription belonging to ``binding``'s view."""
        disposal = [
            subscription
            for subscription in self._subscriptions.values()
            if subscription.view_id == binding.view_id
        ]
        for subscription in disposal:
            subscription.close_source()
            self._subscriptions.pop(subscription.id, None)
        return len(disposal)

    def _subscribe(
        self,
        binding: ViewBinding,
        raw: Mapping[str, Any],
        *,
        cancelled: Callable[[], bool] | None,
    ) -> dict[str, Any]:
        call_id = peek_call_id(raw) or ""
        try:
            request = SubscriptionRequest.parse(raw)
        except QgisSdkBridgeProtocolError as error:
            return failure(call_id, BridgeErrorCode.INVALID_MESSAGE, str(error))
        call_id = request.call_id

        refusal = self._refuse(binding, request.operation)
        if refusal is not None:
            return refusal(call_id)
        factory = self._streams.get(request.operation)
        if factory is None:
            return failure(
                call_id,
                BridgeErrorCode.UNKNOWN_OPERATION,
                f"No streaming operation {request.operation!r} is exposed",
            )
        if cancelled is not None and cancelled():
            return failure(
                call_id, BridgeErrorCode.CANCELLED, "The subscription was cancelled"
            )
        if self._subscriptions_for(binding) >= MAX_SUBSCRIPTIONS_PER_VIEW:
            return failure(
                call_id,
                BridgeErrorCode.LIMIT_EXCEEDED,
                f"This view already holds {MAX_SUBSCRIPTIONS_PER_VIEW} subscriptions",
            )
        try:
            payload = to_wire(request.payload)
        except QgisSdkBridgeError as error:
            return failure(call_id, BridgeErrorCode.INVALID_PAYLOAD, str(error))

        try:
            source = factory(payload)
        except QgisSdkError as error:
            return failure(call_id, BridgeErrorCode.OPERATION_FAILED, str(error))
        except Exception:  # noqa: BLE001 - a reply must always be produced
            return failure(
                call_id,
                BridgeErrorCode.OPERATION_FAILED,
                "The subscription failed; the host recorded the details",
            )
        if source is not None and not hasattr(source, "__next__"):
            return failure(
                call_id,
                BridgeErrorCode.OPERATION_FAILED,
                "The stream did not produce an iterator of events",
            )

        self._counter += 1
        subscription = Subscription(
            id=f"s{self._counter}",
            view_id=binding.view_id,
            generation=binding.generation,
            operation=request.operation,
        )
        subscription.attach(source)
        self._subscriptions[subscription.id] = subscription
        return success(
            call_id,
            {"subscription_id": subscription.id, "capacity": subscription.capacity},
        )

    def _unsubscribe(self, binding: ViewBinding, raw: Mapping[str, Any]) -> dict[str, Any]:
        """Dispose one subscription, idempotently.

        A second disposal of the same id - or one that arrives for a
        subscription that already ended - is answered with ``disposed: false``
        rather than an error: closing twice is what a closing UI does, and a
        refusal would turn a harmless race into a failed call.
        """
        call_id = peek_call_id(raw) or ""
        try:
            request = DisposalRequest.parse(raw)
        except QgisSdkBridgeProtocolError as error:
            return failure(call_id, BridgeErrorCode.INVALID_MESSAGE, str(error))
        call_id = request.call_id
        if binding.generation != self._generation:
            return failure(
                call_id,
                BridgeErrorCode.STALE_GENERATION,
                "This view belongs to a runtime generation that no longer exists",
            )
        subscription = self._subscriptions.get(request.subscription_id)
        if subscription is None:
            return success(
                call_id, {"subscription_id": request.subscription_id, "disposed": False}
            )
        if subscription.view_id != binding.view_id:
            return failure(
                call_id,
                BridgeErrorCode.NOT_AUTHORIZED,
                "This subscription belongs to a different view",
            )
        if not self._is_authorized(binding, subscription.operation):
            return failure(
                call_id,
                BridgeErrorCode.NOT_AUTHORIZED,
                "This view is not authorized for that operation",
            )
        subscription.close_source()
        self._subscriptions.pop(subscription.id, None)
        return success(
            call_id, {"subscription_id": subscription.id, "disposed": True}
        )

    def _refuse(
        self, binding: ViewBinding, operation: str
    ) -> Callable[[str], dict[str, Any]] | None:
        """Return the refusal for a call, or ``None`` when it may proceed."""
        if binding.generation != self._generation:
            return lambda call_id: failure(
                call_id,
                BridgeErrorCode.STALE_GENERATION,
                "This view belongs to a runtime generation that no longer exists",
            )
        if not self._is_authorized(binding, operation):
            return lambda call_id: failure(
                call_id,
                BridgeErrorCode.NOT_AUTHORIZED,
                "This view is not authorized for that operation",
            )
        return None

    def _subscriptions_for(self, binding: ViewBinding) -> int:
        return sum(
            1
            for subscription in self._subscriptions.values()
            if subscription.view_id == binding.view_id
        )

    def _forget_drained(self) -> None:
        for key in [
            key
            for key, subscription in self._subscriptions.items()
            if not subscription.open and subscription.queued == 0
        ]:
            self._subscriptions.pop(key, None)

    def _dispose_all(self) -> None:
        for subscription in self._subscriptions.values():
            subscription.close_source()
        self._subscriptions.clear()

    def _is_authorized(self, binding: ViewBinding, operation: str) -> bool:
        if self._authorize is None:
            return False
        return bool(self._authorize(binding, operation))

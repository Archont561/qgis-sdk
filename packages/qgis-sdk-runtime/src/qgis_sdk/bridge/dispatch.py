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

from collections.abc import Callable, Iterator, Mapping
from dataclasses import asdict, dataclass, is_dataclass
from typing import Any

from qgis_sdk.bridge.protocol import (
    BRIDGE_PROTOCOL_VERSION,
    HOST_SCHEMA_VERSION,
    BridgeErrorCode,
    BridgeOperation,
    InvokeEnvelope,
    failure,
    peek_call_id,
    success,
    to_wire,
)
from qgis_sdk.bridge.resources import Handle, HandleKind, ReleaseLedger
from qgis_sdk.bridge.schema import validate
from qgis_sdk.bridge.streams import (
    MAX_FRAMES_PER_PUMP,
    MAX_SUBSCRIPTIONS_PER_VIEW,
    DisposalRequest,
    PushSource,
    StreamEventType,
    StreamSink,
    StreamSource,
    Subscription,
    SubscriptionRequest,
)
from qgis_sdk.declarations import WIRE_KIND_KEYWORD, WIRE_VALUE_METHOD
from qgis_sdk.models.errors import (
    QgisSdkBridgeError,
    QgisSdkBridgeProtocolError,
    QgisSdkBridgeRefusalError,
    QgisSdkError,
)
from qgis_sdk.models.files import FILE_REF_KINDS, FileRef


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
#: A handler that needs to know who is calling: it receives the host-minted
#: binding first, because an operation that resolves a scoped handle has to
#: check it against the caller and must never take that identity from the payload.
BoundHandler = Callable[[ViewBinding, Mapping[str, Any]], Any]
BoundStreamSource = Callable[
    [ViewBinding, Mapping[str, Any]], Iterator[Mapping[str, Any]] | PushSource | None
]
Authorizer = Callable[[ViewBinding, str], bool]
Waker = Callable[[], None]
ThemeProvider = Callable[[], Mapping[str, Any] | None]
"""Reads the host's palette for the handshake's ``theme``; ``None`` means no theme.

Called on every handshake, so a page that reconnects after the user switched the
QGIS theme sees the new palette. The adapter supplies one that reads
``QApplication.palette()``; the dispatcher itself never imports Qt.
"""


class Dispatcher:
    """Route allowlisted operations for one host, per view generation."""

    def __init__(
        self,
        *,
        description: Mapping[str, Any] | None = None,
        authorize: Authorizer | None = None,
        ledger: ReleaseLedger | None = None,
        theme: ThemeProvider | None = None,
    ) -> None:
        self._description = None if description is None else to_wire(description)
        self._authorize = authorize
        self._theme = theme
        self._ledger = ledger if ledger is not None else ReleaseLedger()
        self._ledger.dispose_subscription = self._dispose_subscription
        self._handlers: dict[str, BoundHandler] = {}
        self._streams: dict[str, BoundStreamSource] = {}
        self._wakers: dict[str, Waker] = {}
        self._operations: dict[str, BridgeOperation] = {}
        self._subscriptions: dict[str, Subscription] = {}
        self._counter = 0
        self._generation = 0

    @classmethod
    def from_description(
        cls,
        description: Any,
        handlers: Mapping[str, Handler],
        *,
        streams: Mapping[str, Callable[..., Any]] | None = None,
        authorize: Authorizer | None = None,
        ledger: ReleaseLedger | None = None,
        theme: ThemeProvider | None = None,
    ) -> Dispatcher:
        """Build a dispatcher whose allowlist *is* the plugin description.

        This is the only wiring a plugin needs (decision-26): every declared
        action becomes one allowlisted operation carrying the schemas the
        declaration already produced, its handler is bound by action id, and the
        handshake advertises the same set the description names. A declared
        action without a handler is refused here rather than discovered as a
        missing operation by a view.

        Declared streams (decision-28) are wired the same way from ``streams``:
        the factory is bound by stream id, receives the validated request as
        keyword arguments and returns the iterator of events - or ``None`` for a
        stream the host pushes into.
        """
        advertised, actions, declared_streams = _description_parts(description)
        dispatcher = cls(
            description=advertised, authorize=authorize, ledger=ledger, theme=theme
        )
        for action in actions:
            operation_id = action["id"]
            handler = handlers.get(operation_id)
            if handler is None:
                raise QgisSdkBridgeError(
                    f"action {operation_id!r} is declared but has no handler"
                )
            if not callable(handler):
                raise QgisSdkBridgeError(
                    f"action {operation_id!r}: handler must be callable"
                )
            dispatcher.register(
                BridgeOperation(
                    id=operation_id,
                    title=action["title"],
                    request=action.get("request"),
                    result=action.get("result"),
                ),
                _keyword_handler(handler, action.get("request"), operation_id),
            )
        factories = streams or {}
        for declared in declared_streams:
            operation_id = declared["id"]
            factory = factories.get(operation_id)
            if factory is None:
                raise QgisSdkBridgeError(
                    f"stream {operation_id!r} is declared but has no stream factory"
                )
            if not callable(factory):
                raise QgisSdkBridgeError(
                    f"stream {operation_id!r}: factory must be callable"
                )
            dispatcher.register_stream(
                BridgeOperation(
                    id=operation_id,
                    title=declared["title"],
                    request=declared.get("request"),
                    events=declared.get("events"),
                ),
                _keyword_source(factory, declared.get("request"), operation_id),
            )
        return dispatcher

    @classmethod
    def from_runtime(
        cls,
        runtime: Any,
        *,
        authorize: Authorizer | None = None,
        ledger: ReleaseLedger | None = None,
        theme: ThemeProvider | None = None,
    ) -> Dispatcher:
        """Build from a started runtime: its description and its bound handlers.

        ``PluginRuntime.actions`` and ``PluginRuntime.streams`` are already keyed
        by operation id and already bound to the instance, so nothing here needs
        to know a method name.
        """
        return cls.from_description(
            runtime.description,
            runtime.actions,
            streams=getattr(runtime, "streams", None),
            authorize=authorize,
            ledger=ledger,
            theme=theme,
        )

    @property
    def generation(self) -> int:
        """The runtime generation every live binding must match."""
        return self._generation

    def register(self, operation: BridgeOperation, handler: Handler) -> None:
        """Allowlist one operation and bind it to its handler."""
        self._check_registration(operation, handler, "handler")
        self._operations[operation.id] = operation
        self._handlers[operation.id] = lambda binding, payload: handler(payload)

    def register_bound(self, operation: BridgeOperation, handler: BoundHandler) -> None:
        """Allowlist one operation whose handler receives the caller's binding.

        The binding is the one the host minted for the channel the call arrived
        on; nothing in it came from the payload. This is how an operation that
        takes a scoped handle checks the handle belongs to the view using it.
        """
        self._check_registration(operation, handler, "handler")
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
        when its buffer overruns, never by itself. Or it may return a
        :class:`~qgis_sdk.bridge.streams.PushSource`, which the dispatcher
        starts with a sink once the subscription exists: the source then ends
        the stream itself when its work completes or fails.
        """
        self._check_registration(operation, factory, "factory")
        self._operations[operation.id] = operation
        self._streams[operation.id] = lambda binding, payload: factory(payload)

    def register_bound_stream(
        self, operation: BridgeOperation, factory: BoundStreamSource
    ) -> None:
        """Allowlist one streaming operation whose factory sees the caller."""
        self._check_registration(operation, factory, "factory")
        self._operations[operation.id] = operation
        self._streams[operation.id] = factory

    def _check_registration(
        self, operation: BridgeOperation, target: Any, role: str
    ) -> None:
        if operation.id in self._handlers or operation.id in self._streams:
            raise QgisSdkBridgeError(f"duplicate operation id {operation.id!r}")
        if not callable(target):
            raise QgisSdkBridgeError(f"{operation.id}: {role} must be callable")

    def watch(self, binding: ViewBinding, wake: Waker) -> None:
        """Ask to be woken when a pushed stream queues frames for this view.

        A channel adapter registers its flush here, so a reply that arrives on
        a later event loop turn reaches the page without anyone polling. One
        waker per view: a new channel for the same view replaces the old one.
        """
        self._wakers[binding.view_id] = wake

    def unwatch(self, binding: ViewBinding) -> None:
        """Stop waking this view; a wake after this is simply not delivered."""
        self._wakers.pop(binding.view_id, None)

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
            "host_schema_version": HOST_SCHEMA_VERSION,
            "operations": [operation.to_dict() for operation in self.operations()],
            **self._theme_entry(),
        }
        return binding, to_wire(reply)

    def _theme_entry(self) -> dict[str, Any]:
        """``{"theme": ...}`` when the provider has a palette, nothing otherwise."""
        if self._theme is None:
            return {}
        theme = self._theme()
        return {} if theme is None else {"theme": dict(theme)}

    def dispatch(
        self,
        binding: ViewBinding,
        raw: Mapping[str, Any],
        *,
        cancelled: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        """Answer one call with a reply, never with an exception.

        ``kind`` selects the call: an invocation by default, a subscription,
        its disposal, a release or a handshake otherwise. They share the same
        refusals, so a subscription can never be opened through a path an
        invocation cannot take.
        """
        call_id = peek_call_id(raw) or ""
        kind = raw.get("kind", "invoke") if isinstance(raw, Mapping) else "invoke"
        if kind == "subscribe":
            return self._subscribe(binding, raw, cancelled=cancelled)
        if kind == "unsubscribe":
            return self._unsubscribe(binding, raw)
        if kind == "release":
            return self._release(binding, raw)
        if kind == "handshake":
            return self._handshake_reply(binding, call_id)
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
        operation = self._operations[envelope.operation]
        refusal = _input_refusal(operation, payload)
        if refusal is not None:
            return failure(call_id, BridgeErrorCode.INVALID_PAYLOAD, refusal)

        try:
            value = handler(binding, payload)
        except QgisSdkBridgeRefusalError as error:
            return failure(call_id, BridgeErrorCode(error.code), str(error))
        except QgisSdkError as error:
            return failure(call_id, BridgeErrorCode.OPERATION_FAILED, str(error))
        except Exception:  # noqa: BLE001 - a reply must always be produced
            return failure(
                call_id,
                BridgeErrorCode.OPERATION_FAILED,
                "The operation failed; the host recorded the details",
            )
        try:
            wire_value = to_wire(value)
        except QgisSdkBridgeError as error:
            return failure(call_id, BridgeErrorCode.NOT_SERIALIZABLE, str(error))
        refusal = _output_refusal(operation, wire_value)
        if refusal is not None:
            return failure(call_id, BridgeErrorCode.INVALID_RESULT, refusal)
        return success(call_id, wire_value)

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
            subscription.dispose()
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
        refusal = _input_refusal(self._operations[request.operation], payload)
        if refusal is not None:
            return failure(call_id, BridgeErrorCode.INVALID_PAYLOAD, refusal)

        try:
            source = factory(binding, payload)
        except QgisSdkBridgeRefusalError as error:
            return failure(call_id, BridgeErrorCode(error.code), str(error))
        except QgisSdkError as error:
            return failure(call_id, BridgeErrorCode.OPERATION_FAILED, str(error))
        except Exception:  # noqa: BLE001 - a reply must always be produced
            return failure(
                call_id,
                BridgeErrorCode.OPERATION_FAILED,
                "The subscription failed; the host recorded the details",
            )
        pushed = isinstance(source, PushSource) and not hasattr(source, "__next__")
        if source is not None and not pushed and not hasattr(source, "__next__"):
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
            events=self._operations[request.operation].events,
        )
        subscription.attach(source)
        self._subscriptions[subscription.id] = subscription
        self._ledger.track(
            binding.view_id, Handle(kind=HandleKind.SUBSCRIPTION, id=subscription.id)
        )
        if pushed:
            sink = StreamSink(subscription, wake=self._waker_for(binding.view_id))
            try:
                source.start(sink)  # type: ignore[union-attr]
            except Exception as error:  # noqa: BLE001 - the stream must still end
                # The subscription exists and the view holds its id, so the
                # failure is a terminal frame, exactly as a pulled source's is.
                sink.fail(error)
        return success(
            call_id,
            {"subscription_id": subscription.id, "capacity": subscription.capacity},
        )

    def _waker_for(self, view_id: str) -> Waker:
        """Return a wake callback that looks the view's waker up when it fires.

        Looked up late on purpose: a channel registered after the subscription
        opened still gets woken, and one that unwatched is left alone.
        """

        def wake() -> None:
            waker = self._wakers.get(view_id)
            if waker is not None:
                waker()

        return wake

    def _unsubscribe(
        self, binding: ViewBinding, raw: Mapping[str, Any]
    ) -> dict[str, Any]:
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
        subscription.dispose()
        self._subscriptions.pop(subscription.id, None)
        self._ledger.forget(
            binding.view_id,
            Handle(kind=HandleKind.SUBSCRIPTION, id=subscription.id),
        )
        return success(call_id, {"subscription_id": subscription.id, "disposed": True})

    def _handshake_reply(self, binding: ViewBinding, call_id: str) -> dict[str, Any]:
        """Answer ``kind: "handshake"`` for a view the host already bound.

        A page connected through QWebChannel never minted its own binding - the
        adapter did, before the first message - so it asks for the contract
        with a call instead. The reply is the one :meth:`handshake` builds,
        narrowed to the operations this view is authorized to call: what it
        lists is exactly what ``qgis.host.granted`` may show.
        """
        if binding.generation != self._generation:
            return failure(
                call_id,
                BridgeErrorCode.STALE_GENERATION,
                "This view belongs to a runtime generation that no longer exists",
            )
        reply = {
            "protocol": BRIDGE_PROTOCOL_VERSION,
            "generation": binding.generation,
            "plugin": self._description,
            "host_schema_version": HOST_SCHEMA_VERSION,
            "operations": [
                operation.to_dict()
                for operation in self.operations()
                if self._is_authorized(binding, operation.id)
            ],
            **self._theme_entry(),
        }
        return success(call_id, to_wire(reply))

    def track(self, binding: ViewBinding, kind: HandleKind, handle_id: str) -> Handle:
        """Record a handle the view now holds, so it can be released later."""
        handle = Handle(kind=kind, id=handle_id)
        self._ledger.track(binding.view_id, handle)
        return handle

    def _release(self, binding: ViewBinding, raw: Mapping[str, Any]) -> dict[str, Any]:
        """Release handles the view names, one outcome per handle.

        The view names kinds and ids, never a callable: releasing a borrowed
        handle is a no-op by construction, so a compromised view cannot turn one
        into a delete of the project's layer.
        """
        call_id = peek_call_id(raw) or ""
        if binding.generation != self._generation:
            return failure(
                call_id,
                BridgeErrorCode.STALE_GENERATION,
                "This view belongs to a runtime generation that no longer exists",
            )
        if not self._is_authorized(binding, "bridge.release"):
            return failure(
                call_id,
                BridgeErrorCode.NOT_AUTHORIZED,
                "This view is not authorized to release resources",
            )
        payload = raw.get("payload", {})
        if not isinstance(payload, Mapping):
            return failure(
                call_id, BridgeErrorCode.INVALID_PAYLOAD, "payload must be an object"
            )
        requested = payload.get("handles", [])
        if not isinstance(requested, list):
            return failure(
                call_id,
                BridgeErrorCode.INVALID_PAYLOAD,
                "handles must be a list of handles",
            )
        try:
            handles = [Handle.parse(item) for item in requested]
        except QgisSdkBridgeError as error:
            return failure(call_id, BridgeErrorCode.INVALID_PAYLOAD, str(error))
        return success(
            call_id, {"released": self._ledger.release_all(binding.view_id, handles)}
        )

    def _dispose_subscription(self, subscription_id: str) -> bool:
        """Dispose a subscription by id; ``False`` when it already ended."""
        subscription = self._subscriptions.pop(subscription_id, None)
        if subscription is None:
            return False
        subscription.dispose()
        return True

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
            subscription.dispose()
            self._ledger.forget(
                subscription.view_id,
                Handle(kind=HandleKind.SUBSCRIPTION, id=subscription.id),
            )
        self._subscriptions.clear()

    def _is_authorized(self, binding: ViewBinding, operation: str) -> bool:
        if self._authorize is None:
            return False
        return bool(self._authorize(binding, operation))


def _description_parts(
    description: Any,
) -> tuple[Any, list[dict[str, Any]], list[dict[str, Any]]]:
    """Return the advertised description, its actions and its streams as records."""
    if hasattr(description, "to_dict") and hasattr(description, "actions"):
        actions = [
            {
                "id": action.id,
                "title": action.title,
                "request": action.request,
                "result": action.result,
            }
            for action in description.actions
        ]
        streams = [
            {
                "id": declared.id,
                "title": declared.title,
                "request": declared.request,
                "events": declared.events,
            }
            for declared in getattr(description, "streams", ())
        ]
        return description.to_dict(), actions, streams
    if isinstance(description, Mapping):
        return (
            description,
            _declared_records(description, "actions"),
            _declared_records(description, "streams"),
        )
    raise QgisSdkBridgeError(
        "description must be a PluginDescription or a mapping with actions"
    )


def _declared_records(description: Mapping[str, Any], key: str) -> list[dict]:
    """Return ``description[key]`` as checked records; a missing list is empty."""
    declared = description.get(key, [])
    if not isinstance(declared, list):
        raise QgisSdkBridgeError(f"description.{key} must be a list")
    noun = key[:-1]
    records: list[dict[str, Any]] = []
    for item in declared:
        if not isinstance(item, Mapping):
            raise QgisSdkBridgeError(f"every {noun} in a description must be an object")
        for field_name in ("id", "title"):
            if not isinstance(item.get(field_name), str) or not item[field_name]:
                raise QgisSdkBridgeError(
                    f"{noun} {field_name} must be a nonempty string"
                )
        records.append(dict(item))
    return records


def _keyword_handler(
    handler: Callable[..., Any], request: Any, operation_id: str
) -> Handler:
    """Bind a declared action's named-argument payload to the callable.

    A declaration describes the inputs as an object, and the payload is
    validated against that object before this runs, so the only thing left to do
    is spell it as keyword arguments.
    """
    _check_parameter_names(request, operation_id)
    refs = _ref_inputs(request)

    def invoke(payload: Mapping[str, Any]) -> Any:
        if refs:
            payload = {
                key: FileRef.from_wire(value)
                if key in refs and value is not None
                else value
                for key, value in payload.items()
            }
        return _wire_result(handler(**payload))

    return invoke


def _ref_inputs(request: Any) -> frozenset[str]:
    """Name the inputs declared as file or directory refs.

    A page sends the ``FileRef`` the host minted as its wire object; the
    handler declared ``FileInput()`` and receives the ref, the way a toolbox
    run and a native form hand it one.
    """
    properties = request.get("properties", {}) if isinstance(request, Mapping) else {}
    names = set()
    for name, schema in properties.items():
        if not isinstance(schema, Mapping):
            continue
        branches = schema.get("anyOf") or [schema]
        for branch in branches:
            intent = (
                branch.get(WIRE_KIND_KEYWORD) if isinstance(branch, Mapping) else None
            )
            if isinstance(intent, Mapping) and intent.get("kind") in FILE_REF_KINDS:
                names.add(name)
    return frozenset(names)


def _keyword_source(
    factory: Callable[..., Any], request: Any, operation_id: str
) -> StreamSource:
    """Bind a declared stream's request to its factory, the way actions are bound.

    What the factory yields is handed to the subscription as produced; the
    dataclasses a declared event is spelled with are unwrapped there, so an
    author yields ``Change(...)`` and the view receives the object it declared.
    """
    _check_parameter_names(request, operation_id)

    def open_stream(payload: Mapping[str, Any]) -> Any:
        source = factory(**payload)
        if source is None:
            return None

        def serialize_stream() -> Iterator[Any]:
            try:
                for item in source:
                    yield _wire_result(item)
            finally:
                close = getattr(source, "close", None)
                if close is not None:
                    close()

        return serialize_stream()

    return open_stream


def _check_parameter_names(request: Any, operation_id: str) -> None:
    properties: Any = {}
    if isinstance(request, Mapping):
        properties = request.get("properties", {})
    if isinstance(properties, Mapping):
        for name in properties:
            if not isinstance(name, str) or not name.isidentifier():
                raise QgisSdkBridgeError(
                    f"{operation_id}: input {name!r} is not a Python parameter name"
                )


def _wire_result(value: Any) -> Any:
    """Turn declared value objects into plain JSON before the boundary check.

    A declared action returns the dataclass its annotation names, and the
    declaration already described that dataclass as an object schema. Converting
    here keeps :func:`~qgis_sdk.bridge.protocol.to_wire` strict for everything
    else: a Qt or QGIS object is still refused, because only dataclasses, lists
    and mappings are unwrapped.
    """
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    wire = getattr(type(value), WIRE_VALUE_METHOD, None)
    if wire is not None:
        return _wire_result(wire(value))
    if isinstance(value, (list, tuple)):
        return [_wire_result(item) for item in value]
    if isinstance(value, Mapping):
        return {key: _wire_result(item) for key, item in value.items()}
    return value


def _input_refusal(operation: BridgeOperation, payload: Any) -> str | None:
    """Return the refusal for a payload, or ``None`` when it may proceed."""
    if operation.request is None:
        return None
    try:
        validate(payload, operation.request, path="payload")
    except QgisSdkBridgeError as error:
        return str(error)
    return None


def _output_refusal(operation: BridgeOperation, value: Any) -> str | None:
    """Validate a result leniently: required fields yes, extra fields no."""
    if operation.result is None:
        return None
    try:
        validate(value, operation.result, path="result", allow_unknown=True)
    except QgisSdkBridgeError as error:
        return str(error)
    return None

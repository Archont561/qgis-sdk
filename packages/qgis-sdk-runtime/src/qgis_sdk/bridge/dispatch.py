"""The narrow endpoint every bridge call passes through.

One dispatcher owns one view's traffic. It decides, in this order, whether a
call is allowed to exist at all: protocol, session generation, authorization,
allowlist, payload, handler, and finally a reply that is itself JSON-safe
(decision-9, decision-18). Subscriptions are decided in the same order and stop
at the same place: opening one is a call, and the frames that follow belong to
the view and generation that opened it.

The object here is the caller's view of that endpoint; the decisions live in
:mod:`qgis_sdk.bridge.endpoint`, one role per module - what may be called, who
may call it, what is already running, and the invocation itself. Nothing in the
roles is reachable without passing through this object, and nothing here
decides anything: a method either names the state it returns or the role it
asks.

Two choices are deliberate and belong to the roles rather than to this file.

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

The dispatcher is driven, never threaded. :meth:`Dispatcher.pump` is what the Qt
adapter calls on a timer to collect the frames waiting for a view, so ordering
and bounded buffering are decided by ordinary code that a test can run in a
loop, not by whatever the transport happens to do with a callback.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any

from qgis_sdk.bridge.endpoint._calls import _Calls
from qgis_sdk.bridge.endpoint._refusals import QgisSdkRefusal
from qgis_sdk.bridge.endpoint._registry import _Registry
from qgis_sdk.bridge.endpoint._streams import _Book, _Streams
from qgis_sdk.bridge.endpoint._types import (
    Authorizer,
    BoundHandler,
    BoundStreamSource,
    Handler,
    ThemeProvider,
    ViewBinding,
    Waker,
)
from qgis_sdk.bridge.endpoint._views import _Views
from qgis_sdk.bridge.endpoint._wire import wire_result
from qgis_sdk.bridge.protocol import (
    BridgeErrorCode,
    BridgeOperation,
    failure,
    peek_call_id,
)
from qgis_sdk.bridge.resources import Handle, HandleKind, ReleaseLedger
from qgis_sdk.bridge.streams import (
    MAX_FRAMES_PER_PUMP,
    StreamEventType,
    StreamSource,
    Subscription,
)
from qgis_sdk.declarations import WIRE_KIND_KEYWORD
from qgis_sdk.models.errors import QgisSdkBridgeError
from qgis_sdk.models.files import FILE_REF_KINDS, FileRef

#: The dispatch module's own name for the wire helper, kept for its importers.
_wire_result = wire_result

__all__ = [
    "Authorizer",
    "BoundHandler",
    "BoundStreamSource",
    "Dispatcher",
    "Handler",
    "ThemeProvider",
    "ViewBinding",
    "Waker",
]


@dataclass(frozen=True, slots=True)
class DispatchSetup:
    """Everything a dispatcher is built from, in one record.

    The declaration, the handlers bound to it and the three options a host may
    vary used to be seven parameters, which every caller had to spell out even
    when it varied one of them. ``streams`` belongs here rather than to a second
    constructor: a stream is a declared operation like any other (decision-28).
    """

    description: Any
    handlers: Mapping[str, Handler]
    streams: Mapping[str, Callable[..., Any]] | None = None
    authorize: Authorizer | None = None
    ledger: ReleaseLedger | None = None
    theme: ThemeProvider | None = None


class _DispatcherMixin1:
    @classmethod
    def from_description(cls, setup: DispatchSetup) -> Dispatcher:
        """Build a dispatcher whose allowlist *is* the plugin description.

        The only wiring a plugin needs (decision-26): every declared action
        becomes one allowlisted operation carrying the schemas the declaration
        already produced, bound to its handler by action id. Declared streams
        (decision-28) are wired the same way from ``setup.streams``, with the
        request spelled as keyword arguments.
        """
        advertised, actions, declared = _description_parts(setup.description)
        dispatcher = cls(
            description=advertised,
            authorize=setup.authorize,
            ledger=setup.ledger,
            theme=setup.theme,
        )
        _wire_declared(
            dispatcher, actions, declared, setup.handlers, setup.streams or {}
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

        ``PluginRuntime.actions`` and ``streams`` are already keyed by id.
        """
        return cls.from_description(
            DispatchSetup(
                description=runtime.description,
                handlers=runtime.actions,
                streams=getattr(runtime, "streams", None),
                authorize=authorize,
                ledger=ledger,
                theme=theme,
            )
        )

    def register(self, operation: BridgeOperation, handler: Handler) -> None:
        """Allowlist one operation and bind it to its handler."""
        self._registry.register(operation, handler)

    def register_bound(self, operation: BridgeOperation, handler: BoundHandler) -> None:
        """Allowlist one operation whose handler receives the caller's binding."""
        self._registry.register_bound(operation, handler)

    def register_stream(
        self, operation: BridgeOperation, factory: StreamSource
    ) -> None:
        """Allowlist one streaming operation and its source factory."""
        self._registry.register_stream(operation, factory)

    def register_bound_stream(
        self, operation: BridgeOperation, factory: BoundStreamSource
    ) -> None:
        """Allowlist one streaming operation whose factory sees the caller."""
        self._registry.register_bound_stream(operation, factory)

    def operations(self) -> tuple[BridgeOperation, ...]:
        """Return the allowlisted operations in id order."""
        return self._registry.operations()

    @property
    def generation(self) -> int:
        """The runtime generation every live binding must match."""
        return self._views.generation

    def bind(self, *, view_id: str, origin: str) -> ViewBinding:
        """Mint the binding for a view that just connected."""
        return self._views.bind(view_id=view_id, origin=origin)

    def handshake(self, *, view_id: str, origin: str) -> tuple[ViewBinding, dict]:
        """Bind a view and return the reply that completes the handshake."""
        return self._views.handshake(view_id=view_id, origin=origin)

    def advance_generation(self) -> int:
        """Start a new runtime generation, invalidating every existing binding."""
        self._streams.dispose_all()
        return self._views.advance()

    def watch(self, binding: ViewBinding, wake: Waker) -> None:
        """Ask to be woken when a pushed stream queues frames for this view."""
        self._views.watch(binding, wake)

    def unwatch(self, binding: ViewBinding) -> None:
        """Stop waking this view; a wake after this is simply not delivered."""
        self._views.unwatch(binding)


class _DispatcherMixin2:
    def dispatch(
        self,
        binding: ViewBinding,
        raw: Mapping[str, Any],
        *,
        cancelled: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        """Answer one call with a reply, never with an exception.

        ``kind`` selects the call: an invocation by default, a subscription, its
        acknowledgement, its disposal, a release or a handshake otherwise. All of
        them share the same refusals, so a subscription can never be opened
        through a path an invocation cannot take.
        """
        try:
            kind = _call_kind(raw)
            if kind == "invoke":
                return self._calls.invoke(binding, raw, cancelled=cancelled)
            if kind == "subscribe":
                return self._streams.subscribe(binding, raw, cancelled=cancelled)
            known = self._kinds.get(kind) if isinstance(kind, str) else None
            if known is None:
                return failure(
                    peek_call_id(raw) or "",
                    BridgeErrorCode.INVALID_MESSAGE,
                    f"Unknown call kind {kind!r}",
                )
            return known(binding, raw)
        except QgisSdkRefusal as refused:
            return refused.reply

    def track(self, binding: ViewBinding, kind: HandleKind, handle_id: str) -> Handle:
        """Record a handle the view now holds, so it can be released later."""
        return self._calls.track(binding, kind, handle_id)

    def register_editing(
        self,
        *,
        close: Callable[[str], bool],
        close_view: Callable[[str], None],
    ) -> None:
        """Let the host close its editing sessions when the view is released."""
        self._streams.register_editing(close=close, close_view=close_view)

    def pump(
        self, binding: ViewBinding, *, limit: int = MAX_FRAMES_PER_PUMP
    ) -> list[dict[str, Any]]:
        """Collect the frames waiting for ``binding``'s view, oldest first."""
        return self._streams.pump(binding, limit=limit)

    def emit(
        self,
        subscription_id: str,
        payload: Any,
        *,
        kind: StreamEventType = StreamEventType.DATA,
    ) -> bool:
        """Push one event into an open subscription; ``False`` when it ended."""
        return self._streams.emit(subscription_id, payload, kind=kind)

    def subscriptions(self) -> tuple[Subscription, ...]:
        """Return the live subscriptions in id order, for tests and teardown."""
        return self._streams.subscriptions()

    def dispose(self, binding: ViewBinding) -> int:
        """Close every subscription and editing session of ``binding``'s view."""
        return self._streams.dispose(binding)


class Dispatcher(_DispatcherMixin1, _DispatcherMixin2):
    """Route allowlisted operations for one host, per view generation.

    Four roles composed here, one per way a call can be answered - what may be
    called, who may call it, what is running, the invocation itself - so the
    order the endpoint decides in is stated once, in
    :mod:`qgis_sdk.bridge.endpoint`, not in a method that also decides.
    """

    def __init__(
        self,
        *,
        description: Mapping[str, Any] | None = None,
        authorize: Authorizer | None = None,
        ledger: ReleaseLedger | None = None,
        theme: ThemeProvider | None = None,
    ) -> None:
        self._ledger = ledger if ledger is not None else ReleaseLedger()
        self._registry, self._views, self._streams, self._calls = _assembled(
            description, authorize, self._ledger, theme
        )
        #: Every other kind of call names one method, so adding a kind is a line
        #: here - never a branch in :meth:`dispatch`.
        self._kinds: dict[str, Callable[..., dict]] = {
            "ack": self._streams.acknowledge,
            "handshake": self._views.reply,
            "release": self._calls.release,
            "unsubscribe": self._streams.unsubscribe,
        }


def _assembled(
    description: Mapping[str, Any] | None,
    authorize: Authorizer | None,
    ledger: ReleaseLedger,
    theme: ThemeProvider | None,
) -> tuple[_Registry, _Views, _Streams, _Calls]:
    """Wire the four roles around one ledger, in the order they depend on it."""
    registry = _Registry()
    views = _Views(
        description=description, authorize=authorize, theme=theme, registry=registry
    )
    book = _Book(registry=registry, views=views, ledger=ledger)
    streams = _Streams(book=book, registry=registry, views=views, ledger=ledger)
    calls = _Calls(registry=registry, views=views, ledger=ledger)
    ledger.dispose_subscription = book.close_id
    return registry, views, streams, calls


def _wire_declared(
    dispatcher: Dispatcher,
    actions: list[dict[str, Any]],
    declared: list[dict[str, Any]],
    handlers: Mapping[str, Handler],
    factories: Mapping[str, Callable[..., Any]],
) -> None:
    """Register every declared action and stream, or refuse the description."""
    for action in actions:
        dispatcher.register(*_action_binding(action, handlers))
    for stream in declared:
        dispatcher.register_stream(*_stream_binding(stream, factories))


def _call_kind(raw: Any) -> Any:
    """The kind of call ``raw`` declares; an invocation when it names none."""
    return raw.get("kind", "invoke") if isinstance(raw, Mapping) else "invoke"


def _action_binding(
    action: Mapping[str, Any], handlers: Mapping[str, Handler]
) -> tuple[BridgeOperation, Handler]:
    """The operation, and the keyword-bound handler, one declared action adds."""
    operation_id = action["id"]
    handler = handlers.get(operation_id)
    if handler is None:
        raise QgisSdkBridgeError(
            f"action {operation_id!r} is declared but has no handler"
        )
    if not callable(handler):
        raise QgisSdkBridgeError(f"action {operation_id!r}: handler must be callable")
    return (
        BridgeOperation(
            id=operation_id,
            title=action["title"],
            request=action.get("request"),
            result=action.get("result"),
        ),
        _keyword_handler(handler, action.get("request"), operation_id),
    )


def _stream_binding(
    declared: Mapping[str, Any], factories: Mapping[str, Callable[..., Any]]
) -> tuple[BridgeOperation, StreamSource]:
    """The operation, and the keyword-bound source, one declared stream adds."""
    operation_id = declared["id"]
    factory = factories.get(operation_id)
    if factory is None:
        raise QgisSdkBridgeError(
            f"stream {operation_id!r} is declared but has no stream factory"
        )
    if not callable(factory):
        raise QgisSdkBridgeError(f"stream {operation_id!r}: factory must be callable")
    return (
        BridgeOperation(
            id=operation_id,
            title=declared["title"],
            request=declared.get("request"),
            events=declared.get("events"),
        ),
        _keyword_source(factory, declared.get("request"), operation_id),
    )


def _description_parts(
    description: Any,
) -> tuple[Any, list[dict[str, Any]], list[dict[str, Any]]]:
    """Return the advertised description, its actions and its streams as records."""
    if hasattr(description, "to_dict") and hasattr(description, "actions"):
        return (
            description.to_dict(),
            [_action_record(action) for action in description.actions],
            [_stream_record(stream) for stream in getattr(description, "streams", ())],
        )
    if isinstance(description, Mapping):
        return (
            description,
            _declared_records(description, "actions"),
            _declared_records(description, "streams"),
        )
    raise QgisSdkBridgeError(
        "description must be a PluginDescription or a mapping with actions"
    )


def _action_record(action: Any) -> dict[str, Any]:
    """One declared action as the record the wiring reads."""
    return {
        "id": action.id,
        "title": action.title,
        "request": action.request,
        "result": action.result,
    }


def _stream_record(declared: Any) -> dict[str, Any]:
    """One declared stream as the record the wiring reads."""
    return {
        "id": declared.id,
        "title": declared.title,
        "request": declared.request,
        "events": declared.events,
    }


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
        return wire_result(handler(**payload))

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
                    yield wire_result(item)
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

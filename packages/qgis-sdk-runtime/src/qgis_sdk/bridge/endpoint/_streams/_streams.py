"""The streaming half of the endpoint: open, acknowledge, and close."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from qgis_sdk.bridge.endpoint._refusals import ensure_not_cancelled, opened, refuse
from qgis_sdk.bridge.endpoint._registry import Registry
from qgis_sdk.bridge.endpoint._types import ViewBinding
from qgis_sdk.bridge.endpoint._views import Views
from qgis_sdk.bridge.endpoint._wire import payload_of, require_input
from qgis_sdk.bridge.protocol import BridgeErrorCode, peek_call_id, success
from qgis_sdk.bridge.resources import ReleaseLedger
from qgis_sdk.bridge.streams import (
    MAX_FRAMES_PER_PUMP,
    MAX_SUBSCRIPTIONS_PER_VIEW,
    AckRequest,
    DisposalRequest,
    PushSource,
    StreamEventType,
    Subscription,
    SubscriptionRequest,
)
from qgis_sdk.models.errors import QgisSdkBridgeProtocolError

from ._book import Book

__all__ = ["Streams"]

_CANCELLED = "The subscription was cancelled"
_OTHER_VIEW = "This subscription belongs to a different view"
_NOT_AUTHORIZED = "This view is not authorized for that operation"


class Streams:
    """The streaming half of the endpoint: open, acknowledge, and close.

    Opening a subscription is a call like any other and passes the same checks
    in the same order, because a stream a view may not open is a stream it may
    not open by any path. What follows is delivery: frames wait in the
    subscription until the view collects them, so nothing is pushed into a page
    that is not reading.
    """

    def __init__(
        self,
        *,
        book: Book,
        registry: Registry,
        views: Views,
        ledger: ReleaseLedger,
    ) -> None:
        self._book = book
        self._registry = registry
        self._views = views
        self._ledger = ledger

    def subscribe(
        self,
        binding: ViewBinding,
        raw: Mapping[str, Any],
        *,
        cancelled: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        """Open one subscription; a refusal inside is the reply it raises."""
        return self._subscribe_reply(binding, raw, cancelled)

    def unsubscribe(
        self, binding: ViewBinding, raw: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Dispose one subscription, idempotently."""
        return self._unsubscribe_reply(binding, raw)

    def acknowledge(
        self, binding: ViewBinding, raw: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Record that a view delivered one stream frame (protocol 2)."""
        return self._acknowledge_reply(binding, raw)

    def pump(
        self, binding: ViewBinding, *, limit: int = MAX_FRAMES_PER_PUMP
    ) -> list[dict[str, Any]]:
        """Collect the frames waiting for ``binding``'s view, oldest first.

        Only the view and generation that opened a subscription can collect its
        frames. A stale binding gets nothing at all - not even a terminal frame -
        because delivering state to a runtime that no longer exists is exactly
        what the generation check is for.
        """
        return self._book.pump(binding, limit)

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
        return self._book.emit(subscription_id, payload, kind)

    def dispose(self, binding: ViewBinding) -> int:
        """Close every subscription and editing session of ``binding``'s view."""
        return self._book.dispose_view(binding)

    def subscriptions(self) -> tuple[Subscription, ...]:
        """Return the live subscriptions in id order, for tests and teardown."""
        return self._book.subscriptions()

    def dispose_all(self) -> None:
        """Close every subscription, for a runtime generation that is ending."""
        self._book.dispose_all()

    def register_editing(
        self,
        *,
        close: Callable[[str], bool],
        close_view: Callable[[str], None],
    ) -> None:
        """Let the host close its editing sessions when the view is released.

        Editing sessions live on the host's service, not in the dispatcher, but
        their lifetime is the view's: a page that disappears mid-edit must not
        leave a buffer open behind it. The host hands the two calls it needs -
        one session by id, and every session of a view - so disposal stays a
        decision of the code that owns the buffers.
        """
        self._ledger.dispose_editing = close
        self._book.close_view_editing_with(close_view)

    def _subscribe_reply(
        self,
        binding: ViewBinding,
        raw: Mapping[str, Any],
        cancelled: Callable[[], bool] | None,
    ) -> dict[str, Any]:
        request = _subscription_request(raw)
        self._views.require(binding, request.operation, request.call_id)
        factory = self._registry.source_for(request.operation, request.call_id)
        ensure_not_cancelled(cancelled, request.call_id, _CANCELLED)
        _require_capacity(self._book.count_for(binding), request.call_id)
        payload = payload_of(request.payload, request.call_id)
        operation = self._registry.operation(request.operation)
        require_input(operation, payload, request.call_id)
        source = opened(factory, binding, payload, request.call_id)
        pushed = _pushed(source, request.call_id)
        subscription = self._book.open(binding, request.operation, source)
        if pushed:
            self._book.start(source, subscription, binding.view_id)
        return success(
            request.call_id,
            {"subscription_id": subscription.id, "capacity": subscription.capacity},
        )

    def _unsubscribe_reply(
        self, binding: ViewBinding, raw: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Answer a disposal: ``disposed: false`` for one that already ended.

        A second disposal of the same id - or one that arrives for a
        subscription that already ended - is answered with ``disposed: false``
        rather than an error: closing twice is what a closing UI does, and a
        refusal would turn a harmless race into a failed call.
        """
        request = _disposal_request(raw)
        subscription = self._usable(binding, request.subscription_id, request.call_id)
        if subscription is None:
            return success(
                request.call_id,
                {"subscription_id": request.subscription_id, "disposed": False},
            )
        self._book.close(subscription)
        return success(
            request.call_id, {"subscription_id": subscription.id, "disposed": True}
        )

    def _acknowledge_reply(
        self, binding: ViewBinding, raw: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Answer an acknowledgement with how much is still in flight.

        An acknowledgement is delivery feedback, not a call that does work: it
        names a subscription this view opened and a seq the host handed out. A
        repeat or a late ack is accepted as a no-op, because frames race the
        consumer that acknowledges them; an ack for a seq the host never sent is
        refused, because that client is no longer reading the stream it thinks
        it reads.
        """
        request = _ack_request(raw)
        subscription = self._usable(binding, request.subscription_id, request.call_id)
        if subscription is None:
            return success(
                request.call_id, _nothing_acknowledged(request.subscription_id)
            )
        _require_known_frame(subscription, request)
        return success(request.call_id, _acknowledgement(subscription))

    def _usable(
        self, binding: ViewBinding, subscription_id: str, call_id: str
    ) -> Subscription | None:
        """The subscription this view may act on, or ``None`` when it ended."""
        self._views.require_live(binding, call_id)
        subscription = self._book.held(subscription_id)
        if subscription is None:
            return None
        if subscription.view_id != binding.view_id:
            refuse(call_id, BridgeErrorCode.NOT_AUTHORIZED, _OTHER_VIEW)
        self._views.require_authorized(
            binding, subscription.operation, call_id, reason=_NOT_AUTHORIZED
        )
        return subscription


def _nothing_acknowledged(subscription_id: str) -> dict[str, Any]:
    """The answer to an acknowledgement for a stream that already ended."""
    return {"subscription_id": subscription_id, "acknowledged": None, "in_flight": 0}


def _acknowledgement(subscription: Subscription) -> dict[str, Any]:
    """The answer to an acknowledgement: the watermark it moved, and what is left."""
    return {
        "subscription_id": subscription.id,
        "acknowledged": subscription.acknowledged,
        "in_flight": subscription.in_flight,
    }


def _require_known_frame(subscription: Subscription, request: AckRequest) -> None:
    """Refuse an acknowledgement for a seq this view was never handed."""
    if not subscription.acknowledge(request.seq):
        refuse(
            request.call_id,
            BridgeErrorCode.INVALID_MESSAGE,
            f"Frame {request.seq} of {request.subscription_id!r} was never "
            "handed to this view",
        )


def _pushed(source: Any, call_id: str) -> bool:
    """Whether a source pushes into a sink rather than yielding as it is pulled."""
    if isinstance(source, PushSource) and not hasattr(source, "__next__"):
        return True
    if source is not None and not hasattr(source, "__next__"):
        refuse(
            call_id,
            BridgeErrorCode.OPERATION_FAILED,
            "The stream did not produce an iterator of events",
        )
    return False


def _require_capacity(count: int, call_id: str) -> None:
    """Refuse a subscription once the view holds all it is allowed to."""
    if count >= MAX_SUBSCRIPTIONS_PER_VIEW:
        refuse(
            call_id,
            BridgeErrorCode.LIMIT_EXCEEDED,
            f"This view already holds {MAX_SUBSCRIPTIONS_PER_VIEW} subscriptions",
        )


def _subscription_request(raw: Mapping[str, Any]) -> SubscriptionRequest:
    """The subscription a call asks for, or a refusal naming why it is malformed."""
    call_id = peek_call_id(raw) or ""
    try:
        return SubscriptionRequest.parse(raw)
    except QgisSdkBridgeProtocolError as error:
        refuse(call_id, BridgeErrorCode.INVALID_MESSAGE, str(error))


def _disposal_request(raw: Mapping[str, Any]) -> DisposalRequest:
    """The disposal a call asks for, or a refusal naming why it is malformed."""
    call_id = peek_call_id(raw) or ""
    try:
        return DisposalRequest.parse(raw)
    except QgisSdkBridgeProtocolError as error:
        refuse(call_id, BridgeErrorCode.INVALID_MESSAGE, str(error))


def _ack_request(raw: Mapping[str, Any]) -> AckRequest:
    """The acknowledgement a call carries, or a refusal naming why it is malformed."""
    call_id = peek_call_id(raw) or ""
    try:
        return AckRequest.parse(raw)
    except QgisSdkBridgeProtocolError as error:
        refuse(call_id, BridgeErrorCode.INVALID_MESSAGE, str(error))

"""The subscriptions a host holds open, and the ledger entries for them."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from qgis_sdk.bridge.endpoint._registry import Registry
from qgis_sdk.bridge.endpoint._types import ViewBinding
from qgis_sdk.bridge.endpoint._views import Views
from qgis_sdk.bridge.resources import Handle, HandleKind, ReleaseLedger
from qgis_sdk.bridge.streams import StreamEventType, StreamSink, Subscription

__all__ = ["Book"]


class Book:
    """The subscriptions a host holds open, and the ledger entries for them.

    A subscription belongs to the view and the generation that opened it, so
    every read here goes through that pair: frames are only collected for the
    view that owns them, and a generation change closes the lot rather than
    leaving a source running for a page that can no longer be trusted with it.
    """

    def __init__(
        self, *, registry: Registry, views: Views, ledger: ReleaseLedger
    ) -> None:
        self._registry = registry
        self._views = views
        self._ledger = ledger
        self._subscriptions: dict[str, Subscription] = {}
        self._counter = 0
        self._close_view: Callable[[str], None] | None = None

    def subscriptions(self) -> tuple[Subscription, ...]:
        """Return the live subscriptions in id order, for tests and teardown."""
        return tuple(self._subscriptions[key] for key in sorted(self._subscriptions))

    def held(self, subscription_id: str) -> Subscription | None:
        """Return the subscription with that id, if it is still open."""
        return self._subscriptions.get(subscription_id)

    def open(self, binding: ViewBinding, operation: str, source: Any) -> Subscription:
        """Create the subscription this view now holds, and record its handle."""
        self._counter += 1
        subscription = Subscription(
            id=f"s{self._counter}",
            view_id=binding.view_id,
            generation=binding.generation,
            operation=operation,
            events=self._registry.operation(operation).events,
        )
        subscription.attach(source)
        self._subscriptions[subscription.id] = subscription
        self._ledger.track(
            binding.view_id, Handle(kind=HandleKind.SUBSCRIPTION, id=subscription.id)
        )
        return subscription

    def start(self, source: Any, subscription: Subscription, view_id: str) -> None:
        """Start a pushing source; a failure becomes the frame that ends it."""
        sink = StreamSink(subscription, wake=self._views.waker_for(view_id))
        try:
            source.start(sink)  # type: ignore[union-attr]
        except Exception as error:  # noqa: BLE001 - the stream must still end
            # The subscription exists and the view holds its id, so the
            # failure is a terminal frame, exactly as a pulled source's is.
            sink.fail(error)

    def close(self, subscription: Subscription) -> None:
        """End one subscription and forget the handle the view held for it."""
        subscription.dispose()
        self._subscriptions.pop(subscription.id, None)
        self._ledger.forget(
            subscription.view_id,
            Handle(kind=HandleKind.SUBSCRIPTION, id=subscription.id),
        )

    def close_id(self, subscription_id: str) -> bool:
        """Dispose a subscription by id; ``False`` when it already ended."""
        subscription = self._subscriptions.pop(subscription_id, None)
        if subscription is None:
            return False
        subscription.dispose()
        return True

    def count_for(self, binding: ViewBinding) -> int:
        """How many subscriptions this view holds open."""
        return sum(
            1
            for subscription in self._subscriptions.values()
            if subscription.view_id == binding.view_id
        )

    def forget_drained(self) -> None:
        """Drop the subscriptions that ended and have nothing left to collect."""
        for key in [
            key
            for key, subscription in self._subscriptions.items()
            if not subscription.open and subscription.queued == 0
        ]:
            self._subscriptions.pop(key, None)

    def pump(self, binding: ViewBinding, limit: int) -> list[dict[str, Any]]:
        """Collect the frames waiting for this view, oldest first."""
        frames: list[dict[str, Any]] = []
        for subscription in self.subscriptions():
            if (
                subscription.view_id != binding.view_id
                or subscription.generation != binding.generation
            ):
                continue
            subscription.pull(limit)
            frames.extend(subscription.drain(limit))
        self.forget_drained()
        return frames

    def emit(self, subscription_id: str, payload: Any, kind: StreamEventType) -> bool:
        """Push one event into an open subscription, ``False`` when it ended."""
        subscription = self._subscriptions.get(subscription_id)
        if subscription is None:
            return False
        return subscription.emit(payload, kind=kind)

    def dispose_view(self, binding: ViewBinding) -> int:
        """Close every subscription of ``binding``'s view, and its editing session."""
        if self._close_view is not None:
            self._close_view(binding.view_id)
        disposal = [
            subscription
            for subscription in self._subscriptions.values()
            if subscription.view_id == binding.view_id
        ]
        for subscription in disposal:
            subscription.dispose()
            self._subscriptions.pop(subscription.id, None)
        return len(disposal)

    def dispose_all(self) -> None:
        """Close every subscription, releasing the handles without answering."""
        for subscription in self._subscriptions.values():
            subscription.dispose()
            self._ledger.forget(
                subscription.view_id,
                Handle(kind=HandleKind.SUBSCRIPTION, id=subscription.id),
            )
        self._subscriptions.clear()

    def close_view_editing_with(self, closer: Callable[[str], None] | None) -> None:
        """Let the host close a view's editing sessions when the view is disposed."""
        self._close_view = closer

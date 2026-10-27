"""Behaviour mixins for surfaces (decision-55 point 2).

A mixin adds one behaviour to a ``Dialog``/``Dock`` without a widget of its
own: ``RunsJobs`` runs the plugin's actions and cancels what is still
running when the window closes; ``SubscribesStreams`` keeps the view's
stream subscriptions in one place; ``HasAcceptCancel`` wires the dialog's
``AcceptCancel`` row to ``on_accept()`` and closing. They hook in through
``_attach_behaviours``, which :func:`qgis_sdk.ui.wiring.wire_surface` calls
after ``build()``, so the same class works under the host and under
:func:`qgis_sdk.testing.build_surface`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, ClassVar

from qgis_sdk.models import QgisSdkUiError

from .buttons import AcceptCancel
from .feedback import JobProgress
from .wiring import _find, _qt_signal

if TYPE_CHECKING:
    from qgis_sdk.core.contexts import UiContext

    from .streams import StreamEvent, ViewSubscription

__all__ = ["HasAcceptCancel", "RunsJobs", "SubscribesStreams"]


class _Behaviour:
    """What the mixins share: a cooperative ``_attach_behaviours``."""

    ctx: UiContext

    def _attach_behaviours(self, root: Any, ctx: UiContext) -> None:
        chained = getattr(super(), "_attach_behaviours", None)
        if callable(chained):
            chained(root, ctx)


class RunsJobs(_Behaviour):
    """``self.run(action_id, **values)``: call an action, follow its job, cancel on close.

    Every handle an action returns is kept until it settles; when the window
    closes the ones still running are cancelled, so a dialog never leaves a
    job behind. A :class:`JobProgress` the surface stores as ``progress`` is
    bound to each new handle.
    """

    #: The attribute holding the ``JobProgress`` to bind, when the surface has one.
    progress_attribute: ClassVar[str] = "progress"

    def run(self, action_id: str, /, **values: object) -> Any:
        """Call ``action_id`` through ``ctx.actions``; return its result or handle."""
        result = self.ctx.actions.call(action_id, **values)
        if _is_job_handle(result):
            self._track(result)
        return result

    @property
    def jobs(self) -> tuple[Any, ...]:
        """The handles this surface started that have not settled."""
        handles = getattr(self, "_qgis_sdk_jobs", ())
        return tuple(handle for handle in handles if not handle.status.settled)

    def cancel_jobs(self) -> int:
        """Cancel every unsettled job; returns how many were still active."""
        cancelled = 0
        for handle in self.jobs:
            if handle.cancel():
                cancelled += 1
        return cancelled

    def _track(self, handle: Any) -> None:
        handles = list(getattr(self, "_qgis_sdk_jobs", ()))
        handles = [kept for kept in handles if not kept.status.settled]
        handles.append(handle)
        self._qgis_sdk_jobs = tuple(handles)
        progress = getattr(self, self.progress_attribute, None)
        if isinstance(progress, JobProgress):
            progress.bind(handle)

    def _attach_behaviours(self, root: Any, ctx: UiContext) -> None:
        ctx.scope.on_close(self.cancel_jobs)
        super()._attach_behaviours(root, ctx)


class SubscribesStreams(_Behaviour):
    """``self.subscribe(stream, callback)``: the view's subscriptions in one place."""

    def subscribe(
        self, stream: str, callback: Callable[[StreamEvent], None], /, **request: object
    ) -> ViewSubscription:
        """Subscribe for this window's lifetime; returns the subscription."""
        subscription = self.ctx.on(stream, callback, **request)
        kept = list(getattr(self, "_qgis_sdk_subscriptions", ()))
        kept.append(subscription)
        self._qgis_sdk_subscriptions = tuple(kept)
        return subscription

    @property
    def subscriptions(self) -> tuple[ViewSubscription, ...]:
        """The subscriptions still open."""
        kept = getattr(self, "_qgis_sdk_subscriptions", ())
        return tuple(item for item in kept if item.active)

    def unsubscribe_all(self) -> int:
        """End every open subscription; returns how many there were."""
        open_ones = self.subscriptions
        for subscription in open_ones:
            subscription.dispose()
        return len(open_ones)


class HasAcceptCancel(_Behaviour):
    """Wire the dialog's ``AcceptCancel`` row: Accept runs ``on_accept()``, both close.

    ``buttons`` names the row - the ``AcceptCancel`` component's name, or
    the ``objectName`` of a ``QDialogButtonBox`` in a hand-built or ``.ui``
    tree. ``on_accept()`` returning ``False`` keeps the window open (a
    validation failure); anything else closes it. Cancel calls
    ``on_cancel()`` and closes.
    """

    buttons: ClassVar[str] = "dialog_buttons"

    def on_accept(self) -> Any:
        """Override: what accepting does; return ``False`` to keep the window."""

    def on_cancel(self) -> None:
        """Override: what cancelling does, before the window closes."""

    def accept(self) -> bool:
        """What the Accept button does; returns whether the window was closed."""
        if self.on_accept() is False:
            return False
        self.ctx.view.request_close()
        return True

    def cancel(self) -> None:
        """What the Cancel button does."""
        self.on_cancel()
        self.ctx.view.request_close()

    def _attach_behaviours(self, root: Any, ctx: UiContext) -> None:
        node = _find(root, self.buttons)
        if node is None:
            raise QgisSdkUiError(
                f"{type(self).__name__} (HasAcceptCancel): build() produced no "
                f"node named {self.buttons!r}; give the AcceptCancel row that "
                "name or set `buttons`"
            )
        disconnects: list[Callable[[], None]] = []
        if isinstance(node, AcceptCancel):
            disconnects.append(node.accepted(self.accept))
            disconnects.append(node.cancelled(self.cancel))
        else:
            accepted = _qt_signal(node, "accepted")
            rejected = _qt_signal(node, "cancelled")
            if accepted is None or rejected is None:
                raise QgisSdkUiError(
                    f"{type(self).__name__} (HasAcceptCancel): {self.buttons!r} is "
                    f"a {type(node).__name__}, not an AcceptCancel row or a "
                    "QDialogButtonBox"
                )
            accepted.connect(self._accept_slot)
            rejected.connect(self._cancel_slot)
            disconnects.append(lambda: _disconnect(accepted, self._accept_slot))
            disconnects.append(lambda: _disconnect(rejected, self._cancel_slot))

        def unwire() -> None:
            for disconnect in disconnects:
                disconnect()

        ctx.scope.on_close(unwire)
        super()._attach_behaviours(root, ctx)

    def _accept_slot(self, *_ignored: object) -> None:
        self.accept()

    def _cancel_slot(self, *_ignored: object) -> None:
        self.cancel()


def _disconnect(signal: Any, slot: Callable[..., Any]) -> None:
    try:
        signal.disconnect(slot)
    except (TypeError, RuntimeError):  # already gone with the widget
        pass


def _is_job_handle(value: object) -> bool:
    status = getattr(value, "status", None)
    return (
        status is not None and hasattr(status, "settled") and hasattr(value, "cancel")
    )

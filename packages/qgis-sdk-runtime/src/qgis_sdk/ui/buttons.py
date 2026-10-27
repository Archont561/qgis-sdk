"""Buttons beyond the plain one: ``RunButton`` and ``AcceptCancel`` (TASK-96).

``RunButton`` presses into ``ctx.actions``: it collects the values (from a
``Form``, a mapping or a callable), calls the named action and, when the
action returns a job handle, hands it to a ``JobProgress``. A refusal -
unknown action, invalid values, the action still running from this view -
becomes a warning notification rather than an exception out of a Qt slot.
``AcceptCancel`` is the dialog's button row: ``accepted``/``cancelled``
listeners, ``accept()``/``cancel()`` to press them from a test.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from qgis_sdk.models import QgisSdkFormError, QgisSdkUiError

from .components import Button, Component
from .feedback import JobProgress
from .form import Form

__all__ = ["AcceptCancel", "RunButton"]

Values = Mapping[str, object] | Callable[[], Mapping[str, object]] | Form | None


class RunButton(Button):
    """A button that runs one of the plugin's actions through ``ctx.actions``.

    ``values`` is where the arguments come from: a :class:`Form` (its
    ``values()``), a mapping or a zero-argument callable. ``progress`` is a
    :class:`JobProgress` to bind the returned handle to. ``last`` is what the
    latest call returned; ``finished(listener)`` hears it.
    """

    def __init__(
        self,
        name: str | None = None,
        action_id: str | None = None,
        *,
        values: Values = None,
        progress: JobProgress | None = None,
        text: str | None = None,
        label: str | None = None,
    ) -> None:
        super().__init__(name, text, label=label)
        if not action_id or not isinstance(action_id, str):
            raise QgisSdkUiError(f"{self._describe()} needs an action id")
        self.action_id = action_id
        self._values = values
        self._progress = progress
        self._last: object = None
        self._finished: list[Callable[[object], None]] = []
        self.clicked(self.run)

    @property
    def progress(self) -> JobProgress | None:
        """The ``JobProgress`` a returned handle is bound to, if any."""
        return self._progress

    @property
    def last(self) -> object:
        """The result or job handle of the latest call; ``None`` before one."""
        return self._last

    def finished(self, listener: Callable[[object], None]) -> Callable[[], None]:
        """Call ``listener(result)`` after each call returned; returns the unsubscribe."""
        self._finished.append(listener)

        def unsubscribe() -> None:
            if listener in self._finished:
                self._finished.remove(listener)

        return unsubscribe

    def values(self) -> Mapping[str, object]:
        """The arguments the next press sends."""
        source = self._values
        if source is None:
            return {}
        if isinstance(source, Form):
            return source.values()
        if callable(source):
            return dict(source())
        return dict(source)

    def run(self) -> object:
        """Call the action now; what the press does.

        A refusal is reported through ``ctx.notifications.warning`` and
        returned as ``None``; the exception never leaves a Qt slot.
        """
        actions = self._require_ctx("actions")
        try:
            result = actions.call(self.action_id, **self.values())
        except (QgisSdkUiError, QgisSdkFormError) as error:
            self._last = None
            ctx = self._ctx
            if ctx is not None:
                ctx.notifications.warning(str(error))
            return None
        self._last = result
        if self._progress is not None and _is_job_handle(result):
            self._progress.bind(result)
        for listener in tuple(self._finished):
            listener(result)
        return result

    def dispose(self) -> None:
        super().dispose()
        self._finished.clear()

    def snapshot(self) -> dict[str, Any]:
        node = super().snapshot()
        node["action"] = self.action_id
        return node


class AcceptCancel(Component):
    """The dialog's Accept/Cancel row; a native ``QDialogButtonBox``.

    ``accepted(listener)``/``cancelled(listener)`` subscribe, ``accept()``/
    ``cancel()`` press. What accepting means is the surface's business (the
    ``AcceptCancel`` mixin wires ``on_accept`` and closing); the component
    only reports the press. ``objectName`` is ``buttons/<name>`` with the two
    buttons at ``buttons/<name>/accept`` and ``buttons/<name>/cancel``.
    """

    prefix = "buttons"

    def __init__(
        self,
        name: str | None = "dialog_buttons",
        *,
        accept_text: str = "OK",
        cancel_text: str = "Cancel",
        label: str | None = None,
    ) -> None:
        super().__init__(name, label=label)
        self.accept_text = accept_text
        self.cancel_text = cancel_text
        self._accepted: list[Callable[[], None]] = []
        self._cancelled: list[Callable[[], None]] = []

    def accepted(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Call ``listener()`` on Accept; returns the unsubscribe."""
        return _subscribe(self._accepted, listener)

    def cancelled(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Call ``listener()`` on Cancel; returns the unsubscribe."""
        return _subscribe(self._cancelled, listener)

    def accept(self) -> None:
        """Press Accept."""
        for listener in tuple(self._accepted):
            listener()

    def cancel(self) -> None:
        """Press Cancel."""
        for listener in tuple(self._cancelled):
            listener()

    def dispose(self) -> None:
        super().dispose()
        self._accepted.clear()
        self._cancelled.clear()

    def snapshot(self) -> dict[str, Any]:
        node = super().snapshot()
        node["accept"] = self.accept_text
        node["cancel"] = self.cancel_text
        return node

    def _from_widget(self, value: object) -> None:
        if value == "accept":
            self.accept()
        elif value == "cancel":
            self.cancel()


def _subscribe(
    listeners: list[Callable[[], None]], listener: Callable[[], None]
) -> Callable[[], None]:
    listeners.append(listener)

    def unsubscribe() -> None:
        if listener in listeners:
            listeners.remove(listener)

    return unsubscribe


def _is_job_handle(value: object) -> bool:
    status = getattr(value, "status", None)
    return (
        status is not None and hasattr(status, "settled") and hasattr(value, "cancel")
    )

"""``UiContext.actions``: a surface calls the plugin's own actions, validated.

A surface never holds the plugin instance (decision-55): it reaches an action
as ``self.ctx.actions.buffer(layer_id=..., distance=3)``. The call takes the
same validated path a page's bridge call takes - unknown ids and fields are
refused by name, values are coerced with the form rules, the handler is the
one the runtime bound - and it carries the *view's* authority: the id of the
surface that called, so a host can tell two windows apart, and one rule that
keeps a button from firing twice: while an action still runs from this view
(a plain handler on the GUI thread, or a job whose handle has not settled),
the same action is refused from the same view until it settles.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Protocol

from qgis_sdk.declarations import ActionDescription, PluginDescription
from qgis_sdk.models import QgisSdkFormError, QgisSdkUiError

from .form_fields import coerce_values

__all__ = ["ActionCall", "ViewActions"]


class ActionSource(Protocol):
    """What ``ViewActions`` reads: a started ``PluginRuntime`` fits."""

    @property
    def description(self) -> PluginDescription: ...

    @property
    def actions(self) -> Mapping[str, Callable[..., object]]: ...


class ViewActions:
    """The view-scoped dispatcher a ``UiContext`` carries as ``actions``.

    ``runtime`` is the started ``PluginRuntime`` (or anything with its
    ``description`` and ``actions``): the description is the allowlist and the
    bound handlers are read on every call, so an unloaded runtime refuses
    instead of calling a stale instance. ``view_id`` names the calling surface.
    """

    __slots__ = ("_markers", "_running", "_runtime", "_view_id")

    def __init__(
        self,
        runtime: ActionSource,
        *,
        view_id: str,
        markers: Mapping[str, Mapping[str, str]] | None = None,
    ) -> None:
        self._runtime = runtime
        self._view_id = view_id
        self._markers = dict(markers or {})
        self._running: dict[str, object] = {}

    @property
    def _description(self) -> PluginDescription:
        return self._runtime.description

    @property
    def _handlers(self) -> Mapping[str, Callable[..., object]]:
        return self._runtime.actions

    @property
    def view_id(self) -> str:
        """The id of the surface these calls are made from."""
        return self._view_id

    @property
    def ids(self) -> tuple[str, ...]:
        """The action ids this plugin declares, sorted."""
        return tuple(action.id for action in self._description.actions)

    def describe(self, action_id: str) -> ActionDescription:
        """The declared description of ``action_id``: its title and request schema.

        What ``Form.for_action`` builds its inputs from; an unknown id is
        refused naming the ids the plugin has.
        """
        return self._find(action_id)

    def running(self, action_id: str) -> bool:
        """Whether ``action_id`` is still running from this view."""
        pending = self._running.get(action_id)
        if pending is None:
            return False
        if _settled(pending):
            del self._running[action_id]
            return False
        return True

    def call(self, action_id: str, /, **values: object) -> object:
        """Run ``action_id`` with coerced ``values``; return its result or job handle."""
        action = self._find(action_id)
        if self.running(action.id):
            raise QgisSdkUiError(
                f"{action.id} is still running from {self._view_id}; "
                "wait for it to settle before calling it again"
            )
        handler = self._handlers.get(action.id)
        if handler is None:
            raise QgisSdkUiError(f"{action.id} is not bound: the plugin is not running")
        try:
            coerced = coerce_values(
                action, values, markers=self._markers.get(action.id)
            )
        except QgisSdkFormError as error:
            raise QgisSdkUiError(str(error)) from error
        self._running[action.id] = _RUNNING
        try:
            result = handler(**coerced)
        finally:
            del self._running[action.id]
        if _is_job_handle(result) and not _settled(result):
            self._running[action.id] = result
        return result

    def __getattr__(self, name: str) -> ActionCall:
        if name.startswith("_"):
            raise AttributeError(name)
        return ActionCall(self, self._find(name).id)

    def __getitem__(self, action_id: str) -> ActionCall:
        return ActionCall(self, self._find(action_id).id)

    def __contains__(self, action_id: object) -> bool:
        return any(action.id == action_id for action in self._description.actions)

    def _find(self, action_id: str) -> ActionDescription:
        for action in self._description.actions:
            if action.id == action_id:
                return action
        known = ", ".join(self.ids) or "none"
        raise QgisSdkUiError(
            f"{self._description.id} declares no action {action_id!r}; it has: {known}"
        )


class ActionCall:
    """``ctx.actions.buffer`` - one bound call, keyword arguments only."""

    __slots__ = ("_actions", "_id")

    def __init__(self, actions: ViewActions, action_id: str) -> None:
        self._actions = actions
        self._id = action_id

    @property
    def id(self) -> str:
        return self._id

    @property
    def running(self) -> bool:
        return self._actions.running(self._id)

    def __call__(self, **values: object) -> Any:
        return self._actions.call(self._id, **values)

    def __repr__(self) -> str:
        return f"ActionCall({self._id!r} from {self._actions.view_id!r})"


_RUNNING = object()


def _is_job_handle(value: object) -> bool:
    status = getattr(value, "status", None)
    return (
        status is not None and hasattr(status, "settled") and hasattr(value, "cancel")
    )


def _settled(pending: object) -> bool:
    if pending is _RUNNING:
        return False
    return bool(pending.status.settled)  # type: ignore[attr-defined]

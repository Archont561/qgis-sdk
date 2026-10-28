"""``ctx.notifications``: four levels and ``with_action`` (decision-55 point 3).

The contract is one ``_deliver`` wide; ``RecordingNotifications`` keeps
``messages`` for the assertion most tests make and ``records`` for the
level and the button, which ``press()`` runs the way a user would.
"""

from __future__ import annotations

import pytest
from qgis_sdk.core import PluginContext, PluginRuntime, ResourceScope
from qgis_sdk.declarations._plugin import action, plugin
from qgis_sdk.models import QgisSdkScopeClosedError
from qgis_sdk.services import LEVELS, Notification, NotificationAction, Notifications
from qgis_sdk.testing import RecordingNotifications


def test_every_level_is_recorded_with_its_message_and_no_button() -> None:
    scope = ResourceScope()
    notifications = RecordingNotifications(scope)

    for level in LEVELS:
        getattr(notifications, level)(f"{level} happened")

    assert notifications.messages == [f"{level} happened" for level in LEVELS]
    assert notifications.records == [
        Notification(level, f"{level} happened") for level in LEVELS
    ]
    assert all(
        callable(getattr(notifications, name))
        for name in dir(Notifications)
        if not name.startswith("_")
    )


def test_with_action_attaches_a_button_without_changing_the_original() -> None:
    scope = ResourceScope()
    notifications = RecordingNotifications(scope)

    undo = notifications.with_action("Undo", "undo_buffer", layer_id="L1")
    undo.success("Buffered")
    notifications.info("plain")

    assert notifications.messages == ["Buffered", "plain"]
    assert notifications.records[0] == Notification(
        "success",
        "Buffered",
        NotificationAction("Undo", "undo_buffer", {"layer_id": "L1"}),
    )
    assert notifications.records[1].action is None
    with pytest.raises(TypeError):
        notifications.records[0].action.arguments["layer_id"] = "L2"  # type: ignore[index]
    with pytest.raises(ValueError, match="label and an action id"):
        notifications.with_action("", "undo_buffer")


def test_pressing_the_button_runs_the_plugin_action_with_its_arguments() -> None:
    calls: list[str] = []

    @plugin(id="demo", title="Demo")
    class Demo:
        @action
        def undo(self, layer_id: str) -> str:
            calls.append(layer_id)
            return f"undone {layer_id}"

        @action
        def warn(self) -> None:
            self.ctx.notifications.with_action("Undo", "undo", layer_id="L1").warning(
                "Buffered L1"
            )

    scope = ResourceScope()
    notifications = RecordingNotifications(scope)
    runtime = PluginRuntime._from_plugin_class(
        Demo, PluginContext(notifications=notifications, scope=scope)
    )
    runtime.start()
    notifications.bind_actions(lambda action_id, **kw: runtime.actions[action_id](**kw))

    runtime.actions["warn"]()

    with pytest.raises(ValueError, match="carries no action"):
        notifications.info("no button")
        notifications.press()
    assert notifications.press(0) == "undone L1"
    assert calls == ["L1"]


def test_press_without_bound_actions_and_a_closed_scope_refuse() -> None:
    scope = ResourceScope()
    notifications = RecordingNotifications(scope)
    notifications.with_action("Go", "go").info("x")

    with pytest.raises(ValueError, match="no actions bound"):
        notifications.press()

    scope.close()
    with pytest.raises(QgisSdkScopeClosedError):
        notifications.critical("late")

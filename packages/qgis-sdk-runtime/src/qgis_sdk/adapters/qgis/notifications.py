"""Native implementation of the ``Notifications`` contract: the message log.

Where the message surfaces is an adapter concern: the default goes to the
QGIS message log, which exists in every runtime including a headless one, at
the level the plugin chose; a Desktop deployment injects the message-bar
sink it owns (``MessageBarNotifications``) without any plugin code changing.
The log has no buttons, so a ``with_action`` label is written after the
message instead of being pressable.
"""

from __future__ import annotations

from collections.abc import Callable

from qgis.core import Qgis, QgsMessageLog

from qgis_sdk.core import ResourceScope
from qgis_sdk.services import Notification, NotificationsBase

NOTIFICATION_TAG = "qgis-sdk"

__all__ = ["LEVEL_MAP", "NativeNotifications"]

#: The SDK's four levels on QGIS's ``MessageLevel``.
LEVEL_MAP = {
    "info": Qgis.MessageLevel.Info,
    "success": Qgis.MessageLevel.Success,
    "warning": Qgis.MessageLevel.Warning,
    "critical": Qgis.MessageLevel.Critical,
}


class NativeNotifications(NotificationsBase):
    """Deliver messages through a QGIS-owned sink, the message log by default."""

    def __init__(
        self,
        scope: ResourceScope,
        sink: Callable[[Notification], None] | None = None,
    ) -> None:
        self._scope = scope
        self._sink = sink if sink is not None else _log_to_message_log

    def _deliver(self, notification: Notification) -> None:
        """Deliver one message, if this runtime is still open."""
        self._scope.ensure_open()
        self._sink(notification)


def _log_to_message_log(notification: Notification) -> None:
    """Write to the QGIS message log, the sink every runtime has."""
    message = notification.message
    if notification.action is not None:
        message = (
            f"{message} [{notification.action.label}: {notification.action.action_id}]"
        )
    QgsMessageLog.logMessage(message, NOTIFICATION_TAG, LEVEL_MAP[notification.level])

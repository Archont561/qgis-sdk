"""Native implementation of the existing ``Notifications`` contract.

The contract stays one method wide. Where the message surfaces is an adapter
concern: the default goes to the QGIS message log, which exists in every runtime
including a headless one, and a Desktop deployment can inject the message-bar
sink it owns without any plugin code changing.
"""

from __future__ import annotations

from collections.abc import Callable

from qgis.core import Qgis, QgsMessageLog

from qgis_sdk.core import ResourceScope

NOTIFICATION_TAG = "qgis-sdk"

__all__ = ["NativeNotifications"]


class NativeNotifications:
    """Deliver informational messages through a QGIS-owned sink."""

    def __init__(
        self,
        scope: ResourceScope,
        sink: Callable[[str], None] | None = None,
    ) -> None:
        self._scope = scope
        self._sink = sink if sink is not None else _log_to_message_log

    def info(self, message: str) -> None:
        """Deliver one informational message, if this runtime is still open."""
        self._scope.ensure_open()
        self._sink(message)


def _log_to_message_log(message: str) -> None:
    """Write to the QGIS message log, the sink every runtime has."""
    QgsMessageLog.logMessage(message, NOTIFICATION_TAG, Qgis.MessageLevel.Info)

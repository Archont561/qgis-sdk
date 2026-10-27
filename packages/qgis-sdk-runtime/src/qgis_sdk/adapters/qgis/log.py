"""Native implementation of the ``Log`` contract: ``QgsMessageLog`` by tag.

Every record a plugin writes through ``ctx.log`` lands in the QGIS message
log under the plugin's own tag (decision-63), so the Log Messages panel
groups one plugin's records together and a user can read them without the
SDK. ``debug`` maps to ``NoLevel``: QGIS has no debug level and the records
still arrive, just unhighlighted.
"""

from __future__ import annotations

from qgis.core import Qgis, QgsMessageLog

from qgis_sdk.core import ResourceScope
from qgis_sdk.services import LogBase, LogRecord

__all__ = ["LOG_LEVEL_MAP", "NativeLog"]

#: The SDK's four levels on QGIS's ``MessageLevel``.
LOG_LEVEL_MAP = {
    "debug": Qgis.MessageLevel.NoLevel,
    "info": Qgis.MessageLevel.Info,
    "warning": Qgis.MessageLevel.Warning,
    "error": Qgis.MessageLevel.Critical,
}


class NativeLog(LogBase):
    """Write records to the QGIS message log under the plugin's tag."""

    def __init__(self, scope: ResourceScope, plugin: str) -> None:
        super().__init__(plugin)
        self._scope = scope

    def _deliver(self, record: LogRecord) -> None:
        self._scope.ensure_open()
        QgsMessageLog.logMessage(
            record.format(), self.plugin, LOG_LEVEL_MAP[record.level]
        )

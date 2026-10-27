"""``NativeLog`` writes to the QGIS message log under the plugin's tag (TASK-96 AC 4)."""

from __future__ import annotations

from typing import Any

import pytest

pytestmark = pytest.mark.qgis

try:
    from qgis.core import Qgis, QgsApplication
except ImportError as error:  # pragma: no cover - depends on the host
    pytest.skip(f"the native log needs QGIS: {error}", allow_module_level=True)

from qgis_sdk.core import ResourceScope


def test_records_reach_the_message_log_under_the_plugin_tag(qgis_app: Any) -> None:
    from qgis_sdk.adapters.qgis import NativeLog, native_plugin_context

    received: list[tuple[str, str, Any]] = []
    message_log = QgsApplication.messageLog()
    # QGIS 4 emits ``messageReceivedWithFormat``; 3.x the three-argument
    # ``messageReceived`` (overloaded with a ``bool`` form).
    with_format = getattr(message_log, "messageReceivedWithFormat", None)
    signal = (
        with_format
        if with_format is not None
        else message_log.messageReceived[str, str, Qgis.MessageLevel]
    )

    def slot(message: str, tag: str, level: Any, *_format: Any) -> None:
        received.append((message, tag, level))

    signal.connect(slot)
    scope = ResourceScope()
    try:
        context = native_plugin_context(scope, settings_prefix="field_tools")
        assert isinstance(context.log, NativeLog)
        heard: list[str] = []
        context.log.subscribe(lambda record: heard.append(record.level))

        context.log.info("started", layer="sites")
        context.log.error("failed")
        context.log.debug("detail")
        qgis_app.processEvents()

        assert heard == ["info", "error", "debug"]
        ours = [entry for entry in received if entry[1] == "field_tools"]
        assert [entry[0] for entry in ours] == [
            "started layer='sites'",
            "failed",
            "detail",
        ]
        assert ours[0][2] == Qgis.MessageLevel.Info
        assert ours[1][2] == Qgis.MessageLevel.Critical
        assert ours[2][2] == Qgis.MessageLevel.NoLevel
    finally:
        signal.disconnect(slot)
        scope.close()

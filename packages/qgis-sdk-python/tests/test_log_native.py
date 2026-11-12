"""``NativeLog`` writes to the QGIS message log under the plugin's tag (TASK-96 AC 4)."""

from __future__ import annotations

import copy
from typing import Any

import pytest


class _CcState:
    """A mutable record shared by the phases of one long function."""

    def __init__(_cc_self, **values):
        _cc_self.__dict__.update(values)


class _CcReturn:
    """An early return travelling out of a phase."""

    def __init__(_cc_self, value):
        _cc_self.value = value


class _CcBreak:
    """A loop break travelling out of a phase."""


class _CcContinue:
    """A loop continue travelling out of a phase."""


def _cc_test_records_rea_p1(_s):
    from qgis_sdk.adapters.qgis import (
        NativeContextOptions,
        NativeLog,
        native_plugin_context,
    )

    _s.NativeContextOptions = NativeContextOptions
    _s.NativeLog = NativeLog
    _s.native_plugin_context = native_plugin_context

    _s.received: list[tuple[str, str, Any]] = []
    _s.message_log = QgsApplication.messageLog()
    # QGIS 4 emits ``messageReceivedWithFormat``; 3.x the three-argument
    # ``messageReceived`` (overloaded with a ``bool`` form).
    _s.with_format = getattr(_s.message_log, "messageReceivedWithFormat", None)


def _cc_test_records_rea_p2(_s):
    _s.context = _s.native_plugin_context(
        _s.scope, _s.NativeContextOptions(settings_prefix="field_tools")
    )
    assert isinstance(_s.context.log, _s.NativeLog)
    _s.heard: list[str] = []
    _s.context.log.subscribe(lambda record: _s.heard.append(record.level))

    _s.context.log.info("started", layer="sites")
    _s.context.log.error("failed")
    _s.context.log.debug("detail")
    _s.qgis_app.processEvents()


def _cc_test_records_rea_p3(_s):

    assert _s.heard == ["info", "error", "debug"]
    _s.ours = [entry for entry in _s.received if entry[1] == "field_tools"]
    assert [entry[0] for entry in _s.ours] == _cc_fresh_1()
    assert _s.ours[0][2] == Qgis.MessageLevel.Info
    assert _s.ours[1][2] == Qgis.MessageLevel.Critical
    assert _s.ours[2][2] == Qgis.MessageLevel.NoLevel


def _cc_test_records_rea_p4(_s):
    _s.signal.disconnect(_s.slot)
    _s.scope.close()


def _cc_test_records_rea_p5(_s):
    _s.signal = (
        _s.with_format
        if _s.with_format is not None
        else _s.message_log.messageReceived[str, str, Qgis.MessageLevel]
    )

    def slot(message: str, tag: str, level: Any, *_format: Any) -> None:
        _s.received.append((message, tag, level))

    _s.slot = slot

    _s.signal.connect(_s.slot)
    _s.scope = ResourceScope()


def _cc_test_records_rea_p6(_s):
    try:
        for _p in (_cc_test_records_rea_p2, _cc_test_records_rea_p3):
            _r = _p(_s)
            if isinstance(_r, _CcReturn):
                return _r
    finally:
        for _p in (_cc_test_records_rea_p4,):
            _p(_s)


_CC_DATA_1 = [
    "started layer='sites'",
    "failed",
    "detail",
]


def _cc_fresh_1():
    """Return a fresh copy of the shared data literal."""
    return copy.deepcopy(_CC_DATA_1)


pytestmark = pytest.mark.qgis

try:
    from qgis.core import Qgis, QgsApplication
except ImportError as error:  # pragma: no cover - depends on the host
    pytest.skip(f"the native log needs QGIS: {error}", allow_module_level=True)

from qgis_sdk.core import ResourceScope


def test_records_reach_the_message_log_under_the_plugin_tag(qgis_app: Any) -> None:
    _s = _CcState(qgis_app=qgis_app)
    for _p in (
        _cc_test_records_rea_p1,
        _cc_test_records_rea_p5,
        _cc_test_records_rea_p6,
    ):
        _r = _p(_s)
        if isinstance(_r, _CcReturn):
            return _r.value
    return None

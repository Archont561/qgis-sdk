"""``ctx.log``: the structured-record minimum (decision-63; TASK-96 AC 4)."""

from __future__ import annotations

import pytest
from qgis_sdk.core import PluginContext, ResourceScope, UiContext
from qgis_sdk.models import QgisSdkScopeClosedError, QgisSdkUnsupportedCapabilityError
from qgis_sdk.services import LOG_LEVELS, LogBase, LogRecord
from qgis_sdk.testing import FakeViewControl, RecordingLog, RecordingNotifications


def test_every_level_writes_one_record_with_its_fields() -> None:
    scope = ResourceScope()
    log = RecordingLog(scope, "field_tools")

    log.debug("probing")
    log.info("started", layer="sites", count=3)
    log.warning("slow", seconds=2.5)
    log.error("failed", code=7)

    assert [record.level for record in log.records] == list(LOG_LEVELS)
    assert log.messages == ["probing", "started", "slow", "failed"]
    record = log.records[1]
    assert record.plugin == "field_tools"
    assert dict(record.fields) == {"layer": "sites", "count": 3}
    assert record.time > 0
    assert record.correlation is None
    assert record.format() == "started layer='sites' count=3"
    assert log.records[0].format() == "probing"
    with pytest.raises(TypeError):
        record.fields["layer"] = "other"  # type: ignore[index]


def test_subscribers_hear_each_record_after_delivery_until_they_unsubscribe() -> None:
    scope = ResourceScope()
    log = RecordingLog(scope)
    order: list[str] = []

    class Ordered(LogBase):
        def _deliver(self, record: LogRecord) -> None:
            order.append(f"deliver:{record.message}")

    ordered = Ordered("p")
    unsubscribe = ordered.subscribe(
        lambda record: order.append(f"hear:{record.message}")
    )
    ordered.info("one")
    unsubscribe()
    unsubscribe()
    ordered.info("two")
    assert order == ["deliver:one", "hear:one", "deliver:two"]

    heard: list[LogRecord] = []
    log.subscribe(heard.append)
    log.warning("w")
    assert heard == log.records


def test_a_closed_scope_refuses_further_records() -> None:
    scope = ResourceScope()
    log = RecordingLog(scope)
    scope.close()
    with pytest.raises(QgisSdkScopeClosedError):
        log.info("late")
    assert log.records == []


def test_log_is_a_capability_of_both_contexts() -> None:
    scope = ResourceScope()
    notifications = RecordingNotifications(scope)
    log = RecordingLog(scope)

    bare = PluginContext(notifications, scope)
    assert bare.has("log") is False
    with pytest.raises(QgisSdkUnsupportedCapabilityError, match="'log'"):
        _ = bare.log
    assert bare.with_services(log=log).log is log

    ui = UiContext(notifications, FakeViewControl(), scope, log=log)
    assert ui.log is log
    assert ui.capabilities == frozenset({"log"})

"""The runtime half of the worker contract: a GUI-bound capability off its thread.

A source check reads what the source shows (``qgis-sdk check``, TASK-117); a
capability captured on the driving thread and read inside a job defeats it.
The context therefore remembers the thread it was assembled on and reports the
read - once per capability and thread by default, and as an error in a
development session (decision-69).
"""

from __future__ import annotations

import threading
import warnings
from dataclasses import dataclass, field
from typing import Any

import pytest
from qgis_sdk.core import (
    GUI_BOUND_CAPABILITIES,
    JobContext,
    PluginContext,
    ResourceScope,
    UiContext,
)
from qgis_sdk.core.contexts import _reported_cross_thread
from qgis_sdk.environment import DEV_REQUEST_ENV
from qgis_sdk.models import (
    QgisSdkThreadSafetyWarning,
    QgisSdkUnsupportedCapabilityError,
)


@dataclass
class RecordingNotifications:
    messages: list[str] = field(default_factory=list)

    def info(self, message: str) -> None:
        self.messages.append(message)


@dataclass
class RecordingProgress:
    reported: list[float] = field(default_factory=list)

    def set(self, value: float) -> None:
        self.reported.append(value)


@dataclass
class ControlledCancellation:
    cancelled: bool = False

    def is_cancelled(self) -> bool:
        return self.cancelled


@pytest.fixture(autouse=True)
def _fresh_reports() -> Any:
    """Start every test with no capability reported as read off its thread."""
    _reported_cross_thread.clear()
    yield
    _reported_cross_thread.clear()


def plugin_context(**services: object) -> PluginContext:
    """A plugin context on this thread with ``services`` provided."""
    return PluginContext(
        notifications=RecordingNotifications(), scope=ResourceScope(), **services
    )


def in_a_worker(read: Any) -> list[BaseException]:
    """Run ``read`` on another thread and hand back whatever it raised."""
    failures: list[BaseException] = []

    def run() -> None:
        try:
            read()
        except BaseException as error:  # noqa: BLE001 - the test inspects it
            failures.append(error)

    thread = threading.Thread(target=run, name="worker-under-test")
    thread.start()
    thread.join()
    return failures


def test_a_gui_bound_capability_read_off_its_thread_warns_once() -> None:
    layers = object()
    context = plugin_context(layers=layers)

    def read_twice() -> None:
        for _ in range(2):
            assert context.layers is layers

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert in_a_worker(read_twice) == []
        in_a_worker(lambda: context.layers)

    messages = [str(item.message) for item in caught]
    assert all(item.category is QgisSdkThreadSafetyWarning for item in caught)
    assert len(messages) == 2  # one per thread, not one per read
    assert "PluginContext.layers is GUI-bound" in messages[0]
    assert "worker-under-test" in messages[0]


def test_the_assembling_thread_reads_without_a_warning() -> None:
    layers = object()
    context = plugin_context(layers=layers)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert context.layers is layers

    assert caught == []


@pytest.mark.parametrize(
    "capability", ["network", "settings", "styles", "workers", "algorithms", "log"]
)
def test_a_cross_thread_read_of_another_capability_is_silent(capability: str) -> None:
    service = object()
    context = plugin_context(**{capability: service})

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert in_a_worker(lambda: getattr(context, capability)) == []
        assert getattr(context, capability) is service

    assert caught == []


def test_a_development_session_raises_at_the_call_site(monkeypatch: Any) -> None:
    monkeypatch.setenv(DEV_REQUEST_ENV, "/tmp/qgis-sdk-dev-request.json")
    context = plugin_context(layers=object())

    first = in_a_worker(lambda: context.layers)
    assert isinstance(first[0], QgisSdkUnsupportedCapabilityError)
    assert first[0].capability == "layers"
    assert "GUI-bound" in str(first[0])
    # A development session wants every read, not the first one only.
    second = in_a_worker(lambda: context.layers)
    assert isinstance(second[0], QgisSdkUnsupportedCapabilityError)


def test_the_guard_covers_exactly_the_capabilities_that_reach_gui_state() -> None:
    assert GUI_BOUND_CAPABILITIES == {
        "actions",
        "desktop",
        "files",
        "layers",
        "project",
        "streams",
        "ui",
    }
    assert GUI_BOUND_CAPABILITIES.isdisjoint(
        {"progress", "cancellation", "network", "settings", "styles", "workers"}
    )


def test_the_view_and_job_contexts_record_their_thread_too() -> None:
    ui = UiContext(
        notifications=RecordingNotifications(),
        view=object(),  # type: ignore[arg-type]
        scope=ResourceScope(),
        layers=object(),
        ui=object(),
    )
    job = JobContext(
        progress=RecordingProgress(),
        cancellation=ControlledCancellation(),
        scope=ResourceScope(),
        project=object(),
    )

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert in_a_worker(lambda: ui.ui) == []
        assert in_a_worker(lambda: job.project) == []

    assert [item.category for item in caught] == [QgisSdkThreadSafetyWarning] * 2
    assert "UiContext.ui is GUI-bound" in str(caught[0].message)
    assert "JobContext.project is GUI-bound" in str(caught[1].message)

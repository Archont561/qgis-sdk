"""Desktop lifecycle adapter tests without importing QGIS or Qt."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from qgis_sdk import action, plugin
from qgis_sdk.adapters.desktop import DesktopLifecycleAdapter, create_class_factory
from qgis_sdk.core import (
    PluginContext,
    PluginRuntimeState,
    QgisSdkPluginLifecycleError,
    ResourceScope,
)


@dataclass
class RecordingNotifications:
    messages: list[str] = field(default_factory=list)

    def info(self, message: str) -> None:
        self.messages.append(message)


@plugin(id="example.desktop", title="Desktop example")
class DesktopTools:
    def __init__(self, ctx: PluginContext) -> None:
        self.ctx = ctx

    @action(id="run", title="Run")
    def run(self, value: int) -> int:
        return value


@dataclass
class FakeIface:
    name: str = "desktop"


def context_factory(iface: object) -> PluginContext:
    del iface
    return PluginContext(notifications=RecordingNotifications(), scope=ResourceScope())


def test_adapter_builds_the_context_from_iface_and_delegates_lifecycle() -> None:
    iface = FakeIface()

    adapter = DesktopLifecycleAdapter(
        DesktopTools, iface=iface, context_factory=context_factory
    )

    assert adapter.iface is iface
    assert adapter.runtime.state is PluginRuntimeState.NEW

    adapter.initGui()

    assert adapter.runtime.state is PluginRuntimeState.RUNNING
    assert adapter.runtime.actions["run"](4) == 4

    adapter.unload()
    adapter.unload()

    assert adapter.runtime.state is PluginRuntimeState.STOPPED
    assert adapter.runtime.instance is None


def test_class_factory_helper_returns_a_qgis_entry_point() -> None:
    iface = FakeIface()
    class_factory = create_class_factory(DesktopTools, context_factory=context_factory)

    adapter = class_factory(iface)

    assert isinstance(adapter, DesktopLifecycleAdapter)
    assert adapter.iface is iface


def test_context_factory_receives_the_iface() -> None:
    iface = FakeIface()
    received: list[object] = []

    def factory(received_iface: object) -> PluginContext:
        received.append(received_iface)
        return context_factory(received_iface)

    DesktopLifecycleAdapter(DesktopTools, iface=iface, context_factory=factory)

    assert received == [iface]


def test_init_gui_twice_is_rejected_without_reconstructing() -> None:
    adapter = DesktopLifecycleAdapter(
        DesktopTools, iface=FakeIface(), context_factory=context_factory
    )
    adapter.initGui()
    instance = adapter.runtime.instance

    with pytest.raises(QgisSdkPluginLifecycleError):
        adapter.initGui()

    assert adapter.runtime.instance is instance


def test_unload_before_init_gui_disposes_the_owned_scope() -> None:
    context = PluginContext(
        notifications=RecordingNotifications(), scope=ResourceScope()
    )

    adapter = DesktopLifecycleAdapter(
        DesktopTools, iface=FakeIface(), context_factory=lambda iface: context
    )
    adapter.unload()

    assert context.scope.closed
    assert adapter.runtime.state is PluginRuntimeState.STOPPED

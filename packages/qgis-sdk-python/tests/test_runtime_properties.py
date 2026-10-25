"""Property tests for repeated lifecycle calls on the public plugin runtime."""

from dataclasses import dataclass, field

from hypothesis import given, settings
from hypothesis import strategies as st
from qgis_sdk import action, plugin
from qgis_sdk.core import (
    PluginContext,
    PluginRuntime,
    PluginRuntimeState,
    ResourceScope,
)


@dataclass
class RecordingNotifications:
    messages: list[str] = field(default_factory=list)

    def info(self, message: str) -> None:
        self.messages.append(message)


@plugin(id="example.property", title="Property example")
class PropertyPlugin:
    ctx: PluginContext

    @action(id="noop", title="Noop")
    def noop(self) -> None:
        pass


@given(
    cleanup_count=st.integers(min_value=0, max_value=8),
    unload_calls=st.integers(min_value=0, max_value=4),
)
@settings(max_examples=60, deadline=None)
def test_repeated_unload_releases_each_owned_resource_exactly_once(
    cleanup_count: int, unload_calls: int
) -> None:
    released: list[int] = []
    context = PluginContext(
        notifications=RecordingNotifications(), scope=ResourceScope()
    )
    for index in range(cleanup_count):
        context.scope.on_close(lambda index=index: released.append(index))
    runtime = PluginRuntime(PropertyPlugin, context)
    runtime.start()

    for _ in range(unload_calls):
        runtime.unload()

    expected = list(reversed(range(cleanup_count))) if unload_calls else []
    expected_state = (
        PluginRuntimeState.STOPPED if unload_calls else PluginRuntimeState.RUNNING
    )
    assert released == expected
    assert runtime.state is expected_state
    assert len(runtime.actions) == (0 if unload_calls else 1)

"""Author-facing lifecycle scenarios against the public PluginRuntime API."""

from dataclasses import dataclass, field

import pytest
from pytest_bdd import given, scenarios, then, when
from qgis_sdk import action, plugin
from qgis_sdk.core import (
    PluginContext,
    PluginRuntime,
    PluginRuntimeState,
    QgisSdkPluginLifecycleError,
    ResourceScope,
)

scenarios("features/runtime_lifecycle.feature")


@dataclass
class RecordingNotifications:
    messages: list[str] = field(default_factory=list)

    def info(self, message: str) -> None:
        self.messages.append(message)


def plugin_context() -> PluginContext:
    return PluginContext(notifications=RecordingNotifications(), scope=ResourceScope())


@dataclass
class RuntimeScenario:
    context: PluginContext
    runtime: PluginRuntime
    released: list[str] = field(default_factory=list)
    instance: object | None = None
    error: BaseException | None = None


@given(
    "a declared plugin that records the context it receives",
    target_fixture="scenario",
)
def declared_plugin_recording_context() -> RuntimeScenario:
    @plugin(id="example.bdd.context", title="Context example")
    class Recorded:
        def __init__(self, ctx: PluginContext) -> None:
            self.ctx = ctx

        @action(id="run", title="Run")
        def run(self, value: int) -> int:
            return value

    context = plugin_context()
    return RuntimeScenario(context, PluginRuntime(Recorded, context))


@when("the runtime starts")
def start_runtime(scenario: RuntimeScenario) -> None:
    scenario.instance = scenario.runtime.start()


@then("the plugin receives that same context")
def plugin_received_context(scenario: RuntimeScenario) -> None:
    assert scenario.instance.ctx is scenario.context


@then("the declared action is bound to the instance")
def action_is_bound(scenario: RuntimeScenario) -> None:
    assert scenario.runtime.actions["run"](5) == 5


@then("the runtime is running")
def runtime_is_running(scenario: RuntimeScenario) -> None:
    assert scenario.runtime.state is PluginRuntimeState.RUNNING


@given(
    "a plugin that registers owned resources and then fails to construct",
    target_fixture="scenario",
)
def failing_plugin_with_resources() -> RuntimeScenario:
    released: list[str] = []

    @plugin(id="example.bdd.broken", title="Broken example")
    class Broken:
        def __init__(self, ctx: PluginContext) -> None:
            ctx.scope.on_close(lambda: released.append("action"))
            ctx.scope.on_close(lambda: released.append("signal"))
            ctx.scope.on_close(lambda: released.append("dock"))
            ctx.scope.on_close(lambda: released.append("work"))
            raise ValueError("author startup failed")

        @action(id="run", title="Run")
        def run(self) -> None:
            pass

    context = plugin_context()
    return RuntimeScenario(context, PluginRuntime(Broken, context), released=released)


@when("its runtime start is attempted")
def attempt_start(scenario: RuntimeScenario) -> None:
    try:
        scenario.runtime.start()
    except BaseException as error:  # noqa: BLE001 - the scenario records it
        scenario.error = error


@then("the original startup error is raised")
def original_startup_error(scenario: RuntimeScenario) -> None:
    assert isinstance(scenario.error, ValueError)
    assert str(scenario.error) == "author startup failed"


@then("owned resources are released in reverse order")
def resources_released_in_reverse(scenario: RuntimeScenario) -> None:
    assert scenario.released == ["work", "dock", "signal", "action"]


@then("the runtime is failed and unloading it again is safe")
def failed_runtime_can_unload(scenario: RuntimeScenario) -> None:
    assert scenario.runtime.state is PluginRuntimeState.FAILED
    scenario.runtime.unload()
    assert scenario.released == ["work", "dock", "signal", "action"]


@then("restarting the failed runtime is rejected")
def failed_runtime_cannot_restart(scenario: RuntimeScenario) -> None:
    with pytest.raises(QgisSdkPluginLifecycleError):
        scenario.runtime.start()


@given("a running plugin with two owned resources", target_fixture="scenario")
def running_plugin_with_two_resources() -> RuntimeScenario:
    released: list[str] = []

    @plugin(id="example.bdd.owned", title="Owned example")
    class Owned:
        def __init__(self, ctx: PluginContext) -> None:
            ctx.scope.on_close(lambda: released.append("first"))
            ctx.scope.on_close(lambda: released.append("second"))

        @action(id="run", title="Run")
        def run(self) -> None:
            pass

    context = plugin_context()
    runtime = PluginRuntime(Owned, context)
    runtime.start()
    return RuntimeScenario(context, runtime, released=released)


@when("the runtime unloads three times")
def unload_three_times(scenario: RuntimeScenario) -> None:
    scenario.runtime.unload()
    scenario.runtime.unload()
    scenario.runtime.unload()


@then("each resource is released once and the runtime is stopped")
def resources_released_once(scenario: RuntimeScenario) -> None:
    assert scenario.released == ["second", "first"]
    assert scenario.runtime.state is PluginRuntimeState.STOPPED


@then("the bound actions are cleared")
def actions_cleared(scenario: RuntimeScenario) -> None:
    assert dict(scenario.runtime.actions) == {}
    assert scenario.runtime.instance is None

"""Public lifecycle contract for constructing and disposing plain plugin classes."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field

import pytest
from qgis_sdk import QgisSdkDeclarationError, action, plugin, stream
from qgis_sdk.core import (
    PluginContext,
    PluginRuntime,
    PluginRuntimeState,
    QgisSdkPluginLifecycleError,
    ResourceScope,
)
from qgis_sdk.models import QgisSdkScopeClosedError


@dataclass
class RecordingNotifications:
    messages: list[str] = field(default_factory=list)

    def info(self, message: str) -> None:
        self.messages.append(message)


def plugin_context() -> PluginContext:
    return PluginContext(notifications=RecordingNotifications(), scope=ResourceScope())


@plugin(id="example.tools", title="Example tools")
class Tools:
    def __init__(self, ctx: PluginContext) -> None:
        self.ctx = ctx

    @action(id="run", title="Run")
    def run(self, value: int) -> int:
        return value


def test_start_constructs_the_plugin_with_the_explicit_context() -> None:
    context = plugin_context()
    runtime = PluginRuntime(Tools, context)

    assert runtime.state is PluginRuntimeState.NEW
    assert runtime.instance is None
    assert dict(runtime.actions) == {}
    assert runtime.description.id == "example.tools"

    instance = runtime.start()

    assert instance.ctx is context
    assert runtime.state is PluginRuntimeState.RUNNING
    assert runtime.instance is instance
    assert list(runtime.actions) == ["run"]
    assert runtime.actions["run"](3) == 3


def test_explicit_instance_factory_receives_context_without_calling_the_constructor() -> (
    None
):
    context = plugin_context()
    factory_calls: list[PluginContext] = []

    class ConstructorTrap(Tools):
        def __init__(self, ctx: PluginContext) -> None:
            raise AssertionError("the default constructor must not run")

    @plugin(id="example.factory", title="Factory example")
    class FactoryTools(ConstructorTrap):
        pass

    def factory(received: PluginContext) -> object:
        factory_calls.append(received)
        instance = object.__new__(FactoryTools)
        instance.ctx = received
        return instance

    instance = PluginRuntime(FactoryTools, context, instance_factory=factory).start()

    assert factory_calls == [context]
    assert instance.ctx is context


def test_runtime_rejects_an_undeclared_class_without_constructing_it() -> None:
    context = plugin_context()
    constructed: list[bool] = []

    class Plain:
        def __init__(self, ctx: PluginContext) -> None:
            constructed.append(True)

    with pytest.raises(QgisSdkDeclarationError):
        PluginRuntime(Plain, context)

    assert constructed == []


def test_runtime_rejects_an_already_disposed_context() -> None:
    context = plugin_context()
    context.scope.close()

    with pytest.raises(QgisSdkScopeClosedError):
        PluginRuntime(Tools, context)


def test_starting_twice_does_not_construct_twice() -> None:
    constructed: list[int] = []

    @plugin(id="example.counted", title="Counted")
    class Counted:
        def __init__(self, ctx: PluginContext) -> None:
            constructed.append(1)

        @action(id="noop", title="Noop")
        def noop(self) -> None:
            pass

    runtime = PluginRuntime(Counted, plugin_context())
    runtime.start()

    with pytest.raises(QgisSdkPluginLifecycleError) as caught:
        runtime.start()

    assert caught.value.code == "invalid_plugin_lifecycle"
    assert "running" in str(caught.value)
    assert constructed == [1]


def test_actions_are_read_only_and_cleared_on_unload() -> None:
    runtime = PluginRuntime(Tools, plugin_context())
    instance = runtime.start()

    with pytest.raises(TypeError):
        runtime.actions["other"] = lambda: None  # type: ignore[index]

    runtime.unload()

    assert runtime.state is PluginRuntimeState.STOPPED
    assert runtime.instance is None
    assert dict(runtime.actions) == {}
    assert instance.ctx.scope.closed


def test_unload_closes_the_owned_scope_once_and_is_repeatable() -> None:
    context = plugin_context()
    released: list[str] = []
    context.scope.on_close(lambda: released.append("closed"))
    runtime = PluginRuntime(Tools, context)
    runtime.start()

    runtime.unload()
    runtime.unload()

    assert released == ["closed"]
    assert context.scope.closed
    assert runtime.state is PluginRuntimeState.STOPPED


def test_unload_before_start_still_disposes_registered_resources() -> None:
    context = plugin_context()
    released: list[str] = []
    context.scope.on_close(lambda: released.append("registered"))
    runtime = PluginRuntime(Tools, context)

    runtime.unload()

    assert released == ["registered"]
    assert runtime.state is PluginRuntimeState.STOPPED


def test_unload_disposes_owned_resources_in_reverse_registration_order() -> None:
    released: list[str] = []

    @plugin(id="example.owned", title="Owned")
    class Owned:
        def __init__(self, ctx: PluginContext) -> None:
            ctx.scope.on_close(lambda: released.append("action"))
            ctx.scope.on_close(lambda: released.append("signal"))
            ctx.scope.on_close(lambda: released.append("dock"))
            ctx.scope.on_close(lambda: released.append("work"))

        @action(id="run", title="Run")
        def run(self) -> None:
            pass

    runtime = PluginRuntime(Owned, plugin_context())
    runtime.start()

    runtime.unload()

    assert released == ["work", "dock", "signal", "action"]


def test_partial_startup_failure_disposes_owned_resources_and_reraises() -> None:
    context = plugin_context()
    released: list[str] = []

    @plugin(id="example.broken", title="Broken")
    class Broken:
        def __init__(self, ctx: PluginContext) -> None:
            ctx.scope.on_close(lambda: released.append("action"))
            ctx.scope.on_close(lambda: released.append("work"))
            raise ValueError("author construction failed")

        @action(id="run", title="Run")
        def run(self) -> None:
            pass

    runtime = PluginRuntime(Broken, context)

    with pytest.raises(ValueError, match="author construction failed"):
        runtime.start()

    assert released == ["work", "action"]
    assert context.scope.closed
    assert runtime.state is PluginRuntimeState.FAILED
    assert runtime.instance is None
    assert dict(runtime.actions) == {}

    runtime.unload()
    assert released == ["work", "action"]

    with pytest.raises(QgisSdkPluginLifecycleError):
        runtime.start()


def test_factory_returning_another_type_fails_binding_and_cleans_up() -> None:
    context = plugin_context()
    released: list[str] = []

    def factory(ctx: PluginContext) -> object:
        ctx.scope.on_close(lambda: released.append("registered"))
        return object()

    runtime = PluginRuntime(Tools, context, instance_factory=factory)

    with pytest.raises(QgisSdkPluginLifecycleError) as caught:
        runtime.start()

    assert "Tools" in str(caught.value)
    assert caught.value.code == "invalid_plugin_lifecycle"
    assert released == ["registered"]
    assert context.scope.closed
    assert runtime.state is PluginRuntimeState.FAILED


def test_startup_cleanup_failure_is_attached_to_the_original_error() -> None:
    context = plugin_context()

    @plugin(id="example.cleanup", title="Cleanup")
    class Cleanup:
        def __init__(self, ctx: PluginContext) -> None:
            ctx.scope.on_close(lambda: (_ for _ in ()).throw(RuntimeError("cleanup")))
            raise ValueError("startup")

        @action(id="run", title="Run")
        def run(self) -> None:
            pass

    with pytest.raises(ValueError, match="startup") as caught:
        PluginRuntime(Cleanup, context).start()

    assert isinstance(caught.value.__cause__, ExceptionGroup)
    assert [str(error) for error in caught.value.__cause__.exceptions] == ["cleanup"]
    assert context.scope.closed


def test_unload_reports_cleanup_failures_but_stays_stopped() -> None:
    context = plugin_context()
    attempted: list[str] = []
    context.scope.on_close(lambda: attempted.append("first"))
    context.scope.on_close(lambda: (_ for _ in ()).throw(RuntimeError("cleanup")))
    runtime = PluginRuntime(Tools, context)
    runtime.start()

    with pytest.raises(ExceptionGroup) as caught:
        runtime.unload()

    assert [str(error) for error in caught.value.exceptions] == ["cleanup"]
    assert attempted == ["first"]
    assert runtime.state is PluginRuntimeState.STOPPED
    assert runtime.instance is None

    runtime.unload()
    assert attempted == ["first"]


def test_start_after_unload_is_rejected_without_constructing() -> None:
    constructed: list[int] = []

    @plugin(id="example.stopped", title="Stopped")
    class Stopped:
        def __init__(self, ctx: PluginContext) -> None:
            constructed.append(1)

        @action(id="noop", title="Noop")
        def noop(self) -> None:
            pass

    runtime = PluginRuntime(Stopped, plugin_context())
    runtime.unload()

    with pytest.raises(QgisSdkPluginLifecycleError):
        runtime.start()

    assert constructed == []


def test_start_rejects_a_context_disposed_after_construction() -> None:
    context = plugin_context()
    runtime = PluginRuntime(Tools, context)
    context.scope.close()

    with pytest.raises(QgisSdkScopeClosedError):
        runtime.start()

    assert runtime.state is PluginRuntimeState.NEW


def test_non_callable_action_binding_fails_and_cleans_up() -> None:
    context = plugin_context()
    released: list[str] = []

    def factory(ctx: PluginContext) -> object:
        ctx.scope.on_close(lambda: released.append("registered"))
        instance = object.__new__(Tools)
        instance.run = None  # type: ignore[attr-defined]
        return instance

    runtime = PluginRuntime(Tools, context, instance_factory=factory)

    with pytest.raises(QgisSdkPluginLifecycleError) as caught:
        runtime.start()

    assert "handler 'run'" in str(caught.value)
    assert released == ["registered"]
    assert runtime.state is PluginRuntimeState.FAILED


def test_declared_streams_are_bound_beside_the_actions_and_cleared_on_unload() -> None:
    @plugin(id="example.watch", title="Watch")
    class Watch:
        def __init__(self, ctx: PluginContext) -> None:
            self.ctx = ctx

        @action(id="run", title="Run")
        def run(self) -> None:
            return None

        @stream(id="ticks", title="Ticks", events={"data": int})
        def ticks(self, count: int) -> Iterator[dict]:
            for index in range(count):
                yield {"kind": "data", "payload": index}

    runtime = PluginRuntime(Watch, plugin_context())
    assert dict(runtime.streams) == {}

    runtime.start()

    assert list(runtime.actions) == ["run"]
    assert list(runtime.streams) == ["ticks"]
    assert "ticks" not in runtime.actions
    assert [item["payload"] for item in runtime.streams["ticks"](2)] == [0, 1]
    with pytest.raises(TypeError):
        runtime.streams["other"] = lambda: None  # type: ignore[index]

    runtime.unload()

    assert dict(runtime.streams) == {}


def test_non_callable_stream_binding_names_the_stream() -> None:
    @plugin(id="example.watch", title="Watch")
    class Watch:
        def __init__(self, ctx: PluginContext) -> None:
            self.ticks = "shadowed"

        @stream(id="ticks", title="Ticks", events={"data": int})
        def ticks(self) -> None:
            return None

    runtime = PluginRuntime(Watch, plugin_context())
    with pytest.raises(QgisSdkPluginLifecycleError, match="stream 'ticks'"):
        runtime.start()
    assert runtime.state is PluginRuntimeState.FAILED

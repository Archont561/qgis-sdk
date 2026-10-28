"""The unified description API for authored declarations."""

from __future__ import annotations

from collections.abc import Iterator

from qgis_sdk import action, plugin
from qgis_sdk.core import AlgorithmContext, JobContext
from qgis_sdk.models import VectorLayerInfo
from qgis_sdk.providers import Provider


def test_describe_and_method_describe_plugin_and_algorithm_without_running() -> None:
    from qgis_sdk import describe

    provider = Provider(id="tools", title="Tools")

    @provider.algorithm(id="buffer")
    def buffer(ctx: AlgorithmContext, distance: float) -> VectorLayerInfo:
        raise AssertionError("description must not run the handler")

    @plugin(id="sample", title="Sample")
    class Plugin:
        @action
        def ping(self, value: int) -> int:
            return value

    assert describe(buffer).qualified_id == "tools:buffer"
    assert buffer.describe() == describe(buffer)
    assert describe(Plugin).id == "sample"
    assert Plugin.describe() == describe(Plugin)
    assert Plugin().describe() == describe(Plugin)


def test_action_description_combines_handler_and_stacked_bindings() -> None:
    from qgis_sdk import describe, menu, shortcut, toolbar
    from qgis_sdk.bindings import MenuBinding, ShortcutBinding, ToolbarBinding

    @plugin(id="sample", title="Sample")
    class Plugin:
        @toolbar(text="Run")
        @shortcut("Ctrl+R")
        @menu("Plugins/Tools")
        @action(id="run", title="Run")
        def run_task(self, count: int) -> int:
            return count

    expected = (
        MenuBinding("Plugins/Tools"),
        ShortcutBinding("Ctrl+R"),
        ToolbarBinding(text="Run"),
    )
    info = describe(Plugin.run_task)
    assert info.id == "run"
    assert info.handler == "run_task"
    assert info.request["required"] == ["count"]
    assert info.bindings == expected
    assert Plugin.run_task.describe() == info
    assert describe(Plugin).actions[0].bindings == expected
    assert "bindings" not in describe(Plugin).to_dict()["actions"][0]


def test_job_stream_and_surface_share_describe_entry_points() -> None:
    from qgis_sdk import describe, menu, stream
    from qgis_sdk.bindings import MenuBinding
    from qgis_sdk.jobs import job
    from qgis_sdk.ui import Dialog

    @job(id="sum", title="Sum")
    def sum_job(ctx: JobContext, value: int) -> int:
        return value

    class Plugin:
        @stream(id="events", events={"data": int})
        def events(self) -> Iterator[int]:
            yield 1

    @menu("Plugins/Tools")
    class Window(Dialog):
        title = "Window"

    assert sum_job.describe() == describe(sum_job)
    assert Plugin.events.describe() == describe(Plugin.events)
    assert describe(Plugin.events).events["data"]["type"] == "integer"
    assert Window.describe() == describe(Window)
    assert describe(Window).bindings == (MenuBinding("Plugins/Tools"),)


def test_describe_accepts_a_provider_and_unbound_surface() -> None:
    from qgis_sdk import describe
    from qgis_sdk.ui import Dialog

    provider = Provider(id="tools", title="Tools")

    class Window(Dialog):
        title = "Window"

    assert describe(provider) == provider.describe()
    assert Window.describe() == describe(Window)
    assert describe(Window).bindings == ()


def test_ui_event_decorators_expose_their_wiring() -> None:
    from qgis_sdk import describe
    from qgis_sdk.ui import Button, Dialog, on, subscribe

    class Window(Dialog):
        go = Button(text="Go")

        @on(go).clicked
        @subscribe("updates", every=2)
        def event(self) -> None:
            pass

    info = describe(Window.event)
    assert Window.event.describe() == info
    assert info.handler == "event"
    assert [wire.kind for wire in info.wires] == ["subscribe", "on"]
    assert info.wires[0].target == "updates"
    assert info.wires[0].request == {"every": 2}
    assert info.wires[1].target is Window.go
    assert info.wires[1].signal == "clicked"


def test_plugin_description_includes_registered_surfaces_and_bindings() -> None:
    from qgis_sdk import describe, toolbar
    from qgis_sdk.bindings import ToolbarBinding
    from qgis_sdk.ui import Dialog

    @toolbar(text="Open")
    class Window(Dialog):
        pass

    @plugin(id="sample", title="Sample")
    class Plugin:
        surfaces = (Window,)

        @toolbar(text="Run")
        @action
        def run(self) -> None:
            pass

    info = describe(Plugin)
    assert info.bindings.plugin_id == "sample"
    assert info.bindings.surfaces[0].bindings == (ToolbarBinding(text="Open"),)
    assert info.bindings.actions[0].bindings == (ToolbarBinding(text="Run"),)
    assert "bindings" not in info.to_dict()
    assert Plugin.describe().bindings == info.bindings


def test_describe_accepts_a_bound_action_method() -> None:
    from qgis_sdk import describe

    @plugin(id="sample", title="Sample")
    class Plugin:
        @action
        def add(self, n: int) -> int:
            return n

    assert describe(Plugin().add).id == "add"
    assert Plugin().add.describe() == describe(Plugin.add)


def test_existing_describe_attribute_is_not_overwritten() -> None:
    import pytest
    from qgis_sdk import QgisSdkDeclarationError
    from qgis_sdk.jobs import job

    def existing(ctx: JobContext) -> int:
        return 1

    existing.describe = "author value"  # type: ignore[attr-defined]
    with pytest.raises(QgisSdkDeclarationError, match="already defines 'describe'"):
        job(existing)
    assert existing.describe == "author value"  # type: ignore[attr-defined]
    assert existing(JobContext) == 1  # type: ignore[arg-type]

    with pytest.raises(QgisSdkDeclarationError, match="already defines 'describe'"):

        @plugin(id="collision")
        class Collision:
            def describe(self) -> str:
                return "mine"


def test_inherited_describer_uses_the_actual_declared_plugin() -> None:
    @plugin(id="base")
    class Base:
        pass

    @plugin(id="child")
    class Child(Base):
        pass

    assert Base.describe().id == "base"
    assert Child.describe().id == "child"
    assert Child().describe().id == "child"


def test_action_with_ui_handler_wiring_exposes_both_decorations() -> None:
    from qgis_sdk import describe, toolbar
    from qgis_sdk.ui import on

    @plugin(id="sample")
    class Plugin:
        @on("go").clicked
        @toolbar(text="Go")
        @action
        def run(self) -> None:
            pass

    info = describe(Plugin.run)
    assert len(info.bindings) == 1
    assert len(info.wires) == 1
    assert info.wires[0].target == "go"
    assert info.wires[0].signal == "clicked"


def test_description_does_not_construct_plugin_or_run_actions() -> None:
    from qgis_sdk import describe

    @plugin(id="no_side_effects")
    class Plugin:
        def __init__(self) -> None:
            raise AssertionError("must not construct plugin")

        @action
        def execute(self) -> None:
            raise AssertionError("must not execute action")

    assert describe(Plugin).id == "no_side_effects"
    assert Plugin.execute.describe().id == "execute"


def test_reverse_stacking_keeps_metadata_and_plain_method() -> None:
    import inspect

    from qgis_sdk import describe, toolbar
    from qgis_sdk.bindings import ToolbarBinding

    @plugin(id="reverse")
    class Plugin:
        @action
        @toolbar(text="Reverse")
        def run(self, value: int) -> int:
            return value

    assert describe(Plugin.run).bindings == (ToolbarBinding(text="Reverse"),)
    assert str(inspect.signature(Plugin.run)) == "(self, value: 'int') -> 'int'"
    assert Plugin().run(value=3) == 3

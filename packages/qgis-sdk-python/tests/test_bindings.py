"""``@toolbar``/``@menu``/``@shortcut`` and ``describe_bindings`` without Qt (TASK-67 AC 1)."""

from __future__ import annotations

import pytest
from qgis_sdk import QgisSdkDeclarationError, menu, shortcut, toolbar
from qgis_sdk.bindings import MenuBinding, ShortcutBinding, ToolbarBinding, bindings_of
from qgis_sdk.bindings import _describe_lowered_bindings as describe_bindings
from qgis_sdk.core import PluginContext
from qgis_sdk.declarations._describe import describe_plugin
from qgis_sdk.declarations._plugin import action, plugin, stream
from qgis_sdk.jobs import job
from qgis_sdk.ui import Dialog, Dock


@menu("Plugins/Field tools")
@toolbar(icon="buffer.svg")
class BufferDialog(Dialog):
    title = "Buffer a layer"

    def build(self) -> object:
        return object()


class LayerPanel(Dock, area="left"):
    def build(self) -> object:
        return object()


@plugin(id="field_tools", title="Field tools")
class FieldTools:
    ctx: PluginContext
    surfaces = (BufferDialog, LayerPanel)

    @toolbar(text="Count")
    @shortcut("Ctrl+Alt+C")
    @action
    def count_layers(self) -> int:
        return 0

    @action(id="buffer", title="Buffer")
    @menu("Vector/Field tools")
    @menu("Plugins/Field tools")
    def buffer_selection(self, distance: float) -> None:
        return None

    @action
    def unbound(self) -> None:
        return None


def test_bindings_stack_in_any_order_and_keep_source_order_innermost_first() -> None:
    assert bindings_of(FieldTools.count_layers) == (
        ShortcutBinding("Ctrl+Alt+C"),
        ToolbarBinding(text="Count"),
    )
    assert bindings_of(FieldTools.buffer_selection) == (
        MenuBinding("Plugins/Field tools"),
        MenuBinding("Vector/Field tools"),
    )
    assert bindings_of(BufferDialog) == (
        ToolbarBinding(icon="buffer.svg"),
        MenuBinding("Plugins/Field tools"),
    )
    assert bindings_of(LayerPanel) == ()


def test_describe_bindings_reports_bound_actions_and_every_listed_surface() -> None:
    described = describe_bindings(FieldTools)

    assert described.plugin_id == "field_tools"
    assert [bound.id for bound in described.actions] == ["count_layers", "buffer"]
    assert [bound.id for bound in described.surfaces] == [
        "buffer_dialog",
        "layer_panel",
    ]
    assert described.surfaces[0].surface.title == "Buffer a layer"
    assert described.surfaces[0].surface.kind == "dialog"
    assert described.surfaces[1].surface.kind == "dock"
    assert described.surfaces[1].surface.area == "left"
    assert described.surfaces[1].bindings == ()
    assert described.surface(LayerPanel) is described.surfaces[1]


def test_entries_follow_declaration_order_across_actions_and_surfaces() -> None:
    described = describe_bindings(FieldTools)

    assert [entry.id for entry in described.entries] == [
        "buffer_dialog",
        "count_layers",
        "buffer",
    ]


def test_a_typed_bound_action_without_a_surface_is_the_ui003_finding() -> None:
    described = describe_bindings(FieldTools)

    assert [bound.id for bound in described.typed_without_surface] == ["buffer"]
    assert described.actions[0].takes_inputs is False


def test_bindings_never_reach_describe_plugin() -> None:
    @plugin(id="plain", title="Plain")
    class Plain:
        @action
        def count_layers(self) -> int:
            return 0

        @action(id="buffer", title="Buffer")
        def buffer_selection(self, distance: float) -> None:
            return None

        @action
        def unbound(self) -> None:
            return None

    assert describe_plugin(FieldTools).to_dict() == {
        **describe_plugin(Plain).to_dict(),
        "id": "field_tools",
        "title": "Field tools",
    }


def test_a_job_is_refused_with_the_way_forward() -> None:
    with pytest.raises(QgisSdkDeclarationError, match="bind an @action that submits"):

        @toolbar
        @job
        def long_running(ctx: object) -> None:
            return None

    with pytest.raises(QgisSdkDeclarationError, match="bind an @action instead"):

        @job
        @menu("Plugins/X")
        def other(ctx: object) -> None:
            return None


def test_a_stream_is_refused_either_way() -> None:
    with pytest.raises(QgisSdkDeclarationError, match="cannot bind a @stream"):

        class _Above:
            @shortcut("F5")
            @stream(events={"data": int})
            def ticks(self) -> None:
                return None

    with pytest.raises(QgisSdkDeclarationError, match="bind an @action instead"):

        class _Below:
            @stream(events={"data": int})
            @shortcut("F5")
            def ticks(self) -> None:
                return None


def test_a_plain_method_is_refused_when_the_plugin_class_is_created() -> None:
    with pytest.raises(QgisSdkDeclarationError, match="is not an @action"):

        @plugin(id="broken", title="Broken")
        class _Broken:
            @toolbar
            def helper(self) -> None:
                return None


def test_a_class_that_is_not_a_surface_is_refused() -> None:
    with pytest.raises(QgisSdkDeclarationError, match="Dialog/Dock subclass"):

        @menu("Plugins/X")
        class _NotASurface:
            pass

    with pytest.raises(QgisSdkDeclarationError, match="binds an application action"):
        toolbar(42)


def test_bad_arguments_are_refused_at_decoration_time() -> None:
    with pytest.raises(QgisSdkDeclarationError, match="icon"):
        toolbar(icon="")
    with pytest.raises(QgisSdkDeclarationError, match="path"):
        menu("//")
    with pytest.raises(QgisSdkDeclarationError, match="keys"):
        shortcut("  ")


def test_the_surfaces_list_is_validated() -> None:
    class Stray:
        pass

    @plugin(id="stray", title="Stray")
    class WithStray:
        surfaces = (Stray,)

    with pytest.raises(QgisSdkDeclarationError, match="Stray is not a Dialog/Dock"):
        describe_bindings(WithStray)

    @plugin(id="dupe", title="Dupe")
    class WithDuplicate:
        surfaces = (BufferDialog, BufferDialog)

    with pytest.raises(QgisSdkDeclarationError, match="share the id"):
        describe_bindings(WithDuplicate)

    @plugin(id="unregistered", title="Unregistered")
    class Without:
        surfaces: tuple[type, ...] = ()

    with pytest.raises(QgisSdkDeclarationError, match="not registered"):
        describe_bindings(Without).surface(BufferDialog)


def test_a_dock_refuses_an_unknown_area() -> None:
    with pytest.raises(QgisSdkDeclarationError, match="dock area"):

        class _Sideways(Dock, area="diagonal"):
            pass

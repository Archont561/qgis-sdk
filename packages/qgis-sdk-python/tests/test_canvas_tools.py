"""``@tool``: a declared capture, and the runner that starts one (TASK-85).

Pure tests: the fake canvas stands in for the map, so the whole declaration and
the whole capture path are exercised without QGIS, a Qt event loop or a click.
"""

from __future__ import annotations

from typing import Any

import pytest
from qgis_sdk.core import ResourceScope
from qgis_sdk.declarations import (
    QgisSdkDeclarationError,
    declared_tools,
    describe,
    tool,
)
from qgis_sdk.declarations._tools import start
from qgis_sdk.models import Geometry
from qgis_sdk.testing import FakeCanvas


class ToolPlugin:
    """One plugin class with a tool per shape, the way an author writes them."""

    def __init__(self, ctx: Any) -> None:
        self.ctx = ctx
        self.drawn: list[Geometry] = []

    @tool(captures="point", id="pick", title="Pick a point")
    def pick(self, geometry: Geometry) -> None:
        self.drawn.append(geometry)

    @tool(captures="line", id="trace", title="Trace a line")
    def trace(self, geometry: Geometry) -> None:
        self.drawn.append(geometry)

    @tool(id="sketch")
    def sketch(self, geometry: Geometry) -> None:
        self.drawn.append(geometry)


def _ctx(canvas: FakeCanvas) -> Any:
    """The slice of a context a tool needs: a canvas, and nothing else."""

    class Context:
        pass

    context = Context()
    context.canvas = canvas
    return context


def _geometry(shape: str = "point") -> Geometry:
    value = {
        "point": "POINT (21.1 52.1)",
        "line": "LINESTRING (21 52, 21.2 52.2)",
        "polygon": "POLYGON ((21 52, 21.2 52, 21.2 52.2, 21 52))",
    }[shape]
    vertices = {"point": 1, "line": 2, "polygon": 4}[shape]
    return Geometry(
        encoding="wkt",
        value=value,
        geometry_type=shape,
        crs="EPSG:4326",
        part_count=1,
        vertex_count=vertices,
    )


# -- the declaration ---------------------------------------------------------


def test_a_tool_defaults_its_id_and_title_and_captures_a_polygon() -> None:
    @tool()
    def outline(self, geometry: Geometry) -> None:
        return None

    described = describe(outline)

    assert described.id == "outline"
    assert described.title == "Outline"
    assert described.captures == "polygon"
    assert described.handler == "outline"


def test_a_tool_keeps_the_metadata_it_was_given() -> None:
    described = describe(ToolPlugin.pick)

    assert described.to_dict() == {
        "id": "pick",
        "title": "Pick a point",
        "captures": "point",
        "handler": "pick",
    }
    assert ToolPlugin.pick.describe().captures == "point"


def test_a_shape_nobody_can_draw_is_refused_where_it_is_written() -> None:
    with pytest.raises(QgisSdkDeclarationError) as failure:

        @tool(captures="hexagon")
        def draw(self, geometry: Geometry) -> None:
            return None

    assert "hexagon" in str(failure.value)
    assert "point, line, polygon" in str(failure.value)


def test_a_tool_takes_the_drawn_geometry_and_nothing_else() -> None:
    with pytest.raises(QgisSdkDeclarationError) as failure:

        @tool(id="two_inputs")
        def draw(self, geometry: Geometry, layer_id: str) -> None:
            return None

    assert "nothing else" in str(failure.value)


def test_the_drawn_parameter_is_a_geometry_or_unannotated() -> None:
    with pytest.raises(QgisSdkDeclarationError) as failure:

        @tool(id="wrong_type")
        def draw(self, geometry: str) -> None:
            return None

    assert "Geometry" in str(failure.value)

    @tool(id="unannotated")
    def unannotated(self, geometry) -> None:
        return None

    assert describe(unannotated).id == "unannotated"


def test_a_tool_is_an_instance_method_not_a_function() -> None:
    with pytest.raises(QgisSdkDeclarationError):

        @tool
        def draw(geometry: Geometry) -> None:
            return None


def test_a_tool_can_be_declared_once_and_no_more() -> None:
    @tool(id="once")
    def draw(self, geometry: Geometry) -> None:
        return None

    with pytest.raises(QgisSdkDeclarationError) as failure:
        tool(captures="line")(draw)

    assert "already declared" in str(failure.value)


def test_a_class_lists_its_tools_in_source_order() -> None:
    names = [name for name, _declared in declared_tools(ToolPlugin)]

    assert names == ["pick", "trace", "sketch"]


def test_a_binding_belongs_on_the_action_that_starts_a_tool() -> None:
    """A tool is not a button: an ``@action`` calls ``start`` from one."""
    from qgis_sdk import toolbar
    from qgis_sdk.declarations._describe import describe_plugin
    from qgis_sdk.declarations._plugin import action, plugin

    @plugin(id="field_tools", title="Field tools")
    class Bound:
        @action(id="start_draw", title="Draw a line")
        @toolbar(text="Draw")
        def start_draw(self) -> None:
            start(self.draw, self.ctx)

        @tool(captures="line")
        def draw(self, geometry: Geometry) -> None:
            return None

    described = describe_plugin(Bound)
    assert described.id == "field_tools"
    assert [entry.id for entry in described.actions] == ["start_draw"]


# -- the runner --------------------------------------------------------------


def test_starting_a_tool_captures_its_shape_and_answers_with_the_drawing() -> None:
    canvas = FakeCanvas(ResourceScope())
    plugin = ToolPlugin(_ctx(canvas))

    cancel = start(plugin.pick, plugin.ctx)

    assert canvas.open_captures() == ("point",)
    canvas.draw(_geometry("point"))
    assert [geometry.geometry_type for geometry in plugin.drawn] == ["point"]
    cancel()


def test_a_tool_runs_once_per_drawing() -> None:
    canvas = FakeCanvas(ResourceScope())
    plugin = ToolPlugin(_ctx(canvas))

    start(plugin.trace, plugin.ctx)
    canvas.draw(_geometry("line"))

    assert len(plugin.drawn) == 1
    # The drawing that finished the session closed it: nothing is left asking
    # the user for another line until the tool is started again.
    assert canvas.open_captures() == ()


def test_cancelling_before_the_drawing_never_runs_the_body() -> None:
    canvas = FakeCanvas(ResourceScope())
    plugin = ToolPlugin(_ctx(canvas))

    cancel = start(plugin.sketch, plugin.ctx)
    cancel()
    cancel()

    assert canvas.open_captures() == ()
    assert plugin.drawn == []


def test_a_second_tool_replaces_the_first_drawing() -> None:
    canvas = FakeCanvas(ResourceScope())
    plugin = ToolPlugin(_ctx(canvas))

    start(plugin.pick, plugin.ctx)
    start(plugin.trace, plugin.ctx)

    assert canvas.open_captures() == ("line",)
    canvas.draw(_geometry("line"))
    assert [geometry.geometry_type for geometry in plugin.drawn] == ["line"]


def test_a_plain_method_is_not_a_tool() -> None:
    plugin = ToolPlugin(_ctx(FakeCanvas(ResourceScope())))

    with pytest.raises(QgisSdkDeclarationError) as failure:
        start(ToolPlugin.__init__, plugin.ctx)

    assert "not declared with @tool" in str(failure.value)


def test_a_tool_needs_the_instance_and_a_context_with_a_canvas() -> None:
    with pytest.raises(QgisSdkDeclarationError) as failure:
        start(ToolPlugin.pick, _ctx(FakeCanvas(ResourceScope())))
    assert "plugin instance" in str(failure.value)

    plugin = ToolPlugin(_ctx(FakeCanvas(ResourceScope())))
    with pytest.raises(QgisSdkDeclarationError) as missing:
        start(plugin.pick, object())
    assert "no canvas" in str(missing.value)

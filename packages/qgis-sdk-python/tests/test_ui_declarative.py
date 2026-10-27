"""Surfaces declared as class attributes, with ``@on(component)`` (decision-55).

The imperative form stays: ``build()`` returns a tree of named components.
The declarative form drops the names and the method: components assigned
to class attributes take the attribute's name, the default ``build()``
returns the roots, and ``@on`` accepts the component itself. Each opening
gets its own copies, so two windows never share a widget or a listener.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from qgis_sdk.core import ResourceScope, UiContext
from qgis_sdk.models import QgisSdkUiError
from qgis_sdk.testing import build_surface, fake_ui_context
from qgis_sdk.ui import (
    Button,
    Column,
    Custom,
    Dialog,
    Dock,
    Form,
    Group,
    JobProgress,
    LogView,
    Number,
    ResultTable,
    Row,
    RunButton,
    Tabs,
    Text,
    on,
    snapshot_names,
    ui_snapshot,
    wires_of,
)
from qgis_sdk.ui.declarative import (
    apply_initial,
    declared_components,
    declared_inputs,
    materialise,
)


@pytest.fixture
def ctx() -> Iterator[UiContext]:
    scope = ResourceScope()
    yield fake_ui_context(scope.child())
    if not scope.closed:
        scope.close()


# -- names ----------------------------------------------------------------------------


def test_a_component_declared_on_a_class_takes_the_attribute_s_name() -> None:
    class Panel(Dock):
        distance = Number()
        note = Text(label="A note")
        go = Button(text="Go")
        explicit = Button("named", text="Named")

    assert Panel.distance.name == "distance"
    assert Panel.distance.label == "Distance"
    assert Panel.distance.object_name == "form/distance"
    assert Panel.note.label == "A note"
    assert Panel.go.object_name == "buttons/go"
    assert Panel.go.text == "Go"
    assert Panel.explicit.name == "named"  # an explicit name wins


def test_a_component_without_a_name_says_so_when_one_is_needed(ctx: UiContext) -> None:
    loose = Button(text="Loose")
    assert not loose.named
    with pytest.raises(QgisSdkUiError, match="has no name yet"):
        _ = loose.name
    with pytest.raises(QgisSdkUiError, match="has no name yet"):
        loose.attach(ctx)
    with pytest.raises(QgisSdkUiError, match="has no name yet"):
        loose.snapshot()
    with pytest.raises(QgisSdkUiError, match="needs a name"):
        Button("not a name!", text="x")


def test_children_declared_in_the_same_class_resolve_before_the_duplicate_check() -> (
    None
):
    class Twice(Dialog):
        a = Button(text="A")
        b = Button(text="B")
        row = Row([a, b])

    assert Twice.row.children() == (Twice.a, Twice.b)
    assert [child.name for child in Twice.row.children()] == ["a", "b"]

    with pytest.raises(QgisSdkUiError, match="two children named"):
        Row([Button("same"), Button("same")])

    class Clash(Dialog):
        same = Button(text="A")
        row = Row([same, Button("same")])

    with pytest.raises(QgisSdkUiError, match="two children named 'buttons/same'"):
        materialise(Clash())["row"].attach(fake_ui_context())


def test_tabs_resolve_their_pages_lazily_too() -> None:
    class Pages(Dialog):
        first = Column([])
        second = Column([])
        tabs = Tabs([first, second])

    assert Pages.tabs.pages == ("first", "second")
    assert Pages.tabs.current() == "first"
    assert Pages.tabs.snapshot()["current"] == "first"


# -- the keyword forms of the catalogue ------------------------------------------------


def test_every_catalogue_class_builds_without_a_positional_name() -> None:
    progress = JobProgress()
    table = ResultTable(columns=["id", ("name", "Name")])
    group = Group([table], label="Results", collapsible=True)
    run = RunButton(action_id="buffer", progress=progress, text="Run")
    custom = Custom(widget=lambda parent: parent)
    log = LogView(limit=10)
    assert table.columns == ("id", "name")
    assert group.collapsible and group.children() == (table,)
    assert run.action_id == "buffer" and run.text == "Run"
    assert custom.factory
    assert log.limit == 10
    with pytest.raises(QgisSdkUiError, match="needs an action id"):
        RunButton(text="Run")
    with pytest.raises(QgisSdkUiError, match="needs a widget or a factory"):
        Custom()
    with pytest.raises(QgisSdkUiError, match="name or children"):
        Row([table], [table])  # type: ignore[arg-type]
    # The positional forms are unchanged.
    assert RunButton("go", "buffer").object_name == "buttons/go"
    assert Group("box", [Text("t")]).name == "box"
    assert ResultTable("rows", ["id"]).columns == ("id",)


# -- materialisation -------------------------------------------------------------------


class Results(Dock, area="right"):
    """The example's dock, in the declarative form."""

    progress = JobProgress()
    fixture = RunButton(action_id="open_fixture", progress=progress, text="Fixture")
    clear = Button(text="Clear")
    tools = Row([fixture, clear])
    rows = ResultTable(columns=["id", "name"])
    log = LogView()
    log_group = Group([log], label="Log", collapsible=True)

    @on(clear).clicked
    def cleared(self) -> None:
        self.rows.set_rows([])
        self.clicks = getattr(self, "clicks", 0) + 1


def test_each_instance_gets_its_own_copies_and_the_prototypes_stay_untouched(
    ctx: UiContext,
) -> None:
    assert list(declared_components(Results)) == [
        "progress",
        "fixture",
        "clear",
        "tools",
        "rows",
        "log",
        "log_group",
    ]
    first = build_surface(Results, ctx)
    second = build_surface(Results, fake_ui_context())
    one, two = first.surface, second.surface

    assert one.clear is not two.clear and one.clear is not Results.clear
    assert one.tools.children() == (one.fixture, one.clear)  # the tree is re-pointed
    assert one.fixture.progress is one.progress  # shared references stay shared
    assert one.clear.attached and not Results.clear.attached

    one.clear.click()
    assert one.clicks == 1 and not hasattr(two, "clicks")


def test_the_default_build_returns_the_roots_as_a_column_named_after_the_class(
    ctx: UiContext,
) -> None:
    built = build_surface(Results, ctx)
    root = built.root
    assert isinstance(root, Column)
    assert root.name == "results"
    # Every declared component no other contains is a root, in declaration order.
    assert [c.name for c in root.children()] == [
        "progress",
        "tools",
        "rows",
        "log_group",
    ]
    assert snapshot_names(ui_snapshot(root)) == (
        "results",
        "feedback/progress",
        "tools",
        "buttons/fixture",
        "buttons/clear",
        "feedback/rows",
        "log_group",
        "feedback/log",
    )


def test_a_single_root_is_returned_as_is_and_nothing_declared_still_refuses(
    ctx: UiContext,
) -> None:
    class One(Dialog):
        note = Text()
        root = Column([note])

    built = build_surface(One, ctx)
    assert built.root is built.surface.root
    assert built.root.children() == (built.surface.note,)

    class Nothing(Dialog):
        pass

    with pytest.raises(NotImplementedError, match="must return the widget"):
        build_surface(Nothing, fake_ui_context())


def test_an_author_s_build_sees_the_copies(ctx: UiContext) -> None:
    class Mixed(Dialog):
        note = Text()

        def build(self) -> Column:
            return Column("root", [self.note, Button("go", text="Go")])

    built = build_surface(Mixed, ctx)
    assert built.find("note") is built.surface.note
    assert built.surface.note is not Mixed.note


def test_a_widget_instance_cannot_be_declared_on_the_class() -> None:
    class Widgetish:
        def setObjectName(self, name: str) -> None: ...

        def setParent(self, parent: object) -> None: ...

        def __deepcopy__(self, memo: dict) -> Widgetish:
            raise TypeError("cannot pickle a QWidget")

    class Holds(Dialog):
        custom = Custom(widget=Widgetish())

    with pytest.raises(QgisSdkUiError, match="Holds.custom.*build\\(\\)"):
        materialise(Holds())


# -- @on(component) --------------------------------------------------------------------


def test_on_accepts_the_component_and_wires_to_the_instance_s_copy(
    ctx: UiContext,
) -> None:
    built = build_surface(Results, ctx)
    dock = built.surface
    dock.rows.set_rows([{"id": 1, "name": "a"}])
    built.find("clear").click()
    assert dock.rows.rows() == ()
    assert dock.clicks == 1

    (name, wire), *_ = wires_of(Results)
    assert name == "cleared" and wire.target is Results.clear
    assert wire.signal == "clicked"

    built.close()
    dock.clear.click()
    assert dock.clicks == 1


def test_on_with_a_component_the_class_does_not_declare_is_refused(
    ctx: UiContext,
) -> None:
    elsewhere = Button("elsewhere", text="x")

    class Wrong(Dialog):
        note = Text()

        @on(elsewhere).clicked
        def clicked(self) -> None: ...

    with pytest.raises(QgisSdkUiError, match="not declared on Wrong"):
        build_surface(Wrong, ctx)

    class Fine(Dialog):
        note = Text()

        def build(self) -> Column:
            return Column("root", [self.note, elsewhere])

        @on(elsewhere).clicked
        def clicked(self) -> None:
            self.hit = True

    built = build_surface(Fine, fake_ui_context())
    elsewhere.click()
    assert built.surface.hit
    built.close()
    elsewhere.dispose()

    with pytest.raises(QgisSdkUiError, match="name of a node or a component"):
        on(object())  # type: ignore[arg-type]
    with pytest.raises(AttributeError, match="@on\\(clear\\) has no signal"):
        getattr(on(Results.clear), "hovered")  # noqa: B009


def test_the_methods_stay_plain_methods(ctx: UiContext) -> None:
    dock = Results()
    materialise(dock)
    dock.ctx = ctx
    dock.rows.set_rows([{"id": 1, "name": "a"}])
    dock.cleared()
    assert dock.rows.rows() == () and dock.clicks == 1


# -- Form over declared inputs (TASK-108 AC #3) ---------------------------------------


class Ping(Dialog):
    value = Number(integer=True, required=True)
    note = Text()
    form = Form([value, note], action_id="ping")
    go = Button(text="Ping")


def test_a_form_takes_inputs_declared_on_the_class_and_resolves_their_names() -> None:
    # Inside the class body the inputs had no names yet; after it they do.
    assert [field.name for field in Ping.form.fields] == ["value", "note"]
    assert Ping.form.field("note") is Ping.note
    assert Ping.form.children() == (Ping.value, Ping.note)


def test_the_declared_form_s_copies_hold_the_instance_s_inputs(ctx: UiContext) -> None:
    built = build_surface(Ping, ctx)
    surface = built.surface
    assert surface.form.fields == (surface.value, surface.note)
    assert surface.form is not Ping.form and surface.value is not Ping.value
    # The form is a root (it contains the inputs), the button the other one.
    assert [c.name for c in built.root.children()] == ["form", "go"]
    seen: list[tuple[str, object]] = []
    surface.form.changed(lambda name, value: seen.append((name, value)))
    surface.value.set_value(3)
    assert seen == [("value", 3)]
    assert surface.form.values() == {"value": 3, "note": ""}
    assert Ping.value.value() == 0  # the prototype heard nothing


def test_a_form_of_unnamed_inputs_outside_a_class_refuses_when_read() -> None:
    form = Form([Number(), Text()])
    with pytest.raises(QgisSdkUiError, match="has no name yet"):
        _ = form.fields


def test_a_form_still_refuses_two_declared_inputs_of_one_name() -> None:
    class Clash(Dialog):
        a = Number()
        form = Form([a, Number("a")])

    with pytest.raises(QgisSdkUiError, match="two fields named 'a'"):
        _ = Clash.form.fields


# -- initial values ---------------------------------------------------------------------


def test_the_default_build_seeds_declared_inputs_from_initial(ctx: UiContext) -> None:
    built = build_surface(Ping, ctx, initial={"value": 7})
    assert built.surface.value.value() == 7
    assert built.surface.form.values() == {"value": 7, "note": ""}
    assert Ping.value.value() == 0  # the prototype is untouched


def test_initial_reaches_inputs_nested_in_a_declared_container(ctx: UiContext) -> None:
    class Nested(Dialog):
        count = Number()
        box = Group([count], label="Box")

    built = build_surface(Nested, ctx, initial={"count": 2})
    assert built.surface.count.value() == 2
    assert declared_inputs(built.surface) == {"count": built.surface.count}


def test_an_initial_name_no_declared_input_carries_is_refused(ctx: UiContext) -> None:
    with pytest.raises(
        QgisSdkUiError, match="Ping has no input 'typo'; it has: note, value"
    ):
        build_surface(Ping, ctx, initial={"typo": 1})
    instance = Ping()
    materialise(instance)
    instance.initial = {}
    apply_initial(instance)  # nothing to seed is fine
    assert instance.value.value() == 0


def test_an_author_s_build_keeps_initial_to_itself(ctx: UiContext) -> None:
    class Mixed(Dialog):
        note = Text()

        def build(self) -> Column:
            # The imperative form reads ``self.initial`` as it pleases.
            self.note.set_value(self.initial.get("message"))
            return Column("root", [self.note])

    built = build_surface(Mixed, ctx, initial={"message": "hi", "free": 1})
    assert built.surface.note.value() == "hi"


# -- the attribute name in a snapshot ---------------------------------------------------


def test_a_snapshot_names_the_attribute_a_declared_component_came_from(
    ctx: UiContext,
) -> None:
    class Named(Dialog):
        explicit = Button("named", text="Named")
        plain = Button(text="Plain")

    built = build_surface(Named, ctx)
    nodes = {node["name"]: node for node in ui_snapshot(built.root)["children"]}
    assert nodes["named"]["attribute"] == "explicit"
    assert nodes["plain"]["attribute"] == "plain"
    # A component built by hand has no attribute to report.
    assert "attribute" not in Button("loose", text="x").snapshot()

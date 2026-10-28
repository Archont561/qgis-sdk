"""``@on``/``@subscribe``, ``ctx.on``, ``ui=`` and the behaviour mixins without Qt (TASK-96 AC 1).

A surface's methods are plain methods: a test calls them with a fake
context, and :func:`qgis_sdk.testing.build_surface` wires them to a
hand-built catalogue tree or to the fake tree read from a Designer file,
exactly as the host does, with every connection dropped when the scope
closes.
"""

from __future__ import annotations

import textwrap
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from qgis_sdk.core import (
    JobContext,
    PluginContext,
    PluginRuntime,
    ResourceScope,
    UiContext,
)
from qgis_sdk.declarations._plugin import action, plugin, stream
from qgis_sdk.jobs import JobHandle, JobService, JobStatus, job
from qgis_sdk.models import QgisSdkUiError
from qgis_sdk.testing import (
    FakeViewControl,
    FakeWorkers,
    RecordingNotifications,
    build_surface,
    fake_ui_context,
)
from qgis_sdk.ui import (
    AcceptCancel,
    Button,
    Column,
    Dialog,
    HasAcceptCancel,
    JobProgress,
    Number,
    RunsJobs,
    StreamEvent,
    SubscribesStreams,
    Tabs,
    Text,
    on,
    subscribe,
    wires_of,
)
from qgis_sdk.ui.uifile import FakeUiTree, read_ui, ui_names
from qgis_sdk.ui.wiring import Wire

# -- the plugin behind the surfaces -----------------------------------------------------


@dataclass(frozen=True)
class Tick:
    value: int


@job(id="slow_sum", title="Slow sum")
def slow_sum(ctx: JobContext, a: int, b: int) -> int:
    ctx.progress.report(0.5)
    return a + b


class Ticker:
    """A push source the plugin keeps, so an action can emit into it."""

    def __init__(self, owner: WiringPlugin) -> None:
        self._owner = owner
        self.sink: Any = None

    def start(self, sink: Any) -> None:
        self.sink = sink
        self._owner.tickers.append(self)

    def close(self) -> None:
        if self in self._owner.tickers:
            self._owner.tickers.remove(self)


@plugin(id="wiring", title="Wiring")
class WiringPlugin:
    ctx: PluginContext
    jobs: JobService
    tickers: list[Ticker]
    calls: list[tuple[str, object]]

    @action(id="buffer", title="Buffer")
    def buffer(self, distance: float) -> str:
        self.calls.append(("buffer", distance))
        return f"buffered {distance}"

    @action
    def poke(self, value: int) -> int:
        for ticker in self.tickers:
            ticker.sink.emit({"value": value})
        return value

    @action
    def sum_slowly(self, a: int, b: int) -> JobHandle:
        return self.jobs.delay(slow_sum, a=a, b=b)

    @stream(events={"data": Tick})
    def ticks(self) -> Ticker:
        return Ticker(self)

    @stream(events={"data": Tick})
    def countdown(self, start: int = 3) -> Iterator[dict[str, int]]:
        for value in range(start, 0, -1):
            yield {"value": value}


@pytest.fixture
def scope() -> Iterator[ResourceScope]:
    scope = ResourceScope()
    yield scope
    if not scope.closed:
        scope.close()


@pytest.fixture
def runtime(scope: ResourceScope) -> Iterator[PluginRuntime]:
    context = PluginContext(notifications=RecordingNotifications(scope), scope=scope)
    runtime = PluginRuntime._from_plugin_class(WiringPlugin, context)
    runtime.start()
    instance = runtime.instance
    assert isinstance(instance, WiringPlugin)
    instance.jobs = JobService(scope, workers=FakeWorkers(), gui_thread=lambda: False)
    instance.tickers = []
    instance.calls = []
    yield runtime
    runtime.unload()


@pytest.fixture
def ctx(scope: ResourceScope, runtime: PluginRuntime) -> UiContext:
    return fake_ui_context(scope.child(), runtime=runtime, view_id="wiring.dialog#1")


def plugin_of(runtime: PluginRuntime) -> WiringPlugin:
    instance = runtime.instance
    assert isinstance(instance, WiringPlugin)
    return instance


# -- @on over a hand-built tree ---------------------------------------------------------


class BufferDialog(Dialog):
    def build(self) -> Column:
        self.seen: list[object] = []
        return Column(
            "root",
            [
                Number("distance"),
                Text("note"),
                Button("go", "Go"),
                Tabs("pages", [Column("a", []), Column("b", [])]),
                AcceptCancel("buttons"),
            ],
        )

    @on("distance").changed
    def distance_changed(self, value: float) -> None:
        self.seen.append(("distance", value))

    @on("note").edited
    def note_edited(self, value: str) -> None:
        self.seen.append(("note", value))

    @on("go", "clicked")
    def go(self) -> None:
        self.seen.append(("go", self.ctx.actions.buffer(distance=2)))

    @on("pages").changed
    def page(self, name: str) -> None:
        self.seen.append(("page", name))

    @on("buttons").accepted
    def accepted(self) -> None:
        self.seen.append(("accepted", None))


def test_on_connects_after_build_and_disconnects_with_the_scope(ctx: UiContext) -> None:
    built = build_surface(BufferDialog, ctx)
    dialog = built.surface

    built.find("distance").set_value(3)
    built.find("note").set_value("hi")
    built.find("go").click()
    built.find("pages").set_current("b")
    built.find("buttons").accept()
    assert dialog.seen == [
        ("distance", 3.0),
        ("note", "hi"),
        ("go", "buffered 2.0"),
        ("page", "b"),
        ("accepted", None),
    ]

    built.close()
    built.find("distance").set_value(4)
    built.find("go").click()
    assert len(dialog.seen) == 5


def test_the_methods_are_plain_methods_a_test_calls_directly(ctx: UiContext) -> None:
    dialog = BufferDialog()
    dialog.ctx = ctx
    dialog.seen = []

    dialog.distance_changed(7.5)
    dialog.go()
    assert dialog.seen == [("distance", 7.5), ("go", "buffered 2.0")]
    assert [
        (name, wire.target, wire.signal) for name, wire in wires_of(BufferDialog)
    ] == [
        ("distance_changed", "distance", "changed"),
        ("note_edited", "note", "edited"),
        ("go", "go", "clicked"),
        ("page", "pages", "changed"),
        ("accepted", "buttons", "accepted"),
    ]


def test_a_name_no_node_carries_is_refused_before_anything_connects(
    ctx: UiContext,
) -> None:
    class Wrong(Dialog):
        def build(self) -> Column:
            return Column("root", [Number("distance")])

        @on("radius").changed
        def radius(self, value: float) -> None: ...

    with pytest.raises(QgisSdkUiError, match="no node named 'radius'"):
        build_surface(Wrong, ctx)

    class WrongSignal(Dialog):
        def build(self) -> Column:
            return Column("root", [Number("distance")])

        @on("distance").clicked
        def clicked(self) -> None: ...

    with pytest.raises(QgisSdkUiError, match="Number 'distance' has no such signal"):
        build_surface(WrongSignal, ctx)


def test_the_decorators_refuse_what_they_cannot_mark() -> None:
    with pytest.raises(AttributeError, match="no signal 'hovered'"):
        getattr(on("x"), "hovered")  # noqa: B009
    with pytest.raises(QgisSdkUiError, match="needs a signal"):

        @on("x")
        def bare(self) -> None: ...

    with pytest.raises(QgisSdkUiError, match="name of a node"):
        on("")
    with pytest.raises(QgisSdkUiError, match="id of a stream"):
        subscribe("")
    with pytest.raises(QgisSdkUiError, match="instance method"):
        on("x").changed(object())  # type: ignore[arg-type]
    assert Wire("on", "x", "changed").request == {}


# -- @subscribe, ctx.on and the echo flag -----------------------------------------------


class Watcher(Dialog):
    def build(self) -> Column:
        self.events: list[StreamEvent] = []
        return Column("root", [Button("poke", "Poke")])

    @subscribe("ticks")
    def tick(self, event: StreamEvent) -> None:
        self.events.append(event)

    @subscribe("countdown", start=2)
    def count(self, event: StreamEvent) -> None:
        self.events.append(event)

    @on("poke").clicked
    def poke(self) -> None:
        self.ctx.actions.poke(value=9)


def test_subscribe_opens_the_streams_after_build_and_flags_the_view_s_own_echo(
    ctx: UiContext, runtime: PluginRuntime
) -> None:
    built = build_surface(Watcher, ctx)
    watcher = built.surface
    assert [item.stream for item in ctx.streams.open] == ["ticks", "countdown"]

    # Another caller's event is not an echo; this view's own call is.
    plugin_of(runtime).tickers[0].sink.emit({"value": 1})
    built.find("poke").click()
    assert [(event.kind, event.payload, event.echo) for event in watcher.events] == [
        ("data", {"value": 1}, False),
        ("data", {"value": 9}, True),
    ]

    # The pulled stream advances on pump and ends with ``complete``.
    ctx.streams.pump()
    assert [(e.stream, e.kind, e.payload) for e in watcher.events[2:]] == [
        ("countdown", "data", {"value": 2}),
        ("countdown", "data", {"value": 1}),
        ("countdown", "complete", None),
    ]
    assert watcher.events[-1].terminal is True
    streams = ctx.streams
    assert [item.stream for item in streams.open] == ["ticks"]

    built.close()
    assert streams.open == ()
    assert plugin_of(runtime).tickers == []


def test_ctx_on_is_the_imperative_form_and_refuses_unknown_streams(
    ctx: UiContext, runtime: PluginRuntime
) -> None:
    heard: list[StreamEvent] = []
    subscription = ctx.on("ticks", heard.append)
    assert subscription.active is True
    plugin_of(runtime).tickers[0].sink.emit({"value": 4})
    assert heard[0].payload == {"value": 4}
    assert heard[0].echo is False

    subscription.dispose()
    subscription.dispose()
    assert plugin_of(runtime).tickers == []
    assert ctx.streams.open == ()

    with pytest.raises(QgisSdkUiError, match="declares no stream 'pulse'"):
        ctx.on("pulse", heard.append)
    with pytest.raises(QgisSdkUiError, match="countdown: .*start"):
        ctx.on("countdown", heard.append, start="many")
    with pytest.raises(QgisSdkUiError, match="no such field"):
        ctx.on("countdown", heard.append, speed=2)


def test_a_failing_or_malformed_stream_ends_with_an_error_event(
    ctx: UiContext,
) -> None:
    @plugin(id="broken", title="Broken")
    class Broken:
        @stream(events={"data": Tick})
        def numbers(self) -> Iterator[object]:
            yield 1

        @stream(events={"data": Tick})
        def explodes(self) -> Iterator[object]:
            raise RuntimeError("boom")
            yield  # pragma: no cover

    scope = ResourceScope()
    runtime = PluginRuntime._from_plugin_class(
        Broken, PluginContext(notifications=RecordingNotifications(scope), scope=scope)
    )
    runtime.start()
    other = fake_ui_context(scope.child(), runtime=runtime)
    heard: list[StreamEvent] = []
    other.on("numbers", heard.append)
    other.on("explodes", heard.append)
    other.streams.pump()
    assert [(event.stream, event.kind) for event in heard] == [
        ("numbers", "error"),
        ("explodes", "error"),
    ]
    assert "not a mapping" in heard[0].payload
    assert heard[1].payload == "The stream failed; the host recorded the details"
    runtime.unload()


def test_subscribe_without_streams_or_an_unknown_stream_is_refused(
    scope: ResourceScope,
) -> None:
    class Listens(Dialog):
        def build(self) -> Column:
            return Column("root", [])

        @subscribe("ticks")
        def tick(self, event: StreamEvent) -> None: ...

    with pytest.raises(QgisSdkUiError, match="needs ctx.streams"):
        build_surface(Listens, fake_ui_context(scope))


# -- a ui= tree under the fake ----------------------------------------------------------

UI_FILE = """\
<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>BufferForm</class>
 <widget class="QWidget" name="BufferForm">
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QDoubleSpinBox" name="distance"/>
   </item>
   <item>
    <layout class="QHBoxLayout" name="row">
     <item>
      <widget class="QLineEdit" name="note"/>
     </item>
     <item>
      <widget class="QPushButton" name="go">
       <property name="text"><string>Go</string></property>
      </widget>
     </item>
    </layout>
   </item>
   <item>
    <widget class="QgsMapLayerComboBox" name="layer"/>
   </item>
   <item>
    <widget class="QDialogButtonBox" name="buttons"/>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


@pytest.fixture
def ui_file(tmp_path: Path) -> Path:
    path = tmp_path / "buffer.ui"
    path.write_text(textwrap.dedent(UI_FILE), encoding="utf-8")
    return path


def test_a_designer_file_is_read_as_its_named_widgets(ui_file: Path) -> None:
    root = read_ui(ui_file)
    assert (root.cls, root.name) == ("QWidget", "BufferForm")
    assert [child.name for child in root.children] == [
        "distance",
        "note",
        "go",
        "layer",
        "buttons",
    ]
    assert ui_names(ui_file) == (
        "BufferForm",
        "distance",
        "note",
        "go",
        "layer",
        "buttons",
    )
    broken = ui_file.with_name("broken.ui")
    broken.write_text("<ui>", encoding="utf-8")
    with pytest.raises(QgisSdkUiError, match="cannot read"):
        read_ui(broken)
    empty = ui_file.with_name("empty.ui")
    empty.write_text("<ui version='4.0'/>", encoding="utf-8")
    with pytest.raises(QgisSdkUiError, match="no root widget"):
        read_ui(empty)


def test_on_wires_to_the_fake_tree_of_a_designer_file(
    ui_file: Path, ctx: UiContext
) -> None:
    class FromFile(Dialog):
        ui = str(ui_file)

        def __init__(self) -> None:
            self.seen: list[object] = []

        @on("distance").changed
        def distance(self, value: float) -> None:
            self.seen.append(("distance", value))

        @on("go").clicked
        def go(self) -> None:
            self.seen.append(("go", self.ctx.actions.buffer(distance=1)))

        @on("layer", "layerChanged")
        def layer(self, layer: object) -> None:
            self.seen.append(("layer", layer))

        @on("buttons").cancelled
        def cancelled(self) -> None:
            self.seen.append(("cancel", None))

    built = build_surface(FromFile, ctx)
    tree = built.root
    assert isinstance(tree, FakeUiTree)
    assert tree.names == ("BufferForm", "distance", "note", "go", "layer", "buttons")
    distance = built.find("distance")
    assert distance.widget_class == "QDoubleSpinBox"
    assert distance.valueChanged.receivers == 1

    distance.valueChanged.emit(2.5)
    built.find("go").clicked.emit(False)
    built.find("layer").layerChanged.emit("sites")
    built.find("buttons").rejected.emit()
    assert built.surface.seen == [
        ("distance", 2.5),
        ("go", "buffered 1.0"),
        ("layer", "sites"),
        ("cancel", None),
    ]
    with pytest.raises(AttributeError, match="no signal 'exploded'"):
        getattr(distance, "exploded")  # noqa: B009
    with pytest.raises(QgisSdkUiError, match="declares no widget 'other'"):
        built.find("other")

    built.close()
    assert distance.valueChanged.receivers == 0
    distance.valueChanged.emit(9)
    assert len(built.surface.seen) == 4


def test_a_designer_name_or_signal_that_does_not_exist_is_refused(
    ui_file: Path, ctx: UiContext
) -> None:
    class Missing(Dialog):
        ui = str(ui_file)

        @on("radius").changed
        def radius(self, value: float) -> None: ...

    with pytest.raises(QgisSdkUiError, match="no node named 'radius'"):
        build_surface(Missing, ctx)

    class WrongSignal(Dialog):
        ui = str(ui_file)

        @on("note", "valueChanged")
        def note(self, value: object) -> None: ...

    with pytest.raises(QgisSdkUiError, match="has no such signal"):
        build_surface(WrongSignal, ctx)

    class NoFile(Dialog):
        ui = "nowhere.ui"

    with pytest.raises(QgisSdkUiError, match="does not exist"):
        NoFile().build()

    class Nothing(Dialog):
        pass

    with pytest.raises(NotImplementedError, match="Designer file"):
        Nothing().build()


# -- the behaviour mixins ---------------------------------------------------------------


class SumDialog(RunsJobs, HasAcceptCancel, SubscribesStreams, Dialog):
    accept_result: Any = None

    def build(self) -> Column:
        self.progress = JobProgress("job")
        self.closed_by: list[str] = []
        return Column("root", [self.progress, AcceptCancel()])

    def on_accept(self) -> Any:
        self.closed_by.append("accept")
        return self.accept_result

    def on_cancel(self) -> None:
        self.closed_by.append("cancel")


def test_runs_jobs_follows_the_handle_and_cancels_it_when_the_window_closes(
    ctx: UiContext, runtime: PluginRuntime
) -> None:
    built = build_surface(SumDialog, ctx)
    dialog = built.surface

    handle = dialog.run("sum_slowly", a=1, b=2)
    assert dialog.jobs == (handle,)
    assert dialog.progress.handle is handle
    assert dialog.run("buffer", distance=1) == "buffered 1.0"

    built.close()
    plugin_of(runtime).jobs.tick()
    assert handle.status is JobStatus.CANCELLED
    assert dialog.jobs == ()
    assert dialog.cancel_jobs() == 0


def test_has_accept_cancel_runs_the_hooks_and_closes_the_window(
    ctx: UiContext,
) -> None:
    built = build_surface(SumDialog, ctx)
    dialog = built.surface
    view = ctx.view
    assert isinstance(view, FakeViewControl)

    built.find("dialog_buttons").accept()
    assert dialog.closed_by == ["accept"]
    assert view.close_requests == 1

    dialog.accept_result = False
    assert dialog.accept() is False
    assert view.close_requests == 1

    built.find("dialog_buttons").cancel()
    assert dialog.closed_by == ["accept", "accept", "cancel"]
    assert view.close_requests == 2


def test_has_accept_cancel_needs_its_button_row(ctx: UiContext) -> None:
    class NoRow(HasAcceptCancel, Dialog):
        def build(self) -> Column:
            return Column("root", [Number("distance")])

    with pytest.raises(QgisSdkUiError, match="no node named 'dialog_buttons'"):
        build_surface(NoRow, ctx)

    class WrongRow(HasAcceptCancel, Dialog):
        buttons = "distance"

        def build(self) -> Column:
            return Column("root", [Number("distance")])

    with pytest.raises(QgisSdkUiError, match="not an AcceptCancel row"):
        build_surface(WrongRow, ctx)


def test_has_accept_cancel_wires_a_designer_button_box(
    ui_file: Path, ctx: UiContext
) -> None:
    class FromFile(HasAcceptCancel, Dialog):
        ui = str(ui_file)
        buttons = "buttons"

        def on_accept(self) -> None:
            self.accepted = True

    built = build_surface(FromFile, ctx)
    box = built.find("buttons")
    box.accepted.emit()
    assert built.surface.accepted is True
    view = ctx.view
    assert isinstance(view, FakeViewControl)
    assert view.close_requests == 1
    box.rejected.emit()
    assert view.close_requests == 2
    built.close()
    assert box.accepted.receivers == 0


def test_subscribes_streams_keeps_the_view_s_subscriptions(
    ctx: UiContext, runtime: PluginRuntime
) -> None:
    built = build_surface(SumDialog, ctx)
    dialog = built.surface
    heard: list[StreamEvent] = []

    first = dialog.subscribe("ticks", heard.append)
    second = dialog.subscribe("countdown", heard.append, start=1)
    assert dialog.subscriptions == (first, second)
    plugin_of(runtime).tickers[0].sink.emit({"value": 2})
    assert heard[0].payload == {"value": 2}

    assert dialog.unsubscribe_all() == 2
    assert dialog.subscriptions == ()
    assert ctx.streams.open == ()
    assert dialog.unsubscribe_all() == 0

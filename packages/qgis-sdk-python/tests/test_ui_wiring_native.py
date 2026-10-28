"""``@on``/``@subscribe``, ``ui=`` and the mixins under the host (TASK-96 AC 1).

Skips unless the QGIS bindings are importable. The host opens the surfaces
of a small plugin through :class:`SurfaceHost`: a catalogue tree, a
hand-built ``QWidget`` tree and a Designer file loaded by ``uic``; the
slots run on the GUI thread, a job started by ``RunsJobs`` is cancelled
when the dialog closes, and pushed and pulled stream events reach the
surface through the host's pump.
"""

from __future__ import annotations

import textwrap
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.qgis

try:
    from qgis.PyQt.QtWidgets import (
        QDialogButtonBox,
        QDoubleSpinBox,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )
except ImportError as error:  # pragma: no cover - depends on the host
    pytest.skip(f"native wiring needs QGIS: {error}", allow_module_level=True)

from qgis_sdk.adapters.qgis import native_plugin_context
from qgis_sdk.adapters.surfaces import SurfaceHost
from qgis_sdk.bindings import _describe_lowered_bindings as describe_bindings
from qgis_sdk.core import (
    JobContext,
    PluginContext,
    PluginRuntime,
    ResourceScope,
)
from qgis_sdk.declarations._plugin import action, plugin, stream
from qgis_sdk.jobs import JobHandle, JobService, JobStatus, job
from qgis_sdk.testing import FakeWorkers
from qgis_sdk.ui import (
    AcceptCancel,
    Button,
    Column,
    Dialog,
    HasAcceptCancel,
    JobProgress,
    Number,
    Row,
    RunButton,
    RunsJobs,
    StreamEvent,
    on,
    snapshot_names,
    subscribe,
    ui_snapshot,
)

UI_FILE = """\
<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>BufferForm</class>
 <widget class="QWidget" name="BufferForm">
  <layout class="QVBoxLayout" name="verticalLayout">
   <item><widget class="QDoubleSpinBox" name="distance"/></item>
   <item><widget class="QPushButton" name="go"/></item>
   <item><widget class="QDialogButtonBox" name="buttons"/></item>
  </layout>
 </widget>
</ui>
"""

EVENTS: list[tuple[str, object]] = []


@dataclass(frozen=True)
class Tick:
    value: int


@job(id="slow_sum", title="Slow sum")
def slow_sum(ctx: JobContext, a: int, b: int) -> int:
    return a + b


class Ticker:
    def __init__(self, owner: WiredPlugin) -> None:
        self._owner = owner
        self.sink: Any = None

    def start(self, sink: Any) -> None:
        self.sink = sink
        self._owner.tickers.append(self)

    def close(self) -> None:
        if self in self._owner.tickers:
            self._owner.tickers.remove(self)


class BufferDialog(RunsJobs, HasAcceptCancel, Dialog):
    title = "Buffer"

    def build(self) -> Column:
        self.progress = JobProgress("job")
        return Column(
            "root",
            [
                Number("distance"),
                RunButton("run", "buffer", values=lambda: {"distance": 2}),
                self.progress,
                AcceptCancel(),
            ],
        )

    @on("distance").changed
    def distance(self, value: float) -> None:
        EVENTS.append(("distance", value))

    @on("run").finished
    def ran(self, result: object) -> None:
        EVENTS.append(("ran", result))
        EVENTS.append(("thread", threading.current_thread() is threading.main_thread()))

    def on_accept(self) -> None:
        EVENTS.append(("accept", None))


class Declared(Dialog):
    """The declarative form: no ``build()``, components on the class."""

    title = "Declared"
    distance = Number()
    run = RunButton(action_id="buffer", values=lambda: {"distance": 3}, text="Run")
    reset = Button(text="Reset")
    tools = Row([run, reset])

    @on(distance).changed
    def distance_changed(self, value: float) -> None:
        EVENTS.append(("distance", value))

    @on(run).finished
    def ran(self, result: object) -> None:
        EVENTS.append(("ran", result))

    @on(reset).clicked
    def cleared(self) -> None:
        self.distance.set_value(0)
        EVENTS.append(("reset", self.distance.value()))


class HandBuilt(Dialog):
    def build(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        spin = QDoubleSpinBox(widget)
        spin.setObjectName("spin")
        button = QPushButton("Go", widget)
        button.setObjectName("go")
        layout.addWidget(spin)
        layout.addWidget(button)
        return widget

    @on("spin").changed
    def spun(self, value: float) -> None:
        EVENTS.append(("spin", value))

    @on("go", "clicked")
    def go(self) -> None:
        EVENTS.append(("go", self.ctx.actions.buffer(distance=3)))
        EVENTS.append(("thread", threading.current_thread() is threading.main_thread()))


class FromFile(HasAcceptCancel, Dialog):
    """``ui`` is set by the fixture to the file it writes; no ``build()``."""

    buttons = "buttons"

    @on("distance", "valueChanged")
    def distance(self, value: float) -> None:
        EVENTS.append(("file.distance", value))

    def on_accept(self) -> None:
        EVENTS.append(("file.accept", None))


class Watcher(Dialog):
    def build(self) -> Column:
        return Column("root", [])

    @subscribe("ticks")
    def tick(self, event: StreamEvent) -> None:
        EVENTS.append(("tick", (event.payload, event.echo)))

    @subscribe("countdown", start=2)
    def count(self, event: StreamEvent) -> None:
        EVENTS.append(("count", (event.kind, event.payload)))


@plugin(id="wired", title="Wired")
class WiredPlugin:
    ctx: PluginContext
    jobs: JobService
    tickers: list[Ticker]
    surfaces = (BufferDialog, Declared, HandBuilt, FromFile, Watcher)

    @action(id="buffer", title="Buffer")
    def buffer(self, distance: float) -> str:
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
def host(qgis_app: Any, tmp_path: Path) -> Iterator[tuple[SurfaceHost, WiredPlugin]]:
    path = tmp_path / "buffer.ui"
    path.write_text(textwrap.dedent(UI_FILE), encoding="utf-8")
    EVENTS.clear()
    FromFile.ui = str(path)  # type: ignore[misc]
    scope = ResourceScope()
    context = native_plugin_context(scope, settings_prefix="wired")
    host = SurfaceHost(
        iface=None,
        plugin_id="wired",
        title="Wired",
        bindings=describe_bindings(WiredPlugin),
    )
    runtime = PluginRuntime._from_plugin_class(
        WiredPlugin, context.with_services(ui=host)
    )
    host.attach(runtime, context)
    runtime.start()
    instance = runtime.instance
    assert isinstance(instance, WiredPlugin)
    instance.jobs = JobService(scope, workers=FakeWorkers(), gui_thread=lambda: True)
    instance.tickers = []
    yield host, instance
    host.close_all()
    runtime.unload()


def pump(qgis_app: Any, seconds: float = 0.2) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        qgis_app.processEvents()
        time.sleep(0.01)


def test_on_over_a_catalogue_tree_fires_from_the_widgets_on_the_gui_thread(
    host: tuple[SurfaceHost, WiredPlugin], qgis_app: Any
) -> None:
    surfaces, _plugin = host
    dialog = surfaces.open(BufferDialog)
    assert isinstance(dialog, BufferDialog)
    window = surfaces.dialogs[0].widget

    window.findChild(QDoubleSpinBox, "form/distance").setValue(4)
    window.findChild(QPushButton, "buttons/run").click()
    assert EVENTS == [
        ("distance", 4.0),
        ("ran", "buffered 2.0"),
        ("thread", True),
    ]

    spin = window.findChild(QDoubleSpinBox, "form/distance")
    window.findChild(QDialogButtonBox, "buttons/dialog_buttons").accepted.emit()
    assert EVENTS[-1] == ("accept", None)
    assert surfaces.dialogs == ()
    EVENTS.clear()
    spin.setValue(5)  # disconnected with the scope; the widget is not yet deleted
    assert EVENTS == []
    pump(qgis_app, 0.05)


def test_a_running_job_is_cancelled_when_the_dialog_closes(
    host: tuple[SurfaceHost, WiredPlugin], qgis_app: Any
) -> None:
    surfaces, plugin_instance = host
    dialog = surfaces.open(BufferDialog)
    assert isinstance(dialog, BufferDialog)

    handle = dialog.run("sum_slowly", a=1, b=2)
    assert dialog.progress.handle is handle
    assert dialog.jobs == (handle,)

    surfaces.dialogs[0].widget.close()
    pump(qgis_app, 0.05)
    plugin_instance.jobs.tick()
    assert handle.status is JobStatus.CANCELLED


def test_a_declared_surface_opens_twice_without_sharing_a_widget(
    host: tuple[SurfaceHost, WiredPlugin], qgis_app: Any
) -> None:
    surfaces, _plugin = host
    first = surfaces.open(Declared)
    second = surfaces.open(Declared)
    assert isinstance(first, Declared) and isinstance(second, Declared)
    assert first.distance is not second.distance
    assert first.distance is not Declared.distance and not Declared.distance.mounted
    one, two = (opened.widget for opened in surfaces.dialogs)

    # The native tree carries the declared names, as the fake rendering does.
    names = snapshot_names(ui_snapshot(one))
    for expected in (
        "declared",
        "form/distance",
        "tools",
        "buttons/run",
        "buttons/reset",
    ):
        assert expected in names, names

    one.findChild(QDoubleSpinBox, "form/distance").setValue(4)
    assert two.findChild(QDoubleSpinBox, "form/distance").value() == 0
    one.findChild(QPushButton, "buttons/run").click()
    one.findChild(QPushButton, "buttons/reset").click()
    assert EVENTS == [
        ("distance", 4.0),
        ("ran", "buffered 3.0"),
        ("distance", 0.0),
        ("reset", 0.0),
    ]
    assert one.findChild(QDoubleSpinBox, "form/distance").value() == 0

    one.close()
    EVENTS.clear()
    two.findChild(QPushButton, "buttons/reset").click()
    assert EVENTS == [("reset", 0.0)]
    pump(qgis_app, 0.05)


def test_on_over_a_hand_built_qt_tree(
    host: tuple[SurfaceHost, WiredPlugin], qgis_app: Any
) -> None:
    surfaces, _plugin = host
    surfaces.open(HandBuilt)
    window = surfaces.dialogs[0].widget

    window.findChild(QDoubleSpinBox, "spin").setValue(1.5)
    window.findChild(QPushButton, "go").click()
    assert EVENTS == [("spin", 1.5), ("go", "buffered 3.0"), ("thread", True)]

    spin = window.findChild(QDoubleSpinBox, "spin")
    window.close()
    EVENTS.clear()
    spin.setValue(2.5)
    assert EVENTS == []
    pump(qgis_app, 0.05)


def test_on_over_a_designer_file_loaded_by_uic(
    host: tuple[SurfaceHost, WiredPlugin], qgis_app: Any
) -> None:
    surfaces, _plugin = host
    surfaces.open(FromFile)
    window = surfaces.dialogs[0].widget
    spin = window.findChild(QDoubleSpinBox, "distance")
    assert spin is not None

    spin.setValue(7)
    assert EVENTS == [("file.distance", 7.0)]
    window.findChild(QDialogButtonBox, "buttons").accepted.emit()
    pump(qgis_app, 0.05)
    assert EVENTS[-1] == ("file.accept", None)
    assert surfaces.dialogs == ()


def test_subscribe_delivers_pushed_and_pulled_events_through_the_host_pump(
    host: tuple[SurfaceHost, WiredPlugin], qgis_app: Any
) -> None:
    surfaces, plugin_instance = host
    watcher = surfaces.open(Watcher)
    assert isinstance(watcher, Watcher)

    # The pulled stream is advanced by the host's timer.
    pump(qgis_app, 0.3)
    assert [item for item in EVENTS if item[0] == "count"] == [
        ("count", ("data", {"value": 2})),
        ("count", ("data", {"value": 1})),
        ("count", ("complete", None)),
    ]

    # A push from the GUI thread is immediate; the view's own call is an echo.
    plugin_instance.tickers[0].sink.emit({"value": 1})
    watcher.ctx.actions.poke(value=2)
    assert [item for item in EVENTS if item[0] == "tick"] == [
        ("tick", ({"value": 1}, False)),
        ("tick", ({"value": 2}, True)),
    ]

    # A push from another thread waits for the pump, then arrives on the GUI thread.
    sink = plugin_instance.tickers[0].sink
    worker = threading.Thread(target=lambda: sink.emit({"value": 3}))
    worker.start()
    worker.join()
    assert [item for item in EVENTS if item[0] == "tick"][-1][1] == ({"value": 2}, True)
    pump(qgis_app, 0.3)
    assert [item for item in EVENTS if item[0] == "tick"][-1] == (
        "tick",
        ({"value": 3}, False),
    )

    surfaces.dialogs[0].widget.close()
    pump(qgis_app, 0.05)
    assert plugin_instance.tickers == []

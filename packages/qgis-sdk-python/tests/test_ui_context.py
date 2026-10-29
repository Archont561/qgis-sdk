"""``ctx.ui.open`` under the fake and ``UiContext.actions`` without Qt (TASK-67 AC 3)."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from qgis_sdk.core import (
    JobContext,
    PluginContext,
    PluginRuntime,
    ResourceScope,
    UiContext,
)
from qgis_sdk.declarations._describe import describe_plugin
from qgis_sdk.declarations._plugin import action, plugin
from qgis_sdk.jobs import JobHandle, JobService, JobStatus, job
from qgis_sdk.models import QgisSdkUiError, QgisSdkUnsupportedCapabilityError
from qgis_sdk.testing import (
    FakeUi,
    FakeViewControl,
    FakeWorkers,
    RecordingNotifications,
)
from qgis_sdk.ui import Dialog
from qgis_sdk.ui.actions import ActionCall, ViewActions


@dataclass(frozen=True)
class Total:
    total: int


@job(id="slow_sum", title="Slow sum")
def slow_sum(ctx: JobContext, a: int, b: int) -> Total:
    return Total(total=a + b)


class BufferDialog(Dialog):
    def build(self) -> object:
        return object()


class Unlisted(Dialog):
    def build(self) -> object:
        return object()


@plugin(id="field_tools", title="Field tools")
class FieldTools:
    ctx: PluginContext
    surfaces = (BufferDialog,)
    jobs: JobService

    @action
    def open_buffer(self) -> None:
        self.ctx.ui.open(BufferDialog, initial={"distance": 5})

    @action
    def open_unlisted(self) -> None:
        self.ctx.ui.open(Unlisted)

    @action(id="buffer", title="Buffer")
    def buffer_selection(self, distance: float, note: str = "") -> str:
        return f"{distance}:{note}"

    @action
    def sum_slowly(self, a: int, b: int) -> JobHandle:
        return self.jobs.delay(slow_sum, a=a, b=b)


@pytest.fixture
def scope() -> Iterator[ResourceScope]:
    scope = ResourceScope()
    yield scope
    scope.close()


@pytest.fixture
def ui(scope: ResourceScope) -> FakeUi:
    from qgis_sdk import QgisSdkPlugin

    app = QgisSdkPlugin(id="field_tools", title="Field tools")
    app.add_surface(BufferDialog)
    return FakeUi(scope, app=app)


@pytest.fixture
def runtime(scope: ResourceScope, ui: FakeUi) -> Iterator[PluginRuntime]:
    context = PluginContext(
        notifications=RecordingNotifications(scope), scope=scope, ui=ui
    )
    runtime = PluginRuntime._from_plugin_class(FieldTools, context)
    runtime.start()
    instance = runtime.instance
    assert isinstance(instance, FieldTools)
    instance.jobs = JobService(scope, workers=FakeWorkers(), gui_thread=lambda: False)
    yield runtime
    runtime.unload()


@pytest.fixture
def actions(runtime: PluginRuntime) -> ViewActions:
    return ViewActions(runtime, view_id="buffer_dialog")


# -- ctx.ui.open ----------------------------------------------------------------------


def test_an_action_opening_a_surface_is_recorded_by_the_fake(
    runtime: PluginRuntime, ui: FakeUi
) -> None:
    runtime.actions["open_buffer"]()

    assert [record.id for record in ui.opened] == ["buffer_dialog"]
    assert ui.opened[0].surface is BufferDialog
    assert dict(ui.opened[0].initial) == {"distance": 5}


def test_the_fake_refuses_a_surface_the_plugin_does_not_list(
    runtime: PluginRuntime,
) -> None:
    with pytest.raises(QgisSdkUiError, match="Unlisted is not registered"):
        runtime.actions["open_unlisted"]()


def test_a_host_without_a_gui_refuses_ui_by_name(scope: ResourceScope) -> None:
    context = PluginContext(notifications=RecordingNotifications(scope), scope=scope)
    runtime = PluginRuntime._from_plugin_class(FieldTools, context)
    runtime.start()

    assert context.has("ui") is False
    with pytest.raises(QgisSdkUnsupportedCapabilityError, match="'ui'"):
        runtime.actions["open_buffer"]()
    runtime.unload()


def test_the_fake_ui_is_scope_guarded(scope: ResourceScope) -> None:
    ui = FakeUi(scope)
    scope.close()

    with pytest.raises(Exception, match="disposed"):
        ui.open(BufferDialog)


# -- UiContext.actions ----------------------------------------------------------------


def test_a_surface_calls_an_action_with_coerced_values(actions: ViewActions) -> None:
    assert actions.buffer(distance="2.5", note="x") == "2.5:x"
    assert actions["buffer"](distance=1) == "1.0:"
    assert isinstance(actions.buffer, ActionCall)
    assert actions.buffer.id == "buffer"
    assert "buffer" in actions
    assert actions.ids == ("buffer", "open_buffer", "open_unlisted", "sum_slowly")


def test_unknown_actions_and_fields_are_refused_by_name(actions: ViewActions) -> None:
    with pytest.raises(QgisSdkUiError, match="no action 'explode'"):
        actions.explode()
    with pytest.raises(QgisSdkUiError, match="no such field"):
        actions.buffer(distance=1, radius=2)
    with pytest.raises(QgisSdkUiError, match="distance is required"):
        actions.buffer()
    with pytest.raises(QgisSdkUiError, match="distance"):
        actions.buffer(distance="wide")


def test_a_job_submitting_action_returns_its_handle_and_is_busy_until_settled(
    actions: ViewActions, runtime: PluginRuntime
) -> None:
    handle = actions.sum_slowly(a=1, b=2)

    assert isinstance(handle, JobHandle)
    assert handle.status is JobStatus.QUEUED
    assert actions.sum_slowly.running is True
    with pytest.raises(QgisSdkUiError, match="still running from buffer_dialog"):
        actions.sum_slowly(a=3, b=4)

    instance = runtime.instance
    assert isinstance(instance, FieldTools)
    while not handle.status.settled:
        instance.jobs.tick()

    assert handle.result == Total(total=3)
    assert actions.sum_slowly.running is False
    assert actions.sum_slowly(a=3, b=4).status is JobStatus.QUEUED


def test_another_view_is_not_blocked_by_this_views_running_job(
    actions: ViewActions, runtime: PluginRuntime
) -> None:
    other = ViewActions(runtime, view_id="layer_panel")
    actions.sum_slowly(a=1, b=2)

    assert other.sum_slowly(a=5, b=6).status is JobStatus.QUEUED


def test_a_plain_action_is_free_again_right_after_it_returns(
    actions: ViewActions,
) -> None:
    actions.buffer(distance=1)

    assert actions.buffer.running is False
    assert actions.buffer(distance=2) == "2.0:"


def test_calls_after_unload_are_refused(runtime: PluginRuntime) -> None:
    actions = ViewActions(runtime, view_id="v")
    runtime.unload()

    with pytest.raises(QgisSdkUiError, match="not bound"):
        actions.buffer(distance=1)


# -- the contexts ---------------------------------------------------------------------


@pytest.mark.parametrize("name", ["algorithms", "styles", "desktop", "ui"])
def test_surface_capability_absence_and_closed_scope_are_explicit(
    scope: ResourceScope, name: str
) -> None:
    from qgis_sdk.models import QgisSdkScopeClosedError
    from qgis_sdk.testing import fake_ui_context

    context = fake_ui_context(scope)
    assert not context.has(name)
    with pytest.raises(QgisSdkUnsupportedCapabilityError) as error:
        getattr(context, name)
    assert error.value.capability == name

    view_scope = scope.child()
    provided = object()
    view = fake_ui_context(view_scope, **{name: provided})
    assert getattr(view, name) is provided
    view_scope.close()
    assert not scope.closed
    with pytest.raises(QgisSdkScopeClosedError):
        getattr(view, name)


def test_surface_can_open_another_registered_surface_without_an_action(
    scope: ResourceScope,
) -> None:
    from qgis_sdk import QgisSdkPlugin
    from qgis_sdk.testing import build_surface, fake_ui_context
    from qgis_sdk.ui import Button, on

    app = QgisSdkPlugin(id="surface_navigation")

    @app.surface
    class Detail(Dialog):
        pass

    @app.surface
    class Main(Dialog):
        open_detail = Button(text="Details")

        @on(open_detail).clicked
        def show_detail(self) -> None:
            self.ctx.ui.open(Detail, initial={"item": "one"})

    ui = FakeUi(scope, app=app)
    built = build_surface(Main, fake_ui_context(scope, ui=ui))
    built.surface.open_detail.click()

    assert ui.opened[0].surface is Detail
    assert dict(ui.opened[0].initial) == {"item": "one"}
    with pytest.raises(QgisSdkUiError, match="Unlisted is not registered"):
        built.surface.ctx.ui.open(Unlisted)
    assert len(ui.opened) == 1


def test_surface_can_reach_its_provided_desktop_without_an_action(
    scope: ResourceScope,
) -> None:
    from qgis_sdk.testing import fake_ui_context

    @dataclass
    class Desktop:
        iface: object

    iface = object()
    context = fake_ui_context(scope, desktop=Desktop(iface))
    assert context.desktop.iface is iface


def test_surface_can_apply_styles_directly_without_an_action(
    scope: ResourceScope,
) -> None:
    from pathlib import Path

    from qgis_sdk.testing import FakeLayers, FakeStyles, fake_ui_context

    layers = FakeLayers(scope)
    source = Path("fixtures/reference/points.geojson")
    layers.register(
        source, name="points", geometry_type="point", field_names=("id", "value")
    )
    layer = layers.open_vector(source)
    styles = FakeStyles(layers, scope)
    context = fake_ui_context(scope, styles=styles)

    context.styles.apply_style(layer.id, "reference/point-output")
    assert styles.applied(layer.id) == ("reference/point-output",)


def test_surface_can_use_algorithms_directly_without_an_action(
    scope: ResourceScope,
) -> None:
    from qgis_sdk.testing import FakeAlgorithms, FakeLayers, fake_ui_context

    algorithms = FakeAlgorithms(FakeLayers(scope), scope)
    context = fake_ui_context(scope, algorithms=algorithms)

    assert context.algorithms.describe("native:buffer").id == "native:buffer"


def test_ui_context_carries_actions_and_settings_as_capabilities(
    scope: ResourceScope, actions: ViewActions
) -> None:
    bare = UiContext(RecordingNotifications(scope), FakeViewControl(), scope)
    assert bare.has("actions") is False
    with pytest.raises(QgisSdkUnsupportedCapabilityError, match="'actions'"):
        _ = bare.actions

    full = UiContext(
        RecordingNotifications(scope), FakeViewControl(), scope, actions=actions
    )
    assert full.actions is actions
    assert full.capabilities == frozenset({"actions"})
    full.view.request_close()
    assert isinstance(full.view, FakeViewControl)
    assert full.view.close_requests == 1


def test_describe_plugin_is_unchanged_by_the_ui_capability() -> None:
    ids = [item.id for item in describe_plugin(FieldTools).actions]
    assert ids == ["buffer", "open_buffer", "open_unlisted", "sum_slowly"]


def test_a_job_handle_result_is_described_and_crosses_the_wire_as_id_and_status(
    actions: ViewActions,
) -> None:
    from qgis_sdk.bridge.dispatch import _wire_result
    from qgis_sdk.bridge.protocol import to_wire

    described = next(
        item for item in describe_plugin(FieldTools).actions if item.id == "sum_slowly"
    )
    assert described.result["properties"]["id"] == {"type": "string"}
    assert "queued" in described.result["properties"]["status"]["enum"]

    handle = actions.sum_slowly(a=1, b=2)
    assert to_wire(_wire_result(handle)) == {"id": handle.id, "status": "queued"}


def test_a_job_handle_is_never_an_input() -> None:
    with pytest.raises(Exception, match="unsupported annotation"):

        @plugin(id="bad", title="Bad")
        class _Bad:
            @action
            def resume(self, handle: JobHandle) -> None:
                return None

        describe_plugin(_Bad)

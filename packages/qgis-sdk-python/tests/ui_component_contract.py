"""The component contract both renderings must meet (TASK-68 AC 2).

Not a test module itself: ``test_ui_components.py`` runs these functions
against the fake rendering (attached, never mounted) and
``test_ui_components_native.py`` against the mounted widgets under a
``QgsApplication``. Each defines its own ``rendering`` fixture over
:func:`make_rendering`; the assertions are shared so fake/native parity is
a property of the run, as it is for the services (``tests/services``).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from qgis_sdk import action, plugin
from qgis_sdk.core import (
    JobContext,
    PluginContext,
    PluginRuntime,
    ResourceScope,
    UiContext,
)
from qgis_sdk.jobs import JobHandle, JobService, job
from qgis_sdk.models import FileRef, QgisSdkFormError, QgisSdkUiError
from qgis_sdk.testing import (
    FakeFiles,
    FakeLayers,
    FakeProject,
    FakeViewControl,
    FakeWorkers,
    RecordingLog,
    RecordingNotifications,
)
from qgis_sdk.ui import (
    Choice,
    Colour,
    Component,
    CrsPicker,
    DirectoryInput,
    Distance,
    FieldPicker,
    FileInput,
    LayerPicker,
    Number,
    Text,
    Toggle,
)
from qgis_sdk.ui.actions import ViewActions

GEOJSON = """{"type": "FeatureCollection", "features": [{"type": "Feature",
"properties": {"name": "a", "kind": "b"}, "geometry": {"type": "Point",
"coordinates": [21.0, 52.2]}}]}"""


@job(id="slow_sum", title="Slow sum")
def slow_sum(ctx: JobContext, a: int, b: int, fail: bool = False) -> int:
    ctx.progress.report(0.5)
    if fail:
        raise ValueError("no sum today")
    return a + b


@plugin(id="catalogue", title="Catalogue")
class CataloguePlugin:
    """The actions the button contract presses: one plain, one job."""

    ctx: PluginContext
    jobs: JobService
    calls: list[tuple[str, dict]]

    @action(id="buffer", title="Buffer")
    def buffer(self, distance: float, note: str = "") -> str:
        self.calls.append(("buffer", {"distance": distance, "note": note}))
        return f"{distance}:{note}"

    @action
    def sum_slowly(self, a: int, b: int, fail: bool = False) -> JobHandle:
        return self.jobs.delay(slow_sum, a=a, b=b, fail=fail)


class Rendering:
    """One backend of the contract: a context and a way to attach a component."""

    def __init__(
        self,
        ctx: UiContext,
        scope: ResourceScope,
        dataset: Path,
        *,
        native: bool,
        runtime: PluginRuntime | None = None,
    ) -> None:
        self.ctx = ctx
        self.scope = scope
        self.dataset = dataset
        self.native = native
        self.runtime = runtime

    @property
    def plugin(self) -> CataloguePlugin:
        """The running plugin instance behind ``ctx.actions``."""
        assert self.runtime is not None
        instance = self.runtime.instance
        assert isinstance(instance, CataloguePlugin)
        return instance

    def tick(self) -> None:
        """Advance the plugin's jobs one step, as the host timer would."""
        self.plugin.jobs.tick()

    def attach(self, component: Component) -> Component:
        component.attach(self.ctx)
        if self.native:
            component.mount()
        return component

    def add_layer(self) -> str:
        info = self.ctx.layers.open_vector(self.dataset)
        self.ctx.project.add_layer(info.id)
        return info.id


def make_rendering(
    request: pytest.FixtureRequest, tmp_path: Path, backend: str
) -> Iterator[Rendering]:
    """Yield the ``fake`` or ``native`` rendering; the native one needs ``qgis_app``."""
    scope = ResourceScope()
    notifications = RecordingNotifications(scope)
    dataset = tmp_path / "sites.geojson"
    dataset.write_text(GEOJSON, encoding="utf-8")
    if backend == "native":
        request.getfixturevalue("qgis_app")
        from qgis.core import QgsProject
        from qgis_sdk.adapters.qgis import native_plugin_context

        context = native_plugin_context(
            scope, settings_prefix="components", notifications=notifications
        )
    else:
        layers = FakeLayers(scope)
        layers.register(
            dataset, name="sites", geometry_type="point", field_names=("name", "kind")
        )
        context = PluginContext(
            notifications,
            scope,
            layers=layers,
            project=FakeProject(layers, scope),
            files=FakeFiles(scope),
            log=RecordingLog(scope, "catalogue"),
        )
    runtime = PluginRuntime(CataloguePlugin, context)
    runtime.start()
    instance = runtime.instance
    assert isinstance(instance, CataloguePlugin)
    instance.jobs = JobService(scope, workers=FakeWorkers(), gui_thread=lambda: False)
    instance.calls = []
    # The view's scope is a child of the plugin's, as under the host: closing
    # the window detaches its components while the plugin's services live on.
    view_scope = scope.child()
    ctx = UiContext(
        notifications,
        FakeViewControl(),
        view_scope,
        actions=ViewActions(runtime, view_id="catalogue.test#1"),
        layers=context.layers,
        project=context.project,
        files=context.files,
        log=context.log,
    )
    yield Rendering(
        ctx, view_scope, dataset, native=backend == "native", runtime=runtime
    )
    runtime.unload()
    if not scope.closed:
        scope.close()
    if backend == "native":
        QgsProject.instance().removeAllMapLayers()


@pytest.mark.parametrize(
    ("factory", "value"),
    [
        (lambda: Text("note"), "hello"),
        (lambda: Toggle("enabled"), True),
        (lambda: Number("count", range=(0, 10)), 7),
        (lambda: Number("ratio"), 0.25),
        (lambda: Number("ratio", range=(0.0, 1.0), step=0.1), 0.5),
        (lambda: Distance("distance"), 12.5),
        (lambda: Choice("mode", options=("fast", "safe")), "safe"),
        (lambda: Colour("fill"), "#11223344"),
        (lambda: Colour("fill", alpha=False), "#112233"),
        (lambda: CrsPicker("crs"), "EPSG:3857"),
    ],
    ids=[
        "text",
        "toggle",
        "integer",
        "number",
        "bounded",
        "distance",
        "choice",
        "colour",
        "opaque",
        "crs",
    ],
)
def test_a_value_set_is_the_value_read(
    rendering: Rendering, factory: Callable[[], Component], value: object
) -> None:
    component = rendering.attach(factory())
    seen: list[object] = []
    component.changed(seen.append)

    component.set_value(value)

    assert component.value() == value
    assert type(component.value()) is type(value)
    assert seen == [value]
    assert component.snapshot()["value"] == value


@pytest.mark.parametrize(
    ("factory", "default"),
    [
        (lambda: Text("note"), ""),
        (lambda: Toggle("enabled"), False),
        (lambda: Number("count", range=(2, 10)), 2),
        (lambda: Number("ratio"), 0.0),
        (lambda: Distance("distance"), 0.0),
        (lambda: Choice("mode", options=("fast", "safe")), "fast"),
        (lambda: Colour("fill"), "#000000ff"),
        (lambda: CrsPicker("crs"), None),
        (lambda: LayerPicker("layer"), None),
        (lambda: FileInput("source"), None),
        (lambda: DirectoryInput("folder"), None),
    ],
    ids=[
        "text",
        "toggle",
        "integer",
        "number",
        "distance",
        "choice",
        "colour",
        "crs",
        "layer",
        "file",
        "directory",
    ],
)
def test_the_initial_value_is_the_same_under_both_renderings(
    rendering: Rendering, factory: Callable[[], Component], default: object
) -> None:
    component = rendering.attach(factory())

    assert component.value() == default


@pytest.mark.parametrize(
    ("factory", "value", "expected"),
    [
        (lambda: Number("count", range=(0, 10)), 11, "between 0 and 10"),
        (lambda: Number("ratio"), True, "a number"),
        (lambda: Choice("mode", options=("fast", "safe")), "slow", "one of"),
        (lambda: Colour("fill"), "red", "colour"),
        (lambda: Toggle("enabled"), "yes", "a boolean"),
        (lambda: Text("note"), 3, "a string"),
        (lambda: Distance("distance"), -1.0, "0 or more"),
        (lambda: FileInput("source"), "/tmp/x.csv", "FileRef"),
    ],
    ids=[
        "above-range",
        "bool-number",
        "unknown-choice",
        "named-colour",
        "string-toggle",
        "int-text",
        "negative-distance",
        "path-not-ref",
    ],
)
def test_a_value_outside_the_component_s_rule_is_refused_and_nothing_changes(
    rendering: Rendering,
    factory: Callable[[], Component],
    value: object,
    expected: str,
) -> None:
    component = rendering.attach(factory())
    before = component.value()
    seen: list[object] = []
    component.changed(seen.append)

    with pytest.raises(QgisSdkFormError, match=expected):
        component.set_value(value)

    assert component.value() == before
    assert seen == []


def test_a_layer_picker_lists_the_project_and_follows_additions(
    rendering: Rendering,
) -> None:
    picker = rendering.attach(LayerPicker("layer"))
    assert picker.options() == ()
    assert picker.value() is None

    layer_id = rendering.add_layer()
    picker.refresh()

    assert [option.id for option in picker.options()] == [layer_id]
    assert picker.options()[0].label == "sites"
    picker.set_value(layer_id)
    assert picker.value() == layer_id
    assert picker.snapshot()["value"] == layer_id


def test_a_layer_picker_refuses_an_id_the_project_does_not_hold(
    rendering: Rendering,
) -> None:
    picker = rendering.attach(LayerPicker("layer"))

    with pytest.raises(QgisSdkFormError, match="layer-9.*not in the project"):
        picker.set_value("layer-9")


def test_a_field_picker_follows_its_layer_picker(rendering: Rendering) -> None:
    layer = LayerPicker("layer")
    field = FieldPicker("attribute", of=layer)
    rendering.attach(layer)
    rendering.attach(field)
    assert field.options() == ()
    assert field.value() is None
    with pytest.raises(QgisSdkFormError, match="name.*not a field"):
        field.set_value("name")

    layer_id = rendering.add_layer()
    layer.refresh()
    layer.set_value(layer_id)

    assert [option.id for option in field.options()] == ["name", "kind"]
    field.set_value("kind")
    assert field.value() == "kind"
    assert field.snapshot()["of"] == "layer"

    layer.set_value(None)
    assert field.options() == ()
    assert field.value() is None


def test_a_file_input_mints_a_ref_through_ctx_files(
    rendering: Rendering, tmp_path: Path
) -> None:
    source = tmp_path / "sites.csv"
    source.write_text("id\n1\n", encoding="utf-8")
    component = rendering.attach(FileInput("source", filters=("*.csv",)))
    seen: list[object] = []
    component.changed(seen.append)

    component.set_path(source)

    ref = component.value()
    assert isinstance(ref, FileRef)
    assert (ref.kind, ref.name) == ("file", "sites.csv")
    assert rendering.ctx.files.resolve(ref) == source.resolve()
    assert seen == [ref]
    assert component.snapshot()["value"] == ref.to_wire()
    assert component.snapshot()["filters"] == ["*.csv"]
    assert component.path() == source.resolve()


def test_a_directory_input_mints_a_directory_ref(
    rendering: Rendering, tmp_path: Path
) -> None:
    component = rendering.attach(DirectoryInput("folder"))

    component.set_path(tmp_path)

    ref = component.value()
    assert ref.kind == "directory"
    assert rendering.ctx.files.resolve(ref) == tmp_path.resolve()
    with pytest.raises(QgisSdkFormError, match="a file FileRef, not a directory one"):
        FileInput("other").attach(rendering.ctx).set_value(ref)


def test_a_file_input_accepts_a_ref_it_can_resolve_and_refuses_a_stranger(
    rendering: Rendering, tmp_path: Path
) -> None:
    source = tmp_path / "a.csv"
    source.write_text("", encoding="utf-8")
    minted = rendering.ctx.files.grant_file(source)
    component = rendering.attach(FileInput("source"))

    component.set_value(minted)
    assert component.value() == minted
    assert component.path() == source.resolve()

    stranger = FileRef(id="f" * 16, name="a.csv", operations=("read",))
    with pytest.raises(QgisSdkFormError, match="unknown"):
        component.set_value(stranger)
    assert component.value() == minted


def test_a_file_input_without_a_files_service_refuses_by_name(tmp_path: Path) -> None:
    scope = ResourceScope()
    ctx = UiContext(RecordingNotifications(scope), FakeViewControl(), scope)
    component = FileInput("source").attach(ctx)

    with pytest.raises(QgisSdkUiError, match="files"):
        component.set_path(tmp_path / "x.csv")
    with pytest.raises(QgisSdkUiError, match="attach"):
        FileInput("loose").set_path(tmp_path / "x.csv")


def test_subscriptions_drop_with_the_scope(rendering: Rendering) -> None:
    component = rendering.attach(Text("note"))
    seen: list[object] = []
    unsubscribe = component.changed(seen.append)
    component.set_value("one")
    unsubscribe()
    component.set_value("two")
    assert seen == ["one"]

    component.changed(seen.append)
    rendering.scope.close()

    assert component.attached is False
    assert component.value() == "two"
    component.set_value("three")
    assert seen == ["one"]


def test_a_snapshot_is_the_component_s_semantic_node(rendering: Rendering) -> None:
    component = rendering.attach(Number("count", range=(0, 10), label="How many"))
    component.set_value(3)

    assert component.snapshot() == {
        "type": "Number",
        "name": "count",
        "label": "How many",
        "objectName": "form/count",
        "kind": "range",
        "value": 3,
        "minimum": 0,
        "maximum": 10,
    }


__all__ = [
    "Rendering",
    "make_rendering",
    "test_a_directory_input_mints_a_directory_ref",
    "test_a_field_picker_follows_its_layer_picker",
    "test_a_file_input_accepts_a_ref_it_can_resolve_and_refuses_a_stranger",
    "test_a_file_input_mints_a_ref_through_ctx_files",
    "test_a_file_input_without_a_files_service_refuses_by_name",
    "test_a_layer_picker_lists_the_project_and_follows_additions",
    "test_a_layer_picker_refuses_an_id_the_project_does_not_hold",
    "test_a_snapshot_is_the_component_s_semantic_node",
    "test_a_value_outside_the_component_s_rule_is_refused_and_nothing_changes",
    "test_a_value_set_is_the_value_read",
    "test_subscriptions_drop_with_the_scope",
    "test_the_initial_value_is_the_same_under_both_renderings",
]

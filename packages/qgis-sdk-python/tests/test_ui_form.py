"""``Form``: an action's inputs as catalogue components, under the fake (TASK-68 AC 3).

``Form.for_action``, ``Form.from_schema`` and ``Form(fields=[...])`` build
one tree; ``values()`` reads models, ``changed`` reports ``(name, value)``,
``submit()`` goes through ``UiContext.actions`` with the view's authority.
Nothing here touches Qt: a form is state until a host mounts it
(``test_ui_native.py`` does, under a ``QgsApplication``).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Literal

import pytest
from qgis_sdk.core import PluginContext, PluginRuntime, ResourceScope, UiContext
from qgis_sdk.declarations import action, describe_plugin, plugin
from qgis_sdk.models import (
    Colour as ColourInput,
)
from qgis_sdk.models import (
    CrsInput,
    FieldInput,
    FileInput,
    LayerInput,
    Metres,
    QgisSdkFormError,
    QgisSdkUiError,
    Range,
)
from qgis_sdk.testing import (
    FakeFiles,
    FakeLayers,
    FakeProject,
    FakeViewControl,
    RecordingNotifications,
)
from qgis_sdk.ui import (
    Button,
    Choice,
    Column,
    FieldPicker,
    Form,
    Number,
    Text,
    Toggle,
    ViewActions,
    input_for,
    schema_fields,
)


@plugin(id="demo.forms", title="Form demo")
class FormDemo:
    """One action per widget family; the handlers record what they got."""

    calls: list[dict] = []  # noqa: RUF012 - reset by the fixture

    @action(id="plain", title="Plain fields")
    def plain(
        self,
        name: str,
        count: int,
        ratio: float,
        enabled: bool,
        mode: Literal["fast", "safe"],
        note: str | None = None,
    ) -> str:
        FormDemo.calls.append(
            {
                "name": name,
                "count": count,
                "ratio": ratio,
                "enabled": enabled,
                "mode": mode,
                "note": note,
            }
        )
        return name

    @action(id="buffer", title="Buffer")
    def buffer(self, layer: LayerInput, distance: Metres, crs: CrsInput) -> str:
        FormDemo.calls.append({"layer": layer, "distance": distance, "crs": crs})
        return f"{layer}:{distance}:{crs}"

    @action(id="kinds", title="New kinds")
    def kinds(
        self,
        layer: LayerInput,
        attribute: FieldInput(of="layer"),
        weight: Range(0.0, 1.0),
        fill: ColourInput(),
        source: FileInput(filters=("*.csv",)),
    ) -> str:
        FormDemo.calls.append({"attribute": attribute, "source": source})
        return attribute


GEOJSON = '{"type": "FeatureCollection", "features": []}'


@pytest.fixture
def ctx(tmp_path: Path) -> Iterator[UiContext]:
    FormDemo.calls.clear()
    scope = ResourceScope()
    notifications = RecordingNotifications(scope)
    layers = FakeLayers(scope)
    dataset = tmp_path / "sites.geojson"
    dataset.write_text(GEOJSON, encoding="utf-8")
    layers.register(
        dataset, name="sites", geometry_type="point", field_names=("name", "kind")
    )
    project = FakeProject(layers, scope)
    project.add_layer(layers.open_vector(dataset).id)
    runtime = PluginRuntime(
        FormDemo, PluginContext(notifications=notifications, scope=scope, layers=layers)
    )
    runtime.start()
    yield UiContext(
        notifications,
        FakeViewControl(),
        scope.child(),
        actions=ViewActions(runtime, view_id="test"),
        layers=layers,
        project=project,
        files=FakeFiles(scope),
    )
    runtime.unload()


def _shape(form: Form) -> list[tuple[str, str, str, bool]]:
    return [(type(f).__name__, f.name, f.kind, f.required) for f in form.fields]


# -- construction -----------------------------------------------------------------------


def test_for_action_from_schema_and_by_hand_build_the_same_tree(ctx: UiContext) -> None:
    description = next(a for a in describe_plugin(FormDemo).actions if a.id == "plain")

    by_action = Form.for_action(ctx, "plain")
    by_schema = Form.from_schema(description.request, action_id="plain")
    by_hand = Form(
        fields=[
            Text("name", required=True),
            Number("count", integer=True, required=True),
            Number("ratio", required=True),
            Toggle("enabled", required=True),
            Choice("mode", options=("fast", "safe"), required=True),
            Text("note"),
        ],
        action_id="plain",
    )

    expected = [
        ("Text", "name", "text", True),
        ("Number", "count", "integer", True),
        ("Number", "ratio", "number", True),
        ("Toggle", "enabled", "boolean", True),
        ("Choice", "mode", "choice", True),
        ("Text", "note", "text", False),
    ]
    assert _shape(by_action) == _shape(by_schema) == _shape(by_hand) == expected
    assert by_action.snapshot() == by_schema.snapshot() == by_hand.snapshot()
    assert by_action.attached and not by_schema.attached
    assert by_action.action_id == "plain"
    assert by_action.object_name == "form"
    assert [f.object_name for f in by_action.fields][:2] == ["form/name", "form/count"]


def test_from_schema_accepts_the_action_description_too(ctx: UiContext) -> None:
    description = ctx.actions.describe("buffer")

    form = Form.from_schema(description)

    assert form.action_id == "buffer"
    assert _shape(form) == [
        ("LayerPicker", "layer", "layer", True),
        ("Distance", "distance", "metres", True),
        ("CrsPicker", "crs", "crs", True),
    ]


def test_the_new_kinds_build_their_inputs_and_a_field_picker_follows_its_layer(
    ctx: UiContext,
) -> None:
    form = Form.for_action(ctx, "kinds")

    assert _shape(form) == [
        ("LayerPicker", "layer", "layer", True),
        ("FieldPicker", "attribute", "field", True),
        ("Number", "weight", "range", True),
        ("Colour", "fill", "colour", True),
        ("FileInput", "source", "file", True),
    ]
    attribute: FieldPicker = form.field("attribute")
    assert attribute.of is form.field("layer")
    assert form.field("weight").range == (0.0, 1.0)
    assert form.field("source").filters == ("*.csv",)

    (layer_id,) = ctx.project.layer_ids()
    form.field("layer").refresh()
    form.set_values({"layer": layer_id})
    assert [option.id for option in attribute.options()] == ["name", "kind"]


def test_a_field_picker_whose_layer_is_not_in_the_schema_is_refused() -> None:
    schema = {
        "type": "object",
        "properties": {
            "attribute": {
                "type": "string",
                "x-qgis-sdk": {"kind": "field", "of": "layer"},
            }
        },
        "required": ["attribute"],
    }

    with pytest.raises(QgisSdkFormError, match="follows 'layer', which is not a layer"):
        Form.from_schema(schema)
    with pytest.raises(QgisSdkFormError, match="needs the layer picker"):
        input_for(schema_fields(schema)[0])


def test_a_form_holds_inputs_only_and_refuses_a_duplicate_name() -> None:
    with pytest.raises(QgisSdkUiError, match="Button 'go' is not an input"):
        Form(fields=[Text("a"), Button("go")])  # type: ignore[list-item]
    with pytest.raises(QgisSdkUiError, match="two fields named 'a'"):
        Form(fields=[Text("a"), Text("a")])


def test_for_action_refuses_an_unknown_action_and_an_unknown_initial(
    ctx: UiContext,
) -> None:
    with pytest.raises(QgisSdkUiError, match="declares no action 'explode'"):
        Form.for_action(ctx, "explode")
    with pytest.raises(QgisSdkUiError, match="no field\\(s\\) 'colour'"):
        Form.for_action(ctx, "plain", initial={"colour": "red"})


# -- values -----------------------------------------------------------------------------


def test_initial_values_values_and_changed(ctx: UiContext) -> None:
    form = Form.for_action(ctx, "plain", initial={"name": "a", "count": 2})
    seen: list[tuple[str, object]] = []
    form.changed(lambda name, value: seen.append((name, value)))

    assert form.values() == {
        "name": "a",
        "count": 2,
        "ratio": 0.0,
        "enabled": False,
        "mode": "fast",
        "note": "",
    }
    form.field("ratio").set_value(0.5)
    form.set_values({"enabled": True, "mode": "safe"})

    assert seen == [("ratio", 0.5), ("enabled", True), ("mode", "safe")]
    assert form.field("mode").value() == "safe"
    with pytest.raises(
        QgisSdkUiError, match="has no field 'size'; it has: name, count"
    ):
        form.field("size")


def test_a_refused_value_leaves_the_form_as_it_was(ctx: UiContext) -> None:
    form = Form.for_action(ctx, "plain")

    with pytest.raises(QgisSdkFormError, match="one of"):
        form.set_values({"name": "x", "mode": "slow"})

    assert form.values()["name"] == "x"
    assert form.values()["mode"] == "fast"


# -- submit -----------------------------------------------------------------------------


def test_submit_dispatches_through_ctx_actions_with_the_models(ctx: UiContext) -> None:
    form = Form.for_action(ctx, "plain", initial={"name": "buffer", "count": 3})
    form.set_values({"ratio": 1.5, "enabled": True, "mode": "safe"})

    assert form.submit() == "buffer"

    assert FormDemo.calls == [
        {
            "name": "buffer",
            "count": 3,
            "ratio": 1.5,
            "enabled": True,
            "mode": "safe",
            "note": "",
        }
    ]


def test_submit_names_the_empty_required_fields_first(ctx: UiContext) -> None:
    form = Form.for_action(ctx, "buffer")
    form.set_values({"distance": 10})

    with pytest.raises(QgisSdkFormError, match="layer, crs are required"):
        form.submit()
    assert FormDemo.calls == []

    (layer_id,) = ctx.project.layer_ids()
    form.field("layer").refresh()
    form.set_values({"layer": layer_id, "crs": "EPSG:3857"})
    assert form.submit() == f"{layer_id}:10.0:EPSG:3857"


def test_submit_sends_a_file_ref_the_handler_resolves(
    ctx: UiContext, tmp_path: Path
) -> None:
    source = tmp_path / "rows.csv"
    source.write_text("a\n", encoding="utf-8")
    form = Form.for_action(ctx, "kinds")
    (layer_id,) = ctx.project.layer_ids()
    form.field("layer").refresh()
    form.set_values({"layer": layer_id, "attribute": "kind", "weight": 0.5})
    form.set_values({"fill": "#ff000080"})
    form.field("source").set_path(source)

    assert form.submit() == "kind"

    ref = FormDemo.calls[0]["source"]
    assert ref.kind == "file"
    assert ctx.files.resolve(ref) == source.resolve()


def test_submit_needs_an_action_and_an_attached_context(ctx: UiContext) -> None:
    loose = Form(fields=[Text("name")])
    with pytest.raises(QgisSdkUiError, match="no action to submit"):
        loose.submit()

    unattached = Form(
        fields=[Text("name", value="x", required=True)], action_id="plain"
    )
    with pytest.raises(QgisSdkUiError, match="attached"):
        unattached.submit()


def test_the_scope_closing_detaches_the_form_and_its_fields(ctx: UiContext) -> None:
    form = Form.for_action(ctx, "plain")
    seen: list[object] = []
    form.changed(lambda name, value: seen.append(name))

    ctx.scope.close()
    form.field("name").set_value("after")

    assert form.attached is False
    assert all(not field.attached for field in form.fields)
    assert seen == []


# -- button and column ------------------------------------------------------------------


def test_a_button_is_named_under_buttons_and_click_reaches_its_listeners() -> None:
    button = Button("run", "Run it")
    pressed: list[int] = []
    unsubscribe = button.clicked(lambda: pressed.append(1))

    button.click()
    unsubscribe()
    button.click()

    assert pressed == [1]
    assert button.object_name == "buttons/run"
    assert button.snapshot() == {
        "type": "Button",
        "name": "run",
        "label": "Run it",
        "objectName": "buttons/run",
        "text": "Run it",
    }


def test_a_column_attaches_its_children_and_snapshots_the_tree(ctx: UiContext) -> None:
    form = Form.for_action(ctx, "buffer")
    run = Button("run", "Buffer")
    column = Column("buffer_dialog", [form, run])

    column.attach(ctx)

    assert run.attached and form.attached
    assert column.find("run") is run
    assert column.find("form") is form
    assert column.object_name == "buffer_dialog"
    node = column.snapshot()
    assert [child["type"] for child in node["children"]] == ["Form", "Button"]
    assert node["children"][0]["action"] == "buffer"
    assert [f["objectName"] for f in node["children"][0]["fields"]] == [
        "form/layer",
        "form/distance",
        "form/crs",
    ]
    with pytest.raises(QgisSdkUiError, match="no child named 'x'"):
        column.find("x")
    with pytest.raises(QgisSdkUiError, match="two children named 'buttons/run'"):
        Column("c", [Button("run"), Button("run")])

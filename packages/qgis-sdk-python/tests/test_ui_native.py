"""``Form`` mounted under a ``QgsApplication`` (TASK-68 AC 3, 4).

Skips unless Qt and the QGIS gui bindings are importable. The tree itself
is pinned by ``test_ui_form.py`` in the QGIS-free suite; this file proves
the widget half - a form mounts as labelled rows of the catalogue's QGIS
widgets, each found by its ``objectName``, a user's edits reach ``values()``
and ``submit()`` runs the declared handler with coerced arguments - and that
a ``Dialog`` returning ``Column([Form, Button])`` is what the host shows.

The imports are guarded rather than left to ``importorskip`` because a
*broken* Qt install raises ``ImportError`` from inside the module (a missing
``libGL`` is the usual one, and it says so).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Literal

import pytest
from qgis_sdk.core import PluginRuntime, ResourceScope, UiContext
from qgis_sdk.declarations import action, plugin
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
    Range,
)
from qgis_sdk.testing import FakeViewControl, RecordingNotifications
from qgis_sdk.ui import Button, Column, Form, ViewActions

# The qgis layer: the pickers read QgsProject.instance(), so a bare QApplication
# is not enough. The environment and bindings path come from tests/conftest.py.
pytestmark = pytest.mark.qgis

try:
    from qgis.core import QgsProject
    from qgis.gui import (
        QgsColorButton,
        QgsFieldComboBox,
        QgsFileWidget,
        QgsMapLayerComboBox,
        QgsProjectionSelectionWidget,
    )
    from qgis.PyQt.QtGui import QColor
    from qgis.PyQt.QtWidgets import (
        QCheckBox,
        QComboBox,
        QDoubleSpinBox,
        QFormLayout,
        QLineEdit,
        QPushButton,
        QSpinBox,
        QWidget,
    )
    from qgis_sdk.adapters.qgis import native_plugin_context
except ImportError as error:  # pragma: no cover - depends on the host
    pytest.skip(f"native forms need Qt and QGIS: {error}", allow_module_level=True)


@plugin(id="demo.forms", title="Form demo")
class FormDemo:
    """One action per widget family, with the handler recording what it got."""

    calls: list[dict] = []  # noqa: RUF012 - reset by the fixture

    @action(id="plain", title="Plain fields")
    def plain(
        self,
        name: str,
        count: int,
        ratio: float,
        enabled: bool,
        mode: Literal["fast", "safe"],
    ) -> str:
        FormDemo.calls.append(
            {
                "name": name,
                "count": count,
                "ratio": ratio,
                "enabled": enabled,
                "mode": mode,
            }
        )
        return name

    @action(id="marked", title="Marked fields")
    def marked(
        self, layer_id: LayerInput, working_crs: CrsInput, distance: Metres
    ) -> str:
        FormDemo.calls.append(
            {"layer_id": layer_id, "working_crs": working_crs, "distance": distance}
        )
        return layer_id

    @action(id="kinds", title="New kinds")
    def kinds(
        self,
        layer: LayerInput,
        attribute: FieldInput(of="layer"),
        weight: Range(0.0, 1.0),
        fill: ColourInput(),
    ) -> str:
        FormDemo.calls.append(
            {"layer": layer, "attribute": attribute, "weight": weight, "fill": fill}
        )
        return attribute

    @action(id="file", title="A file")
    def file(self, source: FileInput(filters=("*.csv",))) -> str:
        FormDemo.calls.append({"source": source})
        return source.name


GEOJSON = """{"type": "FeatureCollection", "features": [{"type": "Feature",
"properties": {"name": "a", "kind": "b"}, "geometry": {"type": "Point",
"coordinates": [21.0, 52.2]}}]}"""


@pytest.fixture
def ctx(qgis_app, tmp_path: Path) -> Iterator[UiContext]:
    """A view context over the native services, with one layer in the project."""
    FormDemo.calls.clear()
    scope = ResourceScope()
    notifications = RecordingNotifications(scope)
    context = native_plugin_context(
        scope, settings_prefix="demo.forms", notifications=notifications
    )
    dataset = tmp_path / "sites.geojson"
    dataset.write_text(GEOJSON, encoding="utf-8")
    context.project.add_layer(context.layers.open_vector(dataset).id)
    runtime = PluginRuntime(FormDemo, context)
    runtime.start()
    yield UiContext(
        notifications,
        FakeViewControl(),
        scope.child(),
        actions=ViewActions(runtime, view_id="test"),
        layers=context.layers,
        project=context.project,
        files=context.files,
    )
    runtime.unload()
    QgsProject.instance().removeAllMapLayers()


def _row_labels(widget: QWidget) -> list[str]:
    layout = widget.layout()
    assert isinstance(layout, QFormLayout)
    return [
        layout.itemAt(row, QFormLayout.ItemRole.LabelRole).widget().text()
        for row in range(layout.rowCount())
    ]


def test_a_form_mounts_as_labelled_rows_of_the_catalogue_widgets(
    ctx: UiContext,
) -> None:
    form = Form.for_action(ctx, "plain")

    widget = form.mount()

    assert widget.objectName() == "form"
    assert _row_labels(widget) == [
        "Name *",
        "Count *",
        "Ratio *",
        "Enabled *",
        "Mode *",
    ]
    assert isinstance(widget.findChild(QLineEdit, "form/name"), QLineEdit)
    assert isinstance(widget.findChild(QSpinBox, "form/count"), QSpinBox)
    assert isinstance(widget.findChild(QDoubleSpinBox, "form/ratio"), QDoubleSpinBox)
    assert isinstance(widget.findChild(QCheckBox, "form/enabled"), QCheckBox)
    assert isinstance(widget.findChild(QComboBox, "form/mode"), QComboBox)
    assert form.field("name").widget is widget.findChild(QLineEdit, "form/name")


def test_markers_and_the_new_kinds_mount_the_qgis_widgets(ctx: UiContext) -> None:
    marked = Form.for_action(ctx, "marked")
    kinds = Form.for_action(ctx, "kinds")
    file = Form.for_action(ctx, "file")

    for form in (marked, kinds, file):
        form.mount()

    assert isinstance(marked.field("layer_id").widget, QgsMapLayerComboBox)
    assert isinstance(marked.field("working_crs").widget, QgsProjectionSelectionWidget)
    assert marked.field("distance").widget.suffix() == " m"
    picker = kinds.field("attribute").widget
    assert isinstance(picker, QgsFieldComboBox)
    weight = kinds.field("weight").widget
    assert (weight.minimum(), weight.maximum()) == (0.0, 1.0)
    assert isinstance(kinds.field("fill").widget, QgsColorButton)
    assert kinds.field("fill").widget.allowOpacity() is True
    assert isinstance(file.field("source").widget, QgsFileWidget)
    assert file.field("source").widget.filter() == "CSV (*.csv)"

    # The field picker follows the layer picker it belongs to.
    (layer_id,) = ctx.project.layer_ids()
    kinds.field("layer").set_value(layer_id)
    assert picker.layer() is QgsProject.instance().mapLayer(layer_id)
    assert [o.id for o in kinds.field("attribute").options()] == ["name", "kind"]


def test_edits_in_the_widgets_are_submitted_coerced_to_the_handler(
    ctx: UiContext,
) -> None:
    form = Form.for_action(ctx, "plain")
    widget = form.mount()

    widget.findChild(QLineEdit, "form/name").setText("  buffer ")
    widget.findChild(QSpinBox, "form/count").setValue(3)
    widget.findChild(QDoubleSpinBox, "form/ratio").setValue(1.5)
    widget.findChild(QCheckBox, "form/enabled").setChecked(True)
    widget.findChild(QComboBox, "form/mode").setCurrentIndex(1)

    assert form.values()["name"] == "  buffer "
    assert form.submit() == "buffer"
    assert FormDemo.calls == [
        {"name": "buffer", "count": 3, "ratio": 1.5, "enabled": True, "mode": "safe"}
    ]


def test_a_colour_and_a_file_picked_in_their_widgets_reach_the_handler(
    ctx: UiContext, tmp_path: Path
) -> None:
    kinds = Form.for_action(ctx, "kinds")
    kinds.mount()
    (layer_id,) = ctx.project.layer_ids()
    kinds.field("layer").widget.setLayer(QgsProject.instance().mapLayer(layer_id))
    kinds.field("attribute").widget.setField("kind")
    kinds.field("weight").widget.setValue(0.5)
    kinds.field("fill").widget.setColor(QColor(255, 0, 16, 128))

    assert kinds.submit() == "kind"
    assert FormDemo.calls[-1] == {
        "layer": layer_id,
        "attribute": "kind",
        "weight": 0.5,
        "fill": "#ff001080",
    }

    source = tmp_path / "rows.csv"
    source.write_text("a\n", encoding="utf-8")
    file = Form.for_action(ctx, "file")
    file.mount()
    file.field("source").widget.setFilePath(str(source))

    assert file.submit() == "rows.csv"
    assert ctx.files.resolve(FormDemo.calls[-1]["source"]) == source.resolve()


def test_an_empty_required_field_is_refused_before_the_handler_runs(
    ctx: UiContext,
) -> None:
    form = Form.for_action(ctx, "marked")
    form.mount()

    with pytest.raises(QgisSdkFormError, match="layer_id, working_crs are required"):
        form.submit()
    assert FormDemo.calls == []


def test_a_column_of_form_and_button_is_one_widget_tree(ctx: UiContext) -> None:
    form = Form.for_action(ctx, "plain", initial={"name": "x", "count": 1})
    run = Button("run", "Run")
    results: list[object] = []
    run.clicked(lambda: results.append(form.submit()))
    column = Column("dialog", [form, run]).attach(ctx)

    widget = column.mount()
    widget.findChild(QPushButton, "buttons/run").click()

    assert widget.objectName() == "dialog"
    assert widget.findChild(QWidget, "form") is form.widget
    assert results == ["x"]
    assert FormDemo.calls[0]["name"] == "x"

    ctx.scope.close()
    assert not run.mounted and not form.mounted

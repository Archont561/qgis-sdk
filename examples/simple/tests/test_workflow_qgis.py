"""The same workflow against real QGIS: ``qgis-sdk test --target qgis``.

What only QGIS can prove: Processing buffered in metres, the output file is new
and the fixture is byte-identical afterwards, the packaged style landed on the
output's renderer, the export is a real OGR file, and the ``BufferDialog``
the host opens for the ``buffer`` action dispatches the very same handler the
page calls - native and web are two front ends over one ``runtime.actions``.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest
from conftest import classFactory
from simple.plugin import EXPORT_DIRECTORY_KEY, FIXTURE
from simple.workflow import LocalGisWorkflow

pytestmark = pytest.mark.qgis

WORKING_CRS = "EPSG:3857"


@pytest.fixture
def desktop(qgis_app: Any) -> Any:
    from qgis.core import QgsProject

    QgsProject.instance().removeAllMapLayers()
    plugin = classFactory(None)
    plugin.initGui()
    try:
        yield plugin
    finally:
        plugin.unload()
        QgsProject.instance().removeAllMapLayers()


def _qgs_layer(layer_id: str) -> Any:
    from qgis.core import QgsProject

    layer = QgsProject.instance().mapLayer(layer_id)
    assert layer is not None, layer_id
    return layer


def test_the_workflow_runs_end_to_end_and_preserves_the_source(
    desktop: Any, tmp_path: Path
) -> None:
    actions = desktop.runtime.actions
    before = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    exports = tmp_path / "exports"
    exports.mkdir()
    desktop.runtime.instance.ctx.settings.set(EXPORT_DIRECTORY_KEY, str(exports))

    source = actions["open_fixture"]()
    _qgs_layer(source.id).selectByIds([1, 3])
    assert actions["selected_features"](source.id) == [1, 3]

    output = actions["buffer"](source.id, 500.0, WORKING_CRS)
    export = actions["export_layer"](output.id, "buffer.gpkg")

    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == before
    assert output.id != source.id
    assert output.geometry_type == "polygon"
    assert output.crs == WORKING_CRS
    rendered = _qgs_layer(output.id).renderer().symbol()
    assert rendered.symbolLayer(0).layerType() == "SimpleFill"
    assert (exports / "buffer.gpkg").is_file()
    assert export.driver == "GPKG"
    assert sorted(p.name for p in exports.iterdir()) == ["buffer.gpkg"]


def test_a_geographic_working_crs_is_refused_and_nothing_is_added(
    desktop: Any,
) -> None:
    from qgis.core import QgsProject
    from qgis_sdk.models import QgisSdkAlgorithmRejectedError

    source = desktop.runtime.actions["open_fixture"]()

    with pytest.raises(QgisSdkAlgorithmRejectedError):
        desktop.runtime.actions["buffer"](source.id, 500.0, "EPSG:4326")

    assert list(QgsProject.instance().mapLayers()) == [source.id]


def test_the_native_dialog_and_a_direct_call_dispatch_the_same_handler(
    desktop: Any, qgis_app: Any
) -> None:
    """``BufferDialog`` opened by the host is the ``buffer`` action's ``Form``
    mounted as QGIS widgets; its button submits to the same handler."""
    from qgis.PyQt.QtWidgets import QPushButton, QWidget
    from qgis_sdk.ui import Form
    from simple.surfaces import BufferDialog

    source = desktop.runtime.actions["open_fixture"]()

    dialog = desktop.runtime.instance.ctx.ui.open(
        BufferDialog, initial={"distance_metres": 250}
    )
    form: Form = dialog.form
    window = form.widget.window()
    assert [f.kind for f in form.fields] == ["layer", "metres", "crs"]
    assert isinstance(window.findChild(QWidget, "form"), QWidget)
    form.field("layer_id").widget.setLayer(_qgs_layer(source.id))
    form.field("working_crs").widget.setCrs(_crs(WORKING_CRS))

    window.findChild(QPushButton, "buttons/run").click()
    qgis_app.processEvents()

    output_id = next(layer_id for layer_id in _project_ids() if layer_id != source.id)
    output = _qgs_layer(output_id)
    assert output.geometryType().name.lower().startswith("polygon")
    assert output.crs().authid() == WORKING_CRS
    assert {source.id, output_id} <= set(_project_ids())


def test_the_results_dock_is_the_catalogue_mounted_as_qgis_widgets(
    desktop: Any, qgis_app: Any
) -> None:
    """``ResultsDock`` opened by the host: the table, the log view and the two
    buttons are real widgets with the catalogue's names; ``Open the fixture``
    runs the action through ``ctx.actions`` and the row appears; the log view
    shows the ``ctx.log`` records of other surfaces too."""
    from qgis.PyQt.QtWidgets import QPlainTextEdit, QPushButton, QTableWidget
    from qgis_sdk.ui import ui_snapshot
    from simple.surfaces import ResultsDock

    dock = desktop.runtime.instance.ctx.ui.open(ResultsDock)
    window = dock.table.widget.window()
    names = [node["objectName"] for node in _walk(ui_snapshot(window))]
    assert {"buttons/open", "buttons/clear", "feedback/results", "feedback/log"} <= set(
        names
    )

    window.findChild(QPushButton, "buttons/open").click()
    qgis_app.processEvents()
    table = window.findChild(QTableWidget, "feedback/results")
    assert table.rowCount() == 1
    assert table.item(0, 0).text() == "points"

    desktop.runtime.instance.ctx.log.warning("from elsewhere", source="test")
    log = window.findChild(QPlainTextEdit, "feedback/log")
    assert log.toPlainText().splitlines()[-1].startswith("[warning] from elsewhere")

    window.findChild(QPushButton, "buttons/clear").click()
    assert table.rowCount() == 0


def _walk(node: dict) -> list[dict]:
    found = [node]
    for child in node.get("children", ()):
        found.extend(_walk(child))
    return found


def _crs(authid: str) -> Any:
    from qgis.core import QgsCoordinateReferenceSystem

    return QgsCoordinateReferenceSystem(authid)


def _project_ids() -> list[str]:
    from qgis.core import QgsProject

    return list(QgsProject.instance().mapLayers())


def test_the_workflow_class_refuses_an_unknown_layer_and_a_silent_overwrite(
    desktop: Any, tmp_path: Path
) -> None:
    """The class behind the actions, held to the fakes' contract on real QGIS."""
    from qgis.core import QgsProject
    from qgis_sdk.models import QgisSdkExportRefusedError, QgisSdkLayerNotFoundError

    workflow = LocalGisWorkflow(desktop.runtime.instance.ctx)

    with pytest.raises(QgisSdkLayerNotFoundError):
        workflow.buffer("no-such-layer", 500.0, WORKING_CRS)
    assert list(QgsProject.instance().mapLayers()) == []

    source = workflow.open_dataset(FIXTURE)
    destination = tmp_path / "points.geojson"
    destination.write_text("mine", encoding="utf-8")
    with pytest.raises(QgisSdkExportRefusedError):
        workflow.export(source.id, destination)
    assert destination.read_text(encoding="utf-8") == "mine"

    export = workflow.export(source.id, destination, overwrite=True)

    assert export.driver == "GeoJSON"
    assert destination.read_text(encoding="utf-8") != "mine"


def test_the_plugins_provider_is_in_the_toolbox_only_while_it_runs(
    qgis_app: Any,
) -> None:
    """``providers = (algorithms.provider,)`` is the whole registration step."""
    from qgis.core import QgsApplication

    def advertised() -> list[str]:
        registry = QgsApplication.processingRegistry()
        return sorted(
            algorithm.id()
            for algorithm in registry.algorithms()
            if algorithm.provider() is not None
            and algorithm.provider().id() == "simple"
        )

    plugin = classFactory(None)
    assert advertised() == []
    plugin.initGui()
    try:
        assert advertised() == ["simple:buffer", "simple:centroid"]
        assert plugin.runtime.registered_providers == ("simple",)
    finally:
        plugin.unload()
    assert advertised() == []

"""The same workflow against real QGIS: ``qgis-sdk test --target qgis``.

What only QGIS can prove: Processing buffered in metres, the output file is new
and the fixture is byte-identical afterwards, the packaged style landed on the
output's renderer, the export is a real OGR file, and the native dialog QGIS
renders for the ``buffer`` action dispatches the very same handler the page
calls - native and web are two front ends over one ``runtime.actions``.
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
    desktop: Any,
) -> None:
    from qgis_sdk.adapters.qgis.ui import NativeForms

    forms = NativeForms(desktop.runtime)
    source = desktop.runtime.actions["open_fixture"]()

    assert [f.widget for f in forms.fields("buffer")] == ["layer", "metres", "crs"]
    dialog = forms.render("buffer")
    dialog.widget("layer_id").setLayer(_qgs_layer(source.id))
    dialog.widget("distance_metres").setValue(250.0)
    dialog.widget("working_crs").setCrs(_crs(WORKING_CRS))

    output = forms.dispatch("buffer", dialog.values())

    assert output.geometry_type == "polygon"
    assert output.crs == WORKING_CRS
    assert {source.id, output.id} <= set(_project_ids())


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

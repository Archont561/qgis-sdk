"""Contract: the local GIS reference workflow (decision-19) on both backends.

``LocalGisWorkflow`` is what the reference plugin's actions call, so holding it
to the same expectations against the fakes and against real QGIS is what makes
"native/web equivalence" a property of the services rather than of one page.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import conftest
import pytest
from qgis_sdk.core import PluginContext
from qgis_sdk.models import (
    QgisSdkAlgorithmRejectedError,
    QgisSdkExportRefusedError,
    QgisSdkLayerNotFoundError,
    QgisSdkUnsupportedCapabilityError,
)
from qgis_sdk.reference import LocalGisWorkflow

if TYPE_CHECKING:
    Services = conftest.Services


def _workflow(services: Services) -> LocalGisWorkflow:
    return LocalGisWorkflow(
        PluginContext(
            notifications=services.notifications,
            scope=services.scope,
            layers=services.layers,
            project=services.project,
            styles=services.styles,
            algorithms=services.algorithms,
        )
    )


def test_open_dataset_loads_the_fixture_and_presents_it(services: Services) -> None:
    workflow = _workflow(services)

    info = workflow.open_dataset(services.dataset)

    assert info.name == conftest.FIXTURE_NAME
    assert info.geometry_type == conftest.FIXTURE_GEOMETRY
    assert services.project.layer_ids() == (info.id,)


def test_selected_features_reads_the_host_selection(services: Services) -> None:
    workflow = _workflow(services)
    info = workflow.open_dataset(services.dataset)
    services.select(info.id, (3, 1))

    assert sorted(workflow.selected_features(info.id)) == [1, 3]
    assert workflow.selected_features(info.id) == services.layers.selection(info.id)


def test_buffer_produces_a_styled_new_layer_and_presents_it_last(
    services: Services,
) -> None:
    workflow = _workflow(services)
    info = workflow.open_dataset(services.dataset)

    output = workflow.buffer(info.id, 500.0, services.working_crs)

    assert output.id != info.id, "the output is a new layer, never the source"
    assert output.geometry_type == "polygon"
    assert sorted(services.project.layer_ids()) == sorted((info.id, output.id))
    assert services.layers.layer(info.id) == info, "the source is unchanged"


def test_buffer_without_a_working_crs_is_refused_before_anything_runs(
    services: Services,
) -> None:
    workflow = _workflow(services)
    info = workflow.open_dataset(services.dataset)

    with pytest.raises(QgisSdkAlgorithmRejectedError):
        workflow.buffer(info.id, 500.0, "")

    assert services.project.layer_ids() == (info.id,)


def test_buffer_of_an_unknown_layer_is_refused(services: Services) -> None:
    workflow = _workflow(services)

    with pytest.raises(QgisSdkLayerNotFoundError):
        workflow.buffer("no-such-layer", 500.0, services.working_crs)

    assert services.project.layer_ids() == ()


def test_export_writes_the_output_where_the_caller_said(
    services: Services, tmp_path: Path
) -> None:
    workflow = _workflow(services)
    info = workflow.open_dataset(services.dataset)
    output = workflow.buffer(info.id, 500.0, services.working_crs)
    destination = tmp_path / "buffer.gpkg"

    export = workflow.export(output.id, destination)

    assert export.path == str(destination)
    assert export.driver == "GPKG"
    assert destination.is_file()


def test_export_needs_overwrite_to_replace_a_file(
    services: Services, tmp_path: Path
) -> None:
    workflow = _workflow(services)
    info = workflow.open_dataset(services.dataset)
    destination = tmp_path / "points.geojson"
    destination.write_text("mine", encoding="utf-8")

    with pytest.raises(QgisSdkExportRefusedError):
        workflow.export(info.id, destination)
    workflow.export(info.id, destination, overwrite=True)

    assert destination.read_text(encoding="utf-8") != "mine"


def test_a_host_without_processing_refuses_the_buffer_by_name(
    services: Services,
) -> None:
    context = PluginContext(
        notifications=services.notifications,
        scope=services.scope,
        layers=services.layers,
        project=services.project,
        styles=services.styles,
    )
    workflow = LocalGisWorkflow(context)
    info = workflow.open_dataset(services.dataset)

    with pytest.raises(QgisSdkUnsupportedCapabilityError) as error:
        workflow.buffer(info.id, 500.0, services.working_crs)

    assert "algorithms" in str(error.value)

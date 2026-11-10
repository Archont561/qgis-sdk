"""One plugin runtime over the SDK fakes: the pure half of every test here.

``classFactory`` is what `qgis-sdk build` and `qgis-sdk dev` bind for QGIS
(decision-43): ``host()`` over the application ``pyproject.toml`` names. Outside a
``QgsApplication`` it hands the plugin a bare context, inside one every
curated service - which is why the ``qgis`` tests call the very same entry.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from qgis_sdk.adapters.desktop import (
    DesktopLifecycleAdapter,
    create_class_factory,
    host,
)
from qgis_sdk.bridge.authority import HostAuthority
from qgis_sdk.core import PluginContext, PluginServices, ResourceScope
from qgis_sdk.files import FilesService
from qgis_sdk.models import BufferRequest, RasterStatistics
from qgis_sdk.models.canvas import CanvasExtent
from qgis_sdk.testing import (
    FakeAlgorithms,
    FakeCanvas,
    FakeLayers,
    FakeLayouts,
    FakeProject,
    FakeRasters,
    FakeSettings,
    FakeStyles,
    FakeWorkers,
    RecordingNotifications,
)
from simple.plugin import ELEVATION, FIXTURE, app

WORKING_CRS = "EPSG:3857"
classFactory = host("simple.plugin:app", placement="dock")


@dataclass(frozen=True, slots=True)
class FakeHost:
    """The fakes behind one runtime, so a test can arrange and observe them."""

    runtime: object
    context: PluginContext
    layers: FakeLayers
    algorithms: FakeAlgorithms
    project: FakeProject
    styles: FakeStyles
    settings: FakeSettings
    notifications: RecordingNotifications
    canvas: FakeCanvas
    rasters: FakeRasters
    layouts: FakeLayouts


@pytest.fixture
def fake_host(tmp_path: Path) -> Iterator[FakeHost]:
    scope = ResourceScope()
    files = FilesService(HostAuthority(), scope, owner="plugin:simple")
    # The rasters first: a raster is a layer too, so the layer fake holds it and
    # `list_layers` answers both kinds (TASK-87).
    rasters = FakeRasters(scope)
    rasters.register(
        ELEVATION,
        name="elevation",
        extent=CanvasExtent(x_min=21.0, y_min=52.0, x_max=21.3, y_max=52.2),
        crs="EPSG:4326",
        values=(1.0,),
        holes=((21.15, 52.05),),
        # The three-by-two grid's own numbers: 1, 2, 3 in the top row and
        # 4, no-data, 6 in the bottom one.
        statistics={
            1: RasterStatistics(
                band=1,
                minimum=1.0,
                maximum=6.0,
                mean=3.2,
                std_dev=1.9235384061671346,
                valid_count=5,
                no_data_count=1,
            )
        },
    )
    layers = FakeLayers(scope, rasters=rasters)
    layers.register(
        FIXTURE, name="points", geometry_type="point", field_names=("id", "value")
    )
    algorithms = FakeAlgorithms(layers, scope)
    algorithms.declare_output(
        BufferRequest,
        tmp_path / "buffer-output.gpkg",
        name="buffer",
        geometry_type="polygon",
        field_names=("id", "value"),
        crs=WORKING_CRS,
    )
    # The generic surface is scripted per algorithm id: what `native:centroids`
    # produces here is a layer the fake registered, the way a run allocates one.
    centroids = tmp_path / "centroids.gpkg"
    layers.register(
        centroids, name="centroids", geometry_type="point", field_names=("id", "value")
    )
    algorithms.script_run("native:centroids", {"OUTPUT": centroids})
    project = FakeProject(layers, scope)
    styles = FakeStyles(layers, scope)
    # The buffered output is the layer the workflow presents, so the fake canvas
    # knows where that layer is: zooming onto a layer it was never told about
    # refuses, on the fake as on QGIS. The fake numbers the layers it opens in
    # order, and the workflow opens the fixture first and the output second.
    canvas = FakeCanvas(
        scope,
        layer_extents={
            "layer-1": CanvasExtent(0.0, 0.0, 10.0, 10.0, "EPSG:4326"),
            "layer-2": CanvasExtent(0.0, 0.0, 100.0, 100.0, WORKING_CRS),
        },
    )
    settings = FakeSettings(scope)
    notifications = RecordingNotifications(scope)
    # One layout to export, the way a project with a composed page answers; the
    # fake writes a marker file where QGIS would render the page.
    layouts = FakeLayouts(
        scope,
        workers=FakeWorkers(),
        files=files,
        working_directory=tmp_path / "layouts",
    )
    layouts.declare_layout("report", pages=2)
    context = PluginContext(
        notifications,
        scope,
        PluginServices(
            layers=layers,
            project=project,
            settings=settings,
            styles=styles,
            algorithms=algorithms,
            canvas=canvas,
            rasters=rasters,
            layouts=layouts,
            files=files,
        ),
    )
    factory = create_class_factory(app, context_factory=lambda _: context)
    adapter: DesktopLifecycleAdapter = factory(None)
    adapter.initGui()
    try:
        yield FakeHost(
            runtime=adapter.runtime,
            context=context,
            layers=layers,
            algorithms=algorithms,
            project=project,
            styles=styles,
            settings=settings,
            notifications=notifications,
            canvas=canvas,
            rasters=rasters,
            layouts=layouts,
        )
    finally:
        adapter.unload()

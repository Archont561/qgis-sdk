"""One plugin runtime over the SDK fakes: the pure half of every test here.

``classFactory`` is what `qgis-sdk build` and `qgis-sdk dev` bind for QGIS
(decision-43): ``host()`` over the class ``pyproject.toml`` names. Outside a
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
from qgis_sdk.core import PluginContext, ResourceScope
from qgis_sdk.models import BufferRequest
from qgis_sdk.testing import (
    FakeAlgorithms,
    FakeLayers,
    FakeProject,
    FakeSettings,
    FakeStyles,
    RecordingNotifications,
)
from simple.plugin import FIXTURE, SimplePlugin

WORKING_CRS = "EPSG:3857"
classFactory = host("simple.plugin:SimplePlugin", placement="dock")


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


@pytest.fixture
def fake_host(tmp_path: Path) -> Iterator[FakeHost]:
    scope = ResourceScope()
    layers = FakeLayers(scope)
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
    settings = FakeSettings(scope)
    notifications = RecordingNotifications(scope)
    context = PluginContext(
        notifications=notifications,
        scope=scope,
        layers=layers,
        project=project,
        settings=settings,
        styles=styles,
        algorithms=algorithms,
    )
    factory = create_class_factory(SimplePlugin, context_factory=lambda _: context)
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
        )
    finally:
        adapter.unload()

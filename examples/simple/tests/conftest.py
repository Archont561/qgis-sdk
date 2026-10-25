"""One plugin runtime over the SDK fakes: the pure half of every test here."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from qgis_sdk.adapters.desktop import DesktopLifecycleAdapter, create_class_factory
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


@dataclass(frozen=True, slots=True)
class FakeHost:
    """The fakes behind one runtime, so a test can arrange and observe them."""

    runtime: object
    layers: FakeLayers
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
            layers=layers,
            project=project,
            styles=styles,
            settings=settings,
            notifications=notifications,
        )
    finally:
        adapter.unload()

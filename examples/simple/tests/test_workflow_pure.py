"""The reference workflow through the plugin's declared actions, without QGIS.

These run under ``qgis-sdk test`` (pure target): the services are the SDK
fakes, the actions are the real ones, and the assertions are decision-19's -
new output, source untouched, styled before presented, exports explicit.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import simple
from conftest import WORKING_CRS, FakeHost
from qgis_sdk import describe_plugin
from qgis_sdk.models import (
    QgisSdkAlgorithmRejectedError,
    QgisSdkExportRefusedError,
    QgisSdkUnsupportedCapabilityError,
)
from simple.plugin import EXPORT_DIRECTORY_KEY, SimplePlugin
from simple.workflow import LocalGisWorkflow


def test_the_plugin_declares_the_workflow_and_nothing_else() -> None:
    description = describe_plugin(SimplePlugin)

    assert sorted(a.id for a in description.actions) == [
        "buffer",
        "choose_export_directory",
        "export_layer",
        "open_fixture",
        "selected_features",
    ]


def test_class_factory_starts_and_unloads_without_a_host() -> None:
    plugin = simple.classFactory(None)
    plugin.initGui()
    try:
        assert plugin.runtime.state.value == "running"
        with pytest.raises(QgisSdkUnsupportedCapabilityError):
            plugin.runtime.actions["open_fixture"]()
    finally:
        plugin.unload()
    assert plugin.runtime.state.value == "stopped"


def test_open_fixture_presents_the_bundled_points(fake_host: FakeHost) -> None:
    info = fake_host.runtime.actions["open_fixture"]()

    assert info.name == "points"
    assert info.geometry_type == "point"
    assert fake_host.project.layer_ids() == (info.id,)


def test_selected_features_reads_what_the_host_selected(fake_host: FakeHost) -> None:
    info = fake_host.runtime.actions["open_fixture"]()
    fake_host.layers.select(info.id, (3, 1))

    assert fake_host.runtime.actions["selected_features"](info.id) == [1, 3]


def test_buffer_creates_a_styled_new_layer_and_keeps_the_source(
    fake_host: FakeHost,
) -> None:
    source = fake_host.runtime.actions["open_fixture"]()

    output = fake_host.runtime.actions["buffer"](source.id, 500.0, WORKING_CRS)

    assert output.id != source.id
    assert output.geometry_type == "polygon"
    assert fake_host.styles.applied(output.id) == (LocalGisWorkflow.OUTPUT_STYLE,)
    assert fake_host.project.layer_ids() == (source.id, output.id)
    assert fake_host.layers.layer(source.id) == source


def test_buffer_without_a_working_crs_changes_nothing(fake_host: FakeHost) -> None:
    source = fake_host.runtime.actions["open_fixture"]()

    with pytest.raises(QgisSdkAlgorithmRejectedError):
        fake_host.runtime.actions["buffer"](source.id, 500.0, "")

    assert fake_host.project.layer_ids() == (source.id,)


def test_export_writes_into_the_chosen_directory(
    fake_host: FakeHost, tmp_path: Path
) -> None:
    exports = tmp_path / "exports"
    exports.mkdir()
    fake_host.settings.set(EXPORT_DIRECTORY_KEY, str(exports))
    source = fake_host.runtime.actions["open_fixture"]()

    export = fake_host.runtime.actions["export_layer"](source.id, "points.geojson")

    assert export.path == str(exports / "points.geojson")
    assert (exports / "points.geojson").is_file()


def test_export_without_a_chosen_directory_is_refused(fake_host: FakeHost) -> None:
    source = fake_host.runtime.actions["open_fixture"]()

    with pytest.raises(QgisSdkExportRefusedError) as error:
        fake_host.runtime.actions["export_layer"](source.id, "points.geojson")

    assert any(EXPORT_DIRECTORY_KEY in reason for reason in error.value.reasons)


@pytest.mark.parametrize("name", ["../points.geojson", "sub/points.geojson", ""])
def test_a_file_name_that_is_a_path_is_refused(
    fake_host: FakeHost, tmp_path: Path, name: str
) -> None:
    fake_host.settings.set(EXPORT_DIRECTORY_KEY, str(tmp_path))
    source = fake_host.runtime.actions["open_fixture"]()

    with pytest.raises(QgisSdkExportRefusedError) as error:
        fake_host.runtime.actions["export_layer"](source.id, name)

    assert any("bare file name" in reason for reason in error.value.reasons)
    assert list(tmp_path.iterdir()) == []


def test_choosing_a_directory_needs_the_desktop(fake_host: FakeHost) -> None:
    with pytest.raises(QgisSdkUnsupportedCapabilityError):
        fake_host.runtime.actions["choose_export_directory"]()

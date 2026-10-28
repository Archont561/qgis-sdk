"""Contract: reading layers and selections through the injected service."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import conftest
import pytest
from qgis_sdk import exports
from qgis_sdk.models import (
    QgisSdkExportFailedError,
    QgisSdkExportRefusedError,
    QgisSdkLayerNotFoundError,
    VectorExport,
)

if TYPE_CHECKING:
    Services = conftest.Services


def test_open_vector_describes_the_layer_it_loaded(services: Services) -> None:
    info = services.layers.open_vector(services.dataset)

    assert info.id, "an opened layer must carry a stable identifier"
    assert info.name == conftest.FIXTURE_NAME
    assert info.geometry_type == conftest.FIXTURE_GEOMETRY
    assert info.field_names == conftest.FIXTURE_FIELDS
    assert info.crs == conftest.FIXTURE_CRS


def test_opened_layer_is_listed_and_looked_up_by_id(services: Services) -> None:
    info = services.layers.open_vector(services.dataset)

    assert info in services.layers.list_layers()
    assert services.layers.layer(info.id) == info


def test_unknown_layer_identifier_is_reported(services: Services) -> None:
    with pytest.raises(QgisSdkLayerNotFoundError) as error:
        services.layers.layer("no-such-layer")

    assert error.value.identifier == "no-such-layer"


def test_unreadable_dataset_is_reported_as_a_missing_layer(
    services: Services,
) -> None:
    absent = services.dataset.with_name("absent.geojson")

    with pytest.raises(QgisSdkLayerNotFoundError) as error:
        services.layers.open_vector(absent)

    assert "absent.geojson" in error.value.identifier


def test_selection_reports_the_selected_feature_ids(services: Services) -> None:
    info = services.layers.open_vector(services.dataset)
    services.select(info.id, (3, 1))

    assert sorted(services.layers.selection(info.id)) == [1, 3]


def test_layer_without_a_selection_reports_an_empty_selection(
    services: Services,
) -> None:
    info = services.layers.open_vector(services.dataset)

    assert services.layers.selection(info.id) == ()


def test_selection_of_an_unknown_layer_is_refused(services: Services) -> None:
    with pytest.raises(QgisSdkLayerNotFoundError):
        services.layers.selection("no-such-layer")


# --- explicit export (decision-19: permanent results are an explicit act) ---


def _register_fake_source(services: Services, source: Path) -> None:
    register = getattr(services.layers, "register", None)
    if register is not None:
        register(
            source,
            name="source",
            geometry_type=conftest.FIXTURE_GEOMETRY,
            field_names=conftest.FIXTURE_FIELDS,
            crs=conftest.FIXTURE_CRS,
        )


def test_export_writes_the_named_destination_and_describes_it(
    services: Services, tmp_path: Path
) -> None:
    info = services.layers.open_vector(services.dataset)
    destination = tmp_path / "exported.geojson"

    export = services.layers.export_vector(info.id, destination)

    assert export == VectorExport(path=str(destination), driver="GeoJSON")
    assert destination.is_file()
    assert destination.stat().st_size > 0
    # Nothing but the destination is left behind: no staging directory survives.
    assert sorted(p.name for p in tmp_path.iterdir()) == ["exported.geojson"]


def test_export_names_the_driver_from_the_destination_suffix(
    services: Services, tmp_path: Path
) -> None:
    info = services.layers.open_vector(services.dataset)

    export = services.layers.export_vector(info.id, tmp_path / "exported.gpkg")

    assert export.driver == "GPKG"
    assert Path(export.path).is_file()


def test_export_leaves_the_source_dataset_untouched(
    services: Services, tmp_path: Path
) -> None:
    before = services.dataset.read_bytes()
    info = services.layers.open_vector(services.dataset)

    services.layers.export_vector(info.id, tmp_path / "exported.geojson")

    assert services.dataset.read_bytes() == before


@pytest.mark.parametrize("relative_destination", [False, True])
def test_export_refuses_to_replace_its_source_even_with_overwrite(
    services: Services,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    relative_destination: bool,
) -> None:
    source = tmp_path / "source.geojson"
    source.write_bytes(services.dataset.read_bytes())
    _register_fake_source(services, source)
    info = services.layers.open_vector(source)
    original = source.read_bytes()
    inode = source.stat().st_ino
    monkeypatch.chdir(tmp_path)
    destination = Path(source.name) if relative_destination else source

    with pytest.raises(QgisSdkExportRefusedError, match="source"):
        services.layers.export_vector(info.id, destination, overwrite=True)

    assert source.read_bytes() == original
    assert source.stat().st_ino == inode
    assert sorted(p.name for p in tmp_path.iterdir()) == ["source.geojson"]


def test_export_from_a_stable_source_symlink_to_an_unrelated_destination(
    services: Services, tmp_path: Path
) -> None:
    dataset = tmp_path / "dataset.geojson"
    dataset.write_bytes(services.dataset.read_bytes())
    source = tmp_path / "source.geojson"
    try:
        source.symlink_to(dataset)
    except (OSError, NotImplementedError) as error:
        pytest.skip(f"symbolic links unavailable: {error}")
    _register_fake_source(services, source)
    info = services.layers.open_vector(source)
    original = dataset.read_bytes()
    destination = tmp_path / "output.geojson"

    result = services.layers.export_vector(info.id, destination)

    assert Path(result.path) == destination
    assert destination.is_file()
    assert dataset.read_bytes() == original
    assert source.is_symlink()


def test_export_refuses_a_retargeted_source_symlink(
    services: Services, tmp_path: Path
) -> None:
    first = tmp_path / "first.geojson"
    second = tmp_path / "second.geojson"
    first.write_bytes(services.dataset.read_bytes())
    second.write_bytes(services.dataset.read_bytes())
    source = tmp_path / "source.geojson"
    try:
        source.symlink_to(first)
    except (OSError, NotImplementedError) as error:
        pytest.skip(f"symbolic links unavailable: {error}")
    _register_fake_source(services, source)
    info = services.layers.open_vector(source)
    source.unlink()
    source.symlink_to(second)
    before = second.read_bytes()
    inode = second.stat().st_ino

    with pytest.raises(QgisSdkExportRefusedError, match="source"):
        services.layers.export_vector(info.id, second, overwrite=True)

    assert second.read_bytes() == before
    assert second.stat().st_ino == inode
    assert source.is_symlink()


def test_export_rechecks_a_retargeted_source_symlink_before_commit(
    services: Services, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = tmp_path / "first.geojson"
    second = tmp_path / "second.geojson"
    first.write_bytes(services.dataset.read_bytes())
    second.write_bytes(services.dataset.read_bytes())
    source = tmp_path / "source.geojson"
    try:
        source.symlink_to(first)
    except (OSError, NotImplementedError) as error:
        pytest.skip(f"symbolic links unavailable: {error}")
    _register_fake_source(services, source)
    info = services.layers.open_vector(source)
    before = second.read_bytes()
    inode = second.stat().st_ino
    run_export = exports.run_export

    def retarget_during_write(plan: exports.ExportPlan, write: object) -> None:
        def write_then_retarget(partial: Path) -> None:
            partial.write_text("new contents", encoding="utf-8")
            source.unlink()
            source.symlink_to(second)

        run_export(plan, write_then_retarget)

    monkeypatch.setattr(exports, "run_export", retarget_during_write)
    with pytest.raises(QgisSdkExportRefusedError, match="source"):
        services.layers.export_vector(info.id, second, overwrite=True)

    assert second.read_bytes() == before
    assert second.stat().st_ino == inode
    assert source.is_symlink()
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "first.geojson",
        "second.geojson",
        "source.geojson",
    ]


def test_export_refuses_a_hard_link_to_its_source(
    services: Services, tmp_path: Path
) -> None:
    source = tmp_path / "source.geojson"
    source.write_bytes(services.dataset.read_bytes())
    alias = tmp_path / "alias.geojson"
    alias.hardlink_to(source)
    _register_fake_source(services, source)
    info = services.layers.open_vector(source)
    original = source.read_bytes()
    inode = source.stat().st_ino

    with pytest.raises(QgisSdkExportRefusedError, match="source"):
        services.layers.export_vector(info.id, alias, overwrite=True)

    assert source.read_bytes() == alias.read_bytes() == original
    assert source.stat().st_ino == alias.stat().st_ino == inode


def test_export_refuses_when_the_opened_source_cannot_be_verified(
    services: Services, tmp_path: Path
) -> None:
    source = tmp_path / "source.geojson"
    source.write_bytes(services.dataset.read_bytes())
    _register_fake_source(services, source)
    info = services.layers.open_vector(source)
    source.unlink()
    destination = tmp_path / "output.geojson"

    with pytest.raises(QgisSdkExportRefusedError, match="source"):
        services.layers.export_vector(info.id, destination)

    assert not destination.exists()
    assert not list(tmp_path.iterdir())


def test_export_refuses_when_the_source_file_was_replaced(
    services: Services, tmp_path: Path
) -> None:
    source = tmp_path / "source.geojson"
    source.write_bytes(services.dataset.read_bytes())
    _register_fake_source(services, source)
    info = services.layers.open_vector(source)
    replacement = tmp_path / "replacement.geojson"
    replacement.write_bytes(services.dataset.read_bytes())
    replacement.replace(source)
    destination = tmp_path / "output.geojson"

    with pytest.raises(QgisSdkExportRefusedError, match="source"):
        services.layers.export_vector(info.id, destination)

    assert not destination.exists()


def test_export_remembers_a_relative_source_after_working_directory_changes(
    services: Services, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.geojson"
    source.write_bytes(services.dataset.read_bytes())
    monkeypatch.chdir(tmp_path)
    _register_fake_source(services, Path("source.geojson"))
    info = services.layers.open_vector(Path("source.geojson"))
    monkeypatch.chdir(tmp_path.parent)
    before = source.read_bytes()

    with pytest.raises(QgisSdkExportRefusedError, match="source"):
        services.layers.export_vector(info.id, source, overwrite=True)

    assert source.read_bytes() == before


def test_export_refuses_when_a_relative_source_resolves_to_a_different_file(
    services: Services, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    for directory in (first, second):
        (directory / "source.geojson").write_bytes(services.dataset.read_bytes())
    monkeypatch.chdir(first)
    source = Path("source.geojson")
    _register_fake_source(services, source)
    info = services.layers.open_vector(source)
    monkeypatch.chdir(second)
    destination = second / source
    before = destination.read_bytes()
    inode = destination.stat().st_ino

    with pytest.raises(QgisSdkExportRefusedError, match="source"):
        services.layers.export_vector(info.id, destination, overwrite=True)

    assert destination.read_bytes() == before
    assert destination.stat().st_ino == inode


def test_export_rechecks_source_alias_before_committing(
    services: Services, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.geojson"
    source.write_bytes(services.dataset.read_bytes())
    _register_fake_source(services, source)
    info = services.layers.open_vector(source)
    destination = tmp_path / "output.geojson"
    original = source.read_bytes()
    run_export = exports.run_export

    def create_alias_during_write(plan: exports.ExportPlan, write: object) -> None:
        def write_then_alias(partial: Path) -> None:
            partial.write_text("new contents", encoding="utf-8")
            destination.hardlink_to(source)

        run_export(plan, write_then_alias)

    monkeypatch.setattr(exports, "run_export", create_alias_during_write)
    with pytest.raises(QgisSdkExportRefusedError, match="source"):
        services.layers.export_vector(info.id, destination, overwrite=True)

    assert destination.samefile(source)
    assert source.read_bytes() == original
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "output.geojson",
        "source.geojson",
    ]


def test_export_refuses_to_replace_a_geopackage_container(
    services: Services, tmp_path: Path
) -> None:
    source = tmp_path / "source.gpkg"
    original_layer = services.layers.open_vector(services.dataset)
    services.layers.export_vector(original_layer.id, source)
    register = getattr(services.layers, "register", None)
    if register is not None:
        layer_name = "source"
    else:
        import sqlite3

        with sqlite3.connect(source) as db:
            layer_name = db.execute("SELECT table_name FROM gpkg_contents").fetchone()[
                0
            ]
    uri = Path(f"{source}|layername={layer_name}")
    if register is not None:
        register(
            uri,
            name="source",
            geometry_type=conftest.FIXTURE_GEOMETRY,
            field_names=conftest.FIXTURE_FIELDS,
            crs=conftest.FIXTURE_CRS,
            dataset_path=source,
        )
    info = services.layers.open_vector(uri)
    before = source.read_bytes()
    inode = source.stat().st_ino

    with pytest.raises(QgisSdkExportRefusedError, match="source"):
        services.layers.export_vector(info.id, source, overwrite=True)

    assert source.read_bytes() == before
    assert source.stat().st_ino == inode


def test_export_refuses_a_symbolic_link_to_its_source(
    services: Services, tmp_path: Path
) -> None:
    source = tmp_path / "source.geojson"
    source.write_bytes(services.dataset.read_bytes())
    alias = tmp_path / "alias.geojson"
    try:
        alias.symlink_to(source)
    except (OSError, NotImplementedError) as error:
        pytest.skip(f"symbolic links unavailable: {error}")
    _register_fake_source(services, source)
    info = services.layers.open_vector(source)
    original = source.read_bytes()

    with pytest.raises(QgisSdkExportRefusedError, match="source"):
        services.layers.export_vector(info.id, alias, overwrite=True)

    assert alias.is_symlink()
    assert source.read_bytes() == original


def test_export_does_not_overwrite_a_file_created_during_writing(
    services: Services, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    info = services.layers.open_vector(services.dataset)
    destination = tmp_path / "output.geojson"
    run_export = exports.run_export

    def create_destination(plan: exports.ExportPlan, write: object) -> None:
        def write_then_create(partial: Path) -> None:
            partial.write_text("new export", encoding="utf-8")
            destination.write_text("created by another process", encoding="utf-8")

        run_export(plan, write_then_create)

    monkeypatch.setattr(exports, "run_export", create_destination)
    with pytest.raises(QgisSdkExportRefusedError, match="overwrite"):
        services.layers.export_vector(info.id, destination)

    assert destination.read_text(encoding="utf-8") == "created by another process"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["output.geojson"]


def test_export_refuses_an_existing_destination_without_overwrite(
    services: Services, tmp_path: Path
) -> None:
    info = services.layers.open_vector(services.dataset)
    destination = tmp_path / "exported.geojson"
    destination.write_text("keep me", encoding="utf-8")

    with pytest.raises(QgisSdkExportRefusedError) as error:
        services.layers.export_vector(info.id, destination)

    assert error.value.destination == str(destination)
    assert any("overwrite" in reason for reason in error.value.reasons)
    assert destination.read_text(encoding="utf-8") == "keep me"


def test_export_overwrites_only_when_told_to(
    services: Services, tmp_path: Path
) -> None:
    info = services.layers.open_vector(services.dataset)
    destination = tmp_path / "exported.geojson"
    destination.write_text("stale", encoding="utf-8")

    services.layers.export_vector(info.id, destination, overwrite=True)

    assert destination.read_text(encoding="utf-8") != "stale"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["exported.geojson"]


def test_export_refuses_an_unknown_format_before_touching_disk(
    services: Services, tmp_path: Path
) -> None:
    info = services.layers.open_vector(services.dataset)

    with pytest.raises(QgisSdkExportRefusedError) as error:
        services.layers.export_vector(info.id, tmp_path / "exported.shp")

    assert any(".shp" in reason for reason in error.value.reasons)
    assert list(tmp_path.iterdir()) == []


def test_export_refuses_a_destination_whose_directory_is_missing(
    services: Services, tmp_path: Path
) -> None:
    info = services.layers.open_vector(services.dataset)

    with pytest.raises(QgisSdkExportRefusedError) as error:
        services.layers.export_vector(info.id, tmp_path / "missing" / "out.geojson")

    assert any("directory" in reason for reason in error.value.reasons)
    assert list(tmp_path.iterdir()) == []


def test_export_of_an_unknown_layer_is_refused(
    services: Services, tmp_path: Path
) -> None:
    with pytest.raises(QgisSdkLayerNotFoundError):
        services.layers.export_vector("no-such-layer", tmp_path / "out.geojson")

    assert list(tmp_path.iterdir()) == []


def test_a_failed_export_leaves_no_partial_file(
    services: Services, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Whatever backend writes, a failure mid-write removes the staged file.

    The writer is the backend's own (OGR for the native adapter, a copy for the
    fake); the seam under test is ``exports.run_export``, which every backend
    hands its writer to. Wrapping it with a writer that leaves half a file and
    raises is how both backends are held to the same cleanup rule.
    """
    info = services.layers.open_vector(services.dataset)
    destination = tmp_path / "exported.geojson"
    real_run_export = exports.run_export

    def half_then_fail(partial: Path) -> None:
        partial.write_text("{partial", encoding="utf-8")
        raise OSError("disk full")

    monkeypatch.setattr(
        exports, "run_export", lambda plan, write: real_run_export(plan, half_then_fail)
    )

    with pytest.raises(QgisSdkExportFailedError) as error:
        services.layers.export_vector(info.id, destination)

    assert error.value.destination == str(destination)
    assert "disk full" in error.value.detail
    assert list(tmp_path.iterdir()) == []

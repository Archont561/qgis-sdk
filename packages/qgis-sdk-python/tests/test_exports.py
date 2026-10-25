"""The export policy every backend shares (decision-19): pure, no QGIS."""

from __future__ import annotations

from pathlib import Path

import pytest
from qgis_sdk import exports
from qgis_sdk.models import QgisSdkExportFailedError, QgisSdkExportRefusedError


def test_plan_resolves_the_driver_from_the_suffix(tmp_path: Path) -> None:
    plan = exports.plan_export(tmp_path / "out.geojson", overwrite=False)

    assert plan.destination == tmp_path / "out.geojson"
    assert plan.driver == "GeoJSON"
    assert exports.plan_export(tmp_path / "out.GPKG", overwrite=False).driver == "GPKG"


def test_plan_reports_every_reason_at_once(tmp_path: Path) -> None:
    destination = tmp_path / "missing" / "out.shp"

    with pytest.raises(QgisSdkExportRefusedError) as error:
        exports.plan_export(destination, overwrite=False)

    assert error.value.destination == str(destination)
    assert len(error.value.reasons) == 2
    assert error.value.code == "export_refused"
    assert "out.shp" not in str(error.value).replace(str(destination), "")


def test_plan_refuses_a_directory_as_destination(tmp_path: Path) -> None:
    with pytest.raises(QgisSdkExportRefusedError) as error:
        exports.plan_export(tmp_path, overwrite=True)

    assert any("directory" in reason for reason in error.value.reasons)


def test_run_export_commits_the_staged_file_atomically(tmp_path: Path) -> None:
    plan = exports.plan_export(tmp_path / "out.geojson", overwrite=False)
    seen: list[Path] = []

    def write(partial: Path) -> None:
        seen.append(partial)
        assert partial.parent.parent == tmp_path, "staging sits beside the destination"
        assert partial.name == "out.geojson", "the writer sees the final file name"
        partial.write_text("{}", encoding="utf-8")

    exports.run_export(plan, write)

    assert (tmp_path / "out.geojson").read_text(encoding="utf-8") == "{}"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["out.geojson"]
    assert not seen[0].parent.exists()


def test_run_export_removes_the_staging_directory_on_failure(tmp_path: Path) -> None:
    plan = exports.plan_export(tmp_path / "out.geojson", overwrite=False)

    def write(partial: Path) -> None:
        partial.write_text("{", encoding="utf-8")
        (partial.parent / "out.geojson-journal").write_text("", encoding="utf-8")
        raise RuntimeError("writer exploded")

    with pytest.raises(QgisSdkExportFailedError) as error:
        exports.run_export(plan, write)

    assert error.value.code == "export_failed"
    assert error.value.detail == "writer exploded"
    assert list(tmp_path.iterdir()) == []


def test_a_writer_that_produces_nothing_is_a_failure(tmp_path: Path) -> None:
    plan = exports.plan_export(tmp_path / "out.geojson", overwrite=False)

    with pytest.raises(QgisSdkExportFailedError) as error:
        exports.run_export(plan, lambda partial: None)

    assert "no file" in error.value.detail
    assert list(tmp_path.iterdir()) == []


def test_an_sdk_error_from_the_writer_passes_through_unwrapped(
    tmp_path: Path,
) -> None:
    plan = exports.plan_export(tmp_path / "out.geojson", overwrite=False)

    def write(partial: Path) -> None:
        raise QgisSdkExportFailedError(str(plan.destination), "OGR said no")

    with pytest.raises(QgisSdkExportFailedError) as error:
        exports.run_export(plan, write)

    assert error.value.detail == "OGR said no"
    assert list(tmp_path.iterdir()) == []

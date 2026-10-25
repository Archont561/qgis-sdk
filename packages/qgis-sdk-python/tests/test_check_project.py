"""``check_project``: metadata, configuration and the file walk (TASK-16)."""

from __future__ import annotations

from pathlib import Path

import pytest
from qgis_sdk_tools.check import QgisSdkCheckError, check_project
from qgis_sdk_tools.scaffold import ScaffoldOptions, write_scaffold

METADATA = """[general]
name=Field Tools
description=Field tools.
about=About.
version=0.1.0
qgisMinimumVersion=3.40
author=Jane
email=jane@example.org
"""


def project(tmp_path: Path, *, metadata: str | None = METADATA) -> Path:
    root = tmp_path / "field_tools"
    package = root / "field_tools"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("from .plugin import classFactory\n")
    (package / "plugin.py").write_text("import os\n")
    if metadata is not None:
        (package / "metadata.txt").write_text(metadata)
    return root


def codes(report) -> list[str]:
    return [d.rule for d in report.diagnostics]


def test_a_project_from_qgis_sdk_new_passes_check_clean(tmp_path: Path) -> None:
    target = tmp_path / "survey_helper"
    write_scaffold(ScaffoldOptions.resolve(plugin="survey_helper"), target)

    report = check_project(target)

    assert report.diagnostics == (), [d.render() for d in report.diagnostics]
    assert report.ok
    assert report.files_checked >= 3


def test_a_clean_hand_written_project_passes(tmp_path: Path) -> None:
    report = check_project(project(tmp_path))

    assert report.ok
    assert report.root == (tmp_path / "field_tools").resolve()
    assert report.files_checked == 2


def test_import_diagnostics_carry_paths_relative_to_the_root(tmp_path: Path) -> None:
    root = project(tmp_path)
    (root / "field_tools" / "dialog.py").write_text(
        "from qgis.PyQt.QtWidgets import QDialog\n"
    )

    report = check_project(root)

    (found,) = report.diagnostics
    assert found.path == Path("field_tools/dialog.py")
    assert not report.ok


def test_a_missing_metadata_file_is_meta001(tmp_path: Path) -> None:
    report = check_project(project(tmp_path, metadata=None))

    (found,) = report.diagnostics
    assert found.rule == "META001"
    assert found.path == Path("field_tools/metadata.txt")
    assert "metadata.txt" in found.message


def test_a_missing_required_key_is_meta002_per_key(tmp_path: Path) -> None:
    short = "[general]\nname=Field Tools\nversion=0.1.0\n"
    report = check_project(project(tmp_path, metadata=short))

    assert codes(report) == ["META002"] * 5
    missing = sorted(d.message.split("`")[1] for d in report.diagnostics)
    assert missing == ["about", "author", "description", "email", "qgisMinimumVersion"]
    assert all(d.path == Path("field_tools/metadata.txt") for d in report.diagnostics)


def test_a_metadata_file_without_a_general_section_is_meta003(tmp_path: Path) -> None:
    report = check_project(project(tmp_path, metadata="name=Field Tools\n"))

    assert codes(report) == ["META003"]


def test_a_root_without_a_plugin_package_is_project001(tmp_path: Path) -> None:
    root = tmp_path / "empty"
    (root / "tests").mkdir(parents=True)
    (root / "tests" / "test_x.py").write_text("")

    report = check_project(root)

    assert codes(report) == ["PROJECT001"]
    assert report.diagnostics[0].path == Path(".")


def test_a_root_that_is_not_a_directory_is_refused(tmp_path: Path) -> None:
    with pytest.raises(QgisSdkCheckError, match="not a directory"):
        check_project(tmp_path / "missing")


def test_tooling_and_dependency_directories_are_not_checked(tmp_path: Path) -> None:
    root = project(tmp_path)
    for folder in (
        ".venv/lib",
        "node_modules/x",
        ".pixi/envs",
        "build",
        "dist",
        "__pycache__",
        ".git",
    ):
        path = root / folder
        path.mkdir(parents=True)
        (path / "native.py").write_text("import qgis.core\n")

    report = check_project(root)

    assert report.ok
    assert report.files_checked == 2


def test_native_modules_come_from_pyproject_and_from_the_caller(tmp_path: Path) -> None:
    root = project(tmp_path)
    (root / "field_tools" / "views.py").write_text(
        "from qgis.gui import QgisInterface\n"
    )
    (root / "field_tools" / "native.py").write_text("import qgis.core\n")
    (root / "pyproject.toml").write_text(
        '[tool.qgis-sdk.check]\nnative-modules = ["field_tools.native"]\n'
    )

    assert [d.path for d in check_project(root).diagnostics] == [
        Path("field_tools/views.py")
    ]
    assert check_project(root, native_modules=("field_tools.views",)).ok


def test_a_malformed_pyproject_section_is_config001(tmp_path: Path) -> None:
    root = project(tmp_path)
    (root / "pyproject.toml").write_text(
        '[tool.qgis-sdk.check]\nnative-modules = "field_tools.native"\n'
    )

    report = check_project(root)

    assert codes(report) == ["CONFIG001"]
    assert report.diagnostics[0].path == Path("pyproject.toml")


def test_the_report_serializes_for_machines(tmp_path: Path) -> None:
    root = project(tmp_path, metadata=None)

    data = check_project(root).to_json()

    assert data["ok"] is False
    assert data["files_checked"] == 2
    assert data["root"] == str(root.resolve())
    (entry,) = data["diagnostics"]
    assert entry == {
        "rule": "META001",
        "severity": "error",
        "path": "field_tools/metadata.txt",
        "line": 0,
        "column": 0,
        "message": entry["message"],
        "remediation": entry["remediation"],
    }

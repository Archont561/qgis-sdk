"""``check_project``: project shape, host artifacts, configuration and the file walk.

TASK-16 wrote the walk; TASK-64 (decision-43) moved the metadata rules onto
``pyproject.toml``: a hand-written ``metadata.txt`` or ``classFactory`` is
the finding now, and the values QGIS needs are read from ``[project]`` and
``[tool.qgis-sdk]``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from qgis_sdk_tools.check import QgisSdkCheckError, check_project
from qgis_sdk_tools.scaffold import ScaffoldOptions, write_scaffold

PYPROJECT = """[project]
name = "field-tools"
version = "0.1.0"
description = "Field tools."
authors = [{ name = "Jane", email = "jane@example.org" }]
dependencies = ["qgis-sdk-runtime>=0.1,<99"]

[tool.qgis-sdk]
plugin = "field_tools.plugin:FieldTools"
qgis-minimum-version = "3.40"
"""


def project(tmp_path: Path, *, pyproject: str | None = PYPROJECT) -> Path:
    root = tmp_path / "field_tools"
    package = root / "field_tools"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "plugin.py").write_text("import os\n")
    if pyproject is not None:
        (root / "pyproject.toml").write_text(pyproject)
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


def test_a_hand_written_metadata_file_is_meta001(tmp_path: Path) -> None:
    root = project(tmp_path)
    (root / "field_tools" / "metadata.txt").write_text("[general]\nname=X\n")

    report = check_project(root)

    (found,) = report.diagnostics
    assert found.rule == "META001"
    assert found.path == Path("field_tools/metadata.txt")
    assert "generate it from pyproject.toml" in found.message
    assert "[tool.qgis-sdk.metadata]" in found.remediation


@pytest.mark.parametrize(
    "binding",
    [
        "from .plugin import classFactory\n",
        "from .plugin import make as classFactory\n",
        "def classFactory(iface):\n    return None\n",
        "classFactory = None\n",
    ],
)
def test_a_hand_written_class_factory_is_entry002(tmp_path: Path, binding: str) -> None:
    root = project(tmp_path)
    (root / "field_tools" / "__init__.py").write_text('"""Doc."""\n\n' + binding)

    report = check_project(root)

    (found,) = report.diagnostics
    assert found.rule == "ENTRY002"
    assert found.path == Path("field_tools/__init__.py")
    assert found.line == 3
    assert "host()" in found.message


def test_a_legacy_project_gets_one_finding_per_leftover(tmp_path: Path) -> None:
    """A 0.5.0 scaffold: no [tool.qgis-sdk] plugin, metadata.txt, classFactory."""
    root = project(tmp_path, pyproject=None)
    (root / "field_tools" / "metadata.txt").write_text("[general]\nname=X\n")
    (root / "field_tools" / "__init__.py").write_text(
        "from .plugin import classFactory\n"
    )

    report = check_project(root)

    assert sorted(codes(report)) == ["ENTRY002", "META001", "PROJECT002"]
    missing = next(d for d in report.diagnostics if d.rule == "PROJECT002")
    assert missing.path == Path("pyproject.toml")
    assert "[tool.qgis-sdk] plugin" in missing.remediation


def test_a_missing_required_value_is_meta002_per_key(tmp_path: Path) -> None:
    short = """[project]
name = "field-tools"
version = "0.1.0"
dependencies = ["qgis-sdk-runtime>=0.1,<99"]

[tool.qgis-sdk]
plugin = "field_tools.plugin:FieldTools"
"""
    report = check_project(project(tmp_path, pyproject=short))

    assert codes(report) == ["META002"] * 3
    missing = sorted(d.message.split("`")[1] for d in report.diagnostics)
    assert missing == ["author", "description", "qgisMinimumVersion"]
    assert all(d.path == Path("pyproject.toml") for d in report.diagnostics)


def test_an_author_without_an_email_is_meta002_for_the_email(tmp_path: Path) -> None:
    text = PYPROJECT.replace(', email = "jane@example.org"', "")
    report = check_project(project(tmp_path, pyproject=text))

    assert codes(report) == ["META002"]
    assert "`email`" in report.diagnostics[0].message


@pytest.mark.parametrize(
    ("extra", "fragment"),
    [
        ('plugin = "field_tools.plugin"\n', "pkg.module:Class"),
        ("experimental = 'yes'\n", "experimental must be true or false"),
        ('[tool.qgis-sdk.web]\nplacement = "window"\n', "placement must be"),
        ('[tool.qgis-sdk.web]\ngrants = "layers.list"\n', "grants must be a list"),
        ('[tool.qgis-sdk.metadata]\nversion = "2"\n', "derived from [project]"),
        ("[tool.qgis-sdk.metadata]\ntags = [1]\n", "tags must be a string"),
    ],
)
def test_a_malformed_tool_table_is_config001(
    tmp_path: Path, extra: str, fragment: str
) -> None:
    text = PYPROJECT.replace('plugin = "field_tools.plugin:FieldTools"\n', "") + extra
    if "plugin =" not in extra:
        text = text.replace(
            "[tool.qgis-sdk]\n",
            '[tool.qgis-sdk]\nplugin = "field_tools.plugin:FieldTools"\n',
        )

    report = check_project(project(tmp_path, pyproject=text))

    assert "CONFIG001" in codes(report)
    assert any(fragment in d.message for d in report.diagnostics), codes(report)


def test_an_unknown_grant_is_grant001(tmp_path: Path) -> None:
    text = (
        PYPROJECT
        + '\n[tool.qgis-sdk.web]\nplacement = "dock"\n'
        + 'grants = ["layers.read", "layers.list", "layers.nope"]\n'
    )

    report = check_project(project(tmp_path, pyproject=text))

    (found,) = report.diagnostics  # a grant and an id are both accepted
    assert found.rule == "GRANT001"
    assert "`layers.nope`" in found.message
    assert "layers.read" in found.remediation
    assert "layers.list" in found.remediation


def test_passthrough_metadata_and_a_page_are_accepted(tmp_path: Path) -> None:
    text = (
        PYPROJECT
        + '\n[tool.qgis-sdk.metadata]\nhomepage = "https://example.org"\ntags = "a, b"\n'
        + '\n[tool.qgis-sdk.web]\nplacement = "dock"\ngrants = ["layers.list"]\n'
    )

    assert check_project(project(tmp_path, pyproject=text)).diagnostics == ()


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
        PYPROJECT + '\n[tool.qgis-sdk.check]\nnative-modules = ["field_tools.native"]\n'
    )

    assert [d.path for d in check_project(root).diagnostics] == [
        Path("field_tools/views.py")
    ]
    assert check_project(root, native_modules=("field_tools.views",)).ok


def test_a_malformed_pyproject_section_is_config001(tmp_path: Path) -> None:
    root = project(tmp_path)
    (root / "pyproject.toml").write_text(
        PYPROJECT + '\n[tool.qgis-sdk.check]\nnative-modules = "field_tools.native"\n'
    )

    report = check_project(root)

    assert codes(report) == ["CONFIG001"]
    assert report.diagnostics[0].path == Path("pyproject.toml")


def test_the_report_serializes_for_machines(tmp_path: Path) -> None:
    root = project(tmp_path)
    (root / "field_tools" / "metadata.txt").write_text("[general]\nname=X\n")

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

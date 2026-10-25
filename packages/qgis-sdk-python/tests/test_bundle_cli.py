"""``qgis-sdk build``: argument parsing over ``build_plugin`` (decision-8)."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from qgis_sdk_tools.__main__ import app
from qgis_sdk_tools.scaffold import ScaffoldOptions, write_scaffold
from qgis_sdk_tools.testing import FakeCliRuntime
from typer.testing import CliRunner

runner = CliRunner()


def scaffolded(tmp_path: Path) -> Path:
    target = tmp_path / "survey_helper"
    write_scaffold(ScaffoldOptions.resolve(plugin="survey_helper"), target)
    return target


def test_build_writes_the_archive_and_says_where(tmp_path: Path) -> None:
    target = scaffolded(tmp_path)
    runtime = FakeCliRuntime(cwd=tmp_path)

    result = runner.invoke(app, ["build", "survey_helper"], obj=runtime)

    assert result.exit_code == 0, runtime.stderr + result.output
    archive = target / "dist" / "survey_helper-0.1.0.zip"
    assert archive.is_file()
    assert str(archive) in runtime.stdout
    assert "survey_helper 0.1.0" in runtime.stdout
    assert "runtime" in runtime.stdout
    assert runtime.processes == []  # no web UI: nothing to run
    assert runtime.stderr == ""


def test_build_defaults_to_the_working_directory_and_honours_out(
    tmp_path: Path,
) -> None:
    target = scaffolded(tmp_path)
    runtime = FakeCliRuntime(cwd=target)

    result = runner.invoke(app, ["build", "--out", "release"], obj=runtime)

    assert result.exit_code == 0, runtime.stderr + result.output
    assert (target / "release" / "survey_helper-0.1.0.zip").is_file()


def test_build_json_is_the_result_serialization(tmp_path: Path) -> None:
    scaffolded(tmp_path)
    runtime = FakeCliRuntime(cwd=tmp_path)

    result = runner.invoke(app, ["build", "survey_helper", "--json"], obj=runtime)

    assert result.exit_code == 0, runtime.stderr + result.output
    data = json.loads(runtime.stdout)
    assert data["plugin"] == "survey_helper"
    assert data["web"] == "none"
    assert data["report"]["ok"] is True
    with zipfile.ZipFile(data["archive"]) as zf:
        assert data["files"] == len(zf.namelist())


def test_build_prints_the_findings_and_fails_with_1(tmp_path: Path) -> None:
    target = scaffolded(tmp_path)
    (target / "survey_helper" / "__init__.py").write_text("", encoding="utf-8")
    (target / "survey_helper" / "extra.py").write_text("import requests\n")
    runtime = FakeCliRuntime(cwd=tmp_path)

    result = runner.invoke(app, ["build", "survey_helper"], obj=runtime)

    assert result.exit_code == 1
    lines = runtime.stdout.splitlines()
    assert any(
        line.startswith("survey_helper/__init__.py: ENTRY001 ") for line in lines
    )
    assert any(line.startswith("survey_helper/extra.py:1:1: DEP001 ") for line in lines)
    assert "build refused: 2 errors" in runtime.stderr
    assert not (target / "dist").exists()


def test_build_runs_the_web_build_through_the_runtime(tmp_path: Path) -> None:
    target = tmp_path / "web_tools"
    write_scaffold(
        ScaffoldOptions.resolve("web_tools", web="vanilla", package_manager="bun"),
        target,
    )
    (target / "web" / "bun.lock").write_text("", encoding="utf-8")
    (target / "web" / "node_modules").mkdir()

    def run_process(argv, cwd) -> int:
        (target / "web_tools" / "web").mkdir()
        (target / "web_tools" / "web" / "index.html").write_text("<html></html>")
        return 0

    runtime = FakeCliRuntime(cwd=target, run_process=run_process)

    result = runner.invoke(app, ["build"], obj=runtime)

    assert result.exit_code == 0, runtime.stderr + result.output
    assert runtime.processes == [(("bun", "run", "build"), target / "web")]
    assert "web: built" in runtime.stdout


def test_build_without_installed_web_dependencies_is_exit_2(tmp_path: Path) -> None:
    target = tmp_path / "web_tools"
    write_scaffold(ScaffoldOptions.resolve("web_tools", web="vanilla"), target)
    runtime = FakeCliRuntime(cwd=target)

    result = runner.invoke(app, ["build"], obj=runtime)

    assert result.exit_code == 2
    assert "npm install" in runtime.stderr
    assert runtime.processes == []


def test_build_outside_a_project_is_exit_2(tmp_path: Path) -> None:
    runtime = FakeCliRuntime(cwd=tmp_path)

    result = runner.invoke(app, ["build"], obj=runtime)

    assert result.exit_code == 2
    assert "no plugin package" in runtime.stderr

"""``qgis-sdk check``: the first command that receives its runtime (decision-34)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from qgis_sdk_tools.__main__ import app
from qgis_sdk_tools.cli import CliRuntime
from qgis_sdk_tools.scaffold import ScaffoldOptions, write_scaffold
from qgis_sdk_tools.testing import FakeCliRuntime
from typer.testing import CliRunner

runner = CliRunner()


def invoke(runtime: CliRuntime, *arguments: str):
    return runner.invoke(app, list(arguments), obj=runtime)


def scaffolded(tmp_path: Path) -> Path:
    target = tmp_path / "survey_helper"
    write_scaffold(ScaffoldOptions.resolve(plugin="survey_helper"), target)
    return target


def test_the_real_runtime_reads_the_process(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("QGIS_SDK_PROBE", "1")

    runtime = CliRuntime.for_process()

    assert runtime.cwd == Path.cwd()
    assert runtime.env["QGIS_SDK_PROBE"] == "1"
    assert runtime.env is os.environ
    assert runtime.out is sys.stdout
    assert runtime.err is sys.stderr
    assert runtime.resolve(Path("x")) == (tmp_path / "x").resolve()


def test_the_fake_runtime_captures_output_and_owns_the_environment(
    tmp_path: Path,
) -> None:
    runtime = FakeCliRuntime(cwd=tmp_path, env={"A": "1"})

    print("hello", file=runtime.out)
    print("oops", file=runtime.err)

    assert isinstance(runtime, CliRuntime)
    assert runtime.stdout == "hello\n"
    assert runtime.stderr == "oops\n"
    assert dict(runtime.env) == {"A": "1"}
    assert runtime.resolve(Path("x")) == (tmp_path / "x").resolve()


def test_check_passes_a_scaffolded_project_and_says_so(tmp_path: Path) -> None:
    target = scaffolded(tmp_path)
    runtime = FakeCliRuntime(cwd=tmp_path)

    result = invoke(runtime, "check", "survey_helper")

    assert result.exit_code == 0, runtime.stderr + result.output
    assert runtime.stdout.strip().endswith("no problems")
    assert str(target) not in runtime.stdout  # paths are root-relative
    assert runtime.stderr == ""


def test_check_defaults_to_the_runtimes_working_directory(tmp_path: Path) -> None:
    target = scaffolded(tmp_path)
    runtime = FakeCliRuntime(cwd=target)

    result = invoke(runtime, "check")

    assert result.exit_code == 0, runtime.stderr + result.output


def test_check_reports_each_problem_and_fails(tmp_path: Path) -> None:
    target = scaffolded(tmp_path)
    (target / "survey_helper" / "dialog.py").write_text(
        "from qgis.PyQt.QtWidgets import QDialog\n"
    )
    (target / "survey_helper" / "metadata.txt").unlink()
    runtime = FakeCliRuntime(cwd=tmp_path)

    result = invoke(runtime, "check", "survey_helper")

    assert result.exit_code == 1
    lines = runtime.stdout.splitlines()
    assert lines[0].startswith("survey_helper/dialog.py:1:1: QGIS001 ")
    assert lines[1].startswith("    ")  # the remediation, indented under it
    assert any(
        line.startswith("survey_helper/metadata.txt: META001 ") for line in lines
    )
    assert lines[-1].endswith("2 problems")
    assert runtime.stderr == ""


def test_check_json_is_the_report_serialization(tmp_path: Path) -> None:
    target = scaffolded(tmp_path)
    (target / "survey_helper" / "metadata.txt").unlink()
    runtime = FakeCliRuntime(cwd=tmp_path)

    result = invoke(runtime, "check", "survey_helper", "--json")

    assert result.exit_code == 1
    data = json.loads(runtime.stdout)
    assert data["ok"] is False
    assert [d["rule"] for d in data["diagnostics"]] == ["META001"]


def test_check_accepts_native_module_globs_on_the_command_line(tmp_path: Path) -> None:
    target = scaffolded(tmp_path)
    (target / "survey_helper" / "views.py").write_text("import qgis.gui\n")
    runtime = FakeCliRuntime(cwd=tmp_path)

    assert invoke(runtime, "check", "survey_helper").exit_code == 1
    assert (
        invoke(
            FakeCliRuntime(cwd=tmp_path),
            "check",
            "survey_helper",
            "--native",
            "survey_helper.views",
        ).exit_code
        == 0
    )


def test_check_refuses_a_path_that_is_not_a_project_on_stderr(tmp_path: Path) -> None:
    runtime = FakeCliRuntime(cwd=tmp_path)

    result = invoke(runtime, "check", "missing")

    assert result.exit_code == 2
    assert "not a directory" in runtime.stderr
    assert runtime.stdout == ""


def test_the_shell_gets_the_process_runtime_when_nobody_seeds_ctx_obj(
    tmp_path: Path, monkeypatch
) -> None:
    target = scaffolded(tmp_path)
    monkeypatch.chdir(target)

    result = runner.invoke(app, ["check"])

    assert result.exit_code == 0, result.output
    assert result.output.strip().endswith("no problems")

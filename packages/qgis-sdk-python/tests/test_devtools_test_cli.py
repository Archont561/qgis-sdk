"""``qgis-sdk test``: a thin runner that forwards arguments and exit codes."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from qgis_sdk_tools.__main__ import app
from qgis_sdk_tools.devtools.testrun import PLUGIN
from qgis_sdk_tools.pytest_plugin import TARGET_ENV
from qgis_sdk_tools.scaffold import ScaffoldOptions, write_scaffold
from qgis_sdk_tools.testing import FakeCliRuntime
from test_devtools_installs import make_prefix
from typer.testing import CliRunner

runner = CliRunner()


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "field_tools"
    write_scaffold(ScaffoldOptions.resolve("field_tools"), root)
    return root


def test_the_default_target_is_pure_and_pytest_arguments_pass_through(
    project: Path,
) -> None:
    runtime = FakeCliRuntime(project)

    result = runner.invoke(app, ["test", "--", "-q", "-k", "ping"], obj=runtime)

    assert result.exit_code == 0, runtime.stderr
    assert runtime.processes == [
        (
            (
                sys.executable,
                "-m",
                "pytest",
                "-p",
                PLUGIN,
                "-m",
                "not qgis and not desktop",
                "-q",
                "-k",
                "ping",
            ),
            project,
        )
    ]
    assert runtime.environments[0][TARGET_ENV] == "pure"
    assert runtime.stderr == "target pure: this interpreter, native imports refused\n"
    assert runtime.stdout == ""


def test_pytests_exit_code_is_the_commands_exit_code(project: Path) -> None:
    runtime = FakeCliRuntime(project, run_process=lambda argv, cwd: 5)

    result = runner.invoke(app, ["test"], obj=runtime)

    assert result.exit_code == 5


def test_pytest_options_need_no_separator(project: Path) -> None:
    runtime = FakeCliRuntime(project)

    result = runner.invoke(app, ["test", "-x", "-k", "ping", "tests"], obj=runtime)

    assert result.exit_code == 0, runtime.stderr
    assert runtime.processes[0][0][-4:] == ("-x", "-k", "ping", "tests")


def test_the_project_option_selects_the_root(project: Path, tmp_path: Path) -> None:
    runtime = FakeCliRuntime(tmp_path)

    result = runner.invoke(app, ["test", "--project", "field_tools"], obj=runtime)

    assert result.exit_code == 0, runtime.stderr
    assert runtime.processes[0][1] == project


def test_the_qgis_target_uses_the_configured_install(
    project: Path, tmp_path: Path
) -> None:
    prefix = make_prefix(tmp_path)
    runtime = FakeCliRuntime(project, {"HOME": "/h"})

    result = runner.invoke(
        app, ["test", "--target", "qgis", "--qgis-prefix", str(prefix)], obj=runtime
    )

    assert result.exit_code == 0, runtime.stderr
    argv, _cwd = runtime.processes[0]
    assert argv[0] == str(prefix.resolve() / "bin" / "python")
    assert argv[-2:] == ("-m", "qgis")
    env = runtime.environments[0]
    assert env is not None
    assert env["QGIS_PREFIX_PATH"] == str(prefix.resolve())
    assert env["HOME"] == "/h"
    assert "the --qgis-prefix option" in runtime.stderr


def test_a_missing_qgis_is_a_failure_with_the_places_looked(
    project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "prefix", str(tmp_path / "no-qgis"))
    runtime = FakeCliRuntime(project, {"PATH": ""})

    result = runner.invoke(app, ["test", "--target", "qgis"], obj=runtime)

    assert result.exit_code == 2
    assert runtime.processes == []
    assert "no QGIS install found" in runtime.stderr
    assert "--qgis-prefix" in runtime.stderr


def test_the_desktop_target_cleans_its_workspace_up(
    project: Path, tmp_path: Path
) -> None:
    prefix = make_prefix(tmp_path)
    seen: list[Path] = []

    def record(argv: tuple[str, ...], cwd: Path) -> int:
        probe = Path(argv[-1])
        seen.append(probe)
        assert probe.is_file()
        return 0

    runtime = FakeCliRuntime(project, run_process=record)

    result = runner.invoke(
        app,
        ["test", "--target", "desktop", "--qgis-prefix", str(prefix)],
        obj=runtime,
    )

    assert result.exit_code == 0, runtime.stderr
    assert seen and not seen[0].exists()
    assert not seen[0].parent.exists()
    assert "profile" in runtime.stderr


def test_a_missing_executable_is_reported_as_such(project: Path) -> None:
    runtime = FakeCliRuntime(project, run_process=lambda argv, cwd: 127)

    result = runner.invoke(app, ["test"], obj=runtime)

    assert result.exit_code == 127
    assert f"{sys.executable} was not found" in runtime.stderr


def test_the_web_target_runs_vitest_through_the_lockfiles_manager(
    project: Path,
) -> None:
    web = project / "web"
    web.mkdir()
    (web / "package.json").write_text("{}")
    (web / "bun.lock").write_text("")
    (web / "node_modules").mkdir()
    runtime = FakeCliRuntime(project)

    result = runner.invoke(app, ["test", "--target", "web", "--", "--run"], obj=runtime)

    assert result.exit_code == 0, runtime.stderr
    assert runtime.processes == [(("bun", "run", "test", "--run"), web)]


def test_an_unknown_target_is_exit_code_2(project: Path) -> None:
    runtime = FakeCliRuntime(project)

    result = runner.invoke(app, ["test", "--target", "gui"], obj=runtime)

    assert result.exit_code == 2
    assert "pure, qgis, desktop, web" in runtime.stderr

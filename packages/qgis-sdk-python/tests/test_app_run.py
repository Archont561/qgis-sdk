"""``qgis-sdk run``: the app host from a scaffolded project, without QGIS.

TASK-81 AC 2 asks for the command to start the app "with the discovered QGIS
environment on Linux and Windows (devtools harness; Windows row recorded or
blocked per TASK-33)". This file is that harness' pure half: the plan the
command builds - interpreter, entry, flags, environment, working directory - and
the command's own wiring, both proven with a laid-out prefix and
``FakeCliRuntime``. The row that actually opens a ``QgsApplication`` is native
and lives in ``test_app_native.py``; a host without PyQGIS skips it, which is
what the Windows row records (TASK-33).
"""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

import pytest
from qgis_sdk_tools.__main__ import app
from qgis_sdk_tools.devtools import find_qgis_install
from qgis_sdk_tools.devtools.dev import (
    APP_PROBE_NAME,
    QgisSdkDevError,
    inspect_project,
    plan_app,
)
from qgis_sdk_tools.scaffold import ScaffoldOptions, write_scaffold
from qgis_sdk_tools.testing import FakeCliRuntime
from test_devtools_installs import make_prefix
from typer.testing import CliRunner

runner = CliRunner()


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A project the app host can start: ``qgis-sdk new --host app``."""
    root = tmp_path / "field_tools"
    write_scaffold(ScaffoldOptions.resolve("field_tools", host="app"), root)
    return root


@pytest.fixture
def desktop_project(tmp_path: Path) -> Path:
    """A Desktop plugin, which has no ``__main__.py`` of its own."""
    root = tmp_path / "field_tools"
    write_scaffold(ScaffoldOptions.resolve("field_tools"), root)
    return root


@pytest.fixture
def prefix(tmp_path: Path) -> Path:
    return make_prefix(tmp_path, conda=True)


def install(prefix: Path, tmp_path: Path):
    return find_qgis_install(
        {}, prefix=prefix, which=lambda name, path=None: None, sys_prefix=tmp_path / "x"
    )


# -- the plan -----------------------------------------------------------------------


def test_the_project_entry_runs_through_the_installs_interpreter(
    project: Path, prefix: Path, tmp_path: Path
) -> None:
    plan = plan_app(
        inspect_project(project),
        install(prefix, tmp_path),
        env={"HOME": "/h"},
        workspace=tmp_path / "workspace",
    )

    assert plan.mode == "app"
    assert plan.argv == (str(prefix.resolve() / "bin" / "python"), "-m", "field_tools")
    assert plan.cwd == project
    assert plan.profile is None
    assert plan.notes[0].startswith("app: ")
    assert "with a window" in plan.notes[0]


def test_the_environment_carries_the_bindings_and_the_project(
    project: Path, prefix: Path, tmp_path: Path
) -> None:
    plan = plan_app(
        inspect_project(project),
        install(prefix, tmp_path),
        env={"HOME": "/h", "DISPLAY": ":0"},
        workspace=tmp_path / "workspace",
    )

    assert plan.env["QGIS_PREFIX_PATH"] == str(prefix.resolve())
    entries = plan.env["PYTHONPATH"].split(os.pathsep)
    assert entries[0] == str(prefix.resolve() / "share" / "qgis" / "python")
    assert str(project) in entries
    assert any(entry.endswith("qgis-sdk-runtime/src") for entry in entries)
    assert "QT_QPA_PLATFORM" not in plan.env


def test_headless_makes_qt_offscreen_and_names_it_in_the_notes(
    project: Path, prefix: Path, tmp_path: Path
) -> None:
    plan = plan_app(
        inspect_project(project),
        install(prefix, tmp_path),
        env={},
        workspace=tmp_path / "workspace",
        gui=False,
    )

    assert plan.argv[3:] == ("--headless",)
    assert plan.env["QT_QPA_PLATFORM"] == "offscreen"
    assert plan.env["DISPLAY"]
    assert "headless" in plan.notes[0]


def test_once_grace_and_title_reach_the_entry(
    project: Path, prefix: Path, tmp_path: Path
) -> None:
    plan = plan_app(
        inspect_project(project),
        install(prefix, tmp_path),
        env={},
        workspace=tmp_path / "workspace",
        once=True,
        grace=0.5,
        title="Field tools",
    )

    assert plan.argv[3:] == ("--once", "--grace", "0.5", "--title", "Field tools")


def test_toolkit_arguments_go_after_the_separator(
    project: Path, prefix: Path, tmp_path: Path
) -> None:
    plan = plan_app(
        inspect_project(project),
        install(prefix, tmp_path),
        env={},
        workspace=tmp_path / "workspace",
        toolkit_args=("-platform", "offscreen"),
    )

    assert plan.argv[-3:] == ("--", "-platform", "offscreen")


def test_a_project_without_an_app_entry_gets_a_probe(
    desktop_project: Path, prefix: Path, tmp_path: Path
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    plan = plan_app(
        inspect_project(desktop_project),
        install(prefix, tmp_path),
        env={},
        workspace=workspace,
    )

    probe = workspace / APP_PROBE_NAME
    assert plan.argv == (
        str(prefix.resolve() / "bin" / "python"),
        str(probe),
    )
    written = probe.read_text(encoding="utf-8")
    assert "'field_tools.plugin'" in written and "'app'" in written
    assert "qgis_sdk.app" in written
    assert "no field_tools/__main__.py" in plan.notes[0]


def test_a_server_only_project_has_no_application_to_start(tmp_path: Path) -> None:
    root = tmp_path / "demo_server"
    write_scaffold(ScaffoldOptions.resolve("demo_server", host="server"), root)

    with pytest.raises(QgisSdkDevError, match="is not an application"):
        plan_app(
            inspect_project(root),
            install(make_prefix(tmp_path), tmp_path),
            env={},
            workspace=tmp_path / "workspace",
        )


def test_an_install_without_an_interpreter_is_refused_by_name(
    project: Path, tmp_path: Path
) -> None:
    prefix = make_prefix(tmp_path, executable=False)
    found = install(prefix, tmp_path)
    without = replace(found, python=None)

    with pytest.raises(QgisSdkDevError, match="no Python interpreter"):
        plan_app(
            inspect_project(project),
            without,
            env={},
            workspace=tmp_path / "workspace",
        )


# -- the command --------------------------------------------------------------------


def test_run_starts_the_app_and_returns_its_exit_code(
    project: Path, prefix: Path
) -> None:
    runtime = FakeCliRuntime(project, {"HOME": "/h"})

    result = runner.invoke(app, ["run", "--qgis-prefix", str(prefix)], obj=runtime)

    assert result.exit_code == 0, runtime.stderr
    argv, cwd = runtime.processes[0]
    assert argv == (str(prefix.resolve() / "bin" / "python"), "-m", "field_tools")
    assert cwd == project
    assert "app: " in runtime.stderr
    assert runtime.started == []


def test_run_asks_for_the_flags_it_was_given(project: Path, prefix: Path) -> None:
    runtime = FakeCliRuntime(project)

    result = runner.invoke(
        app,
        ["run", "--qgis-prefix", str(prefix), "--headless", "--once", "--grace", "0.5"],
        obj=runtime,
    )

    assert result.exit_code == 0, runtime.stderr
    assert runtime.processes[0][0][3:] == ("--headless", "--once", "--grace", "0.5")


def test_the_generated_probe_still_exists_when_the_app_starts(
    desktop_project: Path, prefix: Path
) -> None:
    """The probe is in a temporary directory, so it may only go after the app."""
    seen: list[bool] = []

    def run_process(argv, cwd) -> int:
        seen.append(Path(argv[1]).is_file())
        return 0

    runtime = FakeCliRuntime(desktop_project, run_process=run_process)

    result = runner.invoke(app, ["run", "--qgis-prefix", str(prefix)], obj=runtime)

    assert result.exit_code == 0, runtime.stderr
    assert seen == [True]


def test_the_apps_exit_code_is_the_commands(project: Path, prefix: Path) -> None:
    runtime = FakeCliRuntime(project, run_process=lambda argv, cwd: 4)

    result = runner.invoke(app, ["run", "--qgis-prefix", str(prefix)], obj=runtime)

    assert result.exit_code == 4


def test_a_project_that_is_not_one_is_refused_with_a_code(tmp_path: Path) -> None:
    runtime = FakeCliRuntime(tmp_path)

    result = runner.invoke(app, ["run"], obj=runtime)

    assert result.exit_code == 2
    assert "pyproject.toml" in runtime.stderr or "tool.qgis-sdk" in runtime.stderr


def test_a_missing_qgis_is_refused_with_a_code(project: Path) -> None:
    runtime = FakeCliRuntime(project)

    result = runner.invoke(
        app, ["run", "--qgis-prefix", str(project / "nowhere")], obj=runtime
    )

    assert result.exit_code == 2
    assert "nowhere" in runtime.stderr

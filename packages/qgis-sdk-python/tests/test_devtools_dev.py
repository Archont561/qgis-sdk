"""`qgis-sdk dev`'s plan: Desktop in place with Reload, or a bare QgsApplication."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from qgis_sdk_tools.devtools import QgisInstall, find_qgis_install
from qgis_sdk_tools.devtools.dev import (
    DESKTOP_PROBE,
    DEV_SERVER_ENV,
    REQUEST_ENV,
    STANDALONE_PROBE,
    QgisSdkDevError,
    inspect_project,
    plan_dev,
    plan_web_server,
    wait_for_port,
)
from qgis_sdk_tools.devtools.installs import sdk_import_paths
from qgis_sdk_tools.devtools.testrun import DESKTOP_PROBE as TEST_PROBE
from qgis_sdk_tools.scaffold import ScaffoldOptions, write_scaffold
from test_devtools_installs import make_prefix, no_which


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "field_tools"
    write_scaffold(ScaffoldOptions.resolve("field_tools"), root)
    return root


@pytest.fixture
def web_project(tmp_path: Path) -> Path:
    root = tmp_path / "web_tools"
    write_scaffold(
        ScaffoldOptions.resolve("web_tools", web="vanilla", package_manager="pnpm"),
        root,
    )
    (root / "web" / "node_modules").mkdir()
    (root / "web" / "pnpm-lock.yaml").write_text("")
    return root


@pytest.fixture
def install(tmp_path: Path) -> QgisInstall:
    return find_qgis_install(
        {}, prefix=make_prefix(tmp_path, conda=True), which=no_which
    )


@pytest.mark.parametrize("probe", [DESKTOP_PROBE, STANDALONE_PROBE, TEST_PROBE])
def test_every_probe_is_valid_python(probe: str) -> None:
    # A probe with a syntax error hangs headless QGIS in a modal error dialog.
    compile(probe, "probe", "exec")


class TestInspect:
    def test_finds_the_one_plugin_package(self, project: Path) -> None:
        found = inspect_project(project)

        assert found.plugin == "field_tools"
        assert found.root == project.resolve()
        assert found.web is None

    def test_sees_a_web_ui(self, web_project: Path) -> None:
        assert inspect_project(web_project).web == web_project.resolve() / "web"

    def test_a_package_without_metadata_is_not_a_plugin(self, project: Path) -> None:
        (project / "helpers").mkdir()
        (project / "helpers" / "__init__.py").write_text("")

        assert inspect_project(project).plugin == "field_tools"

    def test_no_plugin_package_is_an_error(self, tmp_path: Path) -> None:
        with pytest.raises(QgisSdkDevError, match="no plugin package"):
            inspect_project(tmp_path)

    def test_two_plugin_packages_are_an_error(self, project: Path) -> None:
        other = project / "other"
        other.mkdir()
        (other / "__init__.py").write_text("")
        (other / "metadata.txt").write_text("[general]\n")

        with pytest.raises(QgisSdkDevError, match="field_tools, other"):
            inspect_project(project)


class TestWebServer:
    def test_none_without_a_web_ui(self, project: Path) -> None:
        assert plan_web_server(inspect_project(project), 5173) is None

    def test_vite_on_loopback_through_the_lockfiles_manager(
        self, web_project: Path
    ) -> None:
        plan = plan_web_server(inspect_project(web_project), 5199)

        assert plan is not None
        assert plan.argv == (
            "pnpm",
            "dev",
            "--host",
            "127.0.0.1",
            "--port",
            "5199",
            "--strictPort",
        )
        assert plan.cwd == web_project.resolve() / "web"
        assert plan.origin == "http://127.0.0.1:5199"

    def test_npm_gets_the_separator(self, web_project: Path) -> None:
        (web_project / "web" / "pnpm-lock.yaml").unlink()

        plan = plan_web_server(inspect_project(web_project), 5199)

        assert plan is not None
        assert plan.argv[:4] == ("npm", "run", "dev", "--")

    def test_missing_dependencies_are_reported_not_installed(
        self, web_project: Path
    ) -> None:
        (web_project / "web" / "node_modules").rmdir()

        with pytest.raises(QgisSdkDevError) as excinfo:
            plan_web_server(inspect_project(web_project), 5199)

        assert "pnpm install" in str(excinfo.value)
        assert "--no-web" in str(excinfo.value)


class TestDesktopPlan:
    def test_runs_desktop_in_place_with_a_project_profile(
        self, project: Path, install: QgisInstall, tmp_path: Path
    ) -> None:
        workspace = tmp_path / "ws"
        workspace.mkdir()

        plan = plan_dev(
            inspect_project(project),
            "desktop",
            install,
            env={"HOME": "/h", "QGIS_PLUGINPATH": "/elsewhere"},
            workspace=workspace,
            headless=True,
        )

        root = project.resolve()
        assert plan.argv == (
            str(install.executable),
            "--profiles-path",
            str(root / ".qgis-sdk"),
            "--profile",
            "dev",
            "--code",
            str(workspace / "dev-desktop.py"),
        )
        assert plan.profile == root / ".qgis-sdk" / "profiles" / "dev"
        assert plan.env["QGIS_PLUGINPATH"] == os.pathsep.join((str(root), "/elsewhere"))
        assert plan.env["PYTHONHOME"] == str(install.prefix)
        assert plan.env["QT_QPA_PLATFORM"] == "offscreen"
        assert DEV_SERVER_ENV not in plan.env
        assert plan.env["HOME"] == "/h"
        request = json.loads(Path(plan.env[REQUEST_ENV]).read_text(encoding="utf-8"))
        assert request == {
            "root": str(root),
            "plugin": "field_tools",
            "mode": "desktop",
            "web": False,
            "dev_server": None,
            "exercise": None,
            "watch": True,
        }
        assert (workspace / "dev-desktop.py").read_text(
            encoding="utf-8"
        ) == DESKTOP_PROBE
        assert "Ctrl+Shift+R" in plan.notes[1]
        assert "on save" in plan.notes[1]
        assert "via QGIS_PLUGINPATH" in plan.notes[0]
        # The bootstrap imports qgis_sdk_tools inside QGIS's own interpreter.
        assert plan.env["PYTHONPATH"].split(os.pathsep)[:3] == [
            str(install.bindings),
            str(root),
            *(str(path) for path in sdk_import_paths()),
        ]

    def test_no_watch_leaves_reloads_to_the_button(
        self, project: Path, install: QgisInstall, tmp_path: Path
    ) -> None:
        plan = plan_dev(
            inspect_project(project),
            "desktop",
            install,
            env={},
            workspace=tmp_path,
            headless=True,
            watch=False,
        )

        request = json.loads(Path(plan.env[REQUEST_ENV]).read_text(encoding="utf-8"))
        assert request["watch"] is False
        assert "on save" not in plan.notes[1]
        assert "Ctrl+Shift+R" in plan.notes[1]

    def test_hands_the_dev_server_to_the_plugin(
        self, web_project: Path, install: QgisInstall, tmp_path: Path
    ) -> None:
        plan = plan_dev(
            inspect_project(web_project),
            "desktop",
            install,
            env={},
            workspace=tmp_path,
            dev_server="http://127.0.0.1:5199",
            exercise=tmp_path / "report.json",
        )

        assert plan.env[DEV_SERVER_ENV] == "http://127.0.0.1:5199"
        request = json.loads(Path(plan.env[REQUEST_ENV]).read_text(encoding="utf-8"))
        assert request["web"] is True
        assert request["dev_server"] == "http://127.0.0.1:5199"
        assert request["exercise"] == str(tmp_path / "report.json")
        assert "page from http://127.0.0.1:5199" in plan.notes[0]

    def test_needs_a_desktop_binary(
        self, project: Path, install: QgisInstall, tmp_path: Path
    ) -> None:
        headless = QgisInstall(
            prefix=install.prefix,
            bindings=install.bindings,
            executable=None,
            python=install.python,
            source=install.source,
            conda=True,
        )

        with pytest.raises(QgisSdkDevError) as excinfo:
            plan_dev(
                inspect_project(project),
                "desktop",
                headless,
                env={},
                workspace=tmp_path,
            )

        assert "no QGIS Desktop binary" in str(excinfo.value)
        assert "--mode standalone" in str(excinfo.value)

    def test_the_probe_is_a_bootstrap_for_the_reloader_module(self) -> None:
        # The policy lives in an importable, unit-tested module; the probe
        # only has to reach it and report when it cannot.
        assert (
            "from qgis_sdk_tools.devtools.bootstrap import bootstrap" in DESKTOP_PROBE
        )
        assert "cannot import qgis_sdk_tools inside QGIS" in DESKTOP_PROBE
        assert "report_bootstrap_failure" in DESKTOP_PROBE


class TestStandalonePlan:
    def test_runs_the_installs_interpreter_without_desktop(
        self, project: Path, install: QgisInstall, tmp_path: Path
    ) -> None:
        plan = plan_dev(
            inspect_project(project),
            "standalone",
            install,
            env={},
            workspace=tmp_path,
        )

        assert plan.argv == (str(install.python), str(tmp_path / "dev-standalone.py"))
        assert plan.profile is None
        assert "PYTHONHOME" not in plan.env
        assert plan.env["PYTHONPATH"].split(os.pathsep)[:3] == [
            str(install.bindings),
            str(project.resolve()),
            *(str(path) for path in sdk_import_paths()),
        ]
        assert "no iface, no plugin lifecycle, no reload" in plan.notes[0]
        assert "classFactory(None)" in plan.notes[0]

    def test_needs_an_interpreter(
        self, project: Path, install: QgisInstall, tmp_path: Path
    ) -> None:
        bare = QgisInstall(
            prefix=install.prefix,
            bindings=install.bindings,
            executable=install.executable,
            python=None,
            source=install.source,
            conda=True,
        )

        with pytest.raises(QgisSdkDevError, match="--mode desktop"):
            plan_dev(
                inspect_project(project), "standalone", bare, env={}, workspace=tmp_path
            )


def test_an_unknown_mode_is_refused(
    project: Path, install: QgisInstall, tmp_path: Path
) -> None:
    with pytest.raises(QgisSdkDevError, match="desktop or standalone"):
        plan_dev(inspect_project(project), "gui", install, env={}, workspace=tmp_path)


class TestWaitForPort:
    def test_returns_as_soon_as_the_port_answers(self) -> None:
        answers = iter([False, False, True])
        slept: list[float] = []

        ok = wait_for_port(
            5199,
            still_running=lambda: True,
            probe=lambda port: next(answers),
            sleep=slept.append,
            clock=lambda: 0.0,
        )

        assert ok is True
        assert slept == [0.1, 0.1]

    def test_gives_up_when_the_server_died(self) -> None:
        ok = wait_for_port(
            5199,
            still_running=lambda: False,
            probe=lambda port: False,
            sleep=lambda s: None,
            clock=lambda: 0.0,
        )

        assert ok is False

    def test_gives_up_at_the_deadline(self) -> None:
        ticks = iter([0.0, 10.0, 70.0])

        ok = wait_for_port(
            5199,
            still_running=lambda: True,
            probe=lambda port: False,
            sleep=lambda s: None,
            clock=lambda: next(ticks),
            timeout=60.0,
        )

        assert ok is False

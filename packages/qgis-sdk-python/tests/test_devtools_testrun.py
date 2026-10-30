"""`qgis-sdk test`'s plan: which process, which environment, which pytest arguments."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest
from qgis_sdk_tools.devtools import QgisInstall, find_qgis_install
from qgis_sdk_tools.devtools.installs import sdk_import_paths
from qgis_sdk_tools.devtools.testrun import (
    PLUGIN,
    REQUEST_ENV,
    QgisSdkTestRunError,
    plan_tests,
)
from qgis_sdk_tools.pytest_plugin import TARGET_ENV
from qgis_sdk_tools.scaffold import ScaffoldOptions, write_scaffold
from test_devtools_installs import make_prefix, no_which


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "field_tools"
    write_scaffold(ScaffoldOptions.resolve("field_tools"), root)
    return root


@pytest.fixture
def install(tmp_path: Path) -> QgisInstall:
    prefix = make_prefix(tmp_path, conda=True)
    return find_qgis_install({}, prefix=prefix, which=no_which)


class TestPure:
    def test_runs_this_interpreters_pytest_with_the_plugin_and_pure_selection(
        self, project: Path
    ) -> None:
        plan = plan_tests(project, "pure", ("-q", "tests/test_x.py"), env={"A": "1"})

        assert plan.argv == (
            sys.executable,
            "-m",
            "pytest",
            "-p",
            PLUGIN,
            "-m",
            "not qgis and not desktop and not server",
            "-q",
            "tests/test_x.py",
        )
        assert plan.cwd == project
        assert plan.env[TARGET_ENV] == "pure"
        assert plan.env["A"] == "1"
        assert "QGIS_PREFIX_PATH" not in plan.env
        assert plan.workspace is None

    def test_needs_no_qgis_install(self, project: Path) -> None:
        plan = plan_tests(project, "pure", (), env={})

        assert plan.notes == ("target pure: this interpreter, native imports refused",)


class TestQgis:
    def test_runs_the_installs_interpreter_under_its_bindings(
        self, project: Path, install: QgisInstall
    ) -> None:
        plan = plan_tests(
            project,
            "qgis",
            ("-x",),
            env={"HOME": "/h"},
            install=install,
            platform="linux",  # no DISPLAY in env: headless
        )

        assert plan.argv == (
            str(install.python),
            "-m",
            "pytest",
            "-p",
            PLUGIN,
            "-m",
            "qgis",
            "-x",
        )
        assert plan.env[TARGET_ENV] == "qgis"
        # Bindings first; then the SDK itself, so ``-p qgis_sdk_tools.pytest_plugin``
        # resolves in QGIS's interpreter even when the CLI runs under another.
        sdk_paths = [str(path) for path in sdk_import_paths()]
        assert plan.env["PYTHONPATH"].split(os.pathsep)[: 1 + len(sdk_paths)] == [
            str(install.bindings),
            *sdk_paths,
        ]
        assert plan.env["QGIS_PREFIX_PATH"] == str(install.prefix)
        assert plan.env["QT_QPA_PLATFORM"] == "offscreen"  # no DISPLAY in env
        assert "PYTHONHOME" not in plan.env
        assert plan.notes[0] == (
            f"target qgis: QGIS {install.prefix} ({install.source}), "
            f"python {install.python}, offscreen"
        )

    def test_a_display_keeps_qt_on_screen(
        self, project: Path, install: QgisInstall
    ) -> None:
        plan = plan_tests(
            project,
            "qgis",
            (),
            env={"DISPLAY": ":0"},
            install=install,
            platform="linux",
        )

        assert "QT_QPA_PLATFORM" not in plan.env

    def test_requires_an_install(self, project: Path) -> None:
        with pytest.raises(QgisSdkTestRunError, match="needs a QGIS install"):
            plan_tests(project, "qgis", (), env={})

    def test_an_install_without_an_interpreter_is_refused(
        self, project: Path, install: QgisInstall
    ) -> None:
        bare = QgisInstall(
            prefix=install.prefix,
            bindings=install.bindings,
            executable=install.executable,
            python=None,
            source=install.source,
            conda=False,
        )

        with pytest.raises(QgisSdkTestRunError) as excinfo:
            plan_tests(project, "qgis", (), env={}, install=bare)

        assert "no Python interpreter" in str(excinfo.value)
        assert str(install.prefix) in str(excinfo.value)


class TestDesktop:
    def test_runs_pytest_inside_the_desktop_binary_with_a_throwaway_profile(
        self, project: Path, install: QgisInstall, tmp_path: Path
    ) -> None:
        workspace = tmp_path / "ws"
        workspace.mkdir()

        plan = plan_tests(
            project,
            "desktop",
            ("-k", "iface"),
            env={},
            install=install,
            workspace=workspace,
            platform="linux",
        )

        assert plan.argv == (
            str(install.executable),
            "--noplugins",
            "--profiles-path",
            str(workspace / "profiles"),
            "--profile",
            "qgis-sdk-test",
            "--code",
            str(workspace / "pytest-probe.py"),
        )
        assert plan.workspace == workspace
        assert plan.env[TARGET_ENV] == "desktop"
        assert plan.env["PYTHONHOME"] == str(install.prefix)  # conda prefix
        assert plan.env["QGIS_PLUGINPATH"] == str(
            project / ".qgis-sdk" / "dev" / "host"
        )
        assert plan.env["DISPLAY"] == ":99"
        request = json.loads(Path(plan.env[REQUEST_ENV]).read_text(encoding="utf-8"))
        assert request == {
            "cwd": str(project),
            "args": ["-p", PLUGIN, "-m", "desktop", "-k", "iface"],
        }
        probe = (workspace / "pytest-probe.py").read_text(encoding="utf-8")
        assert 'pytest.main(request["args"])' in probe
        assert "os._exit(" in probe

    def test_requires_a_desktop_binary(
        self, project: Path, install: QgisInstall, tmp_path: Path
    ) -> None:
        headless = QgisInstall(
            prefix=install.prefix,
            bindings=install.bindings,
            executable=None,
            python=install.python,
            source=install.source,
            conda=False,
        )

        with pytest.raises(QgisSdkTestRunError) as excinfo:
            plan_tests(
                project, "desktop", (), env={}, install=headless, workspace=tmp_path
            )

        assert "no QGIS Desktop binary" in str(excinfo.value)
        assert "--target qgis" in str(excinfo.value)


class TestWeb:
    def write_web(self, project: Path, lockfile: str | None, modules: bool) -> None:
        web = project / "web"
        web.mkdir()
        (web / "package.json").write_text('{"scripts": {"test": "vitest run"}}')
        if lockfile:
            (web / lockfile).write_text("")
        if modules:
            (web / "node_modules").mkdir()

    @pytest.mark.parametrize(
        ("lockfile", "argv"),
        [
            ("bun.lock", ("bun", "run", "test", "--reporter=dot")),
            ("bun.lockb", ("bun", "run", "test", "--reporter=dot")),
            ("pnpm-lock.yaml", ("pnpm", "test", "--reporter=dot")),
            ("package-lock.json", ("npm", "run", "test", "--", "--reporter=dot")),
            (None, ("npm", "run", "test", "--", "--reporter=dot")),
        ],
    )
    def test_the_lockfile_picks_the_manager(
        self, project: Path, lockfile: str | None, argv: tuple[str, ...]
    ) -> None:
        self.write_web(project, lockfile, modules=True)

        plan = plan_tests(project, "web", ("--reporter=dot",), env={"X": "y"})

        assert plan.argv == argv
        assert plan.cwd == project / "web"
        assert plan.env == {"X": "y"}
        assert plan.notes == (f"target web: {argv[0]} in web/",)

    def test_a_project_without_a_web_ui_says_how_to_get_one(
        self, project: Path
    ) -> None:
        with pytest.raises(QgisSdkTestRunError) as excinfo:
            plan_tests(project, "web", (), env={})

        assert "no web/package.json" in str(excinfo.value)
        assert "qgis-sdk new --web" in str(excinfo.value)

    def test_missing_dependencies_are_reported_not_installed(
        self, project: Path
    ) -> None:
        self.write_web(project, "pnpm-lock.yaml", modules=False)

        with pytest.raises(QgisSdkTestRunError) as excinfo:
            plan_tests(project, "web", (), env={})

        assert "web/node_modules" in str(excinfo.value)
        assert "pnpm install" in str(excinfo.value)


class TestServer:
    """TASK-80 AC 4: the server target is the install's interpreter, headless."""

    def test_runs_the_installs_interpreter_with_the_server_selection(
        self, project: Path, install: QgisInstall
    ) -> None:
        plan = plan_tests(
            project, "server", ("-q",), env={}, install=install, platform="linux"
        )

        assert plan.argv == (
            str(install.python),
            "-m",
            "pytest",
            "-p",
            PLUGIN,
            "-m",
            "server",
            "-q",
        )
        assert plan.cwd == project
        assert plan.env[TARGET_ENV] == "server"
        assert plan.env["QGIS_PREFIX_PATH"] == str(install.prefix)
        # A server has no display, and a hook is not a widget: offscreen always.
        assert plan.env["QT_QPA_PLATFORM"] == "offscreen"
        assert "WITH_SERVER=ON" in plan.notes[0]

    def test_requires_an_install(self, project: Path) -> None:
        with pytest.raises(QgisSdkTestRunError, match="needs a QGIS install"):
            plan_tests(project, "server", (), env={})

    def test_an_install_without_an_interpreter_is_refused(
        self, project: Path, install: QgisInstall
    ) -> None:
        bare = QgisInstall(
            prefix=install.prefix,
            bindings=install.bindings,
            executable=install.executable,
            python=None,
            source=install.source,
            conda=False,
        )

        with pytest.raises(QgisSdkTestRunError) as excinfo:
            plan_tests(project, "server", (), env={}, install=bare)

        assert "no Python interpreter" in str(excinfo.value)
        assert str(install.prefix) in str(excinfo.value)


def test_the_server_target_is_native_and_gated() -> None:
    """A server gate must not read as a pass: it is native, and it is selected."""
    from qgis_sdk_tools.devtools import testrun
    from qgis_sdk_tools.pytest_plugin import NATIVE_TARGETS, TARGETS

    assert "server" in TARGETS
    assert "server" in NATIVE_TARGETS
    assert testrun.SELECTION["server"] == "server"
    assert set(testrun.TARGETS) == set(TARGETS)


def test_an_unknown_target_is_refused(project: Path) -> None:
    with pytest.raises(QgisSdkTestRunError, match="pure, qgis, desktop, server, web"):
        plan_tests(project, "gui", (), env={})


def test_a_missing_project_root_is_refused(tmp_path: Path) -> None:
    with pytest.raises(QgisSdkTestRunError, match="not a directory"):
        plan_tests(tmp_path / "nope", "pure", (), env={})

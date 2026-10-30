"""``qgis-sdk dev``: discover QGIS, start Vite if there is a web UI, run, clean up."""

from __future__ import annotations

import json
import socket
import sys
from collections.abc import Iterator, Sequence
from pathlib import Path

import pytest
from qgis_sdk_tools.__main__ import app
from qgis_sdk_tools.devtools.dev import DEV_SERVER_ENV, REQUEST_ENV
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


@pytest.fixture
def web_project(tmp_path: Path) -> Path:
    root = tmp_path / "web_tools"
    write_scaffold(
        ScaffoldOptions.resolve("web_tools", web="react", package_manager="bun"), root
    )
    (root / "web" / "node_modules").mkdir()
    (root / "web" / "bun.lock").write_text("")
    return root


@pytest.fixture
def prefix(tmp_path: Path) -> Path:
    return make_prefix(tmp_path, conda=True)


@pytest.fixture
def listening_port() -> Iterator[int]:
    """A loopback port that answers, standing in for a started dev server."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        yield int(server.getsockname()[1])


def test_desktop_is_the_default_and_runs_the_binary_in_place(
    project: Path, prefix: Path
) -> None:
    runtime = FakeCliRuntime(project, {"HOME": "/h"})

    result = runner.invoke(app, ["dev", "--qgis-prefix", str(prefix)], obj=runtime)

    assert result.exit_code == 0, runtime.stderr
    argv, cwd = runtime.processes[0]
    assert argv[0] == str(prefix.resolve() / "bin" / "qgis")
    assert argv[1:5] == (
        "--profiles-path",
        str(project / ".qgis-sdk"),
        "--profile",
        "dev",
    )
    assert cwd == project
    env = runtime.environments[0]
    assert env is not None
    assert env["QGIS_PLUGINPATH"] == str(project / ".qgis-sdk" / "dev" / "host")
    assert (
        project / ".qgis-sdk" / "dev" / "host" / "field_tools" / "metadata.txt"
    ).is_file()
    assert runtime.started == []
    assert "desktop:" in runtime.stderr
    assert "Ctrl+Shift+R" in runtime.stderr


def test_no_watch_is_passed_to_the_bootstrap(project: Path, prefix: Path) -> None:
    requests: list[dict[str, object]] = []

    def run_process(argv: Sequence[str], cwd: Path) -> int:
        # The request file lives in the workspace, which the command removes
        # once QGIS exits, so read it while "QGIS" runs.
        env = runtime.environments[-1]
        assert env is not None
        requests.append(json.loads(Path(env[REQUEST_ENV]).read_text(encoding="utf-8")))
        return 0

    runtime = FakeCliRuntime(project, {"HOME": "/h"}, run_process=run_process)

    result = runner.invoke(
        app, ["dev", "--qgis-prefix", str(prefix), "--no-watch"], obj=runtime
    )

    assert result.exit_code == 0, runtime.stderr
    assert requests[0]["watch"] is False
    assert "on save" not in runtime.stderr


def test_the_qgis_exit_code_is_the_commands(project: Path, prefix: Path) -> None:
    runtime = FakeCliRuntime(project, run_process=lambda argv, cwd: 3)

    result = runner.invoke(app, ["dev", "--qgis-prefix", str(prefix)], obj=runtime)

    assert result.exit_code == 3


def test_standalone_runs_the_interpreter(project: Path, prefix: Path) -> None:
    runtime = FakeCliRuntime(project)

    result = runner.invoke(
        app, ["dev", "--mode", "standalone", "--qgis-prefix", str(prefix)], obj=runtime
    )

    assert result.exit_code == 0, runtime.stderr
    assert runtime.processes[0][0][0] == str(prefix.resolve() / "bin" / "python")
    assert "no iface, no plugin lifecycle, no reload" in runtime.stderr


def test_host_server_runs_the_interpreter_with_a_server_loop(
    project: Path, prefix: Path
) -> None:
    """TASK-80 AC 4 spells it ``dev --host server``; ``--mode`` is the same flag."""
    runtime = FakeCliRuntime(project)

    result = runner.invoke(
        app,
        ["dev", "--host", "server", "--port", "8099", "--qgis-prefix", str(prefix)],
        obj=runtime,
    )

    assert result.exit_code == 0, runtime.stderr
    argv, cwd = runtime.processes[0]
    assert argv[0] == str(prefix.resolve() / "bin" / "python")
    assert argv[1].endswith("dev-server.py")
    assert cwd == project
    env = runtime.environments[0]
    assert env is not None
    assert "QGIS_PLUGINPATH" not in env
    assert env["QT_QPA_PLATFORM"] == "offscreen"
    assert "http://127.0.0.1:8099" in runtime.stderr
    # The workspace holding the request is removed when the command returns; the
    # plan's own test reads it (TestServerPlan in test_devtools_dev.py).
    assert env[REQUEST_ENV].endswith("dev-request.json")
    assert runtime.started == []  # no Vite for a server plugin


def test_a_web_ui_starts_vite_on_loopback_and_stops_it_afterwards(
    web_project: Path, prefix: Path, listening_port: int
) -> None:
    runtime = FakeCliRuntime(web_project)

    result = runner.invoke(
        app,
        ["dev", "--qgis-prefix", str(prefix), "--port", str(listening_port)],
        obj=runtime,
    )

    assert result.exit_code == 0, runtime.stderr
    assert len(runtime.started) == 1
    vite = runtime.started[0]
    assert vite.argv == (
        "bun",
        "run",
        "dev",
        "--host",
        "127.0.0.1",
        "--port",
        str(listening_port),
        "--strictPort",
    )
    assert vite.cwd == web_project / "web"
    assert vite.terminated is True
    origin = f"http://127.0.0.1:{listening_port}"
    qgis_env = runtime.environments[-1]
    assert qgis_env is not None
    assert qgis_env[DEV_SERVER_ENV] == origin
    assert f"web: {origin} (hot module replacement)" in runtime.stderr


def test_no_web_skips_the_dev_server(web_project: Path, prefix: Path) -> None:
    runtime = FakeCliRuntime(web_project)

    result = runner.invoke(
        app, ["dev", "--no-web", "--qgis-prefix", str(prefix)], obj=runtime
    )

    assert result.exit_code == 0, runtime.stderr
    assert runtime.started == []
    assert DEV_SERVER_ENV not in (runtime.environments[0] or {})


def test_a_dev_server_that_dies_stops_the_command(
    web_project: Path, prefix: Path
) -> None:
    runtime = FakeCliRuntime(web_project)
    # The fake process never listens; make it report that it exited at once.
    original_start = runtime.start_process

    def start(argv, cwd, env=None):  # type: ignore[no-untyped-def]
        process = original_start(argv, cwd, env)
        process.terminate()
        return process

    object.__setattr__(runtime, "start_process", start)

    result = runner.invoke(app, ["dev", "--qgis-prefix", str(prefix)], obj=runtime)

    assert result.exit_code == 2
    assert runtime.processes == []
    assert "did not answer" in runtime.stderr
    assert "--no-web" in runtime.stderr


def test_a_missing_qgis_is_exit_code_2(
    project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "prefix", str(tmp_path / "no-qgis"))
    runtime = FakeCliRuntime(project, {"PATH": ""})

    result = runner.invoke(app, ["dev"], obj=runtime)

    assert result.exit_code == 2
    assert "no QGIS install found" in runtime.stderr


def test_a_directory_without_a_plugin_is_exit_code_2(
    tmp_path: Path, prefix: Path
) -> None:
    runtime = FakeCliRuntime(tmp_path)

    result = runner.invoke(app, ["dev", "--qgis-prefix", str(prefix)], obj=runtime)

    assert result.exit_code == 2
    assert "PROJECT002" in runtime.stderr

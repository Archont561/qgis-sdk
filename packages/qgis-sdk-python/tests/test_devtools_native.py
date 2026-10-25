"""``qgis-sdk test`` and ``qgis-sdk dev`` against the real QGIS (TASK-26, TASK-6).

Opt-in, because it starts the QGIS Desktop binary and, with a package manager
at hand, a Vite dev server::

    QGIS_SDK_DEVTOOLS=1 QT_QPA_PLATFORM=offscreen pytest tests/test_devtools_native.py

What it proves, each through the command line a user would type:

* ``test --target qgis`` runs a ``qgis``-marked test under a headless
  ``QgsApplication`` and forwards pytest's exit code, ``--target desktop``
  runs a ``desktop``-marked test *inside* QGIS Desktop with the real
  ``iface``, and a failing test fails the command;
* ``dev`` loads the source plugin in place, reloads it, refuses a reload
  over a syntax error while the old revision keeps running, and runs the
  edited source after the next reload; ``dev --mode standalone`` runs the
  plugin without Desktop;
* with a web UI, ``dev`` serves the page from Vite inside QGIS with hot
  module replacement, and the bridge answers after the page updated.
"""

from __future__ import annotations

import importlib
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from qgis_sdk_tools.devtools.dev import DEV_SERVER_ENV
from qgis_sdk_tools.scaffold import ScaffoldOptions, write_scaffold
from qgis_sdk_tools.scaffold.web import install_command

pytestmark = pytest.mark.desktop

if not os.environ.get("QGIS_SDK_DEVTOOLS"):
    pytest.skip(
        "set QGIS_SDK_DEVTOOLS=1 to drive qgis-sdk test and dev against real QGIS",
        allow_module_level=True,
    )

try:  # the web half: WebEngine has to be imported before the application
    from PyQt6.QtCore import QCoreApplication, Qt

    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    import PyQt6.QtWebEngineWidgets  # noqa: F401

    WEBENGINE = True
except ImportError:  # pragma: no cover - depends on the host
    WEBENGINE = False

SDK_SOURCE = Path(__file__).resolve().parents[1] / "src"
DEADLINE = 30.0

NATIVE_TESTS = """import pytest
import field_tools


@pytest.mark.qgis
def test_project_layers_under_a_real_qgis(qgis_app):
    plugin = field_tools.classFactory(None)
    plugin.initGui()
    try:
        assert plugin.runtime.actions["project_layers"]() == []
    finally:
        plugin.unload()


@pytest.mark.desktop
def test_the_source_plugin_loads_through_desktop(qgis_iface):
    import qgis.utils

    qgis.utils.updateAvailablePlugins()
    assert "field_tools" in qgis.utils.available_plugins
    assert qgis.utils.loadPlugin("field_tools")
    assert qgis.utils.startPlugin("field_tools")
    assert qgis.utils.plugins["field_tools"].runtime.state.value == "running"
    assert qgis_iface.mainWindow() is not None
    assert qgis.utils.unloadPlugin("field_tools")
"""


def _cli(
    *args: str, cwd: Path, timeout: float = 600
) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTEST_")}
    env["PYTHONPATH"] = str(SDK_SOURCE)
    return subprocess.run(
        [sys.executable, "-m", "qgis_sdk_tools", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


@pytest.fixture(scope="module")
def project(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("devtools") / "field_tools"
    write_scaffold(ScaffoldOptions.resolve("field_tools"), root)
    (root / "tests" / "test_native.py").write_text(NATIVE_TESTS, encoding="utf-8")
    return root


class TestTestCommand:
    def test_pure_deselects_the_native_tests(self, project: Path) -> None:
        result = _cli("test", "-q", cwd=project)

        assert result.returncode == 0, result.stdout + result.stderr
        assert "3 passed, 2 deselected" in result.stdout

    def test_qgis_runs_under_a_headless_application(self, project: Path) -> None:
        result = _cli("test", "--target", "qgis", "-q", cwd=project)

        assert result.returncode == 0, result.stdout + result.stderr
        assert "1 passed, 4 deselected" in result.stdout
        assert "target qgis:" in result.stderr

    def test_desktop_runs_inside_the_binary_with_iface(self, project: Path) -> None:
        result = _cli("test", "--target", "desktop", "-q", cwd=project)

        assert result.returncode == 0, result.stdout + result.stderr
        assert "1 passed, 4 deselected" in result.stdout
        assert "target desktop:" in result.stderr
        assert not list(Path(project).glob(".qgis-sdk"))  # test profiles are temporary

    def test_a_failing_desktop_test_fails_the_command(self, project: Path) -> None:
        failing = project / "tests" / "test_failing.py"
        failing.write_text(
            "import pytest\n\n@pytest.mark.desktop\ndef test_no(qgis_iface):\n"
            "    assert qgis_iface is None\n",
            encoding="utf-8",
        )
        try:
            result = _cli("test", "--target", "desktop", "-q", cwd=project)
        finally:
            failing.unlink()

        assert result.returncode == 1, result.stdout + result.stderr
        assert "1 failed, 1 passed" in result.stdout

    def test_a_native_target_that_only_skips_fails(self, project: Path) -> None:
        skipping = project / "tests" / "test_skipping.py"
        skipping.write_text(
            "import pytest\n\n@pytest.mark.qgis\ndef test_skip():\n"
            "    pytest.skip('nothing here')\n",
            encoding="utf-8",
        )
        try:
            result = _cli(
                "test", "--target", "qgis", "-q", "-k", "test_skip", cwd=project
            )
        finally:
            skipping.unlink()

        assert result.returncode == 1, result.stdout + result.stderr
        assert "every test of the qgis target was skipped" in result.stdout


class TestDevCommand:
    def test_desktop_loads_reloads_refuses_and_runs_the_edit(
        self, project: Path, tmp_path: Path
    ) -> None:
        report_path = tmp_path / "report.json"

        result = _cli("dev", "--exercise", str(report_path), cwd=project)

        assert result.returncode == 0, result.stdout + result.stderr
        report = json.loads(report_path.read_text(encoding="utf-8"))
        assert report == {
            "started": True,
            "error": None,
            "reload_ok": True,
            "reload_refused": True,
            "kept_running": True,
            "reload_after_fix": True,
            "ping_after_edit": 1001,
            "revision": 3,
            "unloaded": True,
        }
        assert "reload refused, revision 2 keeps running" in result.stderr
        assert "field_tools running (revision 3)" in result.stderr
        assert (project / ".qgis-sdk" / "profiles" / "dev").is_dir()
        assert "1000" not in (project / "field_tools" / "plugin.py").read_text()

    def test_standalone_runs_without_desktop(
        self, project: Path, tmp_path: Path
    ) -> None:
        report_path = tmp_path / "standalone.json"

        result = _cli(
            "dev", "--mode", "standalone", "--exercise", str(report_path), cwd=project
        )

        assert result.returncode == 0, result.stdout + result.stderr
        assert json.loads(report_path.read_text(encoding="utf-8")) == {
            "running": "running",
            "window": True,
            "ping": 1,
        }
        assert "no iface, no plugin lifecycle, no reload" in result.stderr


# --- web UI: Vite dev server inside QGIS ---------------------------------------


def _bun() -> str | None:
    found = shutil.which("bun")
    if found is not None:
        return found
    sibling = Path(sys.prefix).parent / "bun" / "bin" / "bun"
    return str(sibling) if sibling.is_file() else None


@pytest.fixture(scope="module")
def web_project(tmp_path_factory: pytest.TempPathFactory) -> Path:
    bun = _bun()
    if bun is None:
        pytest.skip("bun is not available for the web half")
    root = tmp_path_factory.mktemp("devtools-web") / "web_tools"
    write_scaffold(
        ScaffoldOptions.resolve("web_tools", web="vanilla", package_manager="bun"), root
    )
    install = subprocess.run(
        [bun, *install_command("bun")[1:]],
        cwd=root / "web",
        env={**os.environ, "NO_COLOR": "1", "CI": "1"},
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
    )
    assert install.returncode == 0, install.stdout + install.stderr
    return root


def test_dev_serves_the_page_from_vite_inside_desktop(
    web_project: Path, tmp_path: Path
) -> None:
    bun = _bun()
    assert bun is not None
    report_path = tmp_path / "web-report.json"
    env_path = os.pathsep.join((str(Path(bun).parent), os.environ.get("PATH", "")))

    result = subprocess.run(
        [sys.executable, "-m", "qgis_sdk_tools", "dev", "--exercise", str(report_path)],
        cwd=web_project,
        env={
            **{k: v for k, v in os.environ.items() if not k.startswith("PYTEST_")},
            "PYTHONPATH": str(SDK_SOURCE),
            "PATH": env_path,
        },
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["view_shown"] is True
    assert report["error"] is None
    assert "(hot module replacement)" in result.stderr
    assert "page from http://127.0.0.1:" in result.stderr


@pytest.fixture
def vite(web_project: Path) -> Iterator[str]:
    """A Vite dev server for the project on a free loopback port."""
    bun = _bun()
    assert bun is not None
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = subprocess.Popen(
        [bun, "run", "dev", "--host", "127.0.0.1", "--port", str(port), "--strictPort"],
        cwd=web_project / "web",
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        end = time.monotonic() + DEADLINE
        while True:
            with socket.socket() as attempt:
                attempt.settimeout(0.2)
                if attempt.connect_ex(("127.0.0.1", port)) == 0:
                    break
            assert server.poll() is None, "vite exited"
            assert time.monotonic() < end, "vite did not start"
            time.sleep(0.1)
        yield f"http://127.0.0.1:{port}"
    finally:
        server.terminate()
        server.wait(timeout=10)


@pytest.mark.webengine
@pytest.mark.skipif(not WEBENGINE, reason="the web half needs Qt WebEngine")
def test_the_page_served_by_vite_updates_in_place_and_keeps_its_bridge(
    qgis_app: Any, web_project: Path, vite: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(DEV_SERVER_ENV, vite)
    monkeypatch.syspath_prepend(str(web_project))
    module = importlib.import_module("web_tools")
    desktop = module.classFactory(None)
    desktop.initGui()
    widget = module.webview.open_view(desktop.runtime, None, placement="dialog")
    app_ts = web_project / "web" / "src" / "app.ts"
    original = app_ts.read_text(encoding="utf-8")
    try:
        page = widget.layout().itemAt(0).widget().page()
        loads: list[bool] = []
        page.loadFinished.connect(loads.append)
        _pump(qgis_app, lambda: bool(loads))
        assert loads == [True]
        assert page.url().toString() == vite + "/"

        _pump(
            qgis_app, lambda: _js(qgis_app, page, "!!document.querySelector('#ping')")
        )
        _js(qgis_app, page, "document.querySelector('#ping').click(); true")
        _pump(
            qgis_app,
            lambda: (
                _js(
                    qgis_app, page, "document.querySelector('#ping-result').textContent"
                )
                == "1"
            ),
        )

        app_ts.write_text(original.replace("Project layers", "Project layers (edited)"))
        _pump(
            qgis_app,
            lambda: (
                "edited"
                in (
                    _js(qgis_app, page, "document.body ? document.body.innerText : ''")
                    or ""
                )
            ),
        )
        _pump(
            qgis_app, lambda: _js(qgis_app, page, "!!document.querySelector('#ping')")
        )
        _js(qgis_app, page, "document.querySelector('#ping').click(); true")
        _pump(
            qgis_app,
            lambda: (
                _js(
                    qgis_app, page, "document.querySelector('#ping-result').textContent"
                )
                == "1"
            ),
        )
    finally:
        app_ts.write_text(original, encoding="utf-8")
        module.webview.close_view(widget, None)
        desktop.unload()
        qgis_app.processEvents()
        for name in [n for n in sys.modules if n.split(".")[0] == "web_tools"]:
            del sys.modules[name]


def _pump(app: Any, until: Any) -> None:
    end = time.monotonic() + DEADLINE
    while not until():
        if time.monotonic() > end:
            raise AssertionError("condition not met within the deadline")
        app.processEvents()
        time.sleep(0.005)


def _js(app: Any, page: Any, script: str) -> Any:
    box: list[object] = []
    page.runJavaScript(script, box.append)
    _pump(app, lambda: bool(box))
    return box[0]

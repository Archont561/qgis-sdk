"""The generated web project, end to end: install, Vitest, build, then QGIS (TASK-19 AC #2).

Opt-in, because it downloads the pinned dependencies and needs a package
manager plus Qt WebEngine::

    QGIS_SDK_SCAFFOLD_WEB=1 QT_QPA_PLATFORM=offscreen pytest tests/test_scaffold_web_native.py

Every manager found on ``PATH`` (or in the sibling Pixi ``bun`` environment)
is exercised; none found means a skip, not a pass. The QGIS half loads the
*built* page from ``<plugin>/web`` in a real Chromium under a headless
``QgsApplication``, clicks Ping, and reads the answer the plugin returned over
QWebChannel - the same path a user's click takes.
"""

from __future__ import annotations

import importlib
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest
from qgis_sdk_tools.scaffold import ScaffoldOptions, write_scaffold
from qgis_sdk_tools.scaffold.web import install_command, script_command

pytestmark = pytest.mark.webengine

if not os.environ.get("QGIS_SDK_SCAFFOLD_WEB"):
    pytest.skip(
        "set QGIS_SDK_SCAFFOLD_WEB=1 to install, test and build generated web projects",
        allow_module_level=True,
    )

try:
    from PyQt6.QtCore import QCoreApplication, Qt

    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    import PyQt6.QtWebEngineWidgets  # noqa: F401  (must precede the application)
except ImportError as error:  # pragma: no cover - depends on the host
    pytest.skip(
        f"the generated view needs Qt WebEngine: {error}", allow_module_level=True
    )

SDK_SOURCE = Path(__file__).resolve().parents[1] / "src"
DEADLINE = 30.0


def _find(manager: str) -> str | None:
    found = shutil.which(manager)
    if found is not None:
        return found
    sibling = Path(sys.prefix).parent / "bun" / "bin" / manager
    return str(sibling) if sibling.is_file() else None


MANAGERS = {name: path for name in ("bun", "npm", "pnpm") if (path := _find(name))}
if not MANAGERS:
    pytest.skip(
        "no package manager (bun, npm, pnpm) is available", allow_module_level=True
    )


def _run(executable: str, command: tuple[str, ...], cwd: Path) -> None:
    result = subprocess.run(
        [executable, *command[1:]],
        cwd=cwd,
        env={**os.environ, "NO_COLOR": "1", "CI": "1"},
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
    )
    assert result.returncode == 0, (
        f"{' '.join(command)} in {cwd}:\n{result.stdout}\n{result.stderr}"
    )


@pytest.fixture(scope="module", params=sorted(MANAGERS))
def manager(request: pytest.FixtureRequest) -> str:
    return request.param


@pytest.fixture(scope="module", params=["vanilla", "react"])
def built_project(
    request: pytest.FixtureRequest,
    manager: str,
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Path, str]:
    """Scaffold, install, run Vitest and tsc, build; return (root, framework)."""
    framework = request.param
    placement = "dock" if framework == "react" else "dialog"
    plugin = f"{framework}_demo"
    root = tmp_path_factory.mktemp(manager) / plugin
    write_scaffold(
        ScaffoldOptions.resolve(
            plugin, web=framework, placement=placement, package_manager=manager
        ),
        root,
    )
    web = root / "web"
    executable = MANAGERS[manager]
    _run(executable, install_command(manager), web)
    for script in ("test", "typecheck", "build"):
        _run(executable, script_command(manager, script), web)
    return root, framework


def test_the_build_lands_inside_the_plugin_package(
    built_project: tuple[Path, str],
) -> None:
    root, framework = built_project
    index = root / f"{framework}_demo" / "web" / "index.html"

    assert index.is_file()
    html = index.read_text(encoding="utf-8")
    assert 'src="qrc:///qtwebchannel/qwebchannel.js"' in html
    assert 'src="./assets/' in html  # base "./" so file: pages resolve


def test_the_built_page_answers_a_ping_inside_qgis(
    qgis_app: Any, built_project: tuple[Path, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, framework = built_project
    plugin = f"{framework}_demo"
    placement = "dock" if framework == "react" else "dialog"
    button, output = (
        ("button", "output") if framework == "react" else ("#ping", "#ping-result")
    )
    monkeypatch.syspath_prepend(str(root))
    _forget(plugin)  # the other manager's project used the same package name
    module = importlib.import_module(plugin)

    desktop = module.classFactory(None)
    desktop.initGui()
    widget = module.webview.open_view(desktop.runtime, None, placement=placement)
    try:
        view = (
            widget.widget()
            if placement == "dock"
            else widget.layout().itemAt(0).widget()
        )
        page = view.page()
        loaded: list[bool] = []
        page.loadFinished.connect(loaded.append)
        _pump(qgis_app, lambda: bool(loaded))
        assert loaded == [True], page.url().toString()
        assert page.url().toLocalFile() == str(root / plugin / "web" / "index.html")

        _pump(
            qgis_app,
            lambda: _evaluate(
                qgis_app, page, f"document.querySelector({button!r}) !== null"
            ),
        )
        _evaluate(qgis_app, page, f"document.querySelector({button!r}).click(); true")
        _pump(
            qgis_app,
            lambda: (
                _evaluate(
                    qgis_app, page, f"document.querySelector({output!r}).textContent"
                )
                == "1"
            ),
        )
    finally:
        module.webview.close_view(widget, None)
        desktop.unload()
        qgis_app.processEvents()
        _forget(plugin)
    assert desktop.runtime.state.value == "stopped"


def _forget(package: str) -> None:
    for name in [n for n in sys.modules if n == package or n.startswith(package + ".")]:
        del sys.modules[name]
    importlib.invalidate_caches()


def _pump(app: Any, until: Any) -> None:
    end = time.monotonic() + DEADLINE
    while not until():
        if time.monotonic() > end:
            raise AssertionError("condition not met within the deadline")
        app.processEvents()
        time.sleep(0.005)


def _evaluate(app: Any, page: Any, script: str) -> Any:
    box: list[object] = []
    page.runJavaScript(script, box.append)
    _pump(app, lambda: bool(box))
    return box[0]

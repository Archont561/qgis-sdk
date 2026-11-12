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
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import layers
import pytest
from qgis_sdk.adapters.desktop import host
from qgis_sdk_tools.scaffold import ScaffoldOptions, write_scaffold
from qgis_sdk_tools.scaffold.web import install_command, script_command


class _CcState1:
    """A mutable record shared by the phases of one long function."""

    def __init__(_cc_self, **values):
        _cc_self.__dict__.update(values)


class _CcReturn1:
    """An early return travelling out of a phase."""

    def __init__(_cc_self, value):
        _cc_self.value = value


class _CcBreak1:
    """A loop break travelling out of a phase."""


class _CcContinue1:
    """A loop continue travelling out of a phase."""


def _cc_test_the_built_p_p1(_s1):
    _s1.root, _s1.framework = _s1.built_project
    _s1.plugin = f"{_s1.framework}_demo"
    _s1.placement = "dock" if _s1.framework == "react" else "dialog"
    _s1.button, _s1.output = (
        ("button", "output") if _s1.framework == "react" else ("#ping", "#ping-result")
    )
    _s1.monkeypatch.syspath_prepend(str(_s1.root))
    _forget(_s1.plugin)  # the other manager's project used the same package name

    # The scaffold's module-level application, the only public entry point
    # since the class-based authoring API was retired (TASK-141).
    _s1.desktop = host(f"{_s1.plugin}.plugin:app", placement=_s1.placement)(None)


def _cc_test_the_built_p_p2(_s1):
    _s1.view = (
        _s1.widget.widget()
        if _s1.placement == "dock"
        else _s1.widget.layout().itemAt(0).widget()
    )
    _s1.page = _s1.view.page()
    _s1.loaded: list[bool] = []
    _s1.page.loadFinished.connect(_s1.loaded.append)
    _pump(_s1.qgis_app, lambda: bool(_s1.loaded))
    assert _s1.loaded == [True], _s1.page.url().toString()
    assert _s1.page.url().toLocalFile() == str(
        _s1.root / _s1.plugin / "web" / "index.html"
    )


def _cc_test_the_built_p_p3(_s1):

    _pump(
        _s1.qgis_app,
        lambda: _evaluate(
            _s1.qgis_app, _s1.page, f"document.querySelector({_s1.button!r}) !== null"
        ),
    )
    _evaluate(
        _s1.qgis_app, _s1.page, f"document.querySelector({_s1.button!r}).click(); true"
    )


def _cc_test_the_built_p_p4(_s1):
    _pump(
        _s1.qgis_app,
        lambda: (
            _evaluate(
                _s1.qgis_app,
                _s1.page,
                f"document.querySelector({_s1.output!r}).textContent",
            )
            == "1"
        ),
    )
    _assert_page_took_the_host_palette(_s1.qgis_app, _s1.page)


def _cc_test_the_built_p_p5(_s1):
    _s1.desktop.unload()
    _s1.qgis_app.processEvents()
    _forget(_s1.plugin)


def _cc_test_the_built_p_p6(_s1):
    _s1.desktop.initGui()
    _s1.widget = _s1.desktop.show_view()
    try:
        for _p1 in (
            _cc_test_the_built_p_p2,
            _cc_test_the_built_p_p3,
            _cc_test_the_built_p_p4,
        ):
            _r1 = _p1(_s1)
            if isinstance(_r1, _CcReturn1):
                return _r1
    finally:
        for _p1 in (_cc_test_the_built_p_p5,):
            _p1(_s1)
    assert _s1.desktop.runtime.state.value == "stopped"
    assert _s1.desktop.view is None


class _CcState:
    """A mutable record shared by the phases of one long function."""

    def __init__(_cc_self, **values):
        _cc_self.__dict__.update(values)


class _CcReturn:
    """An early return travelling out of a phase."""

    def __init__(_cc_self, value):
        _cc_self.value = value


class _CcBreak:
    """A loop break travelling out of a phase."""


class _CcContinue:
    """A loop continue travelling out of a phase."""


def _cc_built_project_p1(_s):
    _s.framework = _s.request.param
    _s.placement = "dock" if _s.framework == "react" else "dialog"
    _s.plugin = f"{_s.framework}_demo"
    _s.root = _s.tmp_path_factory.mktemp(_s.manager) / _s.plugin


def _cc_built_project_p2(_s):
    write_scaffold(
        ScaffoldOptions.resolve(
            _s.plugin,
            web=_s.framework,
            placement=_s.placement,
            package_manager=_s.manager,
            sdk_dependency=_s.workspace_bridge,
            ui_dependency=_s.workspace_ui,
        ),
        _s.root,
    )
    _s.web = _s.root / "web"


def _cc_built_project_p3(_s):
    _s.executable = MANAGERS[_s.manager]
    _run(_s.executable, install_command(_s.manager), _s.web)
    for script in ("test", "typecheck", "build"):
        _s.script = script
        _run(_s.executable, script_command(_s.manager, _s.script), _s.web)
    return _CcReturn(_s.root, _s.framework)


def _assert_page_took_the_phase1(app, page, theme):
    assert (
        _evaluate(
            app,
            page,
            "getComputedStyle(document.documentElement)"
            ".getPropertyValue('--qgis-sdk-fg').trim()",
        )
        == theme["palette"]["windowText"]
    )


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

DEADLINE = 30.0


MANAGERS = {
    name: path for name in ("bun", "npm", "pnpm") if (path := layers.find_tool(name))
}
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
    workspace_bridge: str,
    workspace_ui: str,
) -> tuple[Path, str]:
    """Scaffold, install, run Vitest and tsc, build; return (root, framework).

    On the workspace bridge and components (decision-41, decision-47): the
    templates are qualified against what this checkout ships, not the
    releases the scaffold pins.
    """
    _s = _CcState(
        request=request,
        manager=manager,
        tmp_path_factory=tmp_path_factory,
        workspace_bridge=workspace_bridge,
        workspace_ui=workspace_ui,
    )
    for _p in (_cc_built_project_p1, _cc_built_project_p2, _cc_built_project_p3):
        _r = _p(_s)
        if isinstance(_r, _CcReturn):
            return _r.value
    return None


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
    _s1 = _CcState1(
        qgis_app=qgis_app, built_project=built_project, monkeypatch=monkeypatch
    )
    for _p1 in (_cc_test_the_built_p_p1, _cc_test_the_built_p_p6):
        _r1 = _p1(_s1)
        if isinstance(_r1, _CcReturn1):
            return _r1.value
    return None


def _assert_page_took_the_host_palette(app: Any, page: Any) -> None:
    """The page's ``--qgis-sdk-*`` variables match the running palette (TASK-70 AC #2).

    The templates call ``applyHostTheme(qgis)`` on start; once the handshake
    answered, the computed ``--qgis-sdk-bg`` of the document is the host's
    ``window`` colour as :func:`palette_theme` read it, and the side attribute
    says which palette the defaults came from.
    """
    from qgis_sdk.adapters.palette import palette_theme

    theme = palette_theme()
    assert theme is not None
    expected = theme["palette"]["window"]
    read = (
        "getComputedStyle(document.documentElement)"
        ".getPropertyValue('--qgis-sdk-bg').trim()"
    )
    _pump(app, lambda: _evaluate(app, page, read) == expected)
    assert _evaluate(
        app, page, "document.documentElement.getAttribute('data-qgis-sdk-theme')"
    ) == ("dark" if theme["dark"] else "light")
    # The matching foreground came along: the tokens move as a set.
    _assert_page_took_the_phase1(app, page, theme)


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

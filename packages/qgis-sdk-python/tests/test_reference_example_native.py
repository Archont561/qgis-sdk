"""The reference plugin (``examples/simple``) through the whole toolchain (TASK-22).

Opt-in, because it installs the page's pinned dependencies, runs QGIS Desktop
and a real Chromium::

    QGIS_SDK_REFERENCE=1 QT_QPA_PLATFORM=offscreen pytest tests/test_reference_example_native.py

What it proves, in order (task-22 AC #1 and #2):

* ``qgis-sdk new`` writes the project the example was grown from, and the
  example still sits on that layout (the example overlays a fresh scaffold);
* ``check``, ``bridge generate --check``, ``test`` (pure, with the SDK fakes)
  and ``test --target qgis`` (real Processing, real OGR export) are clean;
* the page installs, its Vitest and ``tsc`` pass, ``build`` lands it inside
  the package and ``qgis-sdk build`` ships fixture, page and the vendored
  runtime with the packaged style;
* ``dev --exercise`` starts, reloads, shows and unloads the plugin inside an
  isolated QGIS Desktop profile;
* inside a headless ``QgsApplication`` the *built page* in a ``QWebEngineView``
  and the native dialog QGIS renders for the same action produce the same
  result over one handler, and the fixture is byte-identical afterwards.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from typing import Any

import layers
import pytest
from qgis_sdk.adapters.desktop import host
from qgis_sdk_tools.bundle import VENDOR_PACKAGE
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


def _cc_project_p1(_s1):
    _s1.root = _s1.tmp_path_factory.mktemp("reference") / PLUGIN


def _cc_project_p2(_s1):
    _s1.created = _cli(
        "new",
        str(_s1.root),
        "--title",
        "Simple",
        "--author",
        "qgis-sdk",
        "--email",
        "qgis-sdk@example.invalid",
        "--web",
        "vanilla",
        "--placement",
        "dock",
        "--package-manager",
        "bun",
        "--sdk-dependency",
        _s1.workspace_bridge,
        "--ui-dependency",
        _s1.workspace_ui,
        "--no-input",
        "--no-install",
        cwd=_s1.root.parent,
    )


def _cc_project_p3(_s1):
    assert _s1.created.returncode == 0, _s1.created.stdout + _s1.created.stderr
    _s1.scaffolded = sorted(
        p.relative_to(_s1.root).as_posix() for p in _s1.root.rglob("*") if p.is_file()
    )
    (_s1.root / "tests" / "test_plugin.py").unlink()
    _copy_tree(EXAMPLE, _s1.root)
    assert {"README.md", "pyproject.toml", f"{PLUGIN}/plugin.py"} <= set(_s1.scaffolded)
    assert (
        f"{PLUGIN}/metadata.txt" not in _s1.scaffolded
    )  # rendered by build (decision-43)
    _bun_run(install_command("bun"), _s1.root / "web")
    for script in ("test", "typecheck", "build"):
        _s1.script = script
        _bun_run(script_command("bun", _s1.script), _s1.root / "web")
    return _CcReturn1(_s1.root)


def _CcPhases1():
    return (
        _cc_test_the_page_an_p2,
        _cc_test_the_page_an_p3,
        _cc_test_the_page_an_p4,
        _cc_test_the_page_an_p5,
        _cc_test_the_page_an_p6,
        _cc_test_the_page_an_p7,
    )


def _CcPhases2():
    return (
        _cc_test_the_page_an_p1,
        _cc_test_the_page_an_p9,
        _cc_test_the_page_an_p10,
        _cc_test_the_page_an_p11,
    )


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


def _cc_test_the_page_an_p1(_s):
    from qgis.core import QgsProject

    _s.QgsProject = QgsProject
    from qgis.PyQt.QtWidgets import QPushButton

    _s.QPushButton = QPushButton

    _s.monkeypatch.syspath_prepend(str(_s.project))
    _forget(PLUGIN)
    _s.plugin_module = importlib.import_module(f"{PLUGIN}.plugin")
    _s.fixture = _s.plugin_module.FIXTURE
    _s.before = hashlib.sha256(_s.fixture.read_bytes()).hexdigest()
    _s.exports = _s.tmp_path / "exports"
    _s.exports.mkdir()
    _s.QgsProject.instance().removeAllMapLayers()


def _cc_test_the_page_an_p2(_s):
    _s.page = _s.widget.widget().page()
    _s.loaded: list[bool] = []
    _s.page.loadFinished.connect(_s.loaded.append)
    _pump(_s.qgis_app, lambda: bool(_s.loaded))
    assert _s.loaded == [True], _s.page.url().toString()
    assert _s.page.url().toLocalFile() == str(
        _s.project / PLUGIN / "web" / "index.html"
    )

    # The page: open, buffer, export - every step a declared action.
    _click(_s.qgis_app, _s.page, "#open")
    _s.source_text = _text_when(_s.qgis_app, _s.page, "#source")
    assert _s.source_text == "points (point, EPSG:4326)"
    _click(_s.qgis_app, _s.page, "#buffer")


def _cc_test_the_page_an_p3(_s):
    _s.buffer_text = _text_when(_s.qgis_app, _s.page, "#buffer-result")
    assert _s.buffer_text.endswith(f"(polygon, {WORKING_CRS})")
    _click(_s.qgis_app, _s.page, "#export")
    _s.export_text = _text_when(_s.qgis_app, _s.page, "#export-result")
    assert _s.export_text == f"GPKG: {_s.exports / 'buffer.gpkg'}"
    assert (
        _evaluate(_s.qgis_app, _s.page, "document.querySelector('#error').textContent")
        == ""
    )

    _s.layer_ids = list(_s.QgsProject.instance().mapLayers())
    assert len(_s.layer_ids) == 2


def _cc_test_the_page_an_p4(_s):
    _s.web_output = next(
        layer
        for layer in _s.QgsProject.instance().mapLayers().values()
        if layer.geometryType().name.lower().startswith("polygon")
    )
    _s.source_layer = next(
        layer
        for layer in _s.QgsProject.instance().mapLayers().values()
        if layer is not _s.web_output
    )
    assert _s.web_output.renderer().symbol().symbolLayer(0).layerType() == "SimpleFill"


def _cc_test_the_page_an_p5(_s):

    # The native dialog for the same action, dispatched to the same handler.
    _s.surfaces_module = importlib.import_module(f"{PLUGIN}.surfaces")
    _s.dialog = _s.desktop.context.ui.open(_s.surfaces_module.BufferDialog)
    _s.dialog.form.field("layer_id").widget.setLayer(_s.source_layer)
    _s.dialog.form.field("distance_metres").widget.setValue(500.0)
    _s.dialog.form.field("working_crs").widget.setCrs(_s.web_output.crs())
    _s.dialog.form.widget.window().findChild(_s.QPushButton, "buttons/run").click()
    _s.qgis_app.processEvents()


def _cc_test_the_page_an_p6(_s):
    _s.native_output = next(
        layer
        for layer in _s.QgsProject.instance().mapLayers().values()
        if layer not in (_s.source_layer, _s.web_output)
    )
    _s.native_output = _s.desktop.context.layers.layer(_s.native_output.id())

    _s.native_layer = _s.QgsProject.instance().mapLayer(_s.native_output.id)
    assert _s.native_output.geometry_type == "polygon"
    assert _s.native_output.crs == WORKING_CRS
    assert _s.native_layer.featureCount() == _s.web_output.featureCount() == 3


def _cc_test_the_page_an_p7(_s):
    assert (
        _s.native_layer.renderer().symbol().symbolLayer(0).layerType() == "SimpleFill"
    )
    assert len(_s.QgsProject.instance().mapLayers()) == 3
    assert _s.source_layer.featureCount() == 3


def _cc_test_the_page_an_p8(_s):
    _s.desktop.unload()
    _s.qgis_app.processEvents()
    _s.QgsProject.instance().removeAllMapLayers()
    _forget(PLUGIN)


def _cc_test_the_page_an_p9(_s):

    _s.desktop = host(f"{PLUGIN}.plugin:app", placement="dock")(None)
    _s.desktop.initGui()
    _s.desktop.context.settings.set(
        _s.plugin_module.EXPORT_DIRECTORY_KEY, str(_s.exports)
    )
    _s.widget = _s.desktop.show_view()


def _cc_test_the_page_an_p10(_s):
    try:
        for _p in _CcPhases1():
            _r = _p(_s)
            if isinstance(_r, _CcReturn):
                return _r
    finally:
        for _p in (_cc_test_the_page_an_p8,):
            _p(_s)
    assert _s.desktop.view is None

    assert _s.desktop.runtime.state.value == "stopped"
    assert hashlib.sha256(_s.fixture.read_bytes()).hexdigest() == _s.before


def _cc_test_the_page_an_p11(_s):
    assert sorted(p.name for p in _s.exports.iterdir()) == ["buffer.gpkg"]


pytestmark = pytest.mark.webengine

if not os.environ.get("QGIS_SDK_REFERENCE"):
    pytest.skip(
        "set QGIS_SDK_REFERENCE=1 to run the reference plugin through the toolchain",
        allow_module_level=True,
    )

try:
    from PyQt6.QtCore import QCoreApplication, Qt

    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    import PyQt6.QtWebEngineWidgets  # noqa: F401  (must precede the application)
except ImportError as error:  # pragma: no cover - depends on the host
    pytest.skip(f"the page needs Qt WebEngine: {error}", allow_module_level=True)

EXAMPLE = layers.PACKAGES_ROOT.parent / "examples" / "simple"
PLUGIN = "simple"
DEADLINE = 30.0
WORKING_CRS = "EPSG:3857"
SKIPPED = shutil.ignore_patterns(
    "node_modules", "dist", ".qgis-sdk", "__pycache__", ".pytest_cache", "web"
)


BUN = layers.find_tool("bun")
if BUN is None:
    pytest.skip("bun is not available for the page", allow_module_level=True)


def _cli(
    *args: str, cwd: Path, timeout: float = 600
) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTEST_")}
    env["PYTHONPATH"] = layers.source_path()
    env["PATH"] = os.pathsep.join((str(Path(BUN).parent), env.get("PATH", "")))
    return subprocess.run(
        [sys.executable, "-m", "qgis_sdk_tools", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


def _bun_run(command: tuple[str, ...], cwd: Path) -> None:
    result = subprocess.run(
        [BUN, *command[1:]],
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


def _copy_tree(source: Path, target: Path) -> None:
    """The example over the scaffold, leaving the plugin's built page out.

    ``web/package.json`` stays the scaffold's: the example's says
    ``workspace:*``, which only resolves inside this repository's Bun
    workspace, while the scaffold here was given the packed bridge instead.
    """
    for item in source.iterdir():
        if item.name in {"node_modules", "dist", ".qgis-sdk", "__pycache__"}:
            continue
        if item.is_dir():
            ignore = (
                SKIPPED
                if item.name == PLUGIN
                else shutil.ignore_patterns(
                    "node_modules", "dist", "__pycache__", "package.json", "bun.lock"
                )
            )
            shutil.copytree(item, target / item.name, dirs_exist_ok=True, ignore=ignore)
        else:
            shutil.copy2(item, target / item.name)


@pytest.fixture(scope="module")
def project(
    tmp_path_factory: pytest.TempPathFactory, workspace_bridge: str, workspace_ui: str
) -> Path:
    """``qgis-sdk new`` with the example's options, the example copied on top."""
    _s1 = _CcState1(
        tmp_path_factory=tmp_path_factory,
        workspace_bridge=workspace_bridge,
        workspace_ui=workspace_ui,
    )
    for _p1 in (_cc_project_p1, _cc_project_p2, _cc_project_p3):
        _r1 = _p1(_s1)
        if isinstance(_r1, _CcReturn1):
            return _r1.value
    return None


def test_the_example_keeps_the_scaffold_layout(project: Path) -> None:
    for relative in (
        f"{PLUGIN}/__init__.py",
        f"{PLUGIN}/plugin.py",
        f"{PLUGIN}/data/points.geojson",
        f"{PLUGIN}/web/index.html",
        "web/src/bridge.schema.ts",
        "tests/conftest.py",
    ):
        assert (project / relative).is_file(), relative


def test_check_bindings_and_both_test_targets_are_clean(project: Path) -> None:
    checked = _cli("check", cwd=project)
    assert checked.returncode == 0, checked.stdout + checked.stderr
    assert "no problems" in checked.stdout

    bindings = _cli(
        "bridge",
        "generate",
        "--out",
        "web/src/bridge.schema.ts",
        "--check",
        cwd=project,
    )
    assert bindings.returncode == 0, bindings.stdout + bindings.stderr

    pure = _cli("test", "-q", "-p", "no:faulthandler", cwd=project)
    assert pure.returncode == 0, pure.stdout + pure.stderr
    assert "20 passed" in pure.stdout

    native = _cli(
        "test", "--target", "qgis", "-q", "-p", "no:faulthandler", cwd=project
    )
    assert native.returncode == 0, native.stdout + native.stderr
    assert "7 passed" in native.stdout


def test_build_ships_fixture_page_and_the_packaged_style(project: Path) -> None:
    built = _cli("build", cwd=project)
    assert built.returncode == 0, built.stdout + built.stderr
    archive = project / "dist" / f"{PLUGIN}-0.1.0.zip"
    assert archive.is_file()
    with zipfile.ZipFile(archive) as zf:
        entries = set(zf.namelist())
    vendored = f"{PLUGIN}/{VENDOR_PACKAGE}/qgis_sdk"
    assert f"{PLUGIN}/metadata.txt" in entries
    assert f"{PLUGIN}/data/points.geojson" in entries
    assert f"{PLUGIN}/web/index.html" in entries
    assert f"{vendored}/resources/styles/reference-polygon-output.qml" in entries
    assert f"{PLUGIN}/workflow.py" in entries
    assert not any("/tests/" in name for name in entries)


def test_dev_starts_reloads_shows_and_unloads_inside_desktop(
    project: Path, tmp_path: Path
) -> None:
    report_path = tmp_path / "dev-report.json"

    result = _cli("dev", "--exercise", str(report_path), cwd=project)

    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["error"] is None
    assert report["smoke"] is True
    assert report["started"] is True
    assert report["reload_ok"] is True
    assert report["view_shown"] is True
    assert report["unloaded"] is True
    assert report["actions"] == [
        "buffer",
        "choose_export_directory",
        "export_layer",
        "open_fixture",
        "selected_features",
    ]
    assert "(hot module replacement)" in result.stderr


def test_the_page_and_the_native_dialog_share_one_workflow(
    qgis_app: Any, project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _s = _CcState(**locals())
    for _p in _CcPhases2():
        _r = _p(_s)
        if isinstance(_r, _CcReturn):
            return _r.value
    return None


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


def _click(app: Any, page: Any, selector: str) -> None:
    _pump(
        app,
        lambda: _evaluate(app, page, f"document.querySelector({selector!r}) !== null"),
    )
    _evaluate(app, page, f"document.querySelector({selector!r}).click(); true")


def _text_when(app: Any, page: Any, selector: str) -> str:
    script = f"document.querySelector({selector!r}).textContent"
    _pump(app, lambda: _evaluate(app, page, script) != "")
    return str(_evaluate(app, page, script))

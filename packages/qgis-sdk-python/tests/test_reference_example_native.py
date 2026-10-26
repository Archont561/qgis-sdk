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
from qgis_sdk_tools.bundle import VENDOR_PACKAGE
from qgis_sdk_tools.scaffold.web import install_command, script_command

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
def project(tmp_path_factory: pytest.TempPathFactory, workspace_bridge: str) -> Path:
    """``qgis-sdk new`` with the example's options, the example copied on top."""
    root = tmp_path_factory.mktemp("reference") / PLUGIN
    created = _cli(
        "new",
        str(root),
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
        workspace_bridge,
        "--no-input",
        "--no-install",
        cwd=root.parent,
    )
    assert created.returncode == 0, created.stdout + created.stderr
    scaffolded = sorted(
        p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()
    )
    (root / "tests" / "test_plugin_smoke.py").unlink()
    _copy_tree(EXAMPLE, root)
    assert {"README.md", "pyproject.toml", f"{PLUGIN}/metadata.txt"} <= set(scaffolded)
    _bun_run(install_command("bun"), root / "web")
    for script in ("test", "typecheck", "build"):
        _bun_run(script_command("bun", script), root / "web")
    return root


def test_the_example_keeps_the_scaffold_layout(project: Path) -> None:
    for relative in (
        f"{PLUGIN}/__init__.py",
        f"{PLUGIN}/plugin.py",
        f"{PLUGIN}/webview.py",
        f"{PLUGIN}/metadata.txt",
        f"{PLUGIN}/data/points.geojson",
        f"{PLUGIN}/web/index.html",
        "web/src/bridge.ts",
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
        "--plugin",
        f"{PLUGIN}.plugin:SimplePlugin",
        "--out",
        "web/src/bridge.ts",
        "--check",
        cwd=project,
    )
    assert bindings.returncode == 0, bindings.stdout + bindings.stderr

    pure = _cli("test", "-q", "-p", "no:faulthandler", cwd=project)
    assert pure.returncode == 0, pure.stdout + pure.stderr
    assert "17 passed" in pure.stdout

    native = _cli(
        "test", "--target", "qgis", "-q", "-p", "no:faulthandler", cwd=project
    )
    assert native.returncode == 0, native.stdout + native.stderr
    assert "5 passed" in native.stdout


def test_build_ships_fixture_page_and_the_packaged_style(project: Path) -> None:
    built = _cli("build", cwd=project)
    assert built.returncode == 0, built.stdout + built.stderr
    archive = project / "dist" / f"{PLUGIN}-0.1.0.zip"
    assert archive.is_file()
    with zipfile.ZipFile(archive) as zf:
        entries = set(zf.namelist())
    vendored = f"{PLUGIN}/{VENDOR_PACKAGE}/qgis_sdk"
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
    from qgis.core import QgsProject
    from qgis_sdk.adapters.qgis.ui import NativeForms

    monkeypatch.syspath_prepend(str(project))
    _forget(PLUGIN)
    module = importlib.import_module(PLUGIN)
    plugin_module = importlib.import_module(f"{PLUGIN}.plugin")
    fixture = plugin_module.FIXTURE
    before = hashlib.sha256(fixture.read_bytes()).hexdigest()
    exports = tmp_path / "exports"
    exports.mkdir()
    QgsProject.instance().removeAllMapLayers()

    desktop = module.classFactory(None)
    desktop.initGui()
    desktop.runtime.instance.ctx.settings.set(
        plugin_module.EXPORT_DIRECTORY_KEY, str(exports)
    )
    widget = module.webview.open_view(desktop.runtime, None, placement="dock")
    try:
        page = widget.widget().page()
        loaded: list[bool] = []
        page.loadFinished.connect(loaded.append)
        _pump(qgis_app, lambda: bool(loaded))
        assert loaded == [True], page.url().toString()
        assert page.url().toLocalFile() == str(project / PLUGIN / "web" / "index.html")

        # The page: open, buffer, export - every step a declared action.
        _click(qgis_app, page, "#open")
        source_text = _text_when(qgis_app, page, "#source")
        assert source_text == "points (point, EPSG:4326)"
        _click(qgis_app, page, "#buffer")
        buffer_text = _text_when(qgis_app, page, "#buffer-result")
        assert buffer_text.endswith(f"(polygon, {WORKING_CRS})")
        _click(qgis_app, page, "#export")
        export_text = _text_when(qgis_app, page, "#export-result")
        assert export_text == f"GPKG: {exports / 'buffer.gpkg'}"
        assert (
            _evaluate(qgis_app, page, "document.querySelector('#error').textContent")
            == ""
        )

        layer_ids = list(QgsProject.instance().mapLayers())
        assert len(layer_ids) == 2
        web_output = next(
            layer
            for layer in QgsProject.instance().mapLayers().values()
            if layer.geometryType().name.lower().startswith("polygon")
        )
        source_layer = next(
            layer
            for layer in QgsProject.instance().mapLayers().values()
            if layer is not web_output
        )
        assert web_output.renderer().symbol().symbolLayer(0).layerType() == "SimpleFill"

        # The native dialog for the same action, dispatched to the same handler.
        forms = NativeForms(desktop.runtime)
        dialog = forms.render("buffer")
        dialog.widget("layer_id").setLayer(source_layer)
        dialog.widget("distance_metres").setValue(500.0)
        dialog.widget("working_crs").setCrs(web_output.crs())
        native_output = forms.dispatch("buffer", dialog.values())

        native_layer = QgsProject.instance().mapLayer(native_output.id)
        assert native_output.geometry_type == "polygon"
        assert native_output.crs == WORKING_CRS
        assert native_layer.featureCount() == web_output.featureCount() == 3
        assert (
            native_layer.renderer().symbol().symbolLayer(0).layerType() == "SimpleFill"
        )
        assert len(QgsProject.instance().mapLayers()) == 3
        assert source_layer.featureCount() == 3
    finally:
        module.webview.close_view(widget, None)
        desktop.unload()
        qgis_app.processEvents()
        QgsProject.instance().removeAllMapLayers()
        _forget(PLUGIN)

    assert desktop.runtime.state.value == "stopped"
    assert hashlib.sha256(fixture.read_bytes()).hexdigest() == before
    assert sorted(p.name for p in exports.iterdir()) == ["buffer.gpkg"]


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

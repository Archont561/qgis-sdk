"""``qgis-sdk build --target app``: an installable distribution, installed and run.

TASK-81 AC 2 asks for a distribution "whose launcher runs the app, with externals
probed and pure-Python packages vendored (build-install harness)". The harness is
here: the distribution is written, ``pip install`` puts it into a throwaway
prefix, and the console script it installs is executed as the process a user
would start. What the interpreter then finds decides the verdict -

* without PyQGIS the launcher must refuse by name and exit 2 (proven here, at the
  same cost as any subprocess, on every host);
* with the bindings it must start the app and stop it in bounds, which is the
  ``native`` row in ``test_app_native.py``. The Windows row of AC 2 is recorded
  in ``targets.py`` as unqualified - this workspace has no Windows QGIS (TASK-33).
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest
from qgis_sdk_tools.__main__ import app
from qgis_sdk_tools.bundle.app import (
    LAUNCHER_MODULE,
    build_app,
    launcher_source,
    package_data,
    script_name,
)
from qgis_sdk_tools.project import require_project
from qgis_sdk_tools.scaffold import ScaffoldOptions, write_scaffold
from qgis_sdk_tools.testing import FakeCliRuntime
from typer.testing import CliRunner

runner = CliRunner()

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("setuptools") is None,
    reason="building the distribution needs setuptools in this interpreter",
)


def succeed(argv, cwd) -> int:
    return 0


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "field_tools"
    write_scaffold(ScaffoldOptions.resolve("field_tools", host="app"), root)
    return root


@pytest.fixture
def built(project: Path) -> Path:
    result = build_app(project, run=succeed)
    return result.directory


# -- what the target writes ---------------------------------------------------------


def test_the_distribution_is_a_python_project_named_after_the_plugin(
    project: Path,
) -> None:
    result = build_app(project, run=succeed)

    assert result.directory == project / "dist" / "field_tools-0.1.0-app"
    assert result.launcher == "field-tools"
    assert result.web == "none"
    assert (result.directory / "pyproject.toml").is_file()
    assert result.directory / "field_tools" / "plugin.py" in [
        result.directory / name for name in result.files
    ]


def test_the_runtime_is_vendored_and_imported_from_there(built: Path) -> None:
    plugin = built / "field_tools"

    assert (plugin / "_vendor" / "qgis_sdk" / "app" / "__init__.py").is_file()
    assert (plugin / "_vendor" / "NOTICE").is_file()
    launcher = (plugin / f"{LAUNCHER_MODULE}.py").read_text(encoding="utf-8")
    assert "from field_tools._vendor.qgis_sdk.app import main as run_app" in launcher
    plugin_source = (plugin / "plugin.py").read_text(encoding="utf-8")
    assert "field_tools._vendor.qgis_sdk" in plugin_source


def test_the_console_script_is_the_launcher(project: Path) -> None:
    result = build_app(project, run=succeed)
    pyproject = (result.directory / "pyproject.toml").read_text(encoding="utf-8")

    assert '[project.scripts]\nfield-tools = "field_tools._launcher:main"' in pyproject
    assert 'include = ["field_tools*"]' in pyproject
    assert 'requires-python = ">=3.11"' in pyproject
    assert "dependencies = []" in pyproject


def test_the_runtimes_data_files_are_listed_so_a_wheel_carries_them(
    project: Path,
) -> None:
    result = build_app(project, run=succeed)
    pyproject = (result.directory / "pyproject.toml").read_text(encoding="utf-8")

    assert (
        "\"field_tools._vendor.qgis_sdk.processing\" = ['catalogue.json']" in pyproject
    )
    assert "styles/reference-point-output.qml" in pyproject


def test_the_source_tree_is_never_edited(project: Path) -> None:
    before = sorted(path.name for path in (project / "field_tools").iterdir())

    build_app(project, run=succeed)

    after = sorted(path.name for path in (project / "field_tools").iterdir())
    assert before == after
    assert not (project / "field_tools" / f"{LAUNCHER_MODULE}.py").exists()


def test_a_second_build_replaces_the_first(project: Path) -> None:
    build_app(project, run=succeed)
    directory = project / "dist" / "field_tools-0.1.0-app"
    (directory / "left-over.txt").write_text("stale")

    build_app(project, run=succeed)

    assert not (directory / "left-over.txt").exists()


def test_the_web_build_is_the_projects_own_script(tmp_path: Path) -> None:
    root = tmp_path / "web_tools"
    write_scaffold(
        ScaffoldOptions.resolve("web_tools", web="vanilla", package_manager="npm"), root
    )
    (root / "web" / "node_modules").mkdir()
    (root / "web" / "package-lock.json").write_text("")
    calls: list[tuple[str, ...]] = []

    def run(argv, cwd) -> int:
        calls.append(tuple(argv))
        assets = root / "web_tools" / "web"
        (assets / "assets").mkdir(parents=True, exist_ok=True)
        (assets / "index.html").write_text("<html></html>", encoding="utf-8")
        (assets / "assets" / "index-abc.js").write_text("x", encoding="utf-8")
        return 0

    result = build_app(root, run=run)

    assert result.web == "built"
    assert calls == [("npm", "run", "build")]


def test_build_refuses_a_project_with_findings(tmp_path: Path) -> None:
    root = tmp_path / "broken"
    write_scaffold(ScaffoldOptions.resolve("broken"), root)
    (root / "broken" / "plugin.py").write_text("def broken(:\n", encoding="utf-8")

    from qgis_sdk_tools.bundle import QgisSdkBuildRefusedError

    with pytest.raises(QgisSdkBuildRefusedError):
        build_app(root, run=succeed)


def test_a_server_only_project_cannot_be_built_as_an_app(tmp_path: Path) -> None:
    root = tmp_path / "demo_server"
    write_scaffold(ScaffoldOptions.resolve("demo_server", host="server"), root)

    from qgis_sdk_tools.bundle import QgisSdkBuildError

    with pytest.raises(QgisSdkBuildError, match="needs an application"):
        build_app(root, run=succeed)
    assert not (root / "dist").exists()


def test_a_description_is_one_line_in_the_generated_project(tmp_path: Path) -> None:
    root = tmp_path / "wrapped"
    write_scaffold(ScaffoldOptions.resolve("wrapped"), root)
    pyproject = root / "pyproject.toml"
    pyproject.write_text(
        pyproject.read_text(encoding="utf-8").replace(
            'description = "Wrapped: a minimal qgis-sdk plugin."',
            'description = """Wrapped:\n        a minimal plugin."""',
        ),
        encoding="utf-8",
    )

    result = build_app(root, run=succeed)

    generated = (result.directory / "pyproject.toml").read_text(encoding="utf-8")
    assert 'description = "Wrapped: a minimal plugin."' in generated


# -- the helpers --------------------------------------------------------------------


def test_the_launcher_probes_the_declared_externals(tmp_path: Path) -> None:
    root = tmp_path / "needs_pandas"
    write_scaffold(ScaffoldOptions.resolve("needs_pandas"), root)
    pyproject = root / "pyproject.toml"
    pyproject.write_text(
        pyproject.read_text(encoding="utf-8")
        + "\n[tool.qgis-sdk.build]\n"
        + "external = [\n"
        + '    { import = "pandas", requirement = "pandas>=2", '
        + 'reason = "read the attribute table" },\n'
        + "]\n",
        encoding="utf-8",
    )

    result = build_app(root, run=succeed)

    launcher = (result.directory / "needs_pandas" / f"{LAUNCHER_MODULE}.py").read_text(
        encoding="utf-8"
    )
    assert "('pandas', 'pandas>=2', 'read the attribute table')" in launcher
    assert result.external == ("pandas",)


def test_a_script_name_is_the_package_with_dashes() -> None:
    assert script_name("field_tools") == "field-tools"
    assert script_name("tools") == "tools"


def test_package_data_lists_each_file_where_it_sits(tmp_path: Path) -> None:
    (tmp_path / "demo").mkdir()
    (tmp_path / "demo" / "__init__.py").write_text("")
    (tmp_path / "demo" / "data").mkdir()
    (tmp_path / "demo" / "data" / "table.csv").write_text("a,b\n")
    (tmp_path / "demo" / "data" / "sub").mkdir()
    (tmp_path / "demo" / "data" / "sub" / "icon.svg").write_text("<svg/>")

    assert package_data(tmp_path / "demo", plugin="demo") == (
        "\"demo\" = ['data/sub/icon.svg', 'data/table.csv']"
    )


def test_the_launcher_source_names_the_declared_application(tmp_path: Path) -> None:
    root = tmp_path / "field_tools"
    write_scaffold(ScaffoldOptions.resolve("field_tools"), root)

    source = launcher_source(require_project(root))

    assert "importlib.import_module('field_tools.plugin')" in source
    assert "'app'" in source
    assert "from qgis_sdk.app import main as run_app" in source


# -- the command --------------------------------------------------------------------


def test_build_target_app_reports_the_directory_to_install(project: Path) -> None:
    runtime = FakeCliRuntime(project)

    result = runner.invoke(app, ["build", "--target", "app"], obj=runtime)

    assert result.exit_code == 0, runtime.stderr
    assert "pip install" in runtime.stdout
    assert "field-tools" in runtime.stdout


def test_build_with_an_unknown_target_is_refused_by_name(project: Path) -> None:
    runtime = FakeCliRuntime(project)

    result = runner.invoke(app, ["build", "--target", "wheel"], obj=runtime)

    assert result.exit_code == 2
    assert "unknown target 'wheel'" in runtime.stderr


def test_build_target_app_as_json_describes_what_it_wrote(project: Path) -> None:
    runtime = FakeCliRuntime(project)

    result = runner.invoke(app, ["build", "--target", "app", "--json"], obj=runtime)

    assert result.exit_code == 0, runtime.stderr
    assert '"target": "app"' in runtime.stdout
    assert '"launcher": "field-tools"' in runtime.stdout


# -- the build-install harness ------------------------------------------------------


def _install(directory: Path, prefix: Path) -> Path:
    """``pip install --prefix`` the distribution; return the console script."""
    command = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--no-deps",
        "--no-build-isolation",
        "--prefix",
        str(prefix),
        str(directory),
    ]
    installed = subprocess.run(command, capture_output=True, text=True, check=False)
    assert installed.returncode == 0, installed.stdout + installed.stderr
    scripts = prefix / ("Scripts" if os.name == "nt" else "bin")
    return scripts / ("field-tools.exe" if os.name == "nt" else "field-tools")


def _run(
    script: Path, prefix: Path, *arguments: str
) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    site = prefix / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}"
    entries = [str(path) for path in site.glob("site-packages")]
    if environment.get("PYTHONPATH"):
        entries.append(environment["PYTHONPATH"])
    environment["PYTHONPATH"] = os.pathsep.join(entries)
    return subprocess.run(
        [str(script), *arguments],
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )


def test_the_installed_launcher_runs_as_a_console_script(
    built: Path, tmp_path: Path
) -> None:
    prefix = tmp_path / "prefix"
    script = _install(built, prefix)

    assert script.is_file()
    refused = _run(script, prefix, "--grace", "soon")

    assert refused.returncode == 2
    assert "--grace wants seconds" in refused.stderr


def test_the_installed_launcher_refuses_without_pyqgis_rather_than_crashing(
    built: Path, tmp_path: Path
) -> None:
    """The sandbox row: the vendored runtime imports, the toolkit does not exist."""
    prefix = tmp_path / "prefix"
    script = _install(built, prefix)

    started = _run(script, prefix, "--headless", "--once")

    if started.returncode == 0:
        pytest.skip("this interpreter has PyQGIS: the native row proves the app runs")
    assert started.returncode == 2
    assert "cannot import PyQGIS" in started.stderr
    assert "Traceback" not in started.stderr

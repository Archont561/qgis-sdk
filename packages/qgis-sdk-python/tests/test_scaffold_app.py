"""``qgis-sdk new --host app``: a project whose entry is a standalone application.

decision-52 point 3 makes the app the third host one plugin class runs on. The
generated project says so in the two places that matter: ``hosts = ["app"]`` in
``pyproject.toml``, and ``<plugin>/__main__.py`` - the entry ``python -m
<plugin>``, ``qgis-sdk run`` and a built distribution's console script all call -
which hands argv to ``qgis_sdk.app`` instead of parsing it itself.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from qgis_sdk_tools.check import check_project
from qgis_sdk_tools.scaffold import ScaffoldOptions, plan_scaffold, write_scaffold
from qgis_sdk_tools.scaffold.options import QgisSdkScaffoldError


def app_options(**given: object) -> ScaffoldOptions:
    return ScaffoldOptions.resolve("field_tools", host="app", **given)  # type: ignore[arg-type]


def plan_text(options: ScaffoldOptions) -> dict[str, str]:
    return {file.path: file.content for file in plan_scaffold(options)}


def test_the_project_declares_the_app_host() -> None:
    planned = plan_text(app_options())

    assert 'hosts = ["app"]' in planned["pyproject.toml"]
    assert 'plugin = "field_tools.plugin:app"' in planned["pyproject.toml"]


def test_the_entry_is_a_main_that_hands_argv_to_the_app_host() -> None:
    source = plan_text(app_options())["field_tools/__main__.py"]

    assert "from qgis_sdk.app import main as run_app" in source
    assert "from .plugin import app" in source
    assert "return run_app(app, argv)" in source
    assert 'if __name__ == "__main__":' in source


def test_the_package_stays_import_only() -> None:
    """There is no QGIS to call a factory: no classFactory, no serverClassFactory."""
    planned = plan_text(app_options())

    assert planned["field_tools/__init__.py"] == ""


def test_the_starter_test_drives_the_app_host_with_a_fake_backend() -> None:
    source = plan_text(app_options())["tests/test_plugin.py"]

    assert "FakeAppBackend" in source
    assert "run(app, backend=backend, once=True)" in source
    assert "pytest.mark" not in source  # no Qt marker: the fake needs no QGIS
    assert "classFactory" not in source


def test_a_native_ui_and_an_algorithm_are_allowed_on_the_app_host() -> None:
    options = app_options(ui="native", algorithm=True)

    assert options.host == "app"
    planned = plan_text(options)
    assert "field_tools/ui.py" in planned
    assert "field_tools/algorithms.py" in planned
    assert '"open_ping"' in planned["tests/test_plugin.py"]


def test_a_web_page_still_needs_the_desktop_host() -> None:
    with pytest.raises(QgisSdkScaffoldError, match="needs the desktop host"):
        app_options(web="vanilla")


def test_an_unknown_host_names_the_choices() -> None:
    with pytest.raises(QgisSdkScaffoldError, match="desktop, server, app"):
        ScaffoldOptions.resolve("field_tools", host="mobile")


def test_the_generated_project_passes_its_own_check(tmp_path: Path) -> None:
    root = tmp_path / "field_tools"
    write_scaffold(app_options(), root)

    report = check_project(root)

    assert [diagnostic.rule for diagnostic in report.diagnostics] == []


def test_the_generated_project_imports_without_qgis(tmp_path: Path) -> None:
    """The app entry imports the runtime only: a QGIS-free host can read it."""
    root = tmp_path / "field_tools"
    write_scaffold(app_options(), root)
    sys.path.insert(0, str(root))
    try:
        from field_tools.plugin import app as application

        assert application.describe().id == "field_tools"
    finally:
        sys.path.remove(str(root))
        for name in [
            name for name in sys.modules if name.split(".")[0] == "field_tools"
        ]:
            del sys.modules[name]

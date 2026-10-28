"""Static checks understand application action declarations."""

from pathlib import Path

from qgis_sdk_tools.check import check_project
from qgis_sdk_tools.scaffold import ScaffoldOptions, write_scaffold


def test_check_warns_for_bound_application_action_with_inputs(tmp_path: Path) -> None:
    write_scaffold(ScaffoldOptions.resolve("app_checked"), tmp_path)
    module = tmp_path / "app_checked" / "plugin.py"
    module.write_text(
        module.read_text()
        + """
from qgis_sdk import toolbar

@toolbar
@app.action(id="typed", title="Typed")
def typed(ctx: PluginContext, value: int) -> int:
    return value
"""
    )
    assert "UI003" in [item.rule for item in check_project(tmp_path).diagnostics]


def test_check_recognizes_annotated_plugin_assignment(tmp_path: Path) -> None:
    write_scaffold(ScaffoldOptions.resolve("app_checked"), tmp_path)
    module = tmp_path / "app_checked" / "plugin.py"
    source = module.read_text().replace(
        "app = QgisSdkPlugin(", "app: QgisSdkPlugin = QgisSdkPlugin("
    )
    module.write_text(
        source
        + """
from qgis_sdk import toolbar

@toolbar
@app.action(id="typed", title="Typed")
def typed(ctx: PluginContext, value: int) -> int:
    return value
"""
    )
    assert "UI003" in [item.rule for item in check_project(tmp_path).diagnostics]


def test_check_recognizes_imported_group_without_importing_project(
    tmp_path: Path,
) -> None:
    write_scaffold(ScaffoldOptions.resolve("app_checked"), tmp_path)
    package = tmp_path / "app_checked"
    (package / "groups.py").write_text(
        "from qgis_sdk import QgisSdkPlugin\n"
        "raise RuntimeError('static checks must not execute this')\n"
        "reports = QgisSdkPlugin()\n"
    )
    module = package / "plugin.py"
    module.write_text(
        module.read_text()
        + """
from .groups import reports as routed
from qgis_sdk import toolbar

@toolbar
@routed.action(id="typed", title="Typed")
def typed(ctx: PluginContext, value: int) -> int:
    return value
"""
    )
    assert "UI003" in [item.rule for item in check_project(tmp_path).diagnostics]

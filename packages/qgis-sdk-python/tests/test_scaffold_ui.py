"""``qgis-sdk new --ui native``: one bound Dialog in pure PyQt (TASK-67).

decision-55 made surfaces plain classes with ``self.ctx`` bound by the host
and decision-45 put ``@toolbar``/``@menu`` on actions and surfaces; the
starter shows both: ``ui.py`` with a ``Dialog`` subclass on the Plugins menu,
the plugin listing it in ``surfaces`` and a toolbar action that opens it,
and a test over ``FakeUi`` that proves it without QGIS.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import layers
import pytest
from qgis_sdk_tools.__main__ import app
from qgis_sdk_tools.check import check_project
from qgis_sdk_tools.scaffold import ScaffoldOptions, plan_scaffold, write_scaffold
from qgis_sdk_tools.scaffold.options import QgisSdkScaffoldError
from typer.testing import CliRunner


class _CcState:
    """A mutable record shared by the phases of one long function."""

    def __init__(_cc_self, **values):
        _cc_self.__dict__.update(values)


class _CcReturn:
    """An early return travelling out of a phase."""

    def __init__(_cc_self, value):
        _cc_self.value = value


def _cc_test_the_starter_p1(_s):
    import importlib

    _s.importlib = importlib

    from qgis_sdk.core import PluginContext, PluginRuntime, ResourceScope

    _s.PluginContext = PluginContext
    _s.PluginRuntime = PluginRuntime
    _s.ResourceScope = ResourceScope
    from qgis_sdk.testing import RecordingNotifications, build_surface, fake_ui_context

    _s.RecordingNotifications = RecordingNotifications
    _s.build_surface = build_surface
    _s.fake_ui_context = fake_ui_context
    from qgis_sdk.ui import ui_snapshot

    _s.ui_snapshot = ui_snapshot

    _s.project = _s.tmp_path / "project"
    write_scaffold(ScaffoldOptions.resolve("demo_tools", ui="native"), _s.project)
    _s.monkeypatch.syspath_prepend(str(_s.project))
    _s.plugin_module = _s.importlib.import_module("demo_tools.plugin")
    _s.ui_module = _s.importlib.import_module("demo_tools.ui")
    _s.importlib.reload(_s.plugin_module)


def _cc_test_the_starter_p2(_s):

    _s.scope = _s.ResourceScope()
    _s.runtime = _s.PluginRuntime(
        _s.plugin_module.app,
        _s.PluginContext(_s.RecordingNotifications(_s.scope), _s.scope),
    )
    _s.runtime.start()


def _cc_test_the_starter_p3(_s):
    try:
        _s.ctx = _s.fake_ui_context(_s.scope.child(), runtime=_s.runtime)
        _s.built = _s.build_surface(
            _s.ui_module.PingDialog, _s.ctx, initial={"value": 7}
        )
        _s.dialog = _s.built.surface
        assert _s.dialog.value.value() == 7
        assert _s.dialog.form.fields == (_s.dialog.value,)
        _s.dialog.value.set_value(3)
        _s.dialog.ping.click()
        assert [line for line in _s.dialog.answers.lines()] == ["[info] pong value=3"]
        _s.names = [node["name"] for node in _s.ui_snapshot(_s.built.root)["children"]]
        assert _s.names == ["form", "ping", "answers"]
    finally:
        _s.runtime.unload()
        for name in [n for n in list(sys.modules) if n.startswith("demo_tools")]:
            _s.name = name
            del sys.modules[_s.name]


def content_of(plan, path: str) -> str:
    return next(file.content for file in plan if file.path == path)


def test_the_native_ui_plan_adds_one_module_and_nothing_else() -> None:
    plain = [f.path for f in plan_scaffold(ScaffoldOptions.resolve("demo_tools"))]
    with_ui = [
        f.path
        for f in plan_scaffold(ScaffoldOptions.resolve("demo_tools", ui="native"))
    ]

    assert sorted(set(with_ui) - set(plain)) == ["demo_tools/ui.py"]


def test_the_plugin_lists_the_surface_and_binds_the_opening_action() -> None:
    plan = plan_scaffold(ScaffoldOptions.resolve("demo_tools", ui="native"))
    plugin_module = content_of(plan, "demo_tools/plugin.py")
    ui_module = content_of(plan, "demo_tools/ui.py")

    assert "app.add_surface(PingDialog)" in plugin_module
    assert '@toolbar(text="Demo Tools")' in plugin_module
    assert "ctx.ui.open(PingDialog" in plugin_module
    assert '@menu("Plugins/Demo Tools")' in ui_module
    assert "class PingDialog(Dialog):" in ui_module
    # The declarative form (TASK-108 AC #1): components on the class, a Form
    # over the action, ``@on(component)``; no ``build()`` and no Qt at all.
    assert 'form = Form([value], action_id="ping")' in ui_module
    assert "@on(ping).clicked" in ui_module
    assert "self.form.submit()" in ui_module
    assert "def build" not in ui_module
    for module in (plugin_module, ui_module):
        assert not any(
            name.split(".")[0] in {"qgis", "PyQt6"}
            for name in _imported_modules(module)
        )


def _imported_modules(source: str) -> set[str]:
    return {
        node.module
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom) and node.module
    }


def test_the_starter_dialog_opens_under_the_fake_with_its_initial_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """What the host does at ``open``: the copies, ``initial``, the wiring, a click."""
    _s = _CcState(tmp_path=tmp_path, monkeypatch=monkeypatch)
    for _p in (
        _cc_test_the_starter_p1,
        _cc_test_the_starter_p2,
        _cc_test_the_starter_p3,
    ):
        _r = _p(_s)
        if isinstance(_r, _CcReturn):
            return _r.value
    return None


def test_the_native_ui_project_passes_check(tmp_path: Path) -> None:
    project = tmp_path / "project"
    write_scaffold(ScaffoldOptions.resolve("demo_tools", ui="native"), project)

    report = check_project(project)

    assert [d.rule for d in report.diagnostics] == []


def test_the_native_ui_starter_tests_pass_in_a_bare_interpreter(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    write_scaffold(ScaffoldOptions.resolve("demo_tools", ui="native"), project)

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
        env={
            **os.environ,
            "PYTHONPATH": os.pathsep.join(map(str, layers.SOURCE_ROOTS)),
        },
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "4 passed" in result.stdout


def test_the_readme_explains_the_surface_and_the_rules() -> None:
    readme = content_of(
        plan_scaffold(ScaffoldOptions.resolve("demo_tools", ui="native")),
        "README.md",
    )

    assert "## Native UI" in readme
    assert "declares its\ncomponents" in readme
    assert "plain PyQt" in readme  # the escape hatch, in one sentence
    assert "UI003" in readme
    assert "ICON001" in readme
    assert "demo_tools/icons/" in readme


def test_a_plain_project_has_no_surface_wording() -> None:
    plan = plan_scaffold(ScaffoldOptions.resolve("demo_tools"))

    assert "## Native UI" not in content_of(plan, "README.md")
    assert "surfaces" not in content_of(plan, "demo_tools/plugin.py")
    assert "open_ping" not in content_of(plan, "tests/test_plugin.py")


def test_an_unknown_ui_kind_is_refused_by_name() -> None:
    with pytest.raises(QgisSdkScaffoldError, match="--ui must be one of native"):
        ScaffoldOptions.resolve("demo_tools", ui="qml")


def test_the_cli_flag_writes_the_ui_module(tmp_path: Path) -> None:
    target = tmp_path / "demo_tools"

    result = CliRunner().invoke(
        app,
        ["new", str(target), "--ui", "native", "--no-input"],
        env={"NO_COLOR": "1", "TERM": "dumb", "COLUMNS": "120"},
    )

    assert result.exit_code == 0, result.output
    assert (target / "demo_tools" / "ui.py").is_file()
    assert "demo_tools/ui.py" in result.output


@pytest.mark.parametrize("web", [None, "vanilla"])
def test_the_native_ui_combines_with_an_algorithm_and_a_page(web: str | None) -> None:
    options = ScaffoldOptions.resolve(
        "demo_tools",
        ui="native",
        algorithm=True,
        web=web,
        sdk_dependency="workspace:*" if web else None,
    )
    plan = plan_scaffold(options)
    paths = [f.path for f in plan]

    assert {"demo_tools/ui.py", "demo_tools/algorithms.py"} <= set(paths)
    assert ("web/package.json" in paths) is (web is not None)
    ast.parse(content_of(plan, "demo_tools/plugin.py"))
    ast.parse(content_of(plan, "tests/test_plugin.py"))

"""``qgis-sdk new --algorithm``: one provider and one function algorithm (TASK-65).

decision-42 made algorithms plain functions on a provider the plugin lists;
the starter for it is the same shape as ``examples/simple``'s: an
``algorithms.py`` with the provider and a ``buffer`` function, the plugin
listing the provider and exposing the operation as an action, and a test
that proves the request over the SDK fakes without QGIS.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
import tomllib
from pathlib import Path

import layers
import pytest
from qgis_sdk_tools.__main__ import app
from qgis_sdk_tools.artifacts import introspect_plugin, render_metadata
from qgis_sdk_tools.check import check_project
from qgis_sdk_tools.project import require_project
from qgis_sdk_tools.scaffold import ScaffoldOptions, plan_scaffold, write_scaffold
from typer.testing import CliRunner


def content_of(plan, path: str) -> str:
    return next(file.content for file in plan if file.path == path)


def test_the_algorithm_plan_adds_one_module_and_nothing_else() -> None:
    plain = [f.path for f in plan_scaffold(ScaffoldOptions.resolve("demo_tools"))]
    with_algorithm = [
        f.path
        for f in plan_scaffold(ScaffoldOptions.resolve("demo_tools", algorithm=True))
    ]

    assert sorted(set(with_algorithm) - set(plain)) == ["demo_tools/algorithms.py"]


def test_the_plugin_lists_the_provider_and_wires_the_action() -> None:
    plan = plan_scaffold(ScaffoldOptions.resolve("demo_tools", algorithm=True))
    plugin_module = content_of(plan, "demo_tools/plugin.py")
    algorithms = content_of(plan, "demo_tools/algorithms.py")

    assert "providers = (algorithms.provider,)" in plugin_module
    assert '@action(id="buffer"' in plugin_module
    assert "invoke(" in plugin_module
    assert 'Provider(id="demo_tools", title="Demo Tools")' in algorithms
    assert "@provider.algorithm(" in algorithms
    assert "def buffer_layer(" in algorithms
    assert "ctx: AlgorithmContext" in algorithms
    for module in (plugin_module, algorithms):
        imported = {
            node.module
            for node in ast.walk(ast.parse(module))
            if isinstance(node, ast.ImportFrom) and node.module
        }
        assert not any(name.split(".")[0] in {"qgis", "PyQt6"} for name in imported)


def test_the_rendered_metadata_announces_the_processing_provider(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    write_scaffold(ScaffoldOptions.resolve("demo_tools", algorithm=True), project)
    sys.path.insert(0, str(project))
    try:
        config = require_project(project)
        facts = introspect_plugin(config)
    finally:
        sys.path.remove(str(project))
        for name in [m for m in sys.modules if m.startswith("demo_tools")]:
            del sys.modules[name]

    rendered = render_metadata(config, facts)
    assert "hasProcessingProvider=yes" in rendered
    assert facts.has_providers is True


def test_the_algorithm_project_passes_check(tmp_path: Path) -> None:
    project = tmp_path / "project"
    write_scaffold(ScaffoldOptions.resolve("demo_tools", algorithm=True), project)

    report = check_project(project)

    assert [d.rule for d in report.diagnostics] == []


def test_the_algorithm_starter_tests_pass_in_a_bare_interpreter(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    write_scaffold(ScaffoldOptions.resolve("demo_tools", algorithm=True), project)

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


def test_the_readme_names_the_toolbox_entry() -> None:
    readme = content_of(
        plan_scaffold(ScaffoldOptions.resolve("demo_tools", algorithm=True)),
        "README.md",
    )

    assert "## Processing" in readme
    assert "demo_tools:buffer" in readme
    assert "algorithms.py" in readme


def test_a_plain_project_has_no_algorithm_wording() -> None:
    plan = plan_scaffold(ScaffoldOptions.resolve("demo_tools"))

    assert "## Processing" not in content_of(plan, "README.md")
    assert "providers" not in content_of(plan, "demo_tools/plugin.py")
    assert "buffer" not in content_of(plan, "tests/test_plugin.py")


def test_the_cli_flag_writes_the_algorithm_module(tmp_path: Path) -> None:
    target = tmp_path / "demo_tools"

    result = CliRunner().invoke(
        app,
        ["new", str(target), "--algorithm", "--no-input"],
        env={"NO_COLOR": "1", "TERM": "dumb", "COLUMNS": "120"},
    )

    assert result.exit_code == 0, result.output
    assert (target / "demo_tools" / "algorithms.py").is_file()
    assert "demo_tools/algorithms.py" in result.output
    manifest = tomllib.loads((target / "pyproject.toml").read_text(encoding="utf-8"))
    assert manifest["tool"]["qgis-sdk"]["plugin"] == "demo_tools.plugin:DemoToolsPlugin"


@pytest.mark.parametrize("web", [None, "vanilla"])
def test_the_algorithm_combines_with_a_page(web: str | None) -> None:
    options = ScaffoldOptions.resolve(
        "demo_tools",
        algorithm=True,
        web=web,
        sdk_dependency="workspace:*" if web else None,
    )
    paths = [f.path for f in plan_scaffold(options)]

    assert "demo_tools/algorithms.py" in paths
    assert ("web/package.json" in paths) is (web is not None)

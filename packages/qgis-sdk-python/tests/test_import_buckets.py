"""Every import gets a bucket at check time, and ``unknown`` is ``DEP001``.

decision-50 point 3 (TASK-77 AC #3): ``check`` sorts each import root into
stdlib, host, runtime, plugin, vendored, external or unknown, prints the
listing with ``--imports``, and reports an unknown root as ``DEP001`` whose
remediation names both exits (vendor it, or declare it external) - before a
build runs, not from a traceback in a clean QGIS.
"""

from __future__ import annotations

from pathlib import Path

import distributions
import pytest
from qgis_sdk_tools.check import check_project
from qgis_sdk_tools.scaffold import ScaffoldOptions, write_scaffold
from qgis_sdk_tools.testing import FakeCliRuntime
from typer.testing import CliRunner

PLUGIN = "field_tools"


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / PLUGIN
    write_scaffold(ScaffoldOptions.resolve(PLUGIN), root)
    return root


def imports_of(root: Path, source: str, build: str = "") -> Path:
    """Replace the scaffolded plugin module with ``source`` and declare ``build``."""
    plugin = root / PLUGIN / "plugin.py"
    plugin.write_text(
        '"""A plugin whose imports the bucket report has to classify."""\n\n'
        "from __future__ import annotations\n\n"
        "from qgis_sdk import QgisSdkPlugin\n"
        "from qgis_sdk.core import PluginContext\n\n"
        f"{source}\n"
        'app = QgisSdkPlugin(id="field_tools", title="Field Tools")\n\n\n'
        '@app.action(id="ping", title="Ping")\n'
        "def ping(ctx: PluginContext, value: int) -> int:\n"
        '    """Return the value unchanged."""\n'
        "    return value\n",
        encoding="utf-8",
    )
    if build:
        pyproject = root / "pyproject.toml"
        pyproject.write_text(
            pyproject.read_text(encoding="utf-8")
            + f"\n[tool.qgis-sdk.build]\n{build}\n",
            encoding="utf-8",
        )
    return root


def test_every_root_lands_in_its_bucket(project: Path, tmp_path: Path) -> None:
    site = tmp_path / "site"
    site.mkdir()
    distributions.install_fixture(site, "fixture-pure")
    root = imports_of(
        project,
        # qgis inside a function: QGIS001 is about import time, not this test.
        "import json\nimport fixture_pure\n\n\ndef _layers():\n    import qgis.core\n",
        build='vendor = ["fixture-pure"]',
    )

    report = check_project(root)

    assert report.imports is not None
    counts = report.imports.counts()
    assert counts["stdlib"] == 2  # json, and __future__ from the module header
    assert counts["host"] == 1  # qgis
    assert counts["runtime"] == 1  # qgis_sdk (both statements share the root)
    assert counts["vendored"] == 1  # fixture_pure
    assert counts["unknown"] == 0
    assert "json" in report.imports.roots("stdlib")
    assert report.imports.roots("runtime") == ("qgis_sdk",)
    assert [d.rule for d in report.diagnostics] == []


def test_an_undeclared_import_is_dep001_with_both_exits(project: Path) -> None:
    root = imports_of(project, "import mystery_package\n")

    report = check_project(root)

    dep001 = [d for d in report.diagnostics if d.rule == "DEP001"]
    assert len(dep001) == 1
    assert "`mystery_package` is imported" in dep001[0].message
    assert "vendor it" in dep001[0].remediation
    assert "external" in dep001[0].remediation
    assert report.imports is not None
    assert report.imports.roots("unknown") == ("mystery_package",)


def test_a_declared_external_is_its_own_bucket_and_no_finding(project: Path) -> None:
    root = imports_of(project, "import pandas\n", build='external = ["pandas"]')

    report = check_project(root)

    assert report.imports is not None
    assert report.imports.roots("external") == ("pandas",)
    assert [d.rule for d in report.diagnostics] == []


def test_the_tooling_never_ships_and_says_so(project: Path) -> None:
    root = imports_of(project, "import qgis_sdk_tools.bundle\n")

    report = check_project(root)

    dep001 = [d for d in report.diagnostics if d.rule == "DEP001"]
    assert len(dep001) == 1
    assert "developer tooling" in dep001[0].message


def test_the_testing_fakes_are_dep002(project: Path) -> None:
    root = imports_of(project, "from qgis_sdk.testing import FakeUi\n")

    report = check_project(root)

    dep002 = [d for d in report.diagnostics if d.rule == "DEP002"]
    assert len(dep002) == 1
    assert "qgis_sdk.testing" in dep002[0].message


def test_the_cli_prints_the_listing(project: Path) -> None:
    root = imports_of(project, "import json\nimport mystery_package\n")
    runtime = FakeCliRuntime(cwd=root)

    result = CliRunner().invoke(
        __import__("qgis_sdk_tools.__main__", fromlist=["app"]).app,
        ["check", str(root), "--imports"],
        obj=runtime,
    )

    assert result.exit_code == 1
    assert "mystery_package" in runtime.stdout
    assert "unknown" in runtime.stdout
    assert "json" in runtime.stdout
    assert "stdlib" in runtime.stdout


def test_the_json_report_carries_the_buckets(project: Path) -> None:
    root = imports_of(project, "import json\n")

    payload = check_project(root).to_json()

    assert payload["imports"] is not None
    assert payload["imports"]["counts"]["stdlib"] == 2
    roots = {entry["root"] for entry in payload["imports"]["imports"]}
    assert {"json", "__future__"} <= roots

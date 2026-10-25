"""``build_plugin``: a validated, installable plugin ZIP (TASK-8, decision-35).

The archive has the layout QGIS installs, carries the runtime the plugin
needs under a plugin-private import path, excludes what is not the plugin,
reproduces byte for byte, and is refused - with the same diagnostics
``check`` prints - when QGIS would not load it.
"""

from __future__ import annotations

import ast
import json
import os
import sys
import zipfile
from collections.abc import Sequence
from pathlib import Path

import pytest
import qgis_sdk
from qgis_sdk_tools.bundle import (
    VENDOR_PACKAGE,
    BuildResult,
    QgisSdkBuildError,
    QgisSdkBuildRefusedError,
    build_plugin,
    rewrite_imports,
)
from qgis_sdk_tools.scaffold import ScaffoldOptions, write_scaffold

PLUGIN = "field_tools"


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / PLUGIN
    write_scaffold(ScaffoldOptions.resolve(PLUGIN), root)
    (root / PLUGIN / "__pycache__").mkdir()
    (root / PLUGIN / "__pycache__" / "plugin.cpython-314.pyc").write_bytes(b"\0")
    (root / PLUGIN / "plugin.pyc").write_bytes(b"\0")
    (root / PLUGIN / "tests").mkdir()
    (root / PLUGIN / "tests" / "test_inner.py").write_text("", encoding="utf-8")
    (root / ".qgis-sdk" / "profiles").mkdir(parents=True)
    return root


@pytest.fixture
def web_project(tmp_path: Path) -> Path:
    root = tmp_path / "web_tools"
    write_scaffold(
        ScaffoldOptions.resolve("web_tools", web="vanilla", package_manager="bun"), root
    )
    (root / "web" / "bun.lock").write_text("", encoding="utf-8")  # names the manager
    return root


def names(archive: Path) -> list[str]:
    with zipfile.ZipFile(archive) as zf:
        return zf.namelist()


def never_run(argv: Sequence[str], cwd: Path) -> int:
    raise AssertionError(f"no process expected, got {argv} in {cwd}")


class TestArchiveLayout:
    def test_the_plugin_directory_is_the_archive_root(self, project: Path) -> None:
        result = build_plugin(project, run=never_run)

        assert isinstance(result, BuildResult)
        assert result.archive == project / "dist" / f"{PLUGIN}-0.1.0.zip"
        entries = names(result.archive)
        assert f"{PLUGIN}/__init__.py" in entries
        assert f"{PLUGIN}/plugin.py" in entries
        assert f"{PLUGIN}/metadata.txt" in entries
        assert all(name.startswith(f"{PLUGIN}/") for name in entries)
        assert result.plugin == PLUGIN
        assert result.version == "0.1.0"
        assert result.report.ok

    def test_caches_tests_and_tooling_state_stay_out(self, project: Path) -> None:
        result = build_plugin(project, run=never_run)

        entries = names(result.archive)
        assert not any("__pycache__" in name for name in entries)
        assert not any(name.endswith(".pyc") for name in entries)
        assert not any("/tests/" in name for name in entries)
        assert not any(".qgis-sdk" in name for name in entries)
        assert not any("/testing/" in name for name in entries)  # qgis_sdk.testing

    def test_the_runtime_is_vendored_under_a_plugin_private_path(
        self, project: Path
    ) -> None:
        result = build_plugin(project, run=never_run)

        entries = set(names(result.archive))
        vendor = f"{PLUGIN}/{VENDOR_PACKAGE}/qgis_sdk"
        assert f"{PLUGIN}/{VENDOR_PACKAGE}/__init__.py" in entries
        assert f"{vendor}/__init__.py" in entries
        assert f"{vendor}/core/runtime.py" in entries
        assert f"{vendor}/adapters/desktop.py" in entries
        assert f"{vendor}/resources/styles/reference-line-output.qml" in entries
        assert f"{PLUGIN}/{VENDOR_PACKAGE}/NOTICE" in entries
        with zipfile.ZipFile(result.archive) as zf:
            notice = zf.read(f"{PLUGIN}/{VENDOR_PACKAGE}/NOTICE").decode()
            plugin_source = zf.read(f"{PLUGIN}/plugin.py").decode()
            runtime_source = zf.read(f"{vendor}/core/runtime.py").decode()
            vendored_init = zf.read(f"{vendor}/__init__.py").decode()
        assert "qgis-sdk" in notice and "MIT" in notice
        assert result.runtime_version in notice
        assert f"from {PLUGIN}.{VENDOR_PACKAGE}.qgis_sdk import action, plugin" in (
            plugin_source
        )
        assert "from qgis_sdk" not in plugin_source
        assert f"from {PLUGIN}.{VENDOR_PACKAGE}.qgis_sdk." in runtime_source
        assert "from qgis_sdk" not in runtime_source
        ast.parse(plugin_source)
        ast.parse(vendored_init)

    def test_every_vendored_module_still_parses(self, project: Path) -> None:
        result = build_plugin(project, run=never_run)

        with zipfile.ZipFile(result.archive) as zf:
            for name in zf.namelist():
                if name.endswith(".py"):
                    ast.parse(zf.read(name).decode("utf-8"), filename=name)

    def test_the_vendored_tree_is_importable_from_the_archive(
        self, project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        result = build_plugin(project, run=never_run)
        target = tmp_path / "installed"
        with zipfile.ZipFile(result.archive) as zf:
            zf.extractall(target)
        monkeypatch.syspath_prepend(str(target))
        for name in list(sys.modules):
            if name == PLUGIN or name.startswith(f"{PLUGIN}."):
                monkeypatch.delitem(sys.modules, name)

        module = __import__(PLUGIN, fromlist=["classFactory"])

        plugin = module.classFactory(None)
        plugin.initGui()
        try:
            assert plugin.runtime.actions["ping"](7) == 7
            assert type(plugin.runtime).__module__.startswith(
                f"{PLUGIN}.{VENDOR_PACKAGE}.qgis_sdk."
            )
        finally:
            plugin.unload()
        assert qgis_sdk.__name__ == "qgis_sdk"  # the real one is untouched

    def test_builds_are_reproducible(self, project: Path, tmp_path: Path) -> None:
        first = build_plugin(project, out=tmp_path / "a", run=never_run)
        os.utime(project / PLUGIN / "plugin.py")  # a newer mtime changes nothing
        second = build_plugin(project, out=tmp_path / "b", run=never_run)

        assert first.archive.read_bytes() == second.archive.read_bytes()
        with zipfile.ZipFile(first.archive) as zf:
            infos = zf.infolist()
        assert [info.filename for info in infos] == sorted(i.filename for i in infos)
        assert {info.date_time for info in infos} == {(1980, 1, 1, 0, 0, 0)}

    def test_source_date_epoch_sets_the_timestamps(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")

        result = build_plugin(project, run=never_run)

        with zipfile.ZipFile(result.archive) as zf:
            assert {info.date_time for info in zf.infolist()} == {
                (2023, 11, 14, 22, 13, 20)
            }

    def test_out_directory_is_created(self, project: Path, tmp_path: Path) -> None:
        result = build_plugin(project, out=tmp_path / "deep" / "er", run=never_run)

        assert result.archive.parent == tmp_path / "deep" / "er"
        assert result.archive.is_file()


class TestValidation:
    def test_check_errors_refuse_the_build_with_the_same_diagnostics(
        self, project: Path
    ) -> None:
        (project / PLUGIN / "broken.py").write_text("def (\n", encoding="utf-8")

        with pytest.raises(QgisSdkBuildRefusedError) as excinfo:
            build_plugin(project, run=never_run)

        rules = [d.rule for d in excinfo.value.diagnostics]
        assert "SYNTAX001" in rules
        assert not (project / "dist").exists()

    def test_a_missing_entry_point_is_reported(self, project: Path) -> None:
        (project / PLUGIN / "__init__.py").write_text(
            '"""No factory here."""\n', encoding="utf-8"
        )

        with pytest.raises(QgisSdkBuildRefusedError) as excinfo:
            build_plugin(project, run=never_run)

        finding = next(d for d in excinfo.value.diagnostics if d.rule == "ENTRY001")
        assert finding.path == Path(PLUGIN) / "__init__.py"
        assert "classFactory" in finding.message

    def test_an_entry_point_defined_in_place_counts(self, project: Path) -> None:
        (project / PLUGIN / "__init__.py").write_text(
            "def classFactory(iface):\n    return None\n", encoding="utf-8"
        )

        assert build_plugin(project, run=never_run).report.ok

    def test_unsupported_runtime_dependencies_are_named(self, project: Path) -> None:
        (project / PLUGIN / "extra.py").write_text(
            "import os\nimport requests\nfrom qgis.core import QgsProject\n"
            "from numpy import array\nfrom . import plugin\n"
            "from field_tools.plugin import classFactory\n",
            encoding="utf-8",
        )

        with pytest.raises(QgisSdkBuildRefusedError) as excinfo:
            build_plugin(project, run=never_run)

        findings = [d for d in excinfo.value.diagnostics if d.rule == "DEP001"]
        assert sorted(f.message.split("`")[1] for f in findings) == [
            "numpy",
            "requests",
        ]
        assert all(f.path == Path(PLUGIN) / "extra.py" for f in findings)
        assert "[tool.qgis-sdk.build]" in findings[0].remediation

    def test_declared_external_dependencies_pass(self, project: Path) -> None:
        (project / PLUGIN / "extra.py").write_text(
            "import requests\n", encoding="utf-8"
        )
        (project / "pyproject.toml").write_text(
            (project / "pyproject.toml").read_text(encoding="utf-8")
            + '\n[tool.qgis-sdk.build]\nexternal = ["requests"]\n',
            encoding="utf-8",
        )

        result = build_plugin(project, run=never_run)

        assert result.report.ok
        assert result.external == ("requests",)

    def test_a_tools_import_in_the_plugin_is_refused(self, project: Path) -> None:
        (project / PLUGIN / "extra.py").write_text(
            "from qgis_sdk_tools.check import check_project\n", encoding="utf-8"
        )

        with pytest.raises(QgisSdkBuildRefusedError) as excinfo:
            build_plugin(project, run=never_run)

        assert any(
            d.rule == "DEP001" and "qgis_sdk_tools" in d.message
            for d in excinfo.value.diagnostics
        )

    def test_a_testing_import_in_the_plugin_is_refused(self, project: Path) -> None:
        (project / PLUGIN / "extra.py").write_text(
            "from qgis_sdk.testing import FakeWorkers\n", encoding="utf-8"
        )

        with pytest.raises(QgisSdkBuildRefusedError) as excinfo:
            build_plugin(project, run=never_run)

        assert any(
            d.rule == "DEP002" and "qgis_sdk.testing" in d.message
            for d in excinfo.value.diagnostics
        )

    def test_not_a_project_is_a_plain_error(self, tmp_path: Path) -> None:
        with pytest.raises(QgisSdkBuildError, match="no plugin package"):
            build_plugin(tmp_path, run=never_run)


class TestWeb:
    def test_the_web_build_runs_in_web_and_its_output_ships(
        self, web_project: Path
    ) -> None:
        calls: list[tuple[tuple[str, ...], Path]] = []

        def run(argv: Sequence[str], cwd: Path) -> int:
            calls.append((tuple(argv), cwd))
            assets = web_project / "web_tools" / "web"
            (assets / "assets").mkdir(parents=True)
            (assets / "index.html").write_text("<html></html>", encoding="utf-8")
            (assets / "assets" / "index-abc.js").write_text("x", encoding="utf-8")
            return 0

        (web_project / "web" / "node_modules").mkdir()

        result = build_plugin(web_project, run=run)

        assert calls == [(("bun", "run", "build"), web_project / "web")]
        entries = names(result.archive)
        assert "web_tools/web/index.html" in entries
        assert "web_tools/web/assets/index-abc.js" in entries
        assert "web_tools/webview.py" in entries
        assert not any(name.startswith("web_tools/web/src") for name in entries)
        assert not any("node_modules" in name for name in entries)
        assert result.web == "built"

    def test_a_failing_web_build_fails_the_build(self, web_project: Path) -> None:
        (web_project / "web" / "node_modules").mkdir()

        with pytest.raises(QgisSdkBuildError, match="web build failed"):
            build_plugin(web_project, run=lambda argv, cwd: 1)

    def test_missing_dependencies_are_an_error_not_an_install(
        self, web_project: Path
    ) -> None:
        with pytest.raises(QgisSdkBuildError, match="bun install"):
            build_plugin(web_project, run=never_run)

    def test_no_web_ships_prebuilt_assets_as_they_are(self, web_project: Path) -> None:
        assets = web_project / "web_tools" / "web"
        assets.mkdir()
        (assets / "index.html").write_text("<html></html>", encoding="utf-8")

        result = build_plugin(web_project, web=False, run=never_run)

        assert "web_tools/web/index.html" in names(result.archive)
        assert result.web == "prebuilt"

    def test_no_web_without_assets_is_refused(self, web_project: Path) -> None:
        with pytest.raises(QgisSdkBuildRefusedError) as excinfo:
            build_plugin(web_project, web=False, run=never_run)

        assert [d.rule for d in excinfo.value.diagnostics] == ["WEB001"]

    def test_a_project_without_a_web_ui_runs_nothing(self, project: Path) -> None:
        assert build_plugin(project, run=never_run).web == "none"


class TestRewriteImports:
    def test_absolute_sdk_imports_move_under_the_plugin(self) -> None:
        source = (
            "from __future__ import annotations\n"
            "import qgis_sdk\n"
            "import qgis_sdk.core.scope as scope_module\n"
            "import qgis_sdk.jobs\n"
            "from qgis_sdk import action, plugin\n"
            "from qgis_sdk.core import (\n"
            "    PluginContext,\n"
            "    ResourceScope,\n"
            ")\n"
            "from . import sibling\n"
            "from .models import X\n"
            "import qgis_sdk_other\n"
            "text = 'from qgis_sdk import nothing'\n"
        )

        rewritten = rewrite_imports(source, prefix="my_plugin._vendor")

        assert rewritten == (
            "from __future__ import annotations\n"
            "from my_plugin._vendor import qgis_sdk\n"
            "import my_plugin._vendor.qgis_sdk.core.scope as scope_module\n"
            "import my_plugin._vendor.qgis_sdk.jobs; "
            "from my_plugin._vendor import qgis_sdk\n"
            "from my_plugin._vendor.qgis_sdk import action, plugin\n"
            "from my_plugin._vendor.qgis_sdk.core import (\n"
            "    PluginContext,\n"
            "    ResourceScope,\n"
            ")\n"
            "from . import sibling\n"
            "from .models import X\n"
            "import qgis_sdk_other\n"
            "text = 'from qgis_sdk import nothing'\n"
        )
        assert rewritten.count("\n") == source.count("\n")  # line numbers survive

    def test_indented_and_guarded_imports_are_rewritten_too(self) -> None:
        source = (
            "from typing import TYPE_CHECKING\n"
            "if TYPE_CHECKING:\n"
            "    from qgis_sdk.core import PluginContext\n"
            "def f():\n"
            "    from qgis_sdk.jobs import JobService\n"
            "    return JobService\n"
        )

        rewritten = rewrite_imports(source, prefix="p._vendor")

        assert "    from p._vendor.qgis_sdk.core import PluginContext\n" in rewritten
        assert "    from p._vendor.qgis_sdk.jobs import JobService\n" in rewritten


def test_the_result_serialises_for_the_cli(project: Path) -> None:
    result = build_plugin(project, run=never_run)

    data = json.loads(json.dumps(result.to_json()))
    assert data["archive"] == str(result.archive)
    assert data["plugin"] == PLUGIN
    assert data["version"] == "0.1.0"
    assert data["files"] == len(names(result.archive))
    assert data["web"] == "none"
    assert data["runtime_version"] == result.runtime_version
    assert data["report"]["ok"] is True

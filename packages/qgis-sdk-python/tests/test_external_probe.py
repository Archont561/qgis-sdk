"""Externals: the declaration, the metadata.txt line, and the startup probe.

decision-50 point 1 (TASK-77 AC #1): ``[tool.qgis-sdk.build] external`` takes
bare import roots or ``{import, requirement, reason}`` tables; the generated
``classFactory`` imports each one before constructing the plugin and, when one
is missing, shows one message-bar error naming the package and the install
command for the detected host instead of a traceback - leaving the plugin
unloaded, never half-initialised. The declaration also reaches
``metadata.txt``, so the plugin manager says it before installation.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from qgis_sdk_tools.artifacts import PluginFacts, class_factory_source, render_metadata
from qgis_sdk_tools.project import ProjectConfig, load_project
from qgis_sdk_tools.scaffold import ScaffoldOptions, write_scaffold

PLUGIN = "field_tools"


def project(tmp_path: Path, build: str) -> Path:
    """A scaffolded project whose ``[tool.qgis-sdk.build]`` table is ``build``."""
    root = tmp_path / PLUGIN
    write_scaffold(ScaffoldOptions.resolve(PLUGIN), root)
    pyproject = root / "pyproject.toml"
    pyproject.write_text(
        pyproject.read_text(encoding="utf-8") + f"\n[tool.qgis-sdk.build]\n{build}\n",
        encoding="utf-8",
    )
    return root


def config_of(root: Path) -> ProjectConfig:
    config, findings = load_project(root)
    assert config is not None, findings
    assert not [f for f in findings if f.severity == "error"], findings
    return config


class Recorder:
    """Stands in for ``QgisInterface``: records what the probe tells the user."""

    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def messageBar(self) -> Recorder:
        return self

    def pushCritical(self, title: str, message: str) -> None:
        self.messages.append((title, message))


def run_generated(
    config: ProjectConfig, monkeypatch: pytest.MonkeyPatch
) -> dict[str, Any]:
    """Execute the generated ``__init__.py`` with a stub ``host``, return its globals."""
    source = class_factory_source(config, by="test")
    built: list[tuple[str, dict[str, object]]] = []

    def host(spec: str, **options: object) -> Any:
        built.append((spec, options))

        def binding(iface: object) -> str:
            return "built"

        return binding

    module = ModuleType("qgis_sdk.adapters.desktop")
    module.host = host  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "qgis_sdk.adapters.desktop", module)
    namespace: dict[str, Any] = {"__name__": "generated_probe"}
    # Executing the generated module is what this test is about.
    exec(compile(source, "<generated>", "exec"), namespace)  # noqa: S102
    namespace["_built"] = built
    return namespace


class TestDeclaration:
    def test_bare_roots_and_tables_are_read_into_one_model(
        self, tmp_path: Path
    ) -> None:
        root = project(
            tmp_path,
            'external = ["pandas", { import = "numpy", requirement = "numpy>=1.26", '
            'reason = "raster maths" }]',
        )

        build = config_of(root).build

        assert [item.import_name for item in build.external] == ["pandas", "numpy"]
        assert build.external[0].install_requirement == "pandas"
        assert build.external[1].install_requirement == "numpy>=1.26"
        assert build.external[1].reason == "raster maths"
        assert build.external_roots == ("pandas", "numpy")

    @pytest.mark.parametrize(
        ("build", "expected"),
        [
            ('external = "pandas"', "list of import roots or tables"),
            (
                'external = [{ requirement = "pandas>=2" }]',
                "external entry needs `import`",
            ),
            ('external = ["pandas", "pandas"]', "names `pandas` twice"),
            ('external = ["pandas>=2"]', "is not an import root"),
            (
                'external = [{ import = "pandas", requirment = "pandas>=2" }]',
                "external entry has no key `requirment`",
            ),
            ('external = [{ import = "pandas", requirement = 2 }]', "requirement"),
            ('vendor = ["shapely", "Shapely"]', "names `Shapely` twice"),
            ('vendor = ["shapely toolkit"]', "is not a distribution name"),
            ('external = ["pandas"]\nextra = 1', "has no key `extra`"),
        ],
    )
    def test_a_malformed_declaration_is_a_typed_finding(
        self, tmp_path: Path, build: str, expected: str
    ) -> None:
        root = project(tmp_path, build)

        _config, findings = load_project(root)

        assert [finding.rule for finding in findings] == ["CONFIG001"]
        assert expected in findings[0].message


class TestMetadata:
    def test_the_plugin_manager_says_what_the_plugin_needs(
        self, tmp_path: Path
    ) -> None:
        root = project(
            tmp_path,
            'external = [{ import = "pandas", requirement = "pandas>=2", '
            'reason = "reads spreadsheets" }, "numpy"]',
        )

        metadata = render_metadata(
            config_of(root),
            PluginFacts(id=PLUGIN, title="Field Tools", has_providers=False),
        )

        assert (
            "Requires: pandas (pandas>=2) - reads spreadsheets; numpy (numpy)"
            in metadata
        )
        assert metadata.splitlines()[0] == "[general]"
        assert "description=Field Tools" in metadata

    def test_a_plugin_without_externals_keeps_its_description(
        self, tmp_path: Path
    ) -> None:
        root = tmp_path / PLUGIN
        write_scaffold(ScaffoldOptions.resolve(PLUGIN), root)
        config = config_of(root)

        metadata = render_metadata(
            config, PluginFacts(id=PLUGIN, title="Field Tools", has_providers=False)
        )

        assert "Requires:" not in metadata
        assert f"description={config.description}" in metadata


class TestProbe:
    def test_a_missing_external_is_one_message_bar_error_and_no_construction(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = project(
            tmp_path,
            'external = [{ import = "definitely_missing_pkg", requirement = '
            '"definitely-missing>=2", reason = "reads the widget" }]',
        )
        namespace = run_generated(config_of(root), monkeypatch)
        iface = Recorder()

        built = namespace["classFactory"](iface)

        assert built is None  # QGIS leaves a falsy classFactory unloaded
        assert namespace["_built"] == []  # nothing was constructed
        assert len(iface.messages) == 1  # one error, not one per complaint
        title, message = iface.messages[0]
        assert "missing dependency" in title
        assert "definitely_missing_pkg" in message
        assert "reads the widget" in message
        assert "definitely-missing>=2" in message
        assert "pip install" in message

    def test_a_present_external_constructs_the_plugin(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = project(tmp_path, 'external = ["json"]')  # a module every QGIS has
        namespace = run_generated(config_of(root), monkeypatch)

        assert namespace["classFactory"](Recorder()) == "built"
        assert namespace["_built"] == [(f"{PLUGIN}.plugin:app", {})]

    @pytest.mark.parametrize(
        ("platform", "expected"),
        [
            ("win32", "OSGeo4W Shell"),
            ("darwin", "/Applications/QGIS.app/Contents/MacOS/bin/pip3"),
            ("linux", "python3 -m pip install --user"),
        ],
    )
    def test_the_hint_names_the_installer_of_the_host(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        platform: str,
        expected: str,
    ) -> None:
        root = project(tmp_path, 'external = ["definitely_missing_pkg"]')
        namespace = run_generated(config_of(root), monkeypatch)
        iface = Recorder()
        monkeypatch.setattr(sys, "platform", platform)

        namespace["classFactory"](iface)

        assert expected in iface.messages[0][1]

    def test_a_qgis_without_a_message_bar_still_explains(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        root = project(tmp_path, 'external = ["definitely_missing_pkg"]')
        namespace = run_generated(config_of(root), monkeypatch)

        assert namespace["classFactory"](None) is None

        captured = capsys.readouterr()
        assert f"{PLUGIN}: this plugin needs definitely_missing_pkg" in captured.err

    def test_the_generated_source_is_plain_python(self, tmp_path: Path) -> None:
        root = project(tmp_path, 'external = ["pandas"]')

        source = class_factory_source(config_of(root), by="test")

        compile(source, "<generated>", "exec")
        assert source.startswith("# Generated by `test`")
        assert "def classFactory(iface):" in source

"""Generated projects use the public application authoring API."""

from pathlib import Path

from qgis_sdk.adapters.desktop import host
from qgis_sdk_tools.artifacts import introspect_plugin
from qgis_sdk_tools.generate import describe_plugin_spec, generate_schema_typescript
from qgis_sdk_tools.project import require_project
from qgis_sdk_tools.scaffold import ScaffoldOptions, write_scaffold


def test_web_schema_matches_generated_app_with_algorithm_and_native_ui(
    tmp_path: Path, monkeypatch
) -> None:
    options = ScaffoldOptions.resolve(
        "full_app", web="vanilla", algorithm=True, ui="native"
    )
    write_scaffold(options, tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    actual = (tmp_path / "web/src/bridge.schema.ts").read_text(encoding="utf-8")
    expected = generate_schema_typescript(describe_plugin_spec("full_app.plugin:app"))
    assert actual == expected


def test_generated_project_build_facts_and_host_use_application(
    tmp_path: Path, monkeypatch
) -> None:
    write_scaffold(ScaffoldOptions.resolve("app_scaffold"), tmp_path)
    project = require_project(tmp_path)
    assert project.spec == "app_scaffold.plugin:app"
    facts = introspect_plugin(project)
    assert facts.id == "app_scaffold"
    monkeypatch.syspath_prepend(str(tmp_path))
    desktop = host(project.spec)(None)
    desktop.initGui()
    try:
        assert desktop.runtime.actions["ping"](value=7) == 7
    finally:
        desktop.unload()

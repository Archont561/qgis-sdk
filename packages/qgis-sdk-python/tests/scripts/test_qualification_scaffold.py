"""Tests for the scaffold Desktop harness.

The end-to-end run is opt-in because it needs a real QGIS installation, and it
runs the Desktop application with the offscreen Qt platform plugin: it proves the
profile, metadata and plugin-manager path, not GUI behaviour.
"""

from __future__ import annotations

import ast
import configparser
import json
import os
from pathlib import Path

import pytest
from smoke_support import run_isolated_smoke
from smoke_support.desktop_smoke_kit import (
    PROFILE_PROBE,
    desktop_command,
    headless_environment,
)
from smoke_support.scaffold_desktop_smoke import (
    LIFECYCLE_PROBE,
    DesktopScaffoldReport,
    expected_metadata,
    request_document,
    run_smoke,
)

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"


def ini_fields(text: str) -> dict[str, str]:
    parser = configparser.ConfigParser(strict=True, interpolation=None)
    parser.optionxform = str
    parser.read_string(text)
    return dict(parser["general"])


def test_headless_environment_puts_qgis_and_the_sdk_on_the_python_path() -> None:
    prefix = Path("/opt/qgis")

    overrides = headless_environment(prefix, {})

    entries = overrides["PYTHONPATH"].split(os.pathsep)
    assert entries[0] == str(prefix / "share" / "qgis" / "python")
    packages = SCRIPTS_DIR.parents[1]
    assert entries[1:] == [
        str(packages / "qgis-sdk-runtime" / "src"),
        str(packages / "qgis-sdk-tools" / "src"),
    ]
    assert overrides["QT_QPA_PLATFORM"] == "offscreen"
    assert overrides["QGIS_PREFIX_PATH"] == str(prefix)
    assert overrides["PYTHONHOME"] == str(prefix)
    assert overrides["DISPLAY"] == ":99"


def test_headless_environment_keeps_an_existing_python_path() -> None:
    prefix = Path("/opt/qgis")

    overrides = headless_environment(prefix, {"PYTHONPATH": "/work/src"})

    assert overrides["PYTHONPATH"].endswith(os.pathsep + "/work/src")


def test_desktop_command_starts_the_app_with_no_plugins_and_the_probe_last() -> None:
    workspace = Path("/tmp/run")
    probe = Path("/tmp/run/probe.py")
    command = desktop_command(Path("/opt/qgis/bin/qgis"), workspace, probe)

    assert "--noplugins" in command
    assert command[command.index("--profile") + 1] == "sdk-qualification"
    assert command[-2:] == ["--code", str(probe)]
    assert str(workspace / "profiles") in command


def test_request_document_names_every_input_the_probe_reads() -> None:
    plugins_root = Path("/tmp/run/plugins")
    document = json.loads(request_document(plugins_root, "demo_tools", "Demo Tools"))

    assert document == {
        "plugin": "demo_tools",
        "plugins_root": str(plugins_root),
        "metadata_keys": ["name", "qgisMinimumVersion", "hasProcessingProvider"],
        "expected_metadata": {
            "name": "Demo Tools",
            "qgisMinimumVersion": "4.0",
            "hasProcessingProvider": "yes",
        },
        "ping_value": 7,
    }


def test_the_expected_metadata_matches_what_build_renders(tmp_path: Path) -> None:
    """The harness asserts against the generator's own output, not a copy.

    The scaffold writes no metadata.txt (decision-43); ``build`` renders it
    from pyproject.toml, so the rendering is what the expectation is checked
    against.
    """
    from qgis_sdk_tools.artifacts import introspect_plugin, render_metadata
    from qgis_sdk_tools.project import require_project
    from qgis_sdk_tools.scaffold import ScaffoldOptions, write_scaffold

    project = tmp_path / "demo_tools"
    write_scaffold(ScaffoldOptions.resolve("demo_tools", algorithm=True), project)
    config = require_project(project)
    generated = render_metadata(config, introspect_plugin(config))

    fields = ini_fields(generated)
    assert expected_metadata("Demo Tools") == {
        "name": fields["name"],
        "qgisMinimumVersion": fields["qgisMinimumVersion"],
        "hasProcessingProvider": fields["hasProcessingProvider"],
    }


@pytest.mark.parametrize(
    "probe", [PROFILE_PROBE, LIFECYCLE_PROBE], ids=["profile", "lifecycle"]
)
def test_each_probe_is_python_that_ends_the_process_itself(probe: str) -> None:
    tree = ast.parse(probe)

    assert tree.body, "the probe must not be empty"
    assert "os._exit" in probe, "the probe must exit without waiting for the GUI loop"
    assert 'os.environ["QGIS_SDK_DESKTOP_WORKSPACE"]' in probe


def test_unavailable_reports_every_stage_as_false() -> None:
    report = DesktopScaffoldReport.unavailable("demo_tools", "no QGIS here")

    assert report.passed is False
    assert report.error == "no QGIS here"
    payload = report.to_payload()
    assert set(payload) == {
        "action_result",
        "console_action_result",
        "console_actions",
        "console_algorithms",
        "console_closed",
        "console_context_shared",
        "discovered",
        "error",
        "loaded",
        "metadata_matches",
        "passed",
        "platform",
        "provider_registered",
        "provider_released",
        "runtime_running",
        "runtime_stopped",
        "plugin",
        "python_version",
        "qgis_version",
        "unloaded",
    }
    assert payload["plugin"] == "demo_tools"


def test_a_run_without_a_qgis_prefix_reports_instead_of_raising(tmp_path: Path) -> None:
    report = run_smoke(prefix=tmp_path / "definitely-not-a-qgis-prefix")

    assert report.passed is False
    assert report.discovered is False
    assert "QGIS Desktop executable not found" in (report.error or "")


@pytest.mark.desktop
@pytest.mark.smoke
def test_real_qgis_desktop_loads_and_unloads_the_generated_plugin() -> None:
    result = run_isolated_smoke("scaffold_desktop_smoke", timeout=600)

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    assert payload["discovered"] is True
    assert payload["metadata_matches"] is True
    assert payload["loaded"] is True
    assert payload["runtime_running"] is True
    assert payload["action_result"] == 7
    assert payload["provider_registered"] is True
    assert payload["unloaded"] is True
    assert payload["runtime_stopped"] is True
    assert payload["provider_released"] is True
    # TASK-73: the console route over a built, vendored plugin.
    assert payload["console_context_shared"] is True
    assert "ping" in payload["console_actions"]
    assert any(item.endswith(":buffer") for item in payload["console_algorithms"])
    assert payload["console_action_result"] == 7
    assert payload["console_closed"] is True
    assert payload["error"] is None
    assert payload["platform"]
    assert payload["qgis_version"]

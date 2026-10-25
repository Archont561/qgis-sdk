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
import subprocess
import sys
from pathlib import Path

import pytest
from desktop_smoke_kit import (
    PROFILE_PROBE,
    desktop_command,
    headless_environment,
)
from scaffold_desktop_smoke import (
    LIFECYCLE_PROBE,
    DesktopScaffoldReport,
    expected_metadata,
    request_document,
    run_smoke,
)

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
SMOKE_SCRIPT = SCRIPTS_DIR / "scaffold_desktop_smoke.py"
SMOKE_ENV_FLAG = "QGIS_SDK_SCAFFOLD_DESKTOP"


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
        "metadata_keys": ["name", "qgisMinimumVersion"],
        "expected_metadata": {"name": "Demo Tools", "qgisMinimumVersion": "4.0"},
        "ping_value": 7,
    }


def test_the_expected_metadata_matches_what_the_scaffold_writes() -> None:
    """The harness asserts against the generator's own output, not a copy."""
    from qgis_sdk_tools.scaffold import ScaffoldOptions, plan_scaffold

    plan = plan_scaffold(ScaffoldOptions.resolve("demo_tools"))
    generated = next(
        file.content for file in plan if file.path == "demo_tools/metadata.txt"
    )

    fields = ini_fields(generated)
    assert expected_metadata("Demo Tools") == {
        "name": fields["name"],
        "qgisMinimumVersion": fields["qgisMinimumVersion"],
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
        "discovered",
        "error",
        "loaded",
        "metadata_matches",
        "passed",
        "platform",
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
@pytest.mark.skipif(
    os.environ.get(SMOKE_ENV_FLAG) != "1",
    reason=f"set {SMOKE_ENV_FLAG}=1 to load and unload the scaffold in real QGIS Desktop",
)
def test_real_qgis_desktop_loads_and_unloads_the_generated_plugin() -> None:
    result = subprocess.run(
        [sys.executable, str(SMOKE_SCRIPT)],
        cwd=SCRIPTS_DIR.parents[1],
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    assert payload["discovered"] is True
    assert payload["metadata_matches"] is True
    assert payload["loaded"] is True
    assert payload["runtime_running"] is True
    assert payload["action_result"] == 7
    assert payload["unloaded"] is True
    assert payload["runtime_stopped"] is True
    assert payload["error"] is None
    assert payload["platform"]
    assert payload["qgis_version"]

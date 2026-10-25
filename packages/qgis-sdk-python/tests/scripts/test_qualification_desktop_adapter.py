"""Tests for the harness that qualifies the Desktop lifecycle adapter on a real host.

The QGIS-free half pins the evidence the report demands, the fixture's shape and the
drift guards between them. The end-to-end run is opt-in because it needs a real QGIS
Desktop installation, and it runs the application with the offscreen Qt platform
plugin: it proves the plugin and lifecycle path, not GUI behaviour.
"""

from __future__ import annotations

import ast
import configparser
import json
import os
import subprocess
import sys
from dataclasses import fields
from pathlib import Path

import pytest
from desktop_adapter_smoke import (
    EVIDENCE_FIELDS,
    FIXTURE_FILES,
    LIFECYCLE_PROBE,
    REPORT_FIELDS,
    DesktopAdapterReport,
    install_fixture,
    request_document,
    run_smoke,
)

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
SMOKE_SCRIPT = SCRIPTS_DIR / "desktop_adapter_smoke.py"
SMOKE_ENV_FLAG = "QGIS_SDK_DESKTOP_ADAPTER"


def report_payload(**overrides: object) -> dict[str, object]:
    """Return a fully confirmed probe report with the given fields changed."""
    payload: dict[str, object] = {
        "platform": "Linux-6.1.158+-x86_64-with-glibc2.36",
        "python_version": "3.14.8",
        "qgis_version": "4.2.3-Belém do Pará",
        "plugin": "sdk_lifecycle_probe",
        "error": None,
        "action_result": 7,
    }
    payload.update(dict.fromkeys(EVIDENCE_FIELDS, True))
    payload.update(overrides)
    return payload


def assigned_literal(source: str, name: str) -> ast.expr:
    """Return the literal assigned to ``name`` at module level in ``source``."""
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return node.value
    raise AssertionError(f"{name} is not assigned in the probe")


def test_the_report_fields_are_the_dataclass_and_nothing_else() -> None:
    declared = {field.name for field in fields(DesktopAdapterReport)}

    assert set(REPORT_FIELDS) == declared
    # `error` is the only field a passing run may carry, so the evidence stages are
    # exactly the ones that must be True.
    assert declared - set(EVIDENCE_FIELDS) == {
        "platform",
        "python_version",
        "qgis_version",
        "plugin",
        "action_result",
        "error",
    }


def test_the_probe_reports_exactly_the_fields_the_dataclass_reads() -> None:
    payload = assigned_literal(LIFECYCLE_PROBE, "payload")
    assert isinstance(payload, ast.Dict)

    reported = sorted(
        key.value for key in payload.keys if isinstance(key, ast.Constant)
    )
    assert reported == sorted(REPORT_FIELDS)


def test_the_probe_mirrors_the_evidence_the_report_requires() -> None:
    """Two literals must stay in step, so the suite compares them instead of trusting one."""
    evidence = assigned_literal(LIFECYCLE_PROBE, "EVIDENCE")
    assert isinstance(evidence, ast.Tuple)

    assert tuple(element.value for element in evidence.elts) == EVIDENCE_FIELDS


def test_an_unconfirmed_stage_is_a_failure_not_a_skip() -> None:
    """`None` means the stage never ran, which must not read as success."""
    assert "is not True" in LIFECYCLE_PROBE
    assert "is False" not in LIFECYCLE_PROBE


def test_a_run_passes_only_with_every_stage_confirmed() -> None:
    assert DesktopAdapterReport.from_payload(report_payload()).passed is True


@pytest.mark.parametrize("field", EVIDENCE_FIELDS)
def test_one_missing_stage_voids_the_verdict(field: str) -> None:
    report = DesktopAdapterReport.from_payload(report_payload(**{field: False}))

    assert report.passed is False
    assert getattr(report, field) is False


def test_a_wrong_action_result_voids_the_verdict() -> None:
    report = DesktopAdapterReport.from_payload(report_payload(action_result=8))

    assert report.passed is False


def test_the_fixture_is_a_valid_plugin_package_with_the_expected_files() -> None:
    assert set(FIXTURE_FILES) == {"__init__.py", "metadata.txt", "plugin.py"}
    ast.parse(FIXTURE_FILES["plugin.py"])
    ast.parse(FIXTURE_FILES["__init__.py"])

    parser = configparser.ConfigParser(strict=True, interpolation=None)
    parser.optionxform = str
    parser.read_string(FIXTURE_FILES["metadata.txt"])
    assert dict(parser["general"])["qgisMinimumVersion"] == "4.0"


def test_the_fixture_imports_only_the_public_sdk_api() -> None:
    """The evidence is about the adapter, so nothing native or scaffolder-owned appears."""
    tree = ast.parse(FIXTURE_FILES["plugin.py"])
    imported = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    } | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }

    # `from __future__ import annotations` is the fixture's own business, not a dependency.
    assert imported - {"__future__"} == {
        "dataclasses",
        "qgis_sdk",
        "qgis_sdk.adapters.desktop",
        "qgis_sdk.core",
    }
    assert not any(
        name.split(".")[0] in {"qgis", "PyQt5", "PyQt6"} for name in imported
    )


def test_install_fixture_writes_the_package_with_lf_endings(tmp_path: Path) -> None:
    package = install_fixture(tmp_path)

    assert package.name == "sdk_lifecycle_probe"
    assert sorted(path.name for path in package.iterdir()) == [
        "__init__.py",
        "metadata.txt",
        "plugin.py",
    ]
    for path in package.iterdir():
        assert "\r\n" not in path.read_text(encoding="utf-8")


def test_request_document_names_every_input_the_probe_reads(tmp_path: Path) -> None:
    document = json.loads(request_document(tmp_path))

    assert document == {
        "plugin": "sdk_lifecycle_probe",
        "plugins_root": str(tmp_path),
        "ping_value": 7,
    }


def test_a_missing_qgis_prefix_is_reported_instead_of_raising(tmp_path: Path) -> None:
    report = run_smoke(prefix=tmp_path / "definitely-not-a-qgis-prefix")

    assert report.passed is False
    assert report.started is False
    assert "QGIS Desktop executable not found" in (report.error or "")


def test_the_unavailable_report_confirms_nothing() -> None:
    report = DesktopAdapterReport.unavailable("no QGIS here")

    assert report.passed is False
    assert all(getattr(report, name) is False for name in EVIDENCE_FIELDS)
    assert report.to_payload()["passed"] is False


@pytest.mark.desktop
@pytest.mark.skipif(
    os.environ.get(SMOKE_ENV_FLAG) != "1",
    reason=f"set {SMOKE_ENV_FLAG}=1 to qualify the Desktop adapter in real QGIS",
)
def test_real_qgis_desktop_qualifies_the_adapter_lifecycle() -> None:
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
    assert payload["error"] is None
    assert payload["action_result"] == 7
    assert payload["iface_is_host"] is True
    assert payload["native_context_matches"] is True
    assert payload["message_bar_received"] is True
    assert payload["scope_released"] is True
    assert payload["actions_detached"] is True
    assert payload["runtime_running"] is True
    assert payload["runtime_stopped"] is True
    assert payload["qgis_version"]

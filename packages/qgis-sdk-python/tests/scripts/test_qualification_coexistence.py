"""Tests for the harness that qualifies plugin coexistence over the optional native runtime.

TASK-33 AC3 asks for coexistence with another plugin that already uses the same
optional native runtime dependency (``pydantic==2.14.1`` / ``pydantic_core``). The
QGIS-free half pins the report schema, the two fixture packages (a neighbor plugin
using Pydantic directly and an SDK plugin using ``PydanticContractAdapter``) and the
drift guards between the probe and the report dataclass. The end-to-end run is opt-in
through ``QGIS_SDK_PLUGIN_COEXISTENCE=1`` and drives the real QGIS Desktop plugin
manager headless.
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
from plugin_coexistence_smoke import (
    COEXISTENCE_PROBE,
    EVIDENCE_FIELDS,
    NEIGHBOR_FILES,
    NEIGHBOR_PLUGIN,
    REPORT_FIELDS,
    SDK_FILES,
    SDK_PLUGIN,
    PluginCoexistenceReport,
    install_fixtures,
    request_document,
    run_smoke,
)

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
SMOKE_SCRIPT = SCRIPTS_DIR / "plugin_coexistence_smoke.py"
SMOKE_ENV_FLAG = "QGIS_SDK_PLUGIN_COEXISTENCE"


def report_payload(**overrides: object) -> dict[str, object]:
    """Return a fully confirmed coexistence report with the given fields changed."""
    payload: dict[str, object] = {
        "platform": "Linux-6.1.158+-x86_64-with-glibc2.36",
        "python_version": "3.14.8",
        "qgis_version": "4.2.3-Belém do Pará",
        "pydantic_version": "2.14.1",
        "pydantic_core_version": "2.46.1",
        "neighbor_plugin": NEIGHBOR_PLUGIN,
        "sdk_plugin": SDK_PLUGIN,
        "action_result": 7,
        "error": None,
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
    declared = {field.name for field in fields(PluginCoexistenceReport)}

    assert set(REPORT_FIELDS) == declared
    assert declared - set(EVIDENCE_FIELDS) == {
        "platform",
        "python_version",
        "qgis_version",
        "pydantic_version",
        "pydantic_core_version",
        "neighbor_plugin",
        "sdk_plugin",
        "action_result",
        "error",
    }


def test_the_probe_reports_exactly_the_fields_the_dataclass_reads() -> None:
    payload = assigned_literal(COEXISTENCE_PROBE, "payload")
    assert isinstance(payload, ast.Dict)

    reported = sorted(
        key.value for key in payload.keys if isinstance(key, ast.Constant)
    )
    assert reported == sorted(REPORT_FIELDS)


def test_the_probe_mirrors_the_evidence_the_report_requires() -> None:
    evidence = assigned_literal(COEXISTENCE_PROBE, "EVIDENCE")
    assert isinstance(evidence, ast.Tuple)

    assert tuple(element.value for element in evidence.elts) == EVIDENCE_FIELDS


def test_an_unconfirmed_stage_is_a_failure_not_a_skip() -> None:
    assert "is not True" in COEXISTENCE_PROBE
    assert "is False" not in COEXISTENCE_PROBE


def test_a_run_passes_only_with_every_stage_confirmed() -> None:
    assert PluginCoexistenceReport.from_payload(report_payload()).passed is True


@pytest.mark.parametrize("field", EVIDENCE_FIELDS)
def test_one_missing_stage_voids_the_verdict(field: str) -> None:
    report = PluginCoexistenceReport.from_payload(report_payload(**{field: False}))

    assert report.passed is False
    assert getattr(report, field) is False


def test_a_wrong_action_result_voids_the_verdict() -> None:
    report = PluginCoexistenceReport.from_payload(report_payload(action_result=8))

    assert report.passed is False


@pytest.mark.parametrize(
    ("files", "expected_imports"),
    [
        (
            NEIGHBOR_FILES,
            {"pydantic", "pydantic_core"},
        ),
        (
            SDK_FILES,
            {
                "dataclasses",
                "json",
                "pydantic",
                "qgis_sdk",
                "qgis_sdk.adapters.pydantic",
                "qgis_sdk.adapters.pydantic_types",
                "qgis_sdk.core",
            },
        ),
    ],
    ids=["neighbor", "sdk"],
)
def test_both_fixtures_are_valid_plugins_with_explicit_imports(
    files: dict[str, str], expected_imports: set[str]
) -> None:
    assert set(files) == {"__init__.py", "metadata.txt", "plugin.py"}
    ast.parse(files["__init__.py"])
    tree = ast.parse(files["plugin.py"])

    parser = configparser.ConfigParser(strict=True, interpolation=None)
    parser.optionxform = str
    parser.read_string(files["metadata.txt"])
    assert dict(parser["general"])["qgisMinimumVersion"] == "4.0"

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
    assert imported - {"__future__"} == expected_imports
    assert not any(
        name.split(".")[0] in {"qgis", "PyQt5", "PyQt6"} for name in imported
    )
    if files is SDK_FILES:  # bound the way `qgis-sdk build` stages it (decision-43)
        assert (
            'host("sdk_pydantic_probe.plugin:SdkPydanticProbe")' in files["__init__.py"]
        )


def test_install_fixtures_writes_both_packages_with_lf_endings(
    tmp_path: Path,
) -> None:
    neighbor_dir, sdk_dir = install_fixtures(tmp_path)

    assert neighbor_dir.name == NEIGHBOR_PLUGIN
    assert sdk_dir.name == SDK_PLUGIN
    for package in (neighbor_dir, sdk_dir):
        assert sorted(path.name for path in package.iterdir()) == [
            "__init__.py",
            "metadata.txt",
            "plugin.py",
        ]
        for path in package.iterdir():
            assert "\r\n" not in path.read_text(encoding="utf-8")


def test_request_document_names_both_plugins_and_the_ping_value(
    tmp_path: Path,
) -> None:
    document = json.loads(request_document(tmp_path))

    assert document == {
        "neighbor_plugin": NEIGHBOR_PLUGIN,
        "sdk_plugin": SDK_PLUGIN,
        "plugins_root": str(tmp_path),
        "ping_value": 7,
    }


def test_a_missing_qgis_prefix_is_reported_instead_of_raising(
    tmp_path: Path,
) -> None:
    report = run_smoke(prefix=tmp_path / "definitely-not-a-qgis-prefix")

    assert report.passed is False
    assert report.neighbor_started is False
    assert report.sdk_started is False
    assert "QGIS Desktop executable not found" in (report.error or "")


def test_the_unavailable_report_confirms_nothing() -> None:
    report = PluginCoexistenceReport.unavailable("no QGIS here")

    assert report.passed is False
    assert all(getattr(report, name) is False for name in EVIDENCE_FIELDS)
    assert report.to_payload()["passed"] is False


@pytest.mark.desktop
@pytest.mark.skipif(
    os.environ.get(SMOKE_ENV_FLAG) != "1",
    reason=f"set {SMOKE_ENV_FLAG}=1 to qualify plugin coexistence in real QGIS Desktop",
)
def test_real_qgis_desktop_qualifies_plugin_coexistence() -> None:
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
    assert payload["pydantic_version"] == "2.14.1"
    assert payload["pydantic_core_version"]
    assert payload["qgis_version"]
    for field in EVIDENCE_FIELDS:
        assert payload[field] is True, field

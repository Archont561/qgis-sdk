"""Tests for the repeatable headless QGIS plugin lifecycle harness.

The end-to-end run is opt-in because it needs a real QGIS installation. It is
not a Desktop GUI qualification: the harness passes an opaque ``None`` iface
and only exercises construction, action binding and disposal.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from smoke_support import run_isolated_smoke
from smoke_support.desktop_lifecycle_smoke import (
    LifecycleReport,
    headless_environment,
)


def successful_report() -> LifecycleReport:
    return LifecycleReport(
        platform="Linux-6.1.0-x86_64",
        python_version="3.14.8",
        qgis_version="4.2.3-Belem do Para",
        qt_version="6.11.2",
        qgis_initialised=True,
        plugin_started=True,
        action_names=("ping",),
        action_result=7,
        plugin_unloaded=True,
        owned_resources_released=True,
        qgis_exited=True,
    )


def test_headless_environment_selects_offscreen_and_the_qgis_prefix() -> None:
    prefix = Path("/opt/qgis")
    overrides = headless_environment(prefix, {})

    assert overrides["QT_QPA_PLATFORM"] == "offscreen"
    assert overrides["QGIS_PREFIX_PATH"] == str(prefix)
    assert overrides["PROJ_LIB"] == str(prefix / "share" / "proj")
    assert overrides["PYTHONPATH"] == str(prefix / "share" / "qgis" / "python")


def test_headless_environment_keeps_an_existing_python_path() -> None:
    prefix = Path("/opt/qgis")
    overrides = headless_environment(prefix, {"PYTHONPATH": "/work/src"})

    expected = os.pathsep.join([str(prefix / "share" / "qgis" / "python"), "/work/src"])
    assert overrides["PYTHONPATH"] == expected


def test_report_passes_only_when_every_lifecycle_stage_succeeds() -> None:
    assert successful_report().passed is True
    assert successful_report().to_dict()["passed"] is True

    failed = LifecycleReport.unavailable(error="QGIS import failed")

    assert failed.passed is False
    assert failed.to_dict()["error"] == "QGIS import failed"


def test_report_serialises_to_a_stable_json_shape() -> None:
    payload = json.loads(json.dumps(successful_report().to_dict(), sort_keys=True))

    assert payload["action_names"] == ["ping"]
    assert set(payload) == {
        "action_names",
        "action_result",
        "error",
        "owned_resources_released",
        "passed",
        "platform",
        "plugin_started",
        "plugin_unloaded",
        "python_version",
        "qgis_exited",
        "qgis_initialised",
        "qgis_version",
        "qt_version",
    }


@pytest.mark.desktop
@pytest.mark.smoke
def test_headless_lifecycle_smoke_starts_and_unloads_a_plugin() -> None:
    result = run_isolated_smoke("desktop_lifecycle_smoke", timeout=180)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    assert payload["qgis_initialised"] is True
    assert payload["plugin_started"] is True
    assert payload["action_names"] == ["ping"]
    assert payload["action_result"] == 7
    assert payload["plugin_unloaded"] is True
    assert payload["owned_resources_released"] is True
    assert payload["qgis_exited"] is True

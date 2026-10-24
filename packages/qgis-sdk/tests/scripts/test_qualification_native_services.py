"""Tests for the headless native layer/project services harness.

The end-to-end run is opt-in because it needs a real QGIS installation. It is not
a Desktop GUI qualification: the harness opens a dataset headless and proves the
service contracts, which says nothing about canvas, widgets or a display.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from native_services_smoke import (
    EXPECTED_CRS,
    EXPECTED_FIELDS,
    EXPECTED_GEOMETRY,
    EXPECTED_NAME,
    FIXTURE_DATASET,
    SELECTED_FEATURES,
    NativeServicesReport,
)

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
SMOKE_SCRIPT = SCRIPTS_DIR / "native_services_smoke.py"
SMOKE_ENV_FLAG = "QGIS_SDK_NATIVE_SERVICES_SMOKE"


def successful_report() -> NativeServicesReport:
    return NativeServicesReport(
        platform="Linux-6.1.0-x86_64",
        python_version="3.14.8",
        qgis_version="4.2.3-Belem do Para",
        qt_version="6.11.2",
        qgis_initialised=True,
        layer_opened=True,
        layer_name=EXPECTED_NAME,
        layer_geometry_type=EXPECTED_GEOMETRY,
        layer_field_names=EXPECTED_FIELDS,
        layer_crs=EXPECTED_CRS,
        selection=SELECTED_FEATURES,
        project_layer_ids=("points_c6597b70",),
        scope_closed=True,
        reads_refused_after_close=True,
        settings_round_trip=True,
        settings_refused_after_close=True,
        notification_delivered=True,
        notification_refused_after_close=True,
        qgis_exited=True,
    )


def test_fixture_dataset_is_shipped_with_the_tests() -> None:
    assert FIXTURE_DATASET.is_file(), "the contract fixture must exist"
    payload = json.loads(FIXTURE_DATASET.read_text(encoding="utf-8"))

    assert payload["type"] == "FeatureCollection"
    assert len(payload["features"]) >= max(SELECTED_FEATURES)


def test_report_passes_only_when_every_stage_matches_its_expected_value() -> None:
    assert successful_report().passed is True
    assert successful_report().to_dict()["passed"] is True

    wrong_crs = replace(successful_report(), layer_crs="EPSG:2180")
    empty_selection = replace(successful_report(), selection=())
    no_project = replace(successful_report(), project_layer_ids=())
    lost_setting = replace(successful_report(), settings_round_trip=False)
    leaked_after_close = replace(
        successful_report(), notification_refused_after_close=False
    )

    assert wrong_crs.passed is False
    assert empty_selection.passed is False
    assert no_project.passed is False
    assert lost_setting.passed is False
    assert leaked_after_close.passed is False


def test_unavailable_report_is_serialisable_and_never_passes() -> None:
    failed = NativeServicesReport.unavailable(error="QGIS import failed")

    assert failed.passed is False
    payload = json.loads(json.dumps(failed.to_dict(), sort_keys=True))
    assert payload["error"] == "QGIS import failed"
    assert payload["qgis_initialised"] is False
    assert payload["layer_field_names"] == []
    assert payload["selection"] == []


def test_report_serialises_to_a_stable_json_shape() -> None:
    payload = json.loads(json.dumps(successful_report().to_dict(), sort_keys=True))

    assert set(payload) == {
        "error",
        "notification_delivered",
        "notification_refused_after_close",
        "settings_refused_after_close",
        "settings_round_trip",
        "layer_crs",
        "layer_field_names",
        "layer_geometry_type",
        "layer_name",
        "layer_opened",
        "passed",
        "platform",
        "project_layer_ids",
        "python_version",
        "qgis_exited",
        "qgis_initialised",
        "qgis_version",
        "qt_version",
        "reads_refused_after_close",
        "scope_closed",
        "selection",
    }


@pytest.mark.skipif(
    os.environ.get(SMOKE_ENV_FLAG) != "1",
    reason=f"set {SMOKE_ENV_FLAG}=1 to run the real native services smoke",
)
def test_native_services_smoke_opens_a_layer_and_releases_it() -> None:
    result = subprocess.run(
        [sys.executable, str(SMOKE_SCRIPT)],
        cwd=SCRIPTS_DIR.parents[1],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    assert payload["qgis_initialised"] is True
    assert payload["layer_opened"] is True
    assert payload["layer_name"] == EXPECTED_NAME
    assert payload["layer_crs"] == EXPECTED_CRS
    assert payload["selection"] == list(SELECTED_FEATURES)
    assert payload["scope_closed"] is True
    assert payload["reads_refused_after_close"] is True
    assert payload["settings_round_trip"] is True
    assert payload["settings_refused_after_close"] is True
    assert payload["notification_delivered"] is True
    assert payload["notification_refused_after_close"] is True
    assert payload["qgis_exited"] is True

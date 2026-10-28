"""Opt-in proof inside the real QGIS Desktop executable, offscreen."""

import ast
import os
from pathlib import Path

import pytest
from plugin_app_desktop_smoke import EVIDENCE_FIELDS, PLUGIN_SOURCE, PROBE, run_smoke


def test_failed_or_incomplete_evidence_never_passes() -> None:
    from plugin_app_desktop_smoke import passed

    assert not passed({})
    payload = dict.fromkeys(EVIDENCE_FIELDS, True)
    assert passed(payload)
    payload[EVIDENCE_FIELDS[0]] = False
    assert not passed(payload)
    payload[EVIDENCE_FIELDS[0]] = True
    payload["error"] = "startup failed"
    assert not passed(payload)


def test_probe_and_generated_plugin_are_valid_python() -> None:
    ast.parse(PROBE)
    ast.parse(PLUGIN_SOURCE.replace("NAME", "one").replace("KEY", "1"))


def test_missing_qgis_executable_fails_closed(tmp_path: Path) -> None:
    result = run_smoke(tmp_path)
    assert result["passed"] is False
    assert "QGIS Desktop not found" in result["error"]


@pytest.mark.desktop
@pytest.mark.skipif(
    os.environ.get("QGIS_SDK_PLUGIN_APP_DESKTOP") != "1",
    reason="set QGIS_SDK_PLUGIN_APP_DESKTOP=1 to launch QGIS Desktop",
)
def test_two_apps_inside_the_real_qgis_plugin_manager() -> None:
    result = run_smoke()
    assert result["passed"], result
    assert all(result[field] is True for field in EVIDENCE_FIELDS)

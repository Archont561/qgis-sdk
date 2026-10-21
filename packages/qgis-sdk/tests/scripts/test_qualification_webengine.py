"""Tests for the repeatable headless QGIS and Qt WebEngine qualification harness."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from webengine_smoke import (
    CHROMIUM_FLAGS,
    QualificationReport,
    chromium_version,
    headless_environment,
    qgis_python_path,
)

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
SMOKE_SCRIPT = SCRIPTS_DIR / "webengine_smoke.py"
SMOKE_ENV_FLAG = "QGIS_SDK_HEADLESS_SMOKE"


def test_headless_environment_selects_the_offscreen_platform() -> None:
    overrides = headless_environment(Path("/opt/qgis"), {})

    assert overrides["QT_QPA_PLATFORM"] == "offscreen"


def test_headless_environment_disables_the_chromium_sandbox_and_gpu() -> None:
    overrides = headless_environment(Path("/opt/qgis"), {})

    assert overrides["QTWEBENGINE_CHROMIUM_FLAGS"] == CHROMIUM_FLAGS
    assert "--no-sandbox" in CHROMIUM_FLAGS
    assert "--disable-gpu" in CHROMIUM_FLAGS
    assert "--disable-dev-shm-usage" in CHROMIUM_FLAGS
    assert "--single-process" in CHROMIUM_FLAGS


def test_headless_environment_exposes_the_qgis_prefix_and_python_path() -> None:
    prefix = Path("/opt/qgis")
    overrides = headless_environment(prefix, {})

    assert overrides["QGIS_PREFIX_PATH"] == str(prefix)
    assert overrides["PROJ_LIB"] == str(prefix / "share" / "proj")
    assert overrides["PYTHONPATH"] == str(prefix / "share" / "qgis" / "python")
    assert qgis_python_path(prefix) == prefix / "share" / "qgis" / "python"


def test_headless_environment_keeps_an_existing_python_path() -> None:
    prefix = Path("/opt/qgis")
    overrides = headless_environment(prefix, {"PYTHONPATH": "/work/src"})

    expected = os.pathsep.join([str(prefix / "share" / "qgis" / "python"), "/work/src"])
    assert overrides["PYTHONPATH"] == expected


def test_chromium_version_is_read_from_the_user_agent() -> None:
    user_agent = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "QtWebEngine/6.11.2 Chrome/140.0.0.0 Safari/537.36"
    )

    assert chromium_version(user_agent) == "140.0.0.0"


def test_chromium_version_is_absent_without_a_chrome_token() -> None:
    assert chromium_version("Mozilla/5.0 (X11; Linux x86_64) Gecko/20100101") is None


def test_report_is_qualified_only_when_every_stage_succeeds() -> None:
    successful = QualificationReport(
        platform="Linux-6.1.0-x86_64",
        python_version="3.14.8",
        qgis_version="4.2.3-Belém do Pará",
        qt_version="6.11.2",
        chromium_version="140.0.0.0",
        webengine_available=True,
        qgis_initialised=True,
        load_finished=True,
        qgis_exited=True,
    )

    assert successful.qualified is True
    assert successful.to_dict()["qualified"] is True

    failed = QualificationReport.unavailable(
        error="Qt WebEngine bindings are not installed"
    )

    assert failed.qualified is False
    assert failed.to_dict()["error"] == "Qt WebEngine bindings are not installed"


def test_report_serialises_to_a_stable_json_shape() -> None:
    report = QualificationReport(
        platform="Linux-6.1.0-x86_64",
        python_version="3.14.8",
        qgis_version="4.2.3-Belém do Pará",
        qt_version="6.11.2",
        chromium_version="140.0.0.0",
        webengine_available=True,
        qgis_initialised=True,
        load_finished=True,
        qgis_exited=True,
    )

    payload = json.loads(json.dumps(report.to_dict(), sort_keys=True))

    assert payload["chromium_version"] == "140.0.0.0"
    assert payload["load_finished"] is True
    assert set(payload) == {
        "chromium_version",
        "error",
        "load_finished",
        "platform",
        "python_version",
        "qgis_exited",
        "qgis_initialised",
        "qgis_version",
        "qualified",
        "qt_version",
        "webengine_available",
    }


@pytest.mark.skipif(
    os.environ.get(SMOKE_ENV_FLAG) != "1",
    reason=f"set {SMOKE_ENV_FLAG}=1 to run the real headless QGIS/WebEngine smoke",
)
def test_headless_webengine_smoke_loads_a_page_and_exits_cleanly() -> None:
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
    assert payload["qualified"] is True
    assert payload["qgis_initialised"] is True
    assert payload["load_finished"] is True
    assert payload["qgis_exited"] is True
    assert payload["webengine_available"] is True
    assert payload["chromium_version"] is not None

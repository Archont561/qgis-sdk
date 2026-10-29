"""Exercise the public pytest smoke-selection interface."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG = "packages/qgis-sdk-python/pyproject.toml"
TESTS = "packages/qgis-sdk-python/tests/scripts"
SMOKES = (
    "test_headless_webengine_smoke_loads_a_page_and_exits_cleanly",
    "test_headless_lifecycle_smoke_starts_and_unloads_a_plugin",
    "test_headless_qt_scheduler_smoke_adopts_the_seam",
    "test_native_services_smoke_opens_a_layer_and_releases_it",
    "test_real_qgis_desktop_qualifies_the_adapter_lifecycle",
    "test_real_qgis_desktop_loads_and_unloads_the_generated_plugin",
    "test_two_apps_inside_the_real_qgis_plugin_manager",
)


def collect(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-c",
            CONFIG,
            TESTS,
            "--collect-only",
            "-q",
            *arguments,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_smoke_tests_are_explicitly_selected_not_in_the_default_suite():
    default = collect()
    assert default.returncode == 0, default.stdout + default.stderr
    assert not any(name in default.stdout for name in SMOKES)
    native = collect("-m", "native and not smoke")
    # In a QGIS-free environment this directory has no other native tests.
    assert native.returncode in (0, 5), native.stdout + native.stderr
    assert not any(name in native.stdout for name in SMOKES)
    smoke = collect("-m", "smoke")
    assert smoke.returncode == 0, smoke.stdout + smoke.stderr
    for name in SMOKES:
        assert name in smoke.stdout
    assert "7 tests collected" in smoke.stdout or "7/" in smoke.stdout

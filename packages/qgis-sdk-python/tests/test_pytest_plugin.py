"""The pytest plugin behind ``qgis-sdk test``: markers, the pure guard, the gate.

Each case runs a real pytest in a subprocess, the way the command does, so what
is asserted is the exit code and output a user would see.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from qgis_sdk.pytest_plugin import TARGET_ENV

PLUGIN = "qgis_sdk.pytest_plugin"
SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"


def run_pytest(
    project: Path, *args: str, target: str | None = None
) -> subprocess.CompletedProcess[str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {TARGET_ENV, "PYTEST_ADDOPTS", "PYTEST_CURRENT_TEST"}
    }
    env["PYTHONPATH"] = str(SOURCE_ROOT)
    if target is not None:
        env[TARGET_ENV] = target
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            PLUGIN,
            "-p",
            "no:cacheprovider",
            "-q",
            "--no-header",
            *args,
        ],
        cwd=project,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def write_tests(project: Path, source: str) -> None:
    (project / "test_sample.py").write_text(source, encoding="utf-8")


def test_the_markers_are_registered_so_strict_marker_projects_pass(
    tmp_path: Path,
) -> None:
    write_tests(
        tmp_path,
        "import pytest\n"
        "@pytest.mark.qgis\n"
        "def test_a(): pass\n"
        "@pytest.mark.desktop\n"
        "def test_b(): pass\n",
    )

    result = run_pytest(tmp_path, "--strict-markers")

    assert result.returncode == 0, result.stdout + result.stderr


def test_the_pure_target_refuses_a_native_import_with_the_way_out(
    tmp_path: Path,
) -> None:
    write_tests(tmp_path, "import qgis.core\n\ndef test_a(): pass\n")

    result = run_pytest(tmp_path, target="pure")

    assert result.returncode != 0
    assert "pure target" in result.stdout
    assert "qgis-sdk test --target qgis" in result.stdout
    assert "qgis.core" in result.stdout


def test_without_a_target_the_guard_is_off(tmp_path: Path) -> None:
    write_tests(
        tmp_path,
        "import pytest\ndef test_a():\n    pytest.importorskip('PyQt6.QtCore')\n",
    )

    result = run_pytest(tmp_path)

    # Either Qt is there and the test passes, or it skips: the import is tried.
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("target", ["qgis", "desktop"])
def test_a_native_target_whose_every_test_skipped_does_not_pass(
    tmp_path: Path, target: str
) -> None:
    write_tests(
        tmp_path,
        "import pytest\n"
        f"@pytest.mark.{target}\n"
        "def test_a():\n"
        "    pytest.skip('no runtime here')\n",
    )

    result = run_pytest(tmp_path, target=target)

    assert result.returncode == 1, result.stdout + result.stderr
    assert f"every test of the {target} target was skipped" in result.stdout


def test_a_native_target_with_one_real_pass_keeps_pytests_verdict(
    tmp_path: Path,
) -> None:
    write_tests(
        tmp_path,
        "import pytest\n"
        "def test_a(): pass\n"
        "def test_b():\n"
        "    pytest.skip('one skip is fine')\n",
    )

    result = run_pytest(tmp_path, target="qgis")

    assert result.returncode == 0, result.stdout + result.stderr


def test_the_pure_target_does_not_apply_the_skip_gate(tmp_path: Path) -> None:
    write_tests(
        tmp_path,
        "import pytest\ndef test_a():\n    pytest.skip('platform specific')\n",
    )

    result = run_pytest(tmp_path, target="pure")

    assert result.returncode == 0, result.stdout + result.stderr


def test_qgis_app_in_the_pure_target_fails_and_names_the_target(
    tmp_path: Path,
) -> None:
    write_tests(tmp_path, "def test_a(qgis_app): pass\n")

    result = run_pytest(tmp_path, target="pure")

    assert result.returncode == 1
    assert "qgis-sdk test --target qgis" in result.stdout


def test_qgis_iface_outside_desktop_fails_and_names_the_target(
    tmp_path: Path,
) -> None:
    write_tests(tmp_path, "def test_a(qgis_iface): pass\n")

    result = run_pytest(tmp_path, target="qgis")

    assert result.returncode == 1
    assert "qgis-sdk test --target desktop" in result.stdout


def test_qgis_app_without_pyqgis_fails_in_the_qgis_target(tmp_path: Path) -> None:
    write_tests(
        tmp_path,
        "import sys\n"
        "sys.modules['qgis'] = None  # make the bindings unimportable here\n"
        "def test_a(qgis_app): pass\n",
    )

    result = run_pytest(tmp_path, target="qgis")

    assert result.returncode == 1
    assert "PyQGIS is not importable" in result.stdout
    assert "--qgis-prefix" in result.stdout

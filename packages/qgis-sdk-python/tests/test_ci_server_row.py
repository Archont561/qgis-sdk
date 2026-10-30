"""The `server` CI row resolves to a verdict, not to a log line.

`scripts/ci.py server` is what `.github/workflows/ci.yml` runs to prove this
interpreter has a QGIS Server (TASK-80 AC 2). Two ways it could lie are worth a
test: reporting success because pytest skipped everything, and reporting failure
with no sentence saying which build was wrong. Both are decided in that helper,
so both are checked here without QGIS, without pytest-in-pytest and without a
subprocess.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[3]
CI_SCRIPT = ROOT / "scripts" / "ci.py"


def load_ci() -> ModuleType:
    """Import ``scripts/ci.py`` by path; it is a script, not a package module."""
    spec = importlib.util.spec_from_file_location("ci_script", CI_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def ci(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    module = load_ci()
    monkeypatch.setattr(module, "annotation", lambda title, text: None)
    return module


def completed(code: int, output: str) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=code, stdout=output)


def test_a_qgis_without_server_bindings_is_named_and_fails(
    ci: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        ci.subprocess,
        "run",
        lambda *a, **k: completed(1, "ModuleNotFoundError: No module named 'qgis'"),
    )

    assert ci.server([]) == 1


def test_a_probe_that_prints_no_server_class_is_not_a_verdict(
    ci: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A probe that exits 0 but never reaches `QgsServer` means the import chain
    # is not what the row assumes; treating it as present would hide that.
    monkeypatch.setattr(
        ci.subprocess, "run", lambda *a, **k: completed(0, "4.2.3-Belém do Pará\n")
    )

    assert ci.server([]) == 1


def test_a_green_run_returns_the_pytest_status(
    ci: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    log = tmp_path / "server-host.log"
    log.write_text("3 passed\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        ci.subprocess, "run", lambda *a, **k: completed(0, "4.2.3\nQgsServer\n")
    )
    monkeypatch.setattr(ci, "run_logged", lambda command, path: 0)

    assert ci.server([]) == 0


def test_a_row_that_collected_nothing_fails(
    ci: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    log = tmp_path / "server-host.log"
    log.write_text("no tests ran in 0.01s\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        ci.subprocess, "run", lambda *a, **k: completed(0, "4.2.3\nQgsServer\n")
    )
    monkeypatch.setattr(ci, "run_logged", lambda command, path: 5)

    assert ci.server([]) == 1


def test_a_failing_server_test_returns_its_status(
    ci: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    log = tmp_path / "server-host.log"
    log.write_text("1 failed\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        ci.subprocess, "run", lambda *a, **k: completed(0, "4.2.3\nQgsServer\n")
    )
    monkeypatch.setattr(ci, "run_logged", lambda command, path: 3)

    assert ci.server([]) == 3

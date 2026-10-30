"""The LTS CI row resolves to a verdict, not to a log line.

`scripts/ci.py lts` is what `.github/workflows/ci.yml` runs to prove this
interpreter has QGIS 3.44 with a Desktop *and* server bindings, on the PyQt
binding that LTS ships. Three ways it could lie are worth a test: reporting
success because pytest skipped everything, reporting success because only one
of the two modules ran, and failing with no sentence saying which build was
wrong. All three are decided in that helper, so all three are checked here
without QGIS, without pytest-in-pytest and without a real subprocess.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[3]
CI_SCRIPT = ROOT / "scripts" / "ci.py"

PROBE_OUTPUT = "qgis 3.44.7\nqgisserver QgsServer\nqt 5.15.13\nbinding PyQt5\n"


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


def runner(ci: ModuleType, monkeypatch: pytest.MonkeyPatch, logs: dict[str, str]):
    """Answer the probe with a healthy build and pytest with ``logs``."""
    monkeypatch.setattr(
        ci.subprocess, "run", lambda *a, **k: completed(0, PROBE_OUTPUT)
    )

    def run_logged(command: list[str], path: Path) -> int:
        module = next((word for word in command if word.endswith(".py")), "")
        text = logs.get(Path(module).name, "1 passed in 0.10s\n")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return 1 if ("failed" in text or not text.strip()) else 0

    monkeypatch.setattr(ci, "run_logged", run_logged)


def test_a_qgis_without_server_bindings_is_named_and_fails(
    ci: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        ci.subprocess,
        "run",
        lambda *a, **k: completed(1, "ModuleNotFoundError: No module named 'qgis'"),
    )

    assert ci.lts([]) == 1


def test_a_probe_that_prints_no_server_class_is_not_a_verdict(
    ci: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A probe that exits 0 but never reaches `QgsServer` means the import chain
    # is not what the row assumes; treating it as present would hide that.
    monkeypatch.setattr(
        ci.subprocess, "run", lambda *a, **k: completed(0, "qgis 3.44.7\n")
    )

    assert ci.lts([]) == 1


def test_a_green_row_runs_both_modules(
    ci: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    runner(ci, monkeypatch, {})

    assert ci.lts([]) == 0
    # One log per module: the row proves the Desktop half *and* the server half,
    # so neither can hide behind the other's summary line.
    assert sorted(path.name for path in (tmp_path / "lts").glob("*.log")) == [
        "test_lts_native.py.log",
        "test_server_devtools_native.py.log",
        "test_server_native.py.log",
    ]


def test_a_module_that_collected_nothing_fails(
    ci: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    runner(ci, monkeypatch, {"test_lts_native.py": "no tests ran in 0.01s\n"})

    assert ci.lts([]) == 1


def test_a_module_that_skipped_fails_the_row(
    ci: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # `importorskip` is how a native module says "this host cannot run me". On
    # the LTS row that means a host the row set out to prove was not proven.
    monkeypatch.chdir(tmp_path)
    runner(ci, monkeypatch, {"test_server_native.py": "3 skipped, 4 passed in 1.20s\n"})

    assert ci.lts([]) == 1


def test_a_failing_module_returns_its_status(
    ci: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    runner(ci, monkeypatch, {"test_lts_native.py": "1 failed, 6 passed in 2.00s\n"})

    assert ci.lts([]) == 1


def test_an_explicit_command_replaces_the_module_loop(
    ci: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        ci.subprocess, "run", lambda *a, **k: completed(0, PROBE_OUTPUT)
    )
    seen: list[list[str]] = []

    def run_logged(command: list[str], path: Path) -> int:
        seen.append(command)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("2 passed in 0.20s\n")
        return 7

    monkeypatch.setattr(ci, "run_logged", run_logged)

    assert ci.lts(["python", "-m", "pytest", "somewhere"]) == 7
    assert seen == [["python", "-m", "pytest", "somewhere"]]

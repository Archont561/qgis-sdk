"""The test layers are declared, selectable and honest about what they need (TASK-7).

Every test in this suite belongs to exactly one layer. The pure layer runs
without QGIS, Qt or a display; the native layers (``qt``, ``qgis``,
``webengine``) need the real bindings and skip themselves with a reason when
those are absent; ``desktop`` is the opt-in end-to-end harness against a real
QGIS Desktop. ``-m pure`` and ``-m native`` select the halves, and each native
layer can be selected on its own.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from functools import cache
from pathlib import Path

import layers
import pytest

TESTS = Path(__file__).resolve().parent
PROJECT = TESTS.parent


def _native_modules() -> list[Path]:
    return sorted(TESTS.glob("test_*_native.py"))


def _declared_layer(module: Path) -> str | None:
    """Return the layer a module's ``pytestmark`` names, statically."""
    tree = ast.parse(module.read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if "pytestmark" not in targets:
            continue
        value = node.value
        if isinstance(value, ast.Attribute):
            return value.attr
    return None


def test_every_native_module_declares_which_native_layer_it_needs() -> None:
    assert _native_modules(), "the native modules moved; update this test"
    for module in _native_modules():
        layer = _declared_layer(module)
        assert layer in layers.NATIVE_LAYERS, (
            f"{module.name}: pytestmark must name one of {sorted(layers.NATIVE_LAYERS)}"
        )


@cache
def _collect(*args: str) -> tuple[str, ...]:
    """Collect the suite with ``args``; cached, one subprocess per selection."""
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-c",
            str(PROJECT / "pyproject.toml"),
            str(TESTS),
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
            *args,
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=PROJECT,
        env={**os.environ, "PYTHONPATH": str(PROJECT / "src")},
    )
    assert completed.returncode in (0, 5), completed.stdout + completed.stderr
    return tuple(line for line in completed.stdout.splitlines() if "::" in line)


def test_pure_and_native_split_the_suite_without_overlap_or_loss() -> None:
    everything = set(_collect())
    pure = set(_collect("-m", "pure"))
    native = set(_collect("-m", "native"))

    assert pure, "the pure layer selected nothing"
    assert pure | native == everything
    assert pure & native == set()


def test_the_pure_selection_never_reaches_a_native_module() -> None:
    """A module whose name says native is native throughout; the QGIS-free half
    of a qualification harness (``tests/scripts``) is pure by design."""
    for item in _collect("-m", "pure"):
        module = Path(item.split("::")[0])
        if module.parts[-2] != "scripts":
            assert "native" not in module.name, f"{item} is not pure"
        assert not item.endswith("[native]"), "the services native backend is not pure"


def test_each_native_layer_selects_only_its_own_modules() -> None:
    for layer in sorted(layers.NATIVE_LAYERS):
        for item in _collect("-m", layer):
            module = item.split("::")[0]
            path = TESTS / module.removeprefix("tests/")
            if not path.exists() or "services/" in module or "scripts/" in module:
                continue
            assert _declared_layer(path) == layer, f"{item} is not in layer {layer}"


def test_the_environment_is_prepared_without_importing_qt() -> None:
    before = set(sys.modules)
    layers.prepare_environment()

    assert os.environ["QT_QPA_PLATFORM"]
    assert os.environ["QGIS_PREFIX_PATH"]
    imported = {name for name in set(sys.modules) - before if "Qt" in name}
    assert imported == set()


def test_the_bindings_path_is_added_only_when_it_exists(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "prefix", str(tmp_path))
    monkeypatch.setattr(sys, "path", list(sys.path))

    assert layers.qgis_bindings() is None
    layers.prepare_environment()
    assert str(tmp_path / "share" / "qgis" / "python") not in sys.path

    bindings = tmp_path / "share" / "qgis" / "python"
    bindings.mkdir(parents=True)
    assert layers.qgis_bindings() == bindings
    layers.prepare_environment()
    assert sys.path[0] == str(bindings)


def test_the_pure_layer_runs_with_qgis_and_qt_unimportable(tmp_path: Path) -> None:
    """AC 1, as an experiment rather than a reading of the markers.

    A child interpreter refuses every ``qgis``/``PyQt6`` import with the same
    ``ModuleNotFoundError`` a host without the bindings raises, then runs a pure
    module next to the native modules of every layer: the pure tests pass, the
    native modules skip themselves with their reasons, and nothing errors.
    """
    script = """
import sys

class NoBindings:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in {"qgis", "PyQt6", "PyQt5", "PySide6"}:
            raise ModuleNotFoundError(f"No module named {fullname!r}")
        return None

sys.meta_path.insert(0, NoBindings())
import pytest
sys.exit(pytest.main(sys.argv[1:]))
"""
    modules = [
        "test_bridge_contract_bdd.py",
        "test_jobs_native.py",
        "test_network_native.py",
        "test_webengine_native.py",
        "test_webchannel_native.py",
        "test_ui_native.py",
    ]
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            "-c",
            str(PROJECT / "pyproject.toml"),
            "-q",
            "-rs",
            "-p",
            "no:cacheprovider",
            "-p",
            "no:faulthandler",
            *(str(TESTS / module) for module in modules),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    summary = result.stdout.strip().splitlines()[-1]
    assert " passed" in summary and "error" not in summary, summary
    for need in ("forms", "jobs", "networking", "WebEngine", "WebChannel"):
        assert f"native {need} need" in result.stdout, (need, result.stdout)

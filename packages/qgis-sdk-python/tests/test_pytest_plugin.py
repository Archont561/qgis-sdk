"""The pytest plugin behind ``qgis-sdk test``: markers, the pure guard, the gate.

Each case runs a real pytest in a subprocess, the way the command does, so what
is asserted is the exit code and output a user would see.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import layers
import pytest
from qgis_sdk_tools.pytest_plugin import TARGET_ENV

PLUGIN = "qgis_sdk_tools.pytest_plugin"


def run_pytest(
    project: Path, *args: str, target: str | None = None, bindings: Path | None = None
) -> subprocess.CompletedProcess[str]:
    """Run pytest the way the command does; ``bindings`` fakes a QGIS prefix.

    A machine with no QGIS at all would otherwise make every native case reach
    the bindings gate instead of the behaviour under test; a directory holding
    an importable ``qgis.server`` is enough for the plugin, which only asks
    whether the import succeeds.
    """
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {TARGET_ENV, "PYTEST_ADDOPTS", "PYTEST_CURRENT_TEST"}
    }
    env["PYTHONPATH"] = os.pathsep.join(
        [str(bindings), layers.source_path()]
        if bindings is not None
        else [layers.source_path()]
    )
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


def fake_server_bindings(root: Path) -> Path:
    """A directory where ``from qgis import server`` succeeds, and nothing else."""
    bindings = root / "bindings"
    (bindings / "qgis").mkdir(parents=True)
    (bindings / "qgis" / "__init__.py").write_text("", encoding="utf-8")
    (bindings / "qgis" / "server.py").write_text("", encoding="utf-8")
    return bindings


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


def test_the_server_target_whose_every_test_skipped_does_not_pass(
    tmp_path: Path,
) -> None:
    write_tests(
        tmp_path,
        "import pytest\n"
        "@pytest.mark.server\n"
        "def test_a():\n"
        "    pytest.skip('no server project here')\n",
    )

    result = run_pytest(
        tmp_path,
        target="server",
        bindings=fake_server_bindings(tmp_path / "fake"),
    )

    assert result.returncode == 1, result.stdout + result.stderr
    assert "every test of the server target was skipped" in result.stdout


def test_the_server_target_refuses_a_qgis_built_without_server_bindings(
    tmp_path: Path,
) -> None:
    """A skip would read as a pass, so the target names the build instead."""
    write_tests(tmp_path, "def test_a(): pass\n")
    (tmp_path / "conftest.py").write_text(
        # `from qgis import server` then fails the way a conda build does.
        "import sys\nsys.modules['qgis'] = None\n",
        encoding="utf-8",
    )

    result = run_pytest(tmp_path, target="server")

    assert result.returncode == 1, result.stdout + result.stderr
    assert "built without server support" in result.stdout + result.stderr
    assert "WITH_SERVER=ON" in result.stdout + result.stderr


def test_the_server_target_registers_its_marker(tmp_path: Path) -> None:
    write_tests(tmp_path, "@pytest.mark.server\ndef test_a(): pass\n")
    (tmp_path / "test_sample.py").write_text(
        "import pytest\n\n\n@pytest.mark.server\ndef test_a(): pass\n",
        encoding="utf-8",
    )
    # The marker must be known even where the target cannot run, so a project
    # using --strict-markers collects before the bindings are asked for.
    result = run_pytest(tmp_path, "--strict-markers", "--collect-only")

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


def test_the_desktop_target_imports_the_plugin_the_way_qgis_loads_it(
    tmp_path: Path,
) -> None:
    """decision-43: the host package on QGIS_PLUGINPATH shadows the bare source.

    pytest puts the project root first on ``sys.path``; in the desktop target
    the generated host package must win, or ``qgis.utils.loadPlugin`` would
    import the source package, which has no ``classFactory``.
    """
    source = tmp_path / "field_tools"
    source.mkdir()
    (source / "__init__.py").write_text("WHERE = 'source'\n", encoding="utf-8")
    host = tmp_path / ".qgis-sdk" / "dev" / "host" / "field_tools"
    host.mkdir(parents=True)
    (host / "__init__.py").write_text("WHERE = 'host'\n", encoding="utf-8")
    (tmp_path / "conftest.py").write_text(
        "import field_tools\nSEEN = field_tools.WHERE\n", encoding="utf-8"
    )
    write_tests(
        tmp_path,
        "import conftest\nimport field_tools\n\n"
        "def test_a():\n    print('WHERE', field_tools.WHERE, conftest.SEEN)\n",
    )
    (tmp_path / "pytest.ini").write_text("[pytest]\npythonpath = .\n", encoding="utf-8")
    os.environ.pop("QGIS_PLUGINPATH", None)

    plain = run_pytest(tmp_path, "-s")
    assert plain.returncode == 0, plain.stdout + plain.stderr
    assert "WHERE source source" in plain.stdout

    desktop_env = {**os.environ, "QGIS_PLUGINPATH": str(host.parent)}
    desktop = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", PLUGIN, "-q", "-s", "--no-header"],
        cwd=tmp_path,
        env={
            **{k: v for k, v in desktop_env.items() if k != "PYTEST_ADDOPTS"},
            "PYTHONPATH": layers.source_path(),
            TARGET_ENV: "desktop",
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert "WHERE host host" in desktop.stdout, desktop.stdout + desktop.stderr

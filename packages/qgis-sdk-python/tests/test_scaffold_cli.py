"""The ``qgis-sdk`` command: the same plan, reachable from a shell or ``-m``."""

import os
import runpy
import subprocess
import sys
from pathlib import Path

import layers
import pytest
from qgis_sdk_tools.__main__ import app, main
from qgis_sdk_tools.scaffold import ScaffoldOptions, write_scaffold
from typer.testing import CliRunner

runner = CliRunner()


def run_cli(*arguments: str) -> tuple[int, str]:
    result = runner.invoke(
        app,
        list(arguments),
        env={"NO_COLOR": "1", "TERM": "dumb", "COLUMNS": "120"},
    )
    return result.exit_code, result.output


def test_scaffold_writes_every_planned_file_and_reports_the_paths(
    tmp_path: Path,
) -> None:
    target = tmp_path / "field_tools"

    exit_code, output = run_cli("new", str(target), "--plugin", "field_tools")

    assert exit_code == 0, output
    written = sorted(
        path.relative_to(target).as_posix()
        for path in target.rglob("*")
        if path.is_file()
    )
    assert written == [
        ".gitignore",
        "README.md",
        "field_tools/__init__.py",
        "field_tools/metadata.txt",
        "field_tools/plugin.py",
        "pyproject.toml",
        "tests/test_plugin_smoke.py",
    ]
    for path in written:
        assert path in output


def test_the_plugin_name_defaults_to_the_target_directory_name(
    tmp_path: Path,
) -> None:
    target = tmp_path / "survey_helper"

    exit_code, output = run_cli("new", str(target))

    assert exit_code == 0, output
    assert "survey_helper/plugin.py" in output


def test_the_choices_reach_the_generated_files(tmp_path: Path) -> None:
    target = tmp_path / "field_tools"

    exit_code, output = run_cli(
        "new",
        str(target),
        "--plugin",
        "field_tools",
        "--title",
        "Field Survey Tools",
        "--author",
        "Ada Lovelace",
        "--email",
        "ada@example.test",
        "--version",
        "1.2.3",
        "--qgis-minimum-version",
        "4.2",
    )

    assert exit_code == 0, output
    metadata = (target / "field_tools" / "metadata.txt").read_text(encoding="utf-8")
    assert "name=Field Survey Tools" in metadata
    assert "author=Ada Lovelace" in metadata
    assert "email=ada@example.test" in metadata
    assert "version=1.2.3" in metadata
    assert "qgisMinimumVersion=4.2" in metadata
    assert "# Field Survey Tools" in (target / "README.md").read_text(encoding="utf-8")
    plugin_module = (target / "field_tools" / "plugin.py").read_text(encoding="utf-8")
    assert '@plugin(id="field_tools", title="Field Survey Tools")' in plugin_module


def test_dry_run_prints_the_plan_and_touches_nothing(tmp_path: Path) -> None:
    target = tmp_path / "field_tools"

    exit_code, output = run_cli(
        "new", str(target), "--plugin", "field_tools", "--dry-run"
    )

    assert exit_code == 0, output
    assert "field_tools/metadata.txt" in output
    assert not target.exists()


def test_a_collision_is_reported_on_stderr_with_a_failing_exit_code(
    tmp_path: Path,
) -> None:
    target = tmp_path / "field_tools"
    run_cli("new", str(target), "--plugin", "field_tools")

    exit_code, output = run_cli("new", str(target), "--plugin", "field_tools")

    assert exit_code == 1
    assert "Refusing to overwrite" in output


def test_force_is_offered_for_an_intentional_regeneration(tmp_path: Path) -> None:
    target = tmp_path / "field_tools"
    run_cli("new", str(target), "--plugin", "field_tools")
    (target / "README.md").write_text("stale\n", encoding="utf-8")

    exit_code, _ = run_cli("new", str(target), "--plugin", "field_tools", "--force")

    assert exit_code == 0
    assert "Desktop mode" in (target / "README.md").read_text(encoding="utf-8")


def test_an_invalid_plugin_name_is_rejected_before_any_file_is_written(
    tmp_path: Path,
) -> None:
    target = tmp_path / "field_tools"

    exit_code, output = run_cli("new", str(target), "--plugin", "Field Tools")

    assert exit_code == 1
    assert "package name" in output
    assert not target.exists()


def test_scaffold_still_works_as_a_hidden_deprecated_alias_of_new(
    tmp_path: Path,
) -> None:
    """`scaffold` was the 0.1-0.3 spelling; it keeps working but is not advertised."""
    target = tmp_path / "field_tools"

    exit_code, output = run_cli("scaffold", str(target), "--plugin", "field_tools")

    assert exit_code == 0, output
    assert (target / "field_tools" / "metadata.txt").is_file()

    exit_code, output = run_cli("--help")
    assert exit_code == 0
    assert " new " in output
    assert "scaffold" not in output

    exit_code, output = run_cli("scaffold", "--help")
    assert exit_code == 0
    assert "deprecated" in output.lower()


def test_the_command_documents_the_options_it_accepts() -> None:
    exit_code, output = run_cli("new", "--help")

    assert exit_code == 0
    for option in (
        "--plugin",
        "--title",
        "--author",
        "--email",
        "--version",
        "--qgis-minimum-version",
        "--dry-run",
        "--force",
    ):
        assert option in output


def test_main_is_the_callable_the_console_script_registers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The wheel maps ``qgis-sdk`` to this function, so it is tested as such."""
    target = tmp_path / "field_tools"
    monkeypatch.setattr(
        sys, "argv", ["qgis-sdk", "new", str(target), "--plugin", "field_tools"]
    )

    with pytest.raises(SystemExit) as exit_info:
        main()

    assert exit_info.value.code == 0

    assert (target / "field_tools" / "metadata.txt").is_file()
    assert (target / "tests" / "test_plugin_smoke.py").is_file()


def test_the_generated_starter_tests_pass_inside_the_generated_project(
    tmp_path: Path,
) -> None:
    """AC3's smoke test is a real pytest run, not a quoted string."""
    project = tmp_path / "field_tools"
    write_scaffold(ScaffoldOptions.resolve("field_tools"), project)

    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("PYTEST_", "QGIS"))
    }
    env["PYTHONPATH"] = layers.source_path(project)

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=project,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "3 passed" in result.stdout


def test_dash_m_reaches_the_same_command_as_the_console_script(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``python -m qgis_sdk_tools`` must not be a second implementation of the command."""
    target = tmp_path / "demo_tools"  # the package name follows the target directory
    monkeypatch.setattr(sys, "argv", ["qgis_sdk", "new", str(target)])
    # The module is already imported by this file's own import, so drop the cached
    # copy: runpy must execute the entry point the way `-m` does, not reuse it.
    monkeypatch.delitem(sys.modules, "qgis_sdk_tools.__main__", raising=False)

    with pytest.raises(SystemExit) as exit_info:  # click exits zero when standalone
        runpy.run_module("qgis_sdk_tools", run_name="__main__")

    assert exit_info.value.code == 0
    assert (target / "pyproject.toml").is_file()
    assert (target / "demo_tools" / "metadata.txt").is_file()
    assert (target / "tests" / "test_plugin_smoke.py").is_file()

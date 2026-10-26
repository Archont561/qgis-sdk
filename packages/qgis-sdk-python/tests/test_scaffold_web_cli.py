"""``qgis-sdk new`` asks or is told; both roads lead to one plan (TASK-19 AC #1, #3)."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import pytest
from qgis_sdk_tools.__main__ import app
from qgis_sdk_tools.scaffold.questionnaire import (
    INSTALL_QUESTION,
    PACKAGE_MANAGER_QUESTION,
    PLACEMENT_QUESTION,
    WEB_FRAMEWORK_QUESTION,
    Question,
    WebAnswers,
    answer,
    ask_web_questions,
)
from qgis_sdk_tools.testing import FakeCliRuntime
from typer.testing import CliRunner

runner = CliRunner()


def invoke(runtime: FakeCliRuntime, *arguments: str):
    return runner.invoke(app, list(arguments), obj=runtime)


def files_under(target: Path) -> list[str]:
    return sorted(
        p.relative_to(target).as_posix() for p in target.rglob("*") if p.is_file()
    )


# -- the questionnaire, as data --------------------------------------------------


def test_an_empty_answer_takes_the_default_and_case_does_not_matter() -> None:
    assert answer(WEB_FRAMEWORK_QUESTION, "") == "none"
    assert answer(WEB_FRAMEWORK_QUESTION, "  React ") == "react"
    assert answer(PLACEMENT_QUESTION, "window") is None


def test_the_questions_are_asked_in_order_and_stop_after_none() -> None:
    asked: list[Question] = []

    def ask(question: Question, error: str | None) -> str:
        asked.append(question)
        return ""

    assert ask_web_questions(ask) == WebAnswers(None, None, None, False)
    assert asked == [WEB_FRAMEWORK_QUESTION]


def test_a_web_answer_unlocks_placement_manager_and_install() -> None:
    script = iter(["react", "dock", "bun", "yes"])
    asked: list[str] = []

    def ask(question: Question, error: str | None) -> str:
        asked.append(question.key)
        return next(script)

    assert ask_web_questions(ask) == WebAnswers("react", "dock", "bun", True)
    assert asked == [
        WEB_FRAMEWORK_QUESTION.key,
        PLACEMENT_QUESTION.key,
        PACKAGE_MANAGER_QUESTION.key,
        INSTALL_QUESTION.key,
    ]


def test_an_invalid_answer_is_asked_again_with_the_choices() -> None:
    script = iter(["svelte", "vanilla", "", "yarn", "pnpm", "maybe", ""])
    errors: list[str | None] = []

    def ask(question: Question, error: str | None) -> str:
        errors.append(error)
        return next(script)

    assert ask_web_questions(ask) == WebAnswers("vanilla", "dialog", "pnpm", False)
    assert errors == [
        None,
        "choose one of none, vanilla, react",
        None,
        None,
        "choose one of npm, pnpm, bun",
        None,
        "choose one of no, yes",
    ]


# -- flags -------------------------------------------------------------------


def test_flags_write_the_web_plan_without_asking_or_installing(tmp_path: Path) -> None:
    runtime = FakeCliRuntime(
        cwd=tmp_path, interactive=True, input="this is never read\n"
    )

    result = invoke(
        runtime,
        "new",
        "field_tools",
        "--web",
        "react",
        "--placement",
        "dock",
        "--package-manager",
        "bun",
    )

    assert result.exit_code == 0, runtime.stderr + result.output
    assert "web/src/App.tsx" in runtime.stdout
    assert "?" not in runtime.stdout  # no question was printed
    assert runtime.processes == []
    assert (tmp_path / "field_tools" / "web" / "package.json").is_file()
    assert (
        'placement="dock"'
        in (tmp_path / "field_tools/tests/test_plugin.py").read_text()
    )


def test_sdk_dependency_flag_reaches_the_package_json(tmp_path: Path) -> None:
    runtime = FakeCliRuntime(cwd=tmp_path, interactive=True, input="never read\n")

    result = invoke(
        runtime,
        "new",
        "field_tools",
        "--web",
        "vanilla",
        "--sdk-dependency",
        "file:../../packages/qgis-sdk-typescript",
    )

    assert result.exit_code == 0, runtime.stderr + result.output
    package = json.loads((tmp_path / "field_tools/web/package.json").read_text())
    assert package["dependencies"]["@archont561/qgis-sdk"] == (
        "file:../../packages/qgis-sdk-typescript"
    )
    assert "?" not in runtime.stdout


def test_sdk_dependency_without_a_web_framework_is_refused(tmp_path: Path) -> None:
    runtime = FakeCliRuntime(cwd=tmp_path)

    result = invoke(runtime, "new", "field_tools", "--sdk-dependency", "0.9.0")

    assert result.exit_code == 1
    assert "needs a web framework" in runtime.stderr
    assert not (tmp_path / "field_tools").exists()


def test_the_target_resolves_against_the_runtimes_cwd(tmp_path: Path) -> None:
    runtime = FakeCliRuntime(cwd=tmp_path)

    result = invoke(runtime, "new", "nested/field_tools", "--web", "vanilla")

    assert result.exit_code == 0, runtime.stderr
    assert (tmp_path / "nested" / "field_tools" / "web" / "src" / "main.ts").is_file()


def test_an_orphaned_web_flag_fails_before_anything_is_written(tmp_path: Path) -> None:
    runtime = FakeCliRuntime(cwd=tmp_path)

    result = invoke(runtime, "new", "field_tools", "--placement", "dock")

    assert result.exit_code == 1
    assert "A placement needs a web framework" in runtime.stderr
    assert not (tmp_path / "field_tools").exists()


def test_install_without_a_web_ui_is_refused(tmp_path: Path) -> None:
    runtime = FakeCliRuntime(cwd=tmp_path)

    result = invoke(runtime, "new", "field_tools", "--install")

    assert result.exit_code == 1
    assert "--install needs --web" in runtime.stderr
    assert not (tmp_path / "field_tools").exists()


def test_dry_run_prints_the_web_plan_and_touches_nothing(tmp_path: Path) -> None:
    runtime = FakeCliRuntime(cwd=tmp_path)

    result = invoke(
        runtime, "new", "field_tools", "--web", "vanilla", "--dry-run", "--install"
    )

    assert result.exit_code == 0, runtime.stderr
    assert "web/src/app.ts" in runtime.stdout
    assert not (tmp_path / "field_tools").exists()
    assert runtime.processes == []


# -- install ---------------------------------------------------------------------


def test_install_runs_the_managers_install_in_the_web_directory(tmp_path: Path) -> None:
    runtime = FakeCliRuntime(cwd=tmp_path)

    result = invoke(
        runtime,
        "new",
        "field_tools",
        "--web",
        "vanilla",
        "--package-manager",
        "pnpm",
        "--install",
    )

    assert result.exit_code == 0, runtime.stderr
    assert runtime.processes == [
        (("pnpm", "install"), tmp_path / "field_tools" / "web")
    ]
    assert runtime.stdout.rstrip().endswith("pnpm install: done")


def test_a_failed_install_keeps_every_file_and_prints_the_retry(tmp_path: Path) -> None:
    def failing(argv: Sequence[str], cwd: Path) -> int:
        return 127

    runtime = FakeCliRuntime(cwd=tmp_path, run_process=failing)

    result = invoke(runtime, "new", "field_tools", "--web", "react", "--install")

    assert result.exit_code == 1
    assert "web/src/App.tsx" in runtime.stdout
    assert files_under(tmp_path / "field_tools")  # nothing was rolled back
    assert "npm install failed (exit 127)" in runtime.stderr
    assert "cd field_tools/web && npm install" in runtime.stderr
    assert "The project is complete" in runtime.stderr


# -- the interactive road ---------------------------------------------------------


def test_an_interactive_terminal_is_asked_and_the_answers_become_the_plan(
    tmp_path: Path,
) -> None:
    runtime = FakeCliRuntime(
        cwd=tmp_path, interactive=True, input="react\ndock\nbun\nyes\n"
    )

    result = invoke(runtime, "new", "field_tools")

    assert result.exit_code == 0, runtime.stderr + result.output
    out = runtime.stdout
    assert "Add a web UI? [none/vanilla/react] (none): " in out
    assert "Show it as [dialog/dock] (dialog): " in out
    assert "JavaScript package manager [npm/pnpm/bun] (npm): " in out
    assert "Install JavaScript dependencies now? [no/yes] (no): " in out
    assert "web/src/App.tsx" in out
    assert runtime.processes == [(("bun", "install"), tmp_path / "field_tools" / "web")]
    assert (
        'placement="dock"'
        in (tmp_path / "field_tools/tests/test_plugin.py").read_text()
    )


def test_a_wrong_answer_is_asked_again(tmp_path: Path) -> None:
    runtime = FakeCliRuntime(
        cwd=tmp_path, interactive=True, input="svelte\nvanilla\n\n\n\n"
    )

    result = invoke(runtime, "new", "field_tools")

    assert result.exit_code == 0, runtime.stderr
    assert "choose one of none, vanilla, react" in runtime.stdout
    assert (tmp_path / "field_tools" / "web" / "src" / "app.ts").is_file()
    assert runtime.processes == []


def test_end_of_input_counts_as_the_default(tmp_path: Path) -> None:
    runtime = FakeCliRuntime(cwd=tmp_path, interactive=True, input="")

    result = invoke(runtime, "new", "field_tools")

    assert result.exit_code == 0, runtime.stderr
    assert not (tmp_path / "field_tools" / "web").exists()


@pytest.mark.parametrize(
    ("interactive", "arguments"), [(False, ()), (True, ("--no-input",))]
)
def test_a_pipe_or_no_input_never_asks(
    tmp_path: Path, interactive: bool, arguments: tuple[str, ...]
) -> None:
    runtime = FakeCliRuntime(cwd=tmp_path, interactive=interactive, input="react\n")

    result = invoke(runtime, "new", "field_tools", *arguments)

    assert result.exit_code == 0, runtime.stderr
    assert "?" not in runtime.stdout
    assert not (tmp_path / "field_tools" / "web").exists()


def test_help_documents_the_web_options() -> None:
    result = runner.invoke(
        app, ["new", "--help"], env={"NO_COLOR": "1", "TERM": "dumb", "COLUMNS": "200"}
    )

    assert result.exit_code == 0
    for option in (
        "--web",
        "--placement",
        "--package-manager",
        "--install",
        "--no-input",
    ):
        assert option in result.output

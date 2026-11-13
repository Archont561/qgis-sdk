"""The gates the checkout runs on itself, as plain Python functions."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from automation import ci
from automation import clean_code as clean_code_rules
from automation import pr as pr_module
from automation.lib import run

__all__ = [
    "check_commits",
    "check_generated",
    "clean_code",
    "format_check",
    "lint_actions",
    "lint_features",
    "lint_python",
    "lint_repository",
    "native",
    "pr_watch",
    "test_alint_policy",
    "test_python",
    "test_reference_example",
    "test_scripts",
]


def lint_python() -> int:
    """Lint every Python tree with Ruff (scope lives in ``ruff.toml``)."""
    return run(["ruff", "check", "."])


def clean_code() -> int:
    """Fail on any Clean Code finding; the tree has no budget to absorb one.

    Rude reports the metrics at WARNING severity and exits 0, so the gate is
    :mod:`automation.clean_code` reading the report, not the exit status.
    """
    return clean_code_rules.gate()


def format_check() -> int:
    """Fail when a Python file is not formatted the way Ruff formats it."""
    return run(["ruff", "format", "--check", "."])


def lint_actions() -> int:
    """Lint the GitHub Actions workflows with actionlint."""
    workflows = sorted(str(path) for path in Path(".github/workflows").glob("*.yml"))
    return run(["actionlint", *workflows])


def lint_repository() -> int:
    """Apply the repository policy rules (Alint) to the whole checkout."""
    return run(["alint", "check", "."])


def check_commits() -> int:
    """Check the commits in the range against the conventional-commit rules."""
    return run(["convco", "check"])


def pr_watch(pr: int = 0, interval: int = 15, timeout: int = 0, repo: str = "") -> int:
    """Watch a pull request's CI, breaking on the first error."""
    return pr_module.watch(pr=pr, interval=interval, timeout=timeout, repo=repo)


def pr_open(
    title: str = "", base: str = "", body_file: str = "", draft: bool = False
) -> int:
    """Open the pull request for the current branch (AGENTS.md).

    The flags are the command line's own, so `pixi run automation pr_open` and
    `python -m automation.pr open` cannot drift apart.
    """
    arguments = ["open"]
    for flag, value in (
        ("--title", title),
        ("--base", base),
        ("--body-file", body_file),
    ):
        if value:
            arguments.extend([flag, value])
    if draft:
        arguments.append("--draft")
    return pr_module.main(arguments)


def test_scripts() -> int:
    """Run the repository script tests and the README mirror rules."""
    status = run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-c",
            "tests/scripts/pyproject.toml",
            "tests/scripts",
            "-q",
        ]
    )
    if status:
        return status
    return run(
        [
            "alint",
            "check",
            "--only",
            "bridge-readme-mirror",
            "--only",
            "ui-readme-mirror",
            "--only",
            "bridge-readme-alias-name",
            "--only",
            "ui-readme-alias-name",
            ".",
        ]
    )


def test_alint_policy() -> int:
    """Run the tests of the Alint policy itself."""
    return run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-c",
            "tests/scripts/pyproject.toml",
            "tests/alint",
            "-q",
        ]
    )


def test_python() -> int:
    """Run the whole kit suite: both layers, one process, as the release gate does."""
    return run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-c",
            "packages/qgis-sdk-python/pyproject.toml",
            "packages/qgis-sdk-python/tests",
            "-q",
        ]
    )


def native() -> int:
    """Run the native suite and annotate the tests a failure names."""
    return ci.native(list(ci.NATIVE_COMMAND))


def check_generated() -> int:
    """Fail when a generated bridge client is stale."""
    return ci.check_generated()


def test_reference_example() -> int:
    """Run the reference plugins through their own ``qgis-sdk test``."""
    # The reference page is exercised without a display; the Pixi task used to
    # carry this, and the task is where it belongs now that CI calls the task.
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    return ci.reference_example()


def lint_features() -> int:
    """Lint every Gherkin scenario with gherlint.

    gherlint pins pydantic 1, which cannot share an environment with the
    runtime's pydantic 2, so it gets a throwaway venv beside the Pixi
    environments - gitignored, reused between runs.
    """
    venv = Path(".pixi/gherkin")
    python = venv / "bin/python"
    if not python.exists():
        status = run([sys.executable, "-m", "venv", str(venv)])
        if status:
            return status
        status = run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--quiet",
                "--disable-pip-version-check",
                "gherlint==0.5.0",
            ]
        )
        if status:
            return status
    return ci.check_gherkin(str(venv / "bin/gherlint"))

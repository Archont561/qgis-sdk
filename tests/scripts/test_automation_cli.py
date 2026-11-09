"""Keep the task registry and the things that call it in agreement.

`dodo.py` is a contract with three parties: the Pixi task that runs it, the
workflows that name tasks, and `automation/tasks.py` that implements them. A
task renamed in one place and not the other fails at the point a release runs,
not at review, so the three are compared here instead.

The rule the registry exists for: an automation module must not import ``doit``.
The task runner is an interface, and the work has to stay runnable - and
testable - without it.
"""

from __future__ import annotations

import ast
import re
import tomllib
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
DODO = ROOT / "dodo.py"
PIXI = ROOT / "pixi.toml"
AUTOMATION = ROOT / "automation"
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))

# `pixi run -e default automation -- lint_python` and the shorter form without
# the separator both appear; the task name is what follows the CLI word.
CALL = re.compile(r"\bautomation\s+(?:--\s+)?(?P<task>[a-z][a-z_]*)")


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def registered() -> dict[str, str]:
    """Every ``task_*`` function in the registry, with its docstring."""
    return {
        node.name.removeprefix("task_"): ast.get_docstring(node) or ""
        for node in _tree(DODO).body
        if isinstance(node, ast.FunctionDef) and node.name.startswith("task_")
    }


def implemented() -> set[str]:
    """Every public function the automation package offers as a task action."""
    return {
        node.name
        for node in _tree(AUTOMATION / "tasks.py").body
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_")
    }


def workflow_commands() -> list[tuple[str, str]]:
    """Every ``run:`` line of every workflow, with the file it came from."""
    commands = []
    for path in WORKFLOWS:
        workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
        for job in workflow.get("jobs", {}).values():
            for step in job.get("steps", []):
                run = step.get("run")
                if isinstance(run, str):
                    commands.append((path.name, run))
    return commands


def test_every_registered_task_documents_itself() -> None:
    """`doit list` is the CLI's own help, so every task needs a docstring."""
    undocumented = sorted(name for name, doc in registered().items() if not doc)
    assert undocumented == [], f"tasks without a docstring: {undocumented}"


def test_every_task_action_exists_in_the_automation_module() -> None:
    """A registry entry that points at a missing function fails only when run."""
    referenced = {
        node.attr
        for node in ast.walk(_tree(DODO))
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "tasks"
    }
    assert referenced <= implemented(), (
        f"dodo.py calls functions automation.tasks does not define: "
        f"{sorted(referenced - implemented())}"
    )


def test_the_workflows_only_call_registered_tasks() -> None:
    """A workflow naming a task the registry does not have is a broken pipeline."""
    unknown = set()
    for workflow, run in workflow_commands():
        for match in CALL.finditer(run):
            task = match.group("task")
            if task not in registered():
                unknown.add((workflow, task))
    assert unknown == set(), (
        f"workflows call tasks that do not exist: {sorted(unknown)}"
    )


def test_the_registry_is_reachable_from_pixi() -> None:
    """`pixi run automation` must exist, in an environment that has doit."""
    pixi = PIXI.read_text(encoding="utf-8")
    assert re.search(r"\[feature\.python\.tasks\.automation\]\s*\ncmd = \"doit\"", pixi)
    assert re.search(r'^doit = "==[^"]+"$', pixi, re.MULTILINE), (
        "doit must be pinned exactly, like every other tool in this file"
    )
    # Both `default` and `build` are built from `feature.python`, so the pin
    # reaches every environment a task runs in; the Bun-only one has neither,
    # and does not need a task runner to run `bun`.
    manifest = tomllib.loads(pixi)
    assert manifest["feature"]["python"]["tasks"]["automation"]["cmd"] == "doit"
    assert "doit" in manifest["feature"]["python"]["dependencies"]


@pytest.mark.parametrize(
    "module", sorted(path.name for path in AUTOMATION.glob("*.py"))
)
def test_the_automation_never_imports_the_runner(module: str) -> None:
    """The work must run without doit: only dodo.py may know it exists."""
    imports = {
        alias.name.split(".")[0]
        for node in ast.walk(_tree(AUTOMATION / module))
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        (node.module or "").split(".")[0]
        for node in ast.walk(_tree(AUTOMATION / module))
        if isinstance(node, ast.ImportFrom)
    }
    assert "doit" not in imports, f"{module} imports doit; the runner is an interface"


def test_no_workflow_still_calls_a_pixi_task_the_registry_replaced() -> None:
    """The migration is one-way: the old one-line task names must be gone."""
    replaced = (
        "lint-python",
        "format-python-check",
        "lint-features",
        "lint-github-actions",
        "lint-repository",
        "test-alint-policy",
        "test-release-tool",
        "test-reference-example",
        "check-commits",
        "release-plan",
        "release-classify",
        "release-tag",
        "release-stamp",
        "release-verify-versions",
        "release-build-python",
        "release-verify-python",
        "release-checksums",
        "release-github",
    )
    offenders = [
        (workflow, name)
        for workflow, run in workflow_commands()
        for name in replaced
        if re.search(rf"pixi run -e \w+ {re.escape(name)}\b", run)
    ]
    assert offenders == [], f"workflows still call the replaced tasks: {offenders}"

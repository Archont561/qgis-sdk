"""The Clean Code rules as a ratchet over a committed budget.

`rude` (the linter) and `rude-clean-code` (the plugin that adds it rules
CC101-CC303) measure the shape of Python definitions: how long a function or a
class is, how many parameters, returns and locals it has, how deep it nests, how
long its outermost boolean chain is, how many branches it owns.

Every one of those rules reports at ``WARNING`` severity, so ``rude check``
prints them and still exits 0. That makes Rude a report, not a gate. This module
turns the report into a gate without pretending the tree is clean: the findings
of the current tree are written to ``clean_code_budget.json``, and the gate fails
when a run disagrees with that file **in either direction**.

- **Up** - a file grew a violation, or a new file arrived with findings. The
  budget cannot absorb it: clean code is the starting point for new code.
- **Down** - a violation was fixed, in whole or in part. The budget is lowered in
  the same change. That is what makes the number a ratchet rather than a
  ceiling: leaving headroom would let the next regression hide inside it.

``pixi run automation clean_code --rebaseline`` rewrites the file from the live
run; the diff it produces is the review surface. Thresholds live in
``[tool.rude]`` in the root ``pyproject.toml`` and are the plugin's own defaults,
so a tightened threshold shows up as budget movement rather than as a config
nobody reads.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path

from automation.lib.shell import ROOT

BUDGET = ROOT / "clean_code_budget.json"
"""Where the current findings are written, relative to the repository root."""

SCOPE = ("packages", "automation", "scripts", "tests", "examples")
"""The directories Rude reads.

Named here rather than in the configuration because Rude has no exclude
setting: what is linted is what is passed on the command line. Everything else
in the checkout is TypeScript, prose, or a build artifact.
"""

RULES = "CC"
"""The plugin's rule prefix. Ruff owns F/E/W and McCabe ``C901``."""

__all__ = [
    "BUDGET",
    "RULES",
    "SCOPE",
    "compare",
    "diagnostics",
    "gate",
    "parse",
    "render",
]

Budget = Mapping[str, Mapping[str, int]]


def command(scope: Iterable[str] = SCOPE) -> list[str]:
    """The Rude invocation, machine-readable and limited to the plugin's rules.

    ``--select`` repeats ``[tool.rude] select`` on purpose: the config states the
    intent for anyone running Rude by hand, and the flag keeps this gate from
    widening to the F/E/W sets if that table is ever dropped.
    """
    return ["rude", "check", "--select", RULES, "--format", "json", *scope]


def parse(output: str) -> dict[str, dict[str, int]]:
    """Count diagnostics per file and rule code.

    ``--format json`` is one JSON object per line, so a project is a stream
    rather than a document and the parser never has to buffer it whole.
    """
    counts: dict[str, dict[str, int]] = {}
    for line in output.splitlines():
        if not line.strip():
            continue
        diagnostic = json.loads(line)
        code = str(diagnostic["code"])
        if not code.startswith(RULES):
            continue
        path = Path(diagnostic["file"]).resolve()
        try:
            relative = path.relative_to(ROOT).as_posix()
        except ValueError:
            relative = path.as_posix()
        per_file = counts.setdefault(relative, {})
        per_file[code] = per_file.get(code, 0) + 1
    return {path: dict(sorted(codes.items())) for path, codes in sorted(counts.items())}


def diagnostics(scope: Iterable[str] = SCOPE) -> dict[str, dict[str, int]] | None:
    """Run Rude over ``scope`` and return its findings, or ``None`` on failure."""
    executable = shutil.which("rude")
    if executable is None:
        print(
            "clean_code: rude is not on PATH - run this through "
            "`pixi run automation clean_code`",
            file=sys.stderr,
        )
        return None
    arguments = command(scope)
    print(f"automation: {' '.join(arguments)}", flush=True)
    completed = subprocess.run(
        arguments, cwd=ROOT, check=False, capture_output=True, text=True
    )
    # A non-zero status here is Rude failing, not Rude finding something: the
    # plugin's rules are WARNINGs and never change the exit code.
    if completed.returncode != 0:
        print(
            f"clean_code: rude exited {completed.returncode}\n{completed.stderr}",
            file=sys.stderr,
        )
        return None
    return parse(completed.stdout)


def render(budget: Budget) -> str:
    """The budget file's text: sorted, indented, with a trailing newline."""
    document = {
        path: dict(sorted(codes.items())) for path, codes in sorted(budget.items())
    }
    # Tabs, because `biome.json` formats this file's JSON and the checks run
    # both: a budget written with spaces fails `biome check`.
    return f"{json.dumps(document, indent=chr(9), sort_keys=True)}\n"


def load(path: Path = BUDGET) -> dict[str, dict[str, int]]:
    """Read the committed budget, or an empty one when the file is absent."""
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def compare(found: Budget, budget: Budget) -> list[str]:
    """Describe every place where the run and the budget disagree."""
    problems: list[str] = []
    for path in sorted(set(found) | set(budget)):
        now = found.get(path, {})
        then = budget.get(path, {})
        for code in sorted(set(now) | set(then)):
            current = now.get(code, 0)
            committed = then.get(code, 0)
            if current == committed:
                continue
            if not committed:
                problems.append(
                    f"{path}: {code} {current} new violation(s); new code starts clean"
                )
            elif not current:
                problems.append(
                    f"{path}: {code} {committed} fixed; lower the budget to lock it in"
                )
            elif current > committed:
                problems.append(
                    f"{path}: {code} {committed} -> {current} (+{current - committed})"
                )
            else:
                problems.append(
                    f"{path}: {code} {committed} -> {current} (-{committed - current}); "
                    "lower the budget to lock it in"
                )
    return problems


def total(budget: Budget) -> int:
    """How many violations the budget accounts for."""
    return sum(sum(codes.values()) for codes in budget.values())


def _rewrite(found: dict[str, dict[str, int]]) -> int:
    """Write the live run out as the budget."""
    BUDGET.write_text(render(found), encoding="utf-8")
    print(
        f"clean_code: {total(found)} finding(s) in {len(found)} file(s) "
        f"written to {BUDGET.relative_to(ROOT)}",
        flush=True,
    )
    return 0


def _enforce(found: dict[str, dict[str, int]]) -> int:
    """Fail when the live run disagrees with the budget, in either direction."""
    if not BUDGET.exists():
        print(
            f"clean_code: no {BUDGET.relative_to(ROOT)} - create it with "
            "`pixi run automation clean_code --rebaseline`",
            file=sys.stderr,
        )
        return 1
    budget = load()
    problems = compare(found, budget)
    if not problems:
        print(
            f"clean_code: {total(found)} finding(s) in {len(found)} file(s), "
            "exactly the committed budget",
            flush=True,
        )
        return 0
    for problem in problems:
        print(f"clean_code: {problem}", file=sys.stderr)
    print(
        f"clean_code: {len(problems)} difference(s) from "
        f"{BUDGET.relative_to(ROOT)}; fix the code, or re-baseline with "
        "`pixi run automation clean_code --rebaseline` when the change is the "
        "trade you mean to make",
        file=sys.stderr,
    )
    return 1


def gate(*, rebaseline: bool = False, scope: Iterable[str] = SCOPE) -> int:
    """Compare the tree with the budget, or rewrite the budget from the tree."""
    found = diagnostics(scope)
    if found is None:
        return 127 if shutil.which("rude") is None else 1
    return _rewrite(found) if rebaseline else _enforce(found)

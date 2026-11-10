"""Keeps the clean-code gate honest about what it compares.

The gate is only as good as its comparison: `rude check` exits 0 whatever the
Clean Code rules find, so nothing else in the pipeline notices a new 40-line
function. These tests pin the three answers the comparison can give - a file
grew, a file shrank, a file arrived - and the parser that feeds them, without
needing Rude installed.

The budget itself is checked by the gate in CI (`automation clean_code`), not
here: this file must run where the linter is absent.
"""

from __future__ import annotations

import json

from automation import clean_code

ROOT = clean_code.ROOT


def diagnostic(path: str, line: int, code: str, measured: str) -> str:
    """One `--format json` line, as Rude prints it."""
    return json.dumps(
        {
            "file": str(ROOT / path),
            "line": line,
            "column": 0,
            "code": code,
            "message": f"Function 'work' is too long ({measured} lines)",
            "severity": "warning",
            "fixable": False,
        }
    )


def test_parsing_counts_findings_per_file_and_rule() -> None:
    output = "\n".join(
        [
            diagnostic("automation/ci.py", 10, "CC101", "31"),
            diagnostic("automation/ci.py", 40, "CC101", "35"),
            diagnostic("automation/ci.py", 80, "CC302", "4"),
            "",
        ]
    )
    assert clean_code.parse(output) == {"automation/ci.py": {"CC101": 2, "CC302": 1}}


def test_parsing_ignores_the_rules_ruff_owns() -> None:
    """Rude also ships F/E/W and McCabe; `ruff.toml` is where those live."""
    output = "\n".join(
        [
            diagnostic("automation/ci.py", 3, "F401", "0"),
            diagnostic("automation/ci.py", 9, "CC101", "31"),
        ]
    )
    assert clean_code.parse(output) == {"automation/ci.py": {"CC101": 1}}


def test_a_finding_above_the_budget_is_a_failure() -> None:
    found = {"automation/ci.py": {"CC101": 1}}
    budget = {"automation/ci.py": {"CC101": 2}}
    (problem,) = clean_code.compare(found, budget)
    assert "CC101 2 -> 1 (-1)" in problem


def test_a_finding_the_budget_never_had_is_a_new_violation() -> None:
    (problem,) = clean_code.compare({"automation/ci.py": {"CC101": 1}}, {})
    assert "new violation" in problem


def test_a_file_the_budget_does_not_know_must_start_clean() -> None:
    budgets = {"automation/ci.py": {"CC101": 1}}
    found = {"automation/ci.py": {"CC101": 1}, "automation/new.py": {"CC101": 2}}
    (problem,) = clean_code.compare(found, budgets)
    assert problem.startswith("automation/new.py: ")


def test_a_gain_must_lower_the_budget() -> None:
    """Equal is the only quiet answer: headroom would hide the next regression."""
    found = {"automation/ci.py": {"CC101": 1}}
    budget = {"automation/ci.py": {"CC101": 3}}
    (problem,) = clean_code.compare(found, budget)
    assert "3 -> 1 (-2)" in problem


def test_matching_runs_are_silent() -> None:
    budget = {"automation/ci.py": {"CC101": 2, "CC302": 1}}
    assert clean_code.compare(budget, budget) == []


def test_the_budget_file_round_trips() -> None:
    budget = {"automation/ci.py": {"CC302": 1, "CC101": 2}, "examples/simple/x.py": {}}
    rendered = clean_code.render(budget)
    assert json.loads(rendered) == budget
    # Biome formats this file too, and it indents with tabs.
    assert rendered.startswith('{\n\t"automation/ci.py": {')
    assert rendered.endswith("}\n")


def test_the_scope_is_source_not_artifacts() -> None:
    assert clean_code.SCOPE == (
        "packages",
        "automation",
        "scripts",
        "tests",
        "examples",
    )
    assert all((ROOT / directory).is_dir() for directory in clean_code.SCOPE)

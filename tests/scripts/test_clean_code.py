"""Keeps the clean-code gate honest about what it fails on.

The gate is only as good as its reading: ``rude check`` exits 0 whatever the
Clean Code rules find, so nothing else in the pipeline notices a new 40-line
function. These tests pin that reading - the parser, the grouped counts, and the
three answers the gate can give - without needing Rude installed.

There is no budget to test: the gate fails on a finding, full stop. What the
whole-tree run says is the CI job's business, not this file's.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from automation import clean_code

ROOT = clean_code.ROOT


def diagnostic(path: str, line: int, code: str, message: str) -> str:
    """One `--format json` line, as Rude prints it."""
    return json.dumps(
        {
            "file": str(ROOT / path),
            "line": line,
            "column": 2,
            "code": code,
            "message": message,
            "severity": "warning",
            "fixable": False,
        }
    )


def test_parsing_names_the_place_and_the_rule() -> None:
    output = "\n".join(
        [
            diagnostic(
                "automation/commits.py", 10, "CC101", "too long (31 > 30 lines)"
            ),
            diagnostic("automation/commits.py", 80, "CC302", "chain of 4"),
            "",
        ]
    )

    found = clean_code.parse(output)

    assert [finding.code for finding in found] == ["CC101", "CC302"]
    assert found[0].path == "automation/commits.py"
    assert found[0].line == 10
    assert str(found[0]) == (
        "automation/commits.py:10:2: CC101 too long (31 > 30 lines)"
    )


def test_parsing_ignores_the_rules_ruff_owns() -> None:
    """Rude also ships F/E/W and McCabe; `ruff.toml` is where those live."""
    output = "\n".join(
        [
            diagnostic("automation/commits.py", 3, "F401", "unused import"),
            diagnostic("automation/commits.py", 9, "CC101", "too long (31 > 30 lines)"),
        ]
    )

    assert [finding.code for finding in clean_code.parse(output)] == ["CC101"]


def test_counting_groups_findings_per_file_and_rule() -> None:
    output = "\n".join(
        [
            diagnostic("automation/ci/_main.py", 10, "CC101", "too long"),
            diagnostic("automation/ci/_main.py", 40, "CC101", "too long"),
            diagnostic("automation/ci/_main.py", 80, "CC302", "chain of 4"),
        ]
    )

    assert clean_code.counts(clean_code.parse(output)) == {
        "automation/ci/_main.py": {"CC101": 2, "CC302": 1}
    }


def test_a_clean_tree_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(clean_code, "findings", lambda scope: ())

    assert clean_code.gate() == 0


def test_one_finding_fails_the_gate(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """No budget: a single finding is a failure, however small the tree."""
    found = clean_code.parse(
        diagnostic("automation/commits.py", 10, "CC101", "too long (31 > 30 lines)")
    )
    monkeypatch.setattr(clean_code, "findings", lambda scope: found)

    assert clean_code.gate() == 1

    printed = capsys.readouterr().err
    assert "automation/commits.py:10:2: CC101" in printed
    assert "1 finding(s) in 1 file(s)" in printed
    assert "no budget" in printed


def test_a_missing_linter_is_not_a_finding(monkeypatch: pytest.MonkeyPatch) -> None:
    """A gate that cannot run must not read as a gate that passed."""
    monkeypatch.setattr(clean_code.shutil, "which", lambda name: None)

    assert clean_code.gate() == 127


def test_a_failing_linter_is_not_a_finding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(clean_code, "findings", lambda scope: None)
    monkeypatch.setattr(clean_code.shutil, "which", lambda name: "/usr/bin/rude")

    assert clean_code.gate() == 2


def test_the_scope_is_source_not_artifacts() -> None:
    assert clean_code.SCOPE == (
        "packages",
        "automation",
        "scripts",
        "tests",
        "examples",
    )
    assert all((ROOT / directory).is_dir() for directory in clean_code.SCOPE)


def test_the_command_selects_only_the_plugin_rules() -> None:
    assert clean_code.command(["automation"]) == [
        "rude",
        "check",
        "--select",
        "CC",
        "--format",
        "json",
        "automation",
    ]


def test_the_hook_checks_the_paths_it_is_given(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`lefthook` passes the staged files; the answer is the same, sooner."""
    seen: list[list[str]] = []
    monkeypatch.setattr(
        clean_code, "gate", lambda scope=clean_code.SCOPE: seen.append(list(scope)) or 0
    )
    staged = tmp_path / "staged.py"
    staged.write_text("x = 1\n", encoding="utf-8")

    assert clean_code.main([str(staged), str(tmp_path / "deleted.py")]) == 0
    assert seen == [[str(staged)]]


def test_the_hook_says_nothing_to_check_rather_than_running_the_tree(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    called: list[object] = []
    monkeypatch.setattr(
        clean_code, "gate", lambda scope=clean_code.SCOPE: called.append(scope) or 0
    )

    assert clean_code.main([str(tmp_path / "deleted.py")]) == 0
    assert called == []


def test_no_budget_file_is_left_to_absorb_a_finding() -> None:
    """The ratchet is gone: reintroducing the file would reintroduce the slack."""
    assert not (ROOT / "clean_code_budget.json").exists()

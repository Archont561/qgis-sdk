"""The Clean Code rules as a gate: the tree is clean, or this fails.

`rude` (the linter) and `rude-clean-code` (the plugin that adds the CC0xx-CC3xx
rules) measure the shape of Python definitions: how long a function or a class
is, how many parameters, returns and locals it has, how deep it nests, how long
its outermost boolean chain is, how many branches it owns.

Every one of those rules reports at ``WARNING`` severity, so ``rude check``
prints them and still exits 0. That makes Rude a report, not a gate; this module
is what turns the report into one.

**There is no budget.** Until PR #214 the tree kept its findings in
``clean_code_budget.json`` and the gate failed only when a run disagreed with
that file, which is what let a 40-line function be a line item instead of a
review comment. The campaign closed the file to ``{}`` and it is gone: a finding
now fails, wherever it appears. New code starts clean because the tree is clean,
not because the budget has headroom.

Three places enforce it, all of them this function:

- ``pixi run automation clean_code`` - the whole tree, also the CI fast job;
- the ``pre-commit`` hook in ``lefthook.yml`` - the staged files, which is the
  same answer sooner, because every rule here is about one file;
- ``pixi run automation check`` - the fast local gate, next to Ruff and Alint.

``python -m automation.clean_code [path ...]`` is the same gate from a shell, so
the hook needs no task runner and no Pixi task in between.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from automation.lib.shell import ROOT

SCOPE = ("packages", "automation", "scripts", "tests", "examples")
"""The directories Rude reads.

Named here rather than in the configuration because Rude has no exclude
setting: what is linted is what is passed on the command line. Everything else
in the checkout is TypeScript, prose, a build artifact, or the vendored tree
below.
"""

VENDORED = (".agents",)
"""Trees of somebody else's code, which nothing in this repository measures.

`.agents/` holds skill bundles copied in from upstream - 59 files, 10 of them
Python - kept for their instructions, not as this repository's source. Because
Rude has no exclude setting, the only way to keep them out of a run is not to
name them: they are absent from `SCOPE`, `ruff.toml` keeps them out of the
whole-checkout Ruff run (which would otherwise reformat upstream code),
`biome.json` excludes the same tree, and `lefthook.yml` never passes one over.
`_measured` is the last line of defence for a path handed over by hand.
"""

RULES = "CC"
"""The plugin's rule prefix. Ruff owns F/E/W and McCabe ``C901``."""

#: The thresholds a failure points at, for the message that names the fix.
THRESHOLDS = "[tool.rude] in pyproject.toml"

__all__ = [
    "RULES",
    "SCOPE",
    "THRESHOLDS",
    "VENDORED",
    "Finding",
    "command",
    "counts",
    "findings",
    "gate",
    "main",
    "parse",
]


@dataclass(frozen=True, slots=True)
class Finding:
    """One clean-code diagnostic, at the place it was raised."""

    path: str
    line: int
    column: int
    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}:{self.column}: {self.code} {self.message}"


def command(scope: Iterable[str] = SCOPE) -> list[str]:
    """The Rude invocation, machine-readable and limited to the plugin's rules.

    ``--select CC`` keeps the gate inside the clean-code plugin even if the
    config table is ever dropped, so Rude's own F/E/W sets can never leak in.
    ``[tool.rude] ignore`` is applied after ``select`` (including this CLI
    ``--select``), so the config still decides which of the plugin's rules this
    gate measures; the two must stay in sync.
    """
    return ["rude", "check", "--select", RULES, "--format", "json", *scope]


def _vendored(path: str | Path) -> bool:
    """Whether ``path`` sits inside a tree this gate never measures."""
    try:
        relative = Path(path).resolve().relative_to(ROOT)
    except (OSError, ValueError):
        return False
    return bool(relative.parts) and relative.parts[0] in VENDORED


def _measured(scope: Iterable[str]) -> list[str]:
    """The paths to hand Rude, with the vendored tree dropped and the root widened.

    A directory that merely contains a vendored tree - `.` or the checkout root -
    is widened back to `SCOPE`, because Rude would otherwise read `.agents/` and
    report on code this repository does not own.
    """
    wanted: list[str] = []
    for item in scope:
        resolved = Path(item).resolve()
        if _vendored(resolved):
            continue
        wanted.extend(SCOPE if resolved == ROOT else [item])
    return wanted


def _relative(path: str) -> str:
    """``path`` as the repository sees it, so a message is a clickable one."""
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def parse(output: str) -> tuple[Finding, ...]:
    """Every clean-code diagnostic in one ``--format json`` stream.

    ``--format json`` is one JSON object per line, so a project is a stream
    rather than a document and the parser never has to buffer it whole.
    """
    found: list[Finding] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        code = str(record["code"])
        if not code.startswith(RULES):
            continue
        found.append(
            Finding(
                path=_relative(record["file"]),
                line=int(record["line"]),
                column=int(record.get("column", 0)),
                code=code,
                message=str(record["message"]),
            )
        )
    return tuple(found)


def counts(found: Iterable[Finding]) -> dict[str, dict[str, int]]:
    """Findings per file and rule code, both sorted."""
    tally: dict[str, dict[str, int]] = {}
    for finding in found:
        per_file = tally.setdefault(finding.path, {})
        per_file[finding.code] = per_file.get(finding.code, 0) + 1
    return {path: dict(sorted(codes.items())) for path, codes in sorted(tally.items())}


def findings(scope: Iterable[str] = SCOPE) -> tuple[Finding, ...] | None:
    """Run Rude over ``scope`` and return its findings, or ``None`` on failure."""
    executable = shutil.which("rude")
    if executable is None:
        print(
            "clean_code: rude is not on PATH - run this through "
            "`pixi run automation clean_code`",
            file=sys.stderr,
        )
        return None
    arguments = command(_measured(scope))
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


def _report(found: Sequence[Finding]) -> None:
    """Name every finding, then the number of files that have to change."""
    for finding in found:
        print(f"clean_code: {finding}", file=sys.stderr)
    print(
        f"clean_code: {len(found)} finding(s) in {len(counts(found))} file(s); "
        "this gate has no budget - extract or split the definition",
        file=sys.stderr,
    )
    print(f"clean_code: thresholds are {THRESHOLDS}", file=sys.stderr)


def gate(scope: Iterable[str] = SCOPE) -> int:
    """Fail on any clean-code finding in ``scope``; 0 only when there is none."""
    found = findings(scope)
    if found is None:
        return 127 if shutil.which("rude") is None else 2
    if not found:
        print("clean_code: no findings", flush=True)
        return 0
    _report(found)
    return 1


def main(argv: Sequence[str] | None = None) -> int:
    """Gate the paths given, or the whole source tree when none are given.

    The pre-commit hook passes the staged files, and a path that no longer
    exists is a file the commit deleted - there is nothing left to measure.
    """
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments:
        return gate()
    paths = [item for item in arguments if Path(item).exists() and not _vendored(item)]
    if not paths:
        print("clean_code: nothing staged to check", flush=True)
        return 0
    return gate(paths)


if __name__ == "__main__":
    raise SystemExit(main())

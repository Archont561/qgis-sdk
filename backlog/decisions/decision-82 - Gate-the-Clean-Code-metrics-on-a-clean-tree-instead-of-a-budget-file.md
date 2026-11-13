---
id: decision-82
title: Gate the Clean Code metrics on a clean tree, with no budget file to absorb a finding
date: '2026-11-12'
status: accepted
---
## Context

decision-80 turned the Clean Code metrics into a gate by writing the tree's
findings to `clean_code_budget.json` and failing on any *movement*: a file that
grew a violation failed, a violation fixed without the budget being lowered
failed, and a new file had to start clean. It was the right instrument for a
tree that reported 939 findings in 268 files, because it made the campaign
monotonic without stopping the rest of the work.

The campaign that followed took the file to `{}`: 813 findings, then 355, then
43, then zero at PR #214, which also renamed every chunk module and closed the
last CC001. Two things are true now that were not true then:

- **There is nothing left to ratchet.** With an empty budget the file says
  "no finding anywhere", which is the same statement as "fail on any finding" -
  except that it is a second copy of the answer, kept in a file that a change
  can edit. Re-baselining was a command, and a command that rewrites the
  expected result is a command that can absorb a regression.
- **The budget was a review surface that no longer earns its keep.** Reviewing a
  diff of `clean_code_budget.json` means reading counts per file and rule; a
  finding printed with its file, line and message is the same information, in
  the place the fix has to happen.

## Decision

**The gate fails on any finding, and there is no budget file.**

1. `automation/clean_code.py` reads Rude's JSON report and returns 1 when it
   finds anything in `packages`, `automation`, `scripts`, `tests` or `examples`.
   `clean_code_budget.json` is deleted, and a test asserts it stays deleted:
   reintroducing it would reintroduce the slack.
2. **Three enforcers, one implementation.** `pixi run automation clean_code`
   gates the whole tree; the `pre-commit` hook in `lefthook.yml` gates the
   staged files, which is the same answer sooner because every rule is about one
   file; and `python -m automation.clean_code` is the same gate from a shell, so
   the hook needs no task runner between it and the code.
3. **CI gains a fast job that owns the cheap gates** - Ruff lint and format, the
   Clean Code rules, Alint and actionlint - and `checks` requires it next to the
   Linux, coverage and LTS jobs. A regression now fails in about a minute instead
   of after the native suite, and `abort` cancels the rest of the run from there.
4. **Raising a threshold is a decision, not a config edit.** The numbers in
   `[tool.rude]` stay written out, because the length a definition may reach is a
   property of this repository. The difference from decision-80 is what happens
   when the code disagrees with them: the code changes.

## Consequences

- A finding can no longer be paid for; the only way past the gate is to fix the
  definition it names.
- The gate is stricter than the tree, in the sense that any future change which
  adds a 31-line function fails locally and in CI - which is the intent: clean
  code from here on, not a number that is allowed to grow back.
- `--rebaseline` is gone from every task, hook and document; the campaign's
  history stays in decision-80 and in the commit log rather than in a file the
  gate reads.
- The families decision-80 excluded (INFO heuristics, DRY/SOLID, opt-in
  architecture and doc hygiene) are still excluded. Turning one on is a separate
  decision with its own findings to close.

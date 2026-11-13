---
id: TASK-166
title: Adopt Rude and the Clean Code plugin as the source-shape linter, gated by a committed budget
status: Done
assignee: []
created_date: '2026-11-10 11:40'
updated_date: '2026-11-13 09:15'
labels: []
dependencies: []
ordinal: 166000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Ruff and Biome decide what is wrong with an expression; neither sees that a function is 300 lines or a class 700. Adopt `rude` and `rude-clean-code` (CC101-CC303: function and class size, parameters, returns, locals, nesting, boolean chains, branches) as the source-shape layer, and make it enforceable without a 939-finding refactor: the current findings become a committed budget that the gate compares against in both directions, so new code starts clean and a fix banks its gain. Decision-80 records the choice.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 `rude` and `rude-clean-code` are pinned as Pixi PyPI dependencies, install on the default environment's Python, and the plugin's CC rules are discovered without being listed (`rude list` shows CC101-CC303).
- [x] #2 The thresholds live in `[tool.rude]` in the root `pyproject.toml` with every number written out; Ruff keeps `F`/`E`/`W` and `C901` in `ruff.toml`, and the two linters report no finding twice.
- [x] #3 `pixi run automation clean_code` exists (task + `dodo.py` entry + membership of `automation check`) and runs as its own step in the `Linux checks` job.
- [x] #4 `clean_code_budget.json` is committed and the gate fails on a violation added, on a file that arrives with one, and on a violation fixed without the budget being lowered; `--rebaseline` rewrites it.
- [x] #5 `tests/scripts/test_clean_code.py` pins the parser, the three comparison answers and the file round-trip without requiring Rude; the repository suites stay green.
- [x] #6 The layer is documented where contributors read it - `docs/development/README.md`, `apps/docs/guides/doc-14` (site) and the `AGENTS.md` guidance - and decision-80 records what was rejected.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Baseline at adoption: **939 findings in 268 files** (CC101 486, CC104 128, CC102 121, CC303 77, CC103 35, CC201 33, CC202 29, CC302 26, CC301 4), the worst being `packages/qgis-sdk-runtime/src/qgis_sdk/bridge/dispatch.py` (756-line class), `http/_server.py` (699-line class, 379-line function), `bridge/host/_handlers.py` (602-line function) and `packages/qgis-sdk-tools/src/qgis_sdk_tools/generate/_generator.py` (588-line class).

Scope: `packages automation scripts tests examples`, stated in `automation/clean_code.py` because Rude has no exclude setting. `pixi.lock` is refreshed by the `relock` workflow after the manifest edit.

Verification: `rude check --select CC` matches the budget exactly; the budget round-trips through `render`/`load` under tab indentation, which is what Biome formats; `tests/scripts` 332 passed; `alint check .` 9/9.
**2026-11-13 - superseded mechanism, kept for the record.** decision-82 retired the
budget this task introduced (`clean_code_budget.json`, `--rebaseline`, AC #3's
"own step in the `Linux checks` job"). The layer itself is unchanged: Rude and
`rude-clean-code` are still the source-shape linter, the thresholds are still
`[tool.rude]` in `pyproject.toml`, Ruff still keeps `F`/`E`/`W` and `C901`, and
`pixi run automation clean_code` is still the gate. What changed is what the gate
compares against - any finding fails, with no file to rebaseline - and where it
runs: lefthook on the staged files and before a push, and the `Fast gates` CI job
rather than a `Linux checks` step. AC #3 and AC #4 above describe the mechanism as
it shipped on 2026-11-10; decision-82 and decision-84 are the current record.

<!-- SECTION:NOTES:END -->

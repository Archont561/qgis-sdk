---
id: decision-80
title: Gate the Clean Code metrics against a committed budget instead of a clean tree
date: '2026-11-10'
status: accepted
---
## Context

Ruff and Biome cover what can be decided locally, rule by rule: an unused import,
an unformatted expression, an import cycle. Neither of them sees the shape of a
definition. The repository has hand-written functions over 300 lines, classes
over 700, parameter lists over 20, and no number anywhere says whether that is
the style of the codebase or an accident of where the deadlines were.

`rude` (a Python linter with a plugin entry point) plus `rude-clean-code` (a
plugin by the same author as this repository) measure exactly those shapes:
function length, parameters, returns, locals, class length, method count, nesting
depth, boolean-chain length and branch count, as CC101-CC303.

Two facts decide how far that can be enforced today:

- The plugin's rules report at `WARNING` severity, so `rude check` exits 0
  whatever it finds. Running it in CI would print 939 findings and pass.
- The tree is nowhere near the thresholds. At the plugin's defaults
  (30 lines, 5 parameters, 5 returns, 10 locals, 200 class lines, 15 methods,
  nesting 4, 3 operands, 10 branches) it reports **939 findings in 268 files**,
  the worst a 756-line class and a 602-line function. Making the tree clean is a
  refactor of most of `packages/qgis-sdk-runtime`, not a lint fix.

## Decision

1. **Rude and its Clean Code plugin are the source layer's shape linter.** They
   are pinned as Pixi PyPI dependencies (`rude==0.1a4`,
   `rude-clean-code==0.1.0`), configured in the root `pyproject.toml` under
   `[tool.rude]`, and run through `automation clean_code` like every other gate.
   Ruff keeps its own `F`/`E`/`W` and McCabe `C901` sets in `ruff.toml`: a rule
   that both linters implement would be reported twice, by two tools with
   different configs.

2. **The thresholds are the plugin's defaults, written out.** The root
   `pyproject.toml` states each number rather than inheriting it, because the
   number a function may reach is a decision of this repository and should be
   readable in the repository, not in an installed package's source.

3. **The measurement is a budget, and the budget is exact.** `clean_code` writes
   the current findings per file and rule to `clean_code_budget.json` and fails
   when a run disagrees with it in **either** direction:
   - a file that grows a violation fails, and a file with no budget entry that
     arrives with one fails: new code starts clean;
   - a violation fixed without the budget being lowered in the same change fails
     too. Headroom left in the file is where the next regression hides, so the
     budget is a ratchet: it moves down when the code does, in the same diff.

4. **Re-baselining is a commit, not a flag in CI.**
   `pixi run automation clean_code --rebaseline` rewrites the file from the live
   run, so widening the budget is visible in review as numbers going up, in the
   same place where numbers going down are the evidence of a fix.

5. **The scope is source.** `packages`, `automation`, `scripts`, `tests` and
   `examples`: every Python definition this repository writes. Rude has no
   exclude setting, so the scope is stated once in `automation/clean_code.py` and
   passed on the command line. Artifacts and generated trees are outside it.

## Alternatives considered

- **Make the tree clean and enforce a clean tree.** The honest reading of "clean
  code enforcement", and rejected only on size: 939 findings including the 20
  largest definitions in the runtime, which are the dispatcher, the HTTP server,
  the bridge handlers and the schema generator. A refactor of that surface is its
  own task with its own evidence, not a lint adoption.
- **A ceiling instead of an exact budget** ("no more than 939 findings"). Cheap,
  and it lets a fixed violation be re-spent somewhere else. The exact budget
  makes every movement visible and forces the gain to be banked.
- **`# noqa` on every finding.** 939 suppressions turn a readable tree into one
  where the linter's opinion is buried next to the code it objects to, and a
  suppression that outlives its reason looks exactly like a violation someone
  meant to keep.
- **Error severity on the rules and a red build until the refactor lands.** The
  plugin reports `WARNING` and offers no severity setting per project; a local
  rule file that flipped it to `ERROR` would be a wrapper around a one-line
  difference, and the build would be red for as long as the refactor takes.
- **Ruff's `PLR091*` family instead** (too-many-branches, -returns, -statements,
  -arguments, -locals). It covers five of the nine metrics and no class size, no
  nesting depth and no boolean-chain length, and it is already partly ignored in
  `ruff.toml`. Rude covers the set the request names, at the cost of a second
  Python linter.
- **Per-directory thresholds** (strict on `packages/qgis-sdk-tools/src`, relaxed
  elsewhere). It encodes "this code is allowed to be worse" in config, and the
  directory boundaries are not the line between careful and hasty code.

## Consequences

- `automation/tasks.py` gains `clean_code`, `dodo.py` gains the task, and
  `pixi run automation check` includes it, so the local gate and CI run the same
  thing. `Linux checks` runs it as its own step.
- `clean_code_budget.json` is a 1,070-line file that every Python change may
  touch. That is the cost: the alternative is a number nobody sees.
- The budget is generated, and regenerating it is a commit. A pull request that
  re-baselines without fixing anything is a red flag in review by construction -
  the diff is a list of files with larger numbers.
- The layer is only as good as its scope. A new Python directory outside the five
  named ones is not measured until it is added to `SCOPE`, and nothing fails when
  it is missing - a task for the burn-down tracks that.
- Biome formats `clean_code_budget.json`, so the writer emits tabs; a budget
  written with spaces fails the JavaScript gate.

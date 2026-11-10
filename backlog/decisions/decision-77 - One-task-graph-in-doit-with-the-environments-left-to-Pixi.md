---
id: decision-77
title: One task graph in doit, with the environments left to Pixi
date: '2026-11-16'
status: accepted
---
## Context

Repository automation had grown into two vocabularies for the same thing. Thirty-five
Pixi tasks, most of them a one-line `cmd` string into `python scripts/release.py
<subcommand>` or `python scripts/ci.py <step>`; four standalone scripts of 3,311 lines
that had to be run by path; and every workflow step spelling the command out again, so
the only description of what CI does was the YAML.

Splitting a task meant editing `pixi.toml` and the workflow step, and the two could
drift: nothing failed if a workflow named a task the manifest no longer had, because the
name in `pixi run <task>` was resolved at run time. The scripts were also unimportable
by their real name - `tests/scripts/conftest.py` put `scripts/` on `sys.path` so a test
could `import release`, shadowing any module of that name.

The proposal was a single CLI backed by [doit](https://pydoit.org): `dodo.py` as the
task registry, `automation/` as ordinary Python, `pixi run automation <task>` as the
front door.

## Decision

1. **One registry, one front door.** `dodo.py` declares every task; `pixi run automation
   <task>` runs one. `pixi run automation list` is the vocabulary, and a task's
   parameters are documented by the runner, so the list cannot go stale the way a table
   in a document does.
2. **Pixi keeps the environments, and only the environments.** Tasks whose body is a
   single tool invocation - `ruff check --fix` for lefthook, `bun run build`,
   `actionlint`, `pixi upload`, `pixi exec rattler-build` - stay Pixi tasks. Everything
   that is logic or orchestration moved to `automation/tasks.py`.
3. **The Python scripts became a package.** `scripts/{ci,release,report_test_results,compute_commit_base}.py`
   are now `automation/{ci,release,results,commits}.py`, imported as
   `automation.release` rather than as a file on a path. `ROOT` stays
   `Path(__file__).parents[2]`, so the move changed no path arithmetic.
4. **`automation/` never imports `doit`.** Each module keeps its `main()`; a test can
   call a function and assert on the exit status, and `python -m automation.ci run-log …`
   is the same code the task runs. `dodo.py` is the only file that knows a task runner
   exists, and `action()` there adapts an exit status to doit's `None`/`False` contract.
5. **The harness stays a CLI.** `run-log`, `annotate-log`, `report-steps` wrap an
   arbitrary command and turn its tail into a workflow annotation. A task runner cannot
   express "run this unknown command and keep its output", so the workflows keep calling
   `python -m automation.ci <verb> …` directly; what *is* a task - the gate itself - is
   named through the registry.
6. **No caching.** No task declares `file_dep` or `targets`. Every one is a gate or a
   publish step whose answer depends on the whole checkout; a cached "the tree is fine"
   is the failure mode this repository cannot afford, and a release step that silently
   skips is worse than one that reruns.
7. **The one path that bypasses the CLI is the release plan.** `autorelease.yml` decides
   whether a release is due before it installs a Pixi environment, so it calls
   `python3 -m automation.release plan` and the release tool stays stdlib-only. The same
   holds for the commit-range helper and the cross-platform job, which run on
   `setup-python` with no environment at all.

## Alternatives considered

- **Keep the Pixi tasks as the front door and add descriptions.** Cheapest and
  non-breaking, but it leaves 35 tasks with no ordering between them and no parameters:
  `pixi run` cannot express "run the four fast gates" or "this release step waits for
  that one". It also does nothing about the unimportable `scripts/` module names.
- **Adopt a custom linter (`rude`) instead of restructuring.** It solves a different
  problem: per-file AST rules, when what was missing was orchestration.
- **Make `doit` the only entry point and drop the Pixi tasks entirely.** The Bun
  environment would then need Python installed to run `bun`, and every Bun job would pay
  for a Python environment it does not use.
- **Declare `file_dep`/`targets` on the generated artifacts.** Tempting for the docs
  build and the stamped manifests; rejected above - a stale artifact that looks fresh is
  exactly what the generated-file checks exist to catch.

## Consequences

- A new gate is one function in `automation/tasks.py`, one `task_*` in `dodo.py`, and a
  line in the workflow. `tests/scripts/test_automation_cli.py` fails if a workflow names
  a task the registry does not declare, if a task lacks a docstring, if `dodo.py` calls a
  function `automation/tasks.py` does not define, or if any automation module imports
  `doit`.
- The command in a workflow and the command a contributor runs are the same string,
  `pixi run automation <task>`; `test_ci.py` asserts the mapping, so the two cannot drift
  apart silently.
- `pixi run automation -n 4 lint_python lint_repository docs_lint test_scripts` runs
  independent gates in parallel; CI keeps its one-step-per-gate structure so a failure
  still gets its own annotation.
- The dependency surface grows by one pinned PyPI wheel, `doit==0.37.0` (MIT, pure
  Python, `>=3.10`), in `feature.python` - so both `default` and `build` have it and the
  Bun environment does not.
- Historical records in `backlog/` that quote `python scripts/release.py` are left as
  written: they describe what ran then, not what to run now.

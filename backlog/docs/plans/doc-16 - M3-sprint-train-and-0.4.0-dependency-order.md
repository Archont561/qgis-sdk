---
id: doc-16
title: M3 sprint train and 0.4.0 dependency order
type: guide
created_date: '2026-10-25 12:40'
---
# M3 sprint train and 0.4.0 dependency order

**Status:** Planning plus the start of sprint 1. This document orders work the
m-3 tasks already declare; it adds no scope. Sprint membership lives here and
in the milestone body, not in task fields ([doc-10](../doc-10%20-%20Backlog-conventions-vocabulary-statuses-and-predicates.md)).

**Baseline measured on 2026-10-25** at `f8d3946` (after `ts-v0.3.0`): Python
suite 1118 passed / 35 skipped (`pixi run -e default python -m pytest -c
packages/qgis-sdk-python/pyproject.toml packages/qgis-sdk-python/tests -q`),
Bun 197 passed (bridge 187 + alias 10), `tests/scripts` 191 passed.

## 1. Where m-3 starts from

Released: Python `0.3.0` (`python-v0.3.0`), TypeScript `0.3.0` under the new
name `@archont561/qgis-sdk` plus the alias `qgis-sdk` (`ts-v0.3.0`, PR #67;
rename and alias in PR #66, [decision-33](../../decisions/decision-33%20-%20Rename-the-npm-package-to-archont561-qgis-sdk-and-suffix-the-package-directories.md)).
Unreleased on `main` since `python-v0.3.0`: `qgis-sdk new` (TASK-50), derived
ids (TASK-51), `ctx` as a class attribute (TASK-52), curated services on
`PluginContext` (TASK-53).

What the CLI contains today, because the sprint has to start from this:

| Command | State | Owner in m-3 |
| --- | --- | --- |
| `new` (`scaffold` hidden alias) | shipped; plain-QGIS project, no web UI | TASK-19 extends it with web questionnaires |
| `bridge generate` | shipped | — |
| `check` | absent; the import boundary exists only as a test (`tests/test_pure_imports.py`) | **TASK-16** |
| `test` | absent | TASK-26 |
| `dev` | absent | TASK-6, TASK-21 |
| `build` | absent | TASK-8 |

The CLI gains an injectable runtime with the first new command
([decision-34](../../decisions/decision-34%20-%20Hand-CLI-commands-a-runtime-through-ctx.obj-and-library-functions-the-same-runtime-as-a-parameter.md)).

## 2. Dependency read of the m-3 tasks

Read from the task files:

| Task | Declared dependencies | State | Startable now |
| --- | --- | --- | --- |
| [TASK-16](../../tasks/task-16%20-%20Implement-non-mutating-check-and-QGIS-import-diagnostics.md) `check` and import diagnostics | TASK-2 ✓, TASK-11 ✓, TASK-12 ✓ | In Progress | **yes** |
| [TASK-19](../../tasks/task-19%20-%20Scaffold-vanilla-and-React-web-projects-through-validated-questionnaires.md) web scaffolds | TASK-1 ✓, TASK-17 ✓, TASK-18 ✓ | To Do | **yes** |
| [TASK-26](../../tasks/task-26%20-%20Implement-environment-aware-test-CLI-and-runtime-selection.md) `test` CLI | TASK-16 (shared runtime discovery) | To Do | after 16 |
| [TASK-6](../../tasks/task-6%20-%20Implement-QGIS-Desktop-and-standalone-development-modes.md) `dev` modes | TASK-16, TASK-19 | To Do | after 16, 19 |
| [TASK-21](../../tasks/task-21%20-%20Implement-generation-safe-development-refresh-and-reconnection.md) refresh and reconnection | TASK-6 | To Do | after 6 |
| [TASK-8](../../tasks/task-8%20-%20Build-a-validated-QGIS-installable-plugin-ZIP.md) plugin ZIP | TASK-16 (shared checks), TASK-19 (assets) | To Do | after 16, 19 |
| [TASK-30](../../tasks/task-30%20-%20Prepare-and-qualify-0.4.0-release.md) 0.4.0 gate | all of the above | To Do | release gate |

## 3. Sprint train

- **Sprint 1 (started 2026-10-25): TASK-16, then TASK-19.** TASK-16 first
  because it is QGIS-free, introduces the CLI runtime that every later
  command reuses, and delivers the `QGIS001`/`ARCH001` diagnostics that
  promote [decision-14](../../decisions/decision-14%20-%20Enforce-QGIS-free-import-boundaries-during-check.md).
  Its first slice: the `qgis_sdk.check` library (import-time native imports
  with class-scope, `try`, conditional blocks and `TYPE_CHECKING` handled;
  `metadata.txt` presence and required keys), the `check` command over
  `ctx.obj`, and the rule that a project from `qgis-sdk new` passes `check`
  clean. TASK-19 follows, consuming `@archont561/qgis-sdk@0.3.0` by exact
  pin.
- **Sprint 2 (2026-10-25, PR #71): TASK-26, TASK-6.** The `test` runner and
  the Desktop/standalone `dev` modes share one runtime discovery
  (`qgis_sdk.devtools.installs`), plan processes the unit tests assert on,
  and are proven against the binary by one opt-in harness
  (`QGIS_SDK_DEVTOOLS=1`, doc-14). TASK-16's remaining criteria (build reuse)
  move with sprint 3.
- **Sprint 2b (2026-10-25): TASK-56.** The runtime/tools tree split of
  [decision-35](../../decisions/decision-35%20-%20Split-the-Python-SDK-into-a-runtime-a-tools-package-and-a-meta-kit-behind-one-contract.md)
  goes in before sprint 3 so that TASK-8 ships a package boundary and the
  unreleased `pytest_plugin`/`devtools` paths move before anyone pins them.
- **Sprint 3 (2026-10-25): TASK-21, TASK-8.** Refresh on top of `dev`:
  `qgis_sdk_tools.devtools.reloader` (policy, QGIS-free tests) with
  `ResourceScope.on_quiesce` / `PluginRuntime.quiesce` on the runtime side,
  reload on save by default (`--no-watch`), the opt-in devtools harness
  extended to a stuck worker thread, a start failure after teardown, a
  coalesced burst and a watcher-triggered reload. The ZIP:
  `qgis_sdk_tools.bundle.build_plugin` behind `qgis-sdk build`, calling
  `check_project` in-process (decision-8) plus `ENTRY001`/`DEP001`/
  `DEP002`/`WEB001`, the runtime vendored under `<plugin>/_vendor` with
  rewritten imports (decision-35), reproducible archive, and a clean-profile
  install of two plugins in a real QGIS with `qgis_sdk` import refused
  (`QGIS_SDK_BUILD_INSTALL=1`, decision-3). TASK-16's build-reuse criterion
  closes with it.
- **Close: TASK-30 (2026-10-25).** Release gate; the Python minor is the
  deliberate act the version policy requires. Qualified without stamping:
  the required tasks are Done with merged PRs, `release.py plan` yields
  `python-v0.4.0` only with `--bump minor` and skips the bridge, the wheel
  installs and runs `new`/`check`/`build` in a clean venv, every opt-in
  harness passed one file per process (doc-14, "0.4.0 release gate"), and
  two findings were fixed on the way: the generated changelog dropped the
  pre-rename commits of PR #65, and one pytest process could not hold the
  scaffold-web harness next to the other webengine modules. decision-15 is
  accepted; its presentation-state restore stays deferred. The stamp, tag
  and publication are AC4 and wait for an explicit request.

## 4. Hygiene done at sprint start

- TASK-44, TASK-45, TASK-46, TASK-47, TASK-48 (the jobs audit, PR #60,
  commits `dc03278` and `9c74613` on `main`) read *In Progress* with every
  criterion checked; closed Done with their existing notes as evidence.
- TASK-29 (0.3.0 gate) closed: both releases are published and recorded;
  the only unexecuted act, attaching assets to the `ts-v0.2.0` GitHub
  Release by dispatching `release.yml`, is optional now that the old npm
  name is deprecated, and is noted on TASK-55's successor steps instead.
- TASK-33 stays In Progress by design (Windows host blocker, restated
  2026-10-24).

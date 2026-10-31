---
id: TASK-83
title: Prepare and qualify 0.9.0 release
status: Done
assignee: []
created_date: '2026-10-26T10:11:00Z'
updated_date: '2026-10-31 20:10'
labels: []
milestone: m-8
dependencies:
  - TASK-78
  - TASK-80
  - TASK-81
  - TASK-82
  - TASK-115
  - TASK-116
  - TASK-117
type: chore
ordinal: 83000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Explicit release gate for the 0.9.0 hosts and worker-first named jobs release (m-8, decisions 52 and 65, amending decision-53), not evidence of release or permission to publish. Python-only release; the bridge is expected unchanged and that is confirmed, not assumed.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Required work has verified outcomes and test/artifact evidence across the Python suite, tests/scripts, the opt-in harnesses the milestone touched and the example projects; doc-12/doc-13 migration notes cover every added or renamed name, including worker-first jobs, restricted context, named registration, action handles and legacy async/offload migration.
- [x] #2 Use valid SemVer and prereleases such as -rc.1; update actual manifests only for released packages (runtime, tools, kit at one version; the tools runtime range moves with it) and keep protocol versions independent.
- [x] #3 Validate compatibility, licenses, generated-file consistency and clean installation where applicable; qgis-sdk check on a project from the previous minor reports what changed rather than crashing.
- [x] #4 Record artifacts/checks and explicit publishing approval; no stable 1.0.0 promise, automatic publication or invented passing checks. (Approved with "publish" after the green `python-v0.9.0-rc.1` rehearsal; released as `python-v0.9.0` on `181f8cc6`, run 41228399266, recorded in doc-14 under "Released afterwards".); no stable 1.0.0 promise, automatic publication or invented passing checks.
- [x] #5 The expected zero bridge delta is confirmed rather than assumed: no file under packages/qgis-sdk-typescript changed, no npm version is consumed, and HOST_FINGERPRINT and the plugin-description contract version still agree across both languages. A changed wire requires a separate contract/version decision and revised gate.
<!-- AC:END -->

## Released (2026-10-31)

Owner said "publish", after the stamp merged as `181f8cc6`. Two annotated
tags on that commit, rehearsal first because a stable tag spends version
space and an rc spends none:

- `python-v0.9.0-rc.1` (run 41227547204) - green end to end: stamped
  `0.9.0-rc.1`, verified the stamped manifests and the shared contract,
  built and twine-checked three wheels plus three Conda outputs, ran the
  PyPI verify step with every publish step skipped, skipped the
  prefix.dev uploads, and published a GitHub prerelease. PyPI still ended
  at 0.8.0 and npm's `latest` was still 0.6.0 afterwards.
- `python-v0.9.0` (run 41228399266) - `build`, `pypi`, `conda` and
  `github-release` succeeded; `npm`, `ui`, `github-packages` and
  `github-packages-ui` skipped, as a Python-only scope must. The three
  PyPI uploads and the three prefix.dev uploads were real, and the
  prerelease skip step was itself skipped.

PyPI serves 0.9.0 as `latest` for `qgis-sdk`, `qgis-sdk-runtime` and
`qgis-sdk-tools` (digests 1ade63c4, 66738aab, ee057933). A fresh CPython
3.11.2 venv installing the published `qgis-sdk[mcp]==0.9.0` resolves
`mcp 2.3.0` with a clean `pip check`, renders `qgis-sdk mcp --help`,
scaffolds `--host server` with `>=0.9,<0.10` windows that `check` passes,
and `targets` still marks the Windows and macOS QGIS rows unqualified.
npm was not touched: `@archont561/qgis-sdk` stays 0.6.0, which is the
train's whole point.

AC 4 was the last open criterion; all five are checked and the task is
Done. prefix.dev and the release-asset CDN are attested by the run logs
only; Conda and the native QGIS rows remain outside this sandbox.

## The 0.9.0 stamp (2026-10-31)

`release.py stamp --version 0.9.0 --scope python` on this branch, after the
gate recorded above. It moved the kit, runtime and tools manifests, the
kit's two exact pins (runtime and tools, plus `tools[mcp]`), the tools'
runtime range (`>=0.9.0,<0.10`), the recipe's three versions and the
`tools_runtime_requirement`, and both examples' windows (`>=0.9,<0.10`).
Nothing under `packages/qgis-sdk-typescript` moved and no npm version is
consumed, so the bridge stays at 0.6.0 - `verify-versions` reports python
0.9.0, typescript 0.6.0, ui 0.1.0 and contract version 1.

By hand, as the rehearsal predicted: the status lines of the root README
and the three Python package READMEs. doc-12's `0.9.0 migration notes`
heading was already final, so the site publishes
`python-migration/v0-9` without a Draft badge and doc-13 needs no entry.

**On the stamped tree.** Pure suite 2418 passed / 89 skipped / 7
deselected (`test_app_build.py` needs `wheel` and `setuptools` in the
venv, as in every earlier gate), `tests/scripts` 289, Ruff clean, Alint
9/9, both examples green through `qgis-sdk test` (20 and 8) and clean
through `check` (11 and 3 files). `build-python --scope python` builds
and twine-checks the three `0.9.0` wheels; the kit's metadata reads
`qgis-sdk-runtime==0.9.0`, `qgis-sdk-tools==0.9.0` and
`qgis-sdk-tools[mcp]==0.9.0`, the tools' `qgis-sdk-runtime<0.10,>=0.9.0`.
Installed from those wheels into a fresh `venv`,
`qgis-sdk new --host server` and `--host app` scaffold
`>=0.9,<0.10` windows with `check` clean on three and four files.

AC 2 is checked by this PR. AC 4 stays open: no tag is pushed and
nothing is published without explicit approval.

## Merge and the `autorelease` gate (2026-10-31)

PR #158 merged as `63b6d108` with all six CI rows green (the `QGIS 3.44
LTS` row had twice failed on a qgis.org TLS handshake, not on the code;
it now retries, and doc-14 records that). The `autorelease` run on the
merge commit, `41222400860`, is the last outstanding piece of evidence:
its *Run quality gate* step - the one failing with exit 139 since
`bc3fb1f` - succeeded, as did the dry-run packaging check. With that the
TASK-82 lifetime defect is closed end to end.

AC 2 (the 0.9.0 stamp) and AC 4 (publishing approval) remain open: both
wait on explicit authorization, and no manifest has been touched.

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
doc-12's 0.9.0 notes are in place (2026-10-31), which is what AC 1 reads: `apps/docs/guides/doc-12 - qgis-sdk-Python-package-guide.md` gained a `## 0.9.0 migration notes` section ahead of the 0.8.0 ones, covering the names and shapes this minor adds or renames - `[tool.qgis-sdk] hosts` and `ctx.host` with HOST001/HOST002/HOST003, the three server hooks with the generated `serverClassFactory` (`test --target server`, `dev --host server`, the `WITH_SERVER=ON` build it needs, 3.44 LTS alongside 4.x), `qgis_sdk.app.run`/`main` with `AppSession`'s bounded shutdown and the `build --target app` launcher, worker-first jobs with the restricted `WorkerContext`, the owner-scoped named registry (`app.jobs`, `@app.job`, `ctx.jobs.<name>.delay`, `ctx.jobs.plugin`), action handles, `JOB001`-`JOB003`, one `QgsTask` per job, and the legacy `async def` + `await ctx.workers.offload(...)` migration refused at bind time - plus a checklist for a 0.8 project. It states the bridge does not move rather than leaving it to be discovered, and doc-13 needs nothing for this release: no file under `packages/qgis-sdk-typescript` changed. Both reference variants are named there too (`examples/simple`'s app entry, `examples/server`). The gate still has to confirm the zero bridge delta on its own run rather than quoting this note.
Gate record (2026-10-31). The evidence lives in doc-14 under "0.9.0 release gate (2026-10-31)": pure Python suite 2411 passed / 93 skipped / 7 deselected, coverage lane 2411 / 32 skipped, `tests/scripts` 289 passed, Alint 9/9, Ruff clean over 470 files, both reference examples through their own `qgis-sdk test` and `check` (20 and 8 passed; *checked 11 files* and *checked 3 files*, no problems), a clean installation of the three 0.8.0 wheels into a fresh venv (kit, runtime, tools, plus `qgis-sdk new --host server`), `qgis-sdk check` on a 0.8-shaped project reporting `JOB002` instead of crashing, the 0.9.0 stamp rehearsed on a scratch copy of the manifests (kit / runtime / tools / recipe / both example windows; `verify-versions` agreeing on python 0.9.0 and typescript 0.6.0, protocol version still 1), and `plan --scope python --bump minor` naming `python-v0.9.0` with `classify` accepting both `0.9.0` and the `0.9.0rc1` prerelease. No QGIS in this sandbox, so every native layer is recorded as not run here and is carried by the CI rows - the same rows the milestone's tasks quote. AC 5 is confirmed rather than assumed: `git diff origin/main --stat -- packages/qgis-sdk-typescript` is empty, no npm version is consumed, HOST_FINGERPRINT / HOST_SCHEMA_VERSION / BRIDGE_PROTOCOL_VERSION are unchanged from 0.8.0, and `verify-versions` reports the plugin-description contract at version 1 across both languages - so doc-13 needs no entry and the bridge is not released. AC 2 and AC 4 stay open on purpose: no manifest is stamped until the stamp pull request is authorized, and nothing is published without explicit approval.

The gate's first act was to unblock `autorelease`, which had gone red on `main` after PR #157 with exit 139 rather than a test failure. The cause was a lifetime defect in `QgsTaskWorkers`: the adapter released its last Python reference inside `_JobTask.finished()`, while the task manager - which owns the task - still had completion work queued for it, so the process died in `QgsTaskManager::progressChanged`. It reproduced only in whole-suite runs (3 of 4 in one job, 1 of 2 in another; never in isolation, and never in CI's split pure/native lanes), which is why it reached the release path. `finished()` now asks Qt to delete the task and the adapter retires the wrapper, releasing it from its own stack only after `destroyed`; `tests/test_jobs_tasks_native.py` gained `test_a_finished_task_outlives_its_own_completion_callback`, and the test's `progressChanged` probe is disconnected because the manager is the application's singleton. Twelve consecutive whole-suite runs after the fix were green. TASK-82's notes carry the defect and the evidence.
Gate must record the server-bindings row (decision-52 implementation note, 2026-10-30): the in-process QgsServer test of TASK-80 #2 needs a QGIS built with WITH_SERVER=ON plus bindings, which no conda build has (conda-forge passes -D WITH_SERVER=FALSE) and which the workspace pixi environment therefore lacks. State whether the row ran (CI job installing qgis-server plus python3-qgis, or a machine where `from qgis.server import QgsServer` imports) or was blocked, with the evidence, and never count it as passed on the strength of the fake-interface tests.
The server row exists now (2026-10-30): `.github/workflows/ci.yml` gained the `Server host` job (qgis.org `qgis-server` + `python3-qgis` on `ubuntu-24.04`, `scripts/ci.py server`, wired into the `checks` aggregate) and the suite gained the `server` test layer. The gate reads that job's result for TASK-80 AC 2 and records it as run or blocked with the log, never as an assumption; the row's first green run is what moves #2 from "the environment is right" to "the same plugin class serves a request inside a QgsServer".
The `Server host` row has run green once (2026-10-30, run 41109578499): qgis.org `qgis-server` + `python3-qgis` on `ubuntu-24.04`, QGIS 3.44.7 with `qgis.server` present, the `server` layer executed rather than skipped, and the `checks` aggregate gated on it. The gate records that run for TASK-80 AC 2 with the version caveat the task note carries - the repository ships the 3.44 LTS line today, so the row is evidence for the bindings and the dispatcher, not yet a 4.x server claim.
The row is now the `QGIS 3.44 LTS` row and proves both hosts on one build (2026-10-30, decision-70): TASK-80 AC 2 reads its result, and the support matrix gained the linux/QGIS 3.44/Qt 5.15 row it names. QGIS 4.x server is deliberately not chased until a 4.x build with server bindings reaches apt.
The `QGIS 3.44 LTS` row is green with evidence the gate can quote on both halves (2026-10-30, run 41115792940): probe `qgis 3.44.7-Solothurn | qgisserver QgsServer | qt 5.15.13 | binding PyQt5`, `7 passed` Desktop and `3 passed` server, one build proving both hosts (decision-70). The 0.9.0 gate reads the row's own summary lines rather than a colleague's memory of it, and `test_ci_lts_row.py` pins that a skipped or empty module fails the row.
The server host's native half is on the row the gate reads (2026-10-30, run 41124104232): `tests/test_server_native.py` reports `7 passed` on `QGIS 3.44 LTS` with the same plugin's hooks served through a real in-process `QgsServer`, and `tests/test_lts_native.py` `7 passed` for the Desktop half. The gate records those two summary lines - TASK-80 AC 2 is evidence, not intent - plus the 27 pure tests around the mapping, and the capabilities-cache and singleton findings the row produced.

TASK-80 AC 4 is evidence for this gate too (2026-10-30): the `QGIS 3.44 LTS` row now runs three modules - `test_server_native.py`, `test_lts_native.py` and `test_server_devtools_native.py` (opted in with `QGIS_SDK_SERVER_DEV=1`) - so the gate reads the row for the scaffold/build half, the in-process server half *and* `qgis-sdk dev --host server`'s reload. `qgis-sdk test --target server` is the other thing the gate quotes: it is a native target with the skip gate and its own bindings gate, so a run that could not load `qgis.server` fails by name instead of passing as skips.

<!-- SECTION:NOTES:END -->

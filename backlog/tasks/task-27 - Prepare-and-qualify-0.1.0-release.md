---
id: TASK-27
title: Prepare and qualify 0.1.0 release
status: In Progress
assignee: []
created_date: '2026-10-16 12:02'
updated_date: '2026-10-24 10:24'
labels: []
milestone: m-0
dependencies:
  - TASK-2
  - TASK-11
  - TASK-12
  - TASK-13
  - TASK-23
references:
  - doc-7
  - doc-8
priority: high
type: chore
ordinal: 27000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Explicit release gate, not evidence of release or permission to publish. Verify milestone work and obtain explicit release authorization.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Required 0.1.0 work has verified outcomes and relevant test/artifact evidence; unresolved targets/spikes remain blockers.
- [x] #2 Use valid SemVer and prereleases such as 0.1.0-alpha.1; update actual manifests only for released packages and document migration notes.
- [x] #3 Validate compatibility, licenses, generated-file consistency and clean installation where applicable; keep protocol versions independent.
- [ ] #4 Record artifacts/checks and explicit publishing approval; no stable 1.0.0 promise, automatic publication or invented passing checks.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-24 (TASK-27 AC #1, #2, #3 verified; AC #4 held at pre-publish gate per user direction):
- AC #1 (0.1.0 milestone outcomes & blocker accounting): All milestone m-0 tasks (`TASK-2`, `TASK-11`, `TASK-12`, `TASK-13`, `TASK-23`) and `TASK-1`/`TASK-24` are `Done` with verified evidence; `TASK-33` AC #3 (in-Desktop `pydantic==2.14.1` / `pydantic_core==2.50.1` plugin coexistence) and AC #4 (published platform qualification & blocker matrix) are verified and checked, while `TASK-33` AC #1 (Windows/macOS QGIS 4 installation) and AC #2 (display-server GUI + visible in-Desktop WebEngine session) remain documented target blockers. The earlier GitHub Actions outage (`doc-8`) is resolved: on `main` (`a023948`) and PR #37/#38, `ci.yml` (`checks` `120843196144`, `cross-platform (macos-latest)` `120842898256`, `cross-platform (windows-latest)` `120842898251`), `publish-sandbox.yml` (`plan` `120839883187`, `publish` `120839914192`), and `autorelease.yml` (`plan-and-tag` `120843196402`) all succeeded, and `scripts/restore.sh` restores `build`, `bun`, and `default` with 0 manifest integrity failures.
- AC #2 (SemVer, prereleases, scoped manifests, migration notes): `scripts/release.py` (`107 passed` in `tests/scripts/test_release.py`) enforces valid SemVer (`0.1.0`) and prereleases (`0.1.0-alpha.1`, `0.1.0-beta.1`, `0.1.0-rc.1`) and supports `--scope sdk|bridge|all` so only released package manifests are stamped. Documented the 0.1.0 experimental SemVer policy, scoped manifest stamping, and pre-0.1.0 `hello()` removal / public surface in `packages/qgis-sdk/README.md`.
- AC #3 (compatibility, licenses, generated-file consistency, clean installation, independent protocol versions): Added root MIT `LICENSE` and `"license": "MIT"` in `packages/qgis-sdk-bridge/package.json` to match `packages/qgis-sdk/pyproject.toml` and `recipe.yaml`. Verified zero contract-generation drift (`pixi run -e bun bun run sdk:generate` + `git status --porcelain`), 100% Python coverage (`383 passed, 6 skipped`, 918/918 statements) and 100% TypeScript coverage (`90 pass`), all 6 opt-in real-QGIS harnesses passing (`389 passed, 0 skipped` on QGIS 4.2.3 / Qt 6.11.2 / Chromium 140.0.0.0 / CPython 3.14.8), `release-build-python` + `release-verify-python` (`twine check --strict` PASSED), clean isolated `venv` wheel installation (`qgis_sdk.__all__` verified), and independent `PluginDescription.schema_version = 1`.
- AC #4 (explicit publishing approval): Left unchecked by explicit user choice (`qualify_only`). `pixi run -e default release-plan` reports `action=skip scope=all tag=v0.1.0 reason=no stable tag exists yet`; no stable `1.0.0` promise is made and no automatic publication occurs until the user dispatches `autorelease.yml`.
<!-- SECTION:NOTES:END -->

## Comments

<!-- COMMENTS:BEGIN -->
created: 2026-10-21 21:15
---
Open decision for the 0.1.0 boundary, recorded by the clean-code audit (doc-7): `qgis_sdk.hello()` and the bridge's `hello()` are placeholder public API - exported from `qgis_sdk/__init__.py`, documented as a smoke-test API in the package README, and their only test (`tests/test_init.py`) asserts a constant against itself. `tests/test_pure_imports.py` already proves the wiring they were standing in for, importing the package and every pure subpackage with native modules forbidden, so deleting the placeholders costs no coverage. Removal changes the public surface, so it is not a refactor and was deliberately not done here.
---

created: 2026-10-21 21:22
---
Merge-evidence gap to resolve before 0.1.0 ships: GitHub Actions cannot start jobs on this account - every job on every branch, including main's scheduled publish-sandbox run, fails in 2-4 seconds with no step executed and the annotation 'The job was not started because recent account payments have failed or your spending limit needs to be increased.' PR #21 was therefore merged on local verification only (full gate set above), not on green CI. checks/plan/publish evidence for 0.1.0 remains unavailable until billing or the spending limit is fixed, so no release qualification claim that depends on CI can be made yet.
---

created: 2026-10-21 21:36
---
2026-10-21 hello() decision resolved (this task's open 0.1.0-boundary item): PR #23, merge 4162829, drops qgis_sdk.hello() and the bridge's hello(). Public surface is now pinned by tests/test_init.py against qgis_sdk.__all__; the bridge entry module is intentionally empty (test asserts it) and its package.json lost the types mapping because bunup emits no declaration for an exportless entry. Local evidence: coverage 285 passed/3 skipped at 100.00% (792 stmts, -2 for the deleted function), opt-in real-QGIS suite 288 passed/0 skipped on QGIS 4.2.3, bridge 90 tests + tsc + bunup build green, biome/ruff/format/actionlint/skill-creator clean, sdk:generate zero drift, wheel rebuilt with twine PASSED and verified hello-free. Not a breaking bump: PyPI/npm still hold 0.0.0 placeholders and release-plan says action=skip. AC1-AC4 stay unchecked - CI evidence is still impossible on this account (billing/spending-limit annotation reconfirmed on this PR, same 2-4s zero-step failures), which is exactly what #1 requires before 0.1.0 can be qualified.
---

created: 2026-10-21 21:56
---
blocked-by-actions (doc-8): November 2026 at the earliest, and this is now a hard publish block, not only an evidence gap: `release.yml` is the only publisher (OIDC trusted publishing under the pypi/npm environments), so 0.1.0 cannot reach PyPI or npm during the window, and hand-publishing with long-lived registry credentials stays refused per TASK-35. AC4 cannot be produced at all, and AC1 cannot conclude while TASK-13 AC1 and TASK-33 stay open. The boundary is still rehearsed locally - `release-plan` returns action=skip (first-stable guard intact, so nothing is lost by waiting), and release-build-python plus release-verify-python pass on current main.
---
<!-- COMMENTS:END -->

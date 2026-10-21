---
id: TASK-27
title: Prepare and qualify 0.1.0 release
status: To Do
assignee: []
created_date: '2026-10-16 12:02'
updated_date: '2026-10-21 21:22'
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
- [ ] #1 Required 0.1.0 work has verified outcomes and relevant test/artifact evidence; unresolved targets/spikes remain blockers.
- [ ] #2 Use valid SemVer and prereleases such as 0.1.0-alpha.1; update actual manifests only for released packages and document migration notes.
- [ ] #3 Validate compatibility, licenses, generated-file consistency and clean installation where applicable; keep protocol versions independent.
- [ ] #4 Record artifacts/checks and explicit publishing approval; no stable 1.0.0 promise, automatic publication or invented passing checks.
<!-- AC:END -->

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
<!-- COMMENTS:END -->

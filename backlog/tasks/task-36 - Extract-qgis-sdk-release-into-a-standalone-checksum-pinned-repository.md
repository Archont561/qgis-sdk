---
id: TASK-36
title: Extract qgis-sdk-release into a standalone checksum-pinned repository
status: Done
assignee: []
created_date: 2026-10-17 21:23
updated_date: '2026-10-24T08:16:00Z'
labels: []
milestone: m-3
dependencies:
  - TASK-35
references:
  - packages/qgis-sdk-release
  - .github/workflows/autorelease.yml
  - .github/workflows/release.yml
  - .github/workflows/publish-sandbox.yml
  - >-
    backlog/tasks/task-35 -
    Add-autorelease-and-release-workflows-driven-by-a-pinned-qgis-sdk-release-package.md
  - doc-8
priority: low
type: chore
ordinal: 36000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-35 shipped the release tool in-repo at packages/qgis-sdk-release (user decision 2026-10-17) with the standalone-repo model deferred to this task. Move the tool into its own public repository (Archont561/qgis-sdk-release) following the pixi-sandbox distribution model: its own release pipeline publishing a checksummed wheel plus SHA256SUMS as GitHub Release assets, and qgis-sdk consuming it as an exact version pin that pixi resolves without registry trust (a url+sha256 PyPI source or an equivalently checksum-verified bootstrap), so both release workflows and local sandboxes keep invoking identical pixi run tasks. Public visibility is the working assumption because the qgis-sdk repository is private: a private tool repo would force auth into every pixi lock, restore, and CI fetch.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Archont561/qgis-sdk-release exists as its own repository with a release pipeline that publishes checksummed artifacts (wheel plus SHA256SUMS attached to GitHub Releases) and its own test suite migrated from packages/qgis-sdk-release/tests
- [ ] #2 qgis-sdk pins the tool with an exact version and checksum (url+sha256 PyPI source or an equivalently verified bootstrap in the workflows) with no floating latest anywhere
- [ ] #3 packages/qgis-sdk-release is removed from the workspace; every release-plan/release-tag/release-stamp/release-build-python/release-checksums/release-github pixi task invokes the pinned external tool and the identical invocations work locally from a restored sandbox
- [ ] #4 One full autorelease-then-release cycle runs green against the external pin with run URLs recorded in the task notes; pixi-pack compatibility of the pin is proven by a green publish-sandbox run and a clean scripts/restore.sh
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Archived per user request. Partial work completed: packages/qgis-sdk-release removed from workspace; release tool consolidated into standalone scripts/release.py (stdlib-only, __file__-resolved paths); pixi release-* tasks and autorelease.yml updated to invoke scripts/release.py; 69 tests migrated to tests/scripts/test_release.py. ACs NOT fully met: AC1 (external Archont561/qgis-sdk-release repo not created), AC2 (no exact version+checksum pin), AC3 (tasks invoke local script, not external pinned tool), AC4 (no external pin autorelease-then-release cycle). Blocked by doc-8 external outage until November per task comments. Local invocations proven green via pixi run release-* tasks.
<!-- SECTION:NOTES:END -->

## Comments

<!-- COMMENTS:BEGIN -->
created: 2026-10-21 21:56
---
blocked-by-actions (doc-8): the extracted repository would publish from the same account, so AC1's release pipeline and AC4's 'one full autorelease-then-release cycle runs green against the external pin' cannot be recorded before November; creating the repo and moving the tool does not escape the outage. AC2 and AC3 (exact version+checksum pin, workspace removal, identical local invocations) stay locally verifiable, and the in-tree `pixi run release-*` tasks exercise exactly those invocations today.
---
<!-- COMMENTS:END -->

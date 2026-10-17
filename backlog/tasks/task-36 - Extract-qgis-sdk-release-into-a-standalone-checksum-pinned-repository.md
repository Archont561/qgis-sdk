---
id: TASK-36
title: Extract qgis-sdk-release into a standalone checksum-pinned repository
status: To Do
assignee: []
created_date: '2026-10-17 21:23'
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
Created 2026-10-17 as the deferred half of TASK-35: the user chose in-repo implementation now with later extraction. Note the known interaction with the restore RECORD integrity warnings: the tool as an external uv-installed PyPI package with console scripts would add RECORD files to the class pixi-sandbox 0.7.0 verification currently flags, so prefer a python -m entrypoint over a console script or resolve the pixi-sandbox side first.
<!-- SECTION:NOTES:END -->

---
id: TASK-50
title: Rename the scaffold CLI command to new
status: In Progress
assignee:
  - '@agent'
created_date: '2026-10-25T09:18:00Z'
updated_date: '2026-10-25T09:18:00Z'
labels: []
milestone: m-3
dependencies: []
type: feature
ordinal: 50000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Rename the project generator verb from `qgis-sdk scaffold` to `qgis-sdk new`, keeping `scaffold` as a hidden, deprecated alias for one minor so existing scripts do not break. The `qgis_sdk.scaffold` Python API and package name do not change.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 `qgis-sdk new <dir>` and `python -m qgis_sdk new <dir>` write the same project `scaffold` wrote, with the same options
- [ ] #2 `qgis-sdk scaffold` still runs, is absent from `qgis-sdk --help`, and its own `--help` marks it deprecated
- [ ] #3 Generated files, READMEs, guides and skills say `qgis-sdk new`; doc-12 carries an unreleased migration note
- [ ] #4 Task listed in the doc-4 0.4.0 inventory; Python suite and tests/scripts green
<!-- AC:END -->

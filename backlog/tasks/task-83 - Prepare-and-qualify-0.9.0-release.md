---
id: TASK-83
title: Prepare and qualify 0.9.0 release
status: To Do
assignee: []
created_date: '2026-10-26T10:11:00Z'
labels: []
milestone: m-8
dependencies:
  - TASK-78
  - TASK-80
  - TASK-81
  - TASK-82
type: chore
ordinal: 83000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Explicit release gate for the hosts release (m-8, decisions 52-53), not evidence of release or permission to publish. Python-only release; the bridge is expected unchanged and that is confirmed, not assumed.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Required work has verified outcomes and test/artifact evidence across the Python suite, tests/scripts, the opt-in harnesses the milestone touched and the example projects; doc-12/doc-13 migration notes cover every added or renamed name.
- [ ] #2 Use valid SemVer and prereleases such as -rc.1; update actual manifests only for released packages (runtime, tools, kit at one version; the tools runtime range moves with it) and keep protocol versions independent.
- [ ] #3 Validate compatibility, licenses, generated-file consistency and clean installation where applicable; qgis-sdk check on a project from the previous minor reports what changed rather than crashing.
- [ ] #4 Record artifacts/checks and explicit publishing approval; no stable 1.0.0 promise, automatic publication or invented passing checks.
- [ ] #5 The expected zero bridge delta is confirmed rather than assumed: no file under packages/qgis-sdk-typescript changed, no npm version is consumed, and HOST_FINGERPRINT and the plugin-description contract version still agree across both languages.
<!-- AC:END -->

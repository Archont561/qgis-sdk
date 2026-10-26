---
id: TASK-90
title: Prepare and qualify 0.10.0 release
status: To Do
assignee: []
created_date: '2026-10-26T10:11:00Z'
labels: []
milestone: m-9
dependencies:
  - TASK-83
  - TASK-85
  - TASK-86
  - TASK-87
  - TASK-88
  - TASK-89
type: chore
ordinal: 90000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Explicit release gate for the services II release (m-9, decision-54), not evidence of release or permission to publish. Python 0.10.0 paired with a bridge minor carrying the regenerated host manifest.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Required work has verified outcomes and test/artifact evidence across the Python suite, tests/scripts, the opt-in harnesses the milestone touched and the example projects; doc-12/doc-13 migration notes cover every added or renamed name.
- [ ] #2 Use valid SemVer and prereleases such as -rc.1; update actual manifests only for released packages (runtime, tools, kit at one version; the tools runtime range moves with it) and keep protocol versions independent.
- [ ] #3 Validate compatibility, licenses, generated-file consistency and clean installation where applicable; qgis-sdk check on a project from the previous minor reports what changed rather than crashing.
- [ ] #4 Record artifacts/checks and explicit publishing approval; no stable 1.0.0 promise, automatic publication or invented passing checks.
- [ ] #5 The bridge pair is confirmed with evidence: the next @archont561/qgis-sdk minor (regenerated generated/host.ts, HOST_FINGERPRINT moved, HOST_SCHEMA_VERSION and BRIDGE_PROTOCOL_VERSION unchanged) is gated in the same run and tagged on the same merge commit only on the same explicit authorization; release.py verify-versions agrees on the contract version in both languages; doc-22 shows every 0.10.0 service complete.
<!-- AC:END -->

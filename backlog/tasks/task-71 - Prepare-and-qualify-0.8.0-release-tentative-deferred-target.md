---
id: TASK-71
title: Prepare and qualify 0.8.0 release (tentative deferred target)
status: To Do
assignee: []
created_date: '2026-10-26T08:52:00Z'
labels: []
milestone: m-7
dependencies:
  - TASK-10
  - TASK-32
priority: low
type: chore
ordinal: 71000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Explicit release gate, not evidence of release or permission to publish. Verify milestone work and obtain explicit release authorization. Fresh scope/go-no-go approval is required; 0.8.0 is reserved, not a commitment to native shipping. Re-pointed from 0.7.0 on 2026-10-26, when the UI toolkit release (m-6, TASK-32) took that number.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Required 0.8.0 work has verified outcomes and relevant test/artifact evidence; unresolved targets/spikes remain blockers.
- [ ] #2 Use valid SemVer and prereleases such as 0.8.0-alpha.1; update actual manifests only for released packages and document migration notes.
- [ ] #3 Validate compatibility, licenses, generated-file consistency and clean installation where applicable; keep protocol versions independent.
- [ ] #4 Record artifacts/checks and explicit publishing approval; no stable 1.0.0 promise, automatic publication or invented passing checks.
- [ ] #5 The expected zero bridge delta is confirmed rather than assumed: no file under packages/qgis-sdk-typescript changed, no npm version is consumed, and the plugin-description contract version still agrees across both languages.
<!-- AC:END -->

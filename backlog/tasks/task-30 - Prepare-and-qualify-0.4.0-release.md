---
id: TASK-30
title: Prepare and qualify 0.4.0 release
status: To Do
assignee: []
created_date: '2026-10-16 12:02'
updated_date: '2026-10-21 21:56'
labels: []
milestone: m-3
dependencies:
  - TASK-6
  - TASK-8
  - TASK-16
  - TASK-19
  - TASK-21
  - TASK-26
  - TASK-29
references:
  - doc-8
priority: high
type: chore
ordinal: 30000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Explicit release gate, not evidence of release or permission to publish. Verify milestone work and obtain explicit release authorization.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Required 0.4.0 work has verified outcomes and relevant test/artifact evidence; unresolved targets/spikes remain blockers.
- [ ] #2 Use valid SemVer and prereleases such as 0.4.0-alpha.1; stamp the one shared version into both released manifests, advance the minor explicitly at this milestone close, and document migration notes.
- [ ] #3 Validate compatibility, licenses, generated-file consistency and clean installation where applicable; keep protocol versions independent.
- [ ] #4 Record artifacts/checks and explicit publishing approval; no stable 1.0.0 promise, automatic publication or invented passing checks.
<!-- AC:END -->

## Comments

<!-- COMMENTS:BEGIN -->
created: 2026-10-21 21:56
---
blocked-by-actions (doc-8): AC4's CI artifacts, checks and explicit publishing approval cannot exist until runners return, and this minor inherits TASK-27's block. The outage changes nothing about the feature scope that has to land first, so build and verify that locally; only the qualification record waits.
---
<!-- COMMENTS:END -->

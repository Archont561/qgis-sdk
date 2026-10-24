---
id: TASK-31
title: Prepare and qualify 0.5.0 release
status: To Do
assignee: []
created_date: '2026-10-16 12:02'
updated_date: '2026-10-24 19:10'
labels: []
milestone: m-4
dependencies:
  - TASK-9
  - TASK-22
  - TASK-30
references:
  - doc-8
priority: high
type: chore
ordinal: 31000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Explicit release gate, not evidence of release or permission to publish. Verify milestone work and obtain explicit release authorization.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Required 0.5.0 work has verified outcomes and relevant test/artifact evidence; unresolved targets/spikes remain blockers.
- [ ] #2 Use valid SemVer and prereleases such as 0.5.0-alpha.1; update actual manifests only for released packages and document migration notes.
- [ ] #3 Validate compatibility, licenses, generated-file consistency and clean installation where applicable; keep protocol versions independent.
- [ ] #4 Record artifacts/checks and explicit publishing approval; no stable 1.0.0 promise, automatic publication or invented passing checks.
- [ ] #5 The bridge is qualified as a pair, not as a bystander: the record states which bridge version ran inside a real `QWebEngineView` against which `qgis-sdk` version, any defect the matrix finds lands as a recorded bridge source change with its own changelog entry, and no bridge version is published unless such a fix exists.
<!-- AC:END -->

## Comments

<!-- COMMENTS:BEGIN -->
author: qgis-sdk agent
created: 2026-10-24 19:10
---
AC #5 was added on 2026-10-24 to carry the bridge obligation [m-4](../../milestones/m-4%20-%200.5.0-%E2%80%94-qualified-experimental-reference-release.md) already states: this milestone qualifies the bridge instead of extending it, TASK-9's compatibility gate has to name the pair, TASK-22 is the first evidence the transport works in a real view, and a defect found here is a bridge source change that does not hide inside "qualification fixes". The earlier criteria said "update actual manifests only for released packages", which is true but silent about who qualifies the bridge and how a defect is published. No criterion had been checked.
---

created: 2026-10-21 21:56
---
blocked-by-actions (doc-8): AC4's CI artifacts, checks and explicit publishing approval cannot exist until runners return, and this minor inherits TASK-27's block. The outage changes nothing about the feature scope that has to land first, so build and verify that locally; only the qualification record waits.
---
<!-- COMMENTS:END -->

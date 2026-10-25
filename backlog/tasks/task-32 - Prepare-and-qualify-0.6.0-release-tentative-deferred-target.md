---
id: TASK-32
title: Prepare and qualify 0.6.0 release (tentative deferred target)
status: To Do
assignee: []
created_date: '2026-10-16 12:02'
updated_date: '2026-10-24 19:10'
labels: []
milestone: m-5
dependencies:
  - TASK-10
  - TASK-31
references:
  - doc-8
priority: low
type: chore
ordinal: 32000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Explicit release gate, not evidence of release or permission to publish. Verify milestone work and obtain explicit release authorization. Fresh scope/go-no-go approval is required; 0.6.0 is reserved, not a commitment to native shipping.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Required 0.6.0 work has verified outcomes and relevant test/artifact evidence; unresolved targets/spikes remain blockers.
- [ ] #2 Use valid SemVer and prereleases such as 0.6.0-alpha.1; update actual manifests only for released packages and document migration notes.
- [ ] #3 Validate compatibility, licenses, generated-file consistency and clean installation where applicable; keep protocol versions independent.
- [ ] #4 Record artifacts/checks and explicit publishing approval; no stable 1.0.0 promise, automatic publication or invented passing checks.
- [ ] #5 The expected zero bridge delta is confirmed rather than assumed: no file under `packages/qgis-sdk-typescript` changed, no npm version is consumed, and the plugin-description contract version still agrees across both languages.
<!-- AC:END -->

## Comments

<!-- COMMENTS:BEGIN -->
author: qgis-sdk agent
created: 2026-10-24 19:10
---
AC #5 was added on 2026-10-24 to carry the bridge obligation [m-5](../milestones/m-5%20-%200.6.0-%E2%80%94-deferred-native-compute-feasibility-%28tenta.md) already states: a native backend changes what runs behind Python, not what crosses `QWebChannel`, so this milestone expects no bridge release at all - and the milestone requires that expectation to be re-checked rather than repeated. Deferred or not, the gate has to be able to say "nothing crossed" with evidence. No criterion had been checked.
---

created: 2026-10-21 21:56
---
blocked-by-actions (doc-8): AC4's CI artifacts, checks and explicit publishing approval cannot exist until runners return, and this minor inherits TASK-27's block. The outage changes nothing about the feature scope that has to land first, so build and verify that locally; only the qualification record waits.
---
<!-- COMMENTS:END -->

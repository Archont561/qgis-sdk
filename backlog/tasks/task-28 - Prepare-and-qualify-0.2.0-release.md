---
id: TASK-28
title: Prepare and qualify 0.2.0 release
status: To Do
assignee: []
created_date: '2026-10-16 12:02'
updated_date: '2026-10-24 16:05'
labels: []
milestone: m-1
dependencies:
  - TASK-1
  - TASK-3
  - TASK-5
  - TASK-14
  - TASK-15
  - TASK-24
  - TASK-25
  - TASK-27
references:
  - doc-8
priority: high
type: chore
ordinal: 28000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Explicit release gate, not evidence of release or permission to publish. Verify milestone work and obtain explicit release authorization.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Required 0.2.0 work has verified outcomes and relevant test/artifact evidence; unresolved targets/spikes remain blockers.
- [ ] #2 Use valid SemVer and prereleases such as 0.2.0-alpha.1; stamp the one shared version into both released manifests (Python package and TypeScript bridge), advance the minor explicitly at this milestone close rather than inferring it, and document migration notes.
- [ ] #3 Validate compatibility, licenses, generated-file consistency and clean installation where applicable; keep protocol versions independent.
- [ ] #4 Record artifacts/checks and explicit publishing approval; no stable 1.0.0 promise, automatic publication or invented passing checks.
<!-- AC:END -->

## Comments

<!-- COMMENTS:BEGIN -->
created: 2026-10-21 21:56
---
blocked-by-actions (doc-8): AC4's CI artifacts, checks and explicit publishing approval cannot exist until runners return, and this minor inherits TASK-27's block. The outage changes nothing about the feature scope that has to land first, so build and verify that locally; only the qualification record waits.
---

author: qgis-sdk agent
created: 2026-10-24 16:05
---
AC #2 amended on 2026-10-24, before any of this task's criteria was checked: it said 'update actual manifests only for released packages', which encoded the old policy that the two packages are versioned independently. decision-24 replaced that policy, so the criterion now says the one shared version is stamped into both released manifests and the minor is advanced explicitly at this milestone close. Consequence worth planning for: release.py plan no longer proposes a minor bump for feature work - on this branch it proposes v0.1.2 - so the 0.2.0 release must pass --bump minor or --version-override 0.2.0 rather than accepting the derived answer. The invariant is enforced by release.py verify-versions (also wired into the build job of release.yml).
---
<!-- COMMENTS:END -->

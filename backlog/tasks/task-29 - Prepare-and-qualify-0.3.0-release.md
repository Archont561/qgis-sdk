---
id: TASK-29
title: Prepare and qualify 0.3.0 release
status: To Do
assignee: []
created_date: '2026-10-16 12:02'
updated_date: '2026-10-24 16:54'
labels: []
milestone: m-2
dependencies:
  - TASK-4
  - TASK-5
  - TASK-7
  - TASK-15
  - TASK-17
  - TASK-18
  - TASK-20
  - TASK-28
references:
  - doc-8
priority: high
type: chore
ordinal: 29000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Explicit release gate, not evidence of release or permission to publish. Verify milestone work and obtain explicit release authorization.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Required 0.3.0 work has verified outcomes and relevant test/artifact evidence; unresolved targets/spikes remain blockers.
- [ ] #2 Use valid SemVer and prereleases (0.3.0-alpha.1 for Python, 0.2.0-alpha.1 for the bridge); release each package under its own tag at its own explicitly advanced minor — `python-v0.3.0` and `ts-v0.2.0` — verify both scopes plus the shared contract version, and document migration notes per package.
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
created: 2026-10-24 16:25
---
AC #2 amended on 2026-10-24, before any criterion was checked: decision-25 split the versions. This gate now covers two releases made from the same milestone - python-v0.3.0 and ts-v0.2.0 - each with its own explicit minor and its own scope check, plus the shared plugin-description contract version. The two numbers are not expected to match.
---
<!-- COMMENTS:END -->

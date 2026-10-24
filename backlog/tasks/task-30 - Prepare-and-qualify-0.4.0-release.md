---
id: TASK-30
title: Prepare and qualify 0.4.0 release
status: To Do
assignee: []
created_date: '2026-10-16 12:02'
updated_date: '2026-10-24 16:30'
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
- [ ] #2 Use valid SemVer and prereleases such as 0.4.0-alpha.1; release Python at its own explicitly advanced minor and release the bridge only if it changed, at a patch of its own version; verify both scopes plus the shared contract version, and document migration notes.
- [ ] #3 Validate compatibility, licenses, generated-file consistency and clean installation where applicable; keep protocol versions independent.
- [ ] #4 Record artifacts/checks and explicit publishing approval; no stable 1.0.0 promise, automatic publication or invented passing checks.
- [ ] #5 The milestone's "no bridge source change" claim is tested rather than assumed: the release diff touches no file under `packages/qgis-sdk-bridge`, or every such change is recorded with its own changelog entry and a bridge patch released at its own version.
<!-- AC:END -->

## Comments

<!-- COMMENTS:BEGIN -->
author: qgis-sdk agent
created: 2026-10-24 19:10
---
AC #5 was added on 2026-10-24 to carry the bridge obligation [m-3](../../milestones/m-3%20-%200.4.0-%E2%80%94-developer-workflow-and-plugin-packaging.md) already states: 0.4.0 adds consumers of the published bridge, not surface, and the milestone says outright that this is a claim the release gate tests rather than assumes. No criterion had been checked, so nothing was invalidated. The bridge versions independently ([decision-25](../../decisions/decision-25%20-%20Version-each-package-independently-behind-a-shared-contract-version.md)), so a consumer-driven fix is a patch of the bridge's own number, never a renumbering to match Python.
---

created: 2026-10-21 21:56
---
blocked-by-actions (doc-8): AC4's CI artifacts, checks and explicit publishing approval cannot exist until runners return, and this minor inherits TASK-27's block. The outage changes nothing about the feature scope that has to land first, so build and verify that locally; only the qualification record waits.
---
<!-- COMMENTS:END -->

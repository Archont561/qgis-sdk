---
id: TASK-95
title: Prepare and qualify 0.11.0 release
status: To Do
assignee: []
created_date: '2026-10-26T10:11:00Z'
labels: []
milestone: m-10
dependencies:
  - TASK-90
  - TASK-91
  - TASK-92
  - TASK-93
  - TASK-94
type: chore
ordinal: 95000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Explicit release gate for the layer-kinds, connections, symbology and Processing-breadth release (m-10, decision-54), not evidence of release or permission to publish. Python 0.11.0 paired with a bridge minor carrying the regenerated host manifest; doc-22 complete is the exit.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Required work has verified outcomes and test/artifact evidence across the Python suite, tests/scripts, the opt-in harnesses the milestone touched and the example projects; doc-12/doc-13 migration notes cover every added or renamed name.
- [ ] #2 Use valid SemVer and prereleases such as -rc.1; update actual manifests only for released packages (runtime, tools, kit at one version; the tools runtime range moves with it) and keep protocol versions independent.
- [ ] #3 Validate compatibility, licenses, generated-file consistency and clean installation where applicable; qgis-sdk check on a project from the previous minor reports what changed rather than crashing.
- [ ] #4 Record artifacts/checks and explicit publishing approval; no stable 1.0.0 promise, automatic publication or invented passing checks.
- [ ] #5 The bridge pair is confirmed with evidence as for 0.10.0, and doc-22 shows every listed area complete or explicitly out of scope by decision.
<!-- AC:END -->

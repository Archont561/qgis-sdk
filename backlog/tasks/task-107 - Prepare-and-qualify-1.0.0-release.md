---
id: TASK-107
title: Prepare and qualify 1.0.0 release
status: To Do
assignee: []
created_date: '2026-10-26T11:13:00Z'
labels: []
milestone: m-11
dependencies:
  - TASK-95
  - TASK-97
  - TASK-98
  - TASK-99
  - TASK-100
  - TASK-101
  - TASK-103
  - TASK-104
  - TASK-105
  - TASK-106
type: chore
ordinal: 107000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Explicit release gate for 1.0.0 (m-11, decisions 56-63), not evidence of release or permission to publish. The first release under the stability policy: the inventory is the baseline, the support matrix has the Windows row qualified, doc-22 and doc-26 are complete, and the three packages release from one gate with the bridge and UI minors the services work produced.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Required work has verified outcomes and test/artifact evidence across the Python suite, tests/scripts, the opt-in harnesses the milestone touched and the example projects; doc-12/doc-13 migration notes cover every added or renamed name.
- [ ] #2 Use valid SemVer and prereleases such as -rc.1; update actual manifests only for released packages (runtime, tools, kit at one version; the tools runtime range moves with it) and keep protocol versions independent.
- [ ] #3 Validate compatibility, licenses, generated-file consistency and clean installation where applicable; qgis-sdk check on a project from the previous minor reports what changed rather than crashing.
- [ ] #4 Record artifacts/checks and explicit publishing approval; no automatic publication or invented passing checks.
- [ ] #5 decision-56 point 5 holds with evidence: verify-api runs against the reviewed inventory, every stable symbol is marked, doc-22 and doc-26 are complete, native.yml is green for the Windows and Linux rows, and the publishing approval names 1.0.0 for each package explicitly.
<!-- AC:END -->

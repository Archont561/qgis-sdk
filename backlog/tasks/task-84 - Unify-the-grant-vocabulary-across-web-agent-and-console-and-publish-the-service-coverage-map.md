---
id: TASK-84
title: >-
  Unify the grant vocabulary across web, agent and console, and publish the
  service coverage map
status: To Do
assignee: []
created_date: '2026-10-26T10:11:00Z'
labels: []
milestone: m-9
dependencies:
  - TASK-76
  - TASK-73
type: enhancement
ordinal: 84000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-54 points 2 and 5. Operation ids <service>.<operation> everywhere; [tool.qgis-sdk.console] grants (default all); one unknown-grant finding; destructive annotations shared by the agent consent list and the audit log; qgis-sdk check --grants prints the client x operation matrix; doc-22 service coverage map (area, service, operations, fake, native, host, grant, status) created and made the source of truth, with a tests/scripts check that every host operation appears in it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The three grant tables accept the same names, reject the same unknown ones with one finding, and check --grants prints the matrix (pure tests).
- [ ] #2 doc-22 exists, lists every current host operation, and tests/scripts fails when a host operation is missing from it.
- [ ] #3 doc-12/doc-13 describe the single vocabulary; the agent consent list and audit use the shared destructive annotation (devtools harness).
<!-- AC:END -->

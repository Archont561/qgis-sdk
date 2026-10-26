---
id: TASK-92
title: >-
  Add connections and authentication configuration: registered data-source
  connections, browsing, opening from a connection, auth configuration ids
status: To Do
assignee: []
created_date: '2026-10-26T10:11:00Z'
labels: []
milestone: m-10
dependencies:
  - TASK-87
type: enhancement
ordinal: 92000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-54 point 4. connections.list/describe/browse over the provider connection registry, open_layer(connection, item), test(connection); auth.configurations as ids and names only (never secrets), attach to a connection; fake, native, host operations, grants with destructive and credential annotations.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A GeoPackage and a PostGIS fixture connection list, browse and open with fake and native sharing the contract tests; no secret crosses any model (native tests; PostGIS row recorded or blocked by environment).
- [ ] #2 Host operations regenerated and typed; the agent consent list shows credential-touching operations distinctly.
- [ ] #3 doc-22 rows complete; doc-12/doc-13 document connections.
<!-- AC:END -->

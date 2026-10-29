---
id: TASK-105
title: >-
  Write doc-26 Authority and threat model, SECURITY.md, and qgis-sdk check
  --security with SEC001
status: To Do
assignee: []
created_date: '2026-10-26T11:13:00Z'
updated_date: '2026-10-28 16:24'
labels: []
milestone: m-11
dependencies:
  - TASK-84
type: docs
ordinal: 105000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-62. doc-26 (specification): principals, assets, trust boundaries, one table operation class x principal -> allowed / granted / consented / refused, the fixed rules (deny by default, static grants baked by build, per-user consent, destructive and credential annotations, no iface/eval/arbitrary Qt, dev tools absent from built plugins, token file 0600 loopback only); every grant name, check rule and refusal message cites a row; SECURITY.md with the reporting path; check --security printing the plugin's effective matrix; SEC001 for a grant exceeding what the plugin's code uses.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 doc-26 exists, every grant name and authority-related check rule in the codebase appears in its table, and a tests/scripts check fails when a new grant or rule is added without a row.
- [ ] #2 check --security prints the effective matrix for the example plugin and SEC001 fires on a fixture with an unused grant (pure tests).
- [ ] #3 SECURITY.md is at the root and linked from the README within decision-29's shape; decisions 23, 27, 48, 49, 51, 52, 54, 55 carry a status review pointing at doc-26.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Ecosystem research: TASK-132 evaluates a discoverable check rule catalog and other QGIS diagnostics; coordinate with this security scope without broadening it implicitly.
<!-- SECTION:NOTES:END -->

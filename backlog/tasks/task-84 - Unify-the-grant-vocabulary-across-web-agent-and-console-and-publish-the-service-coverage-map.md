---
id: TASK-84
title: >-
  Unify the grant vocabulary across web, agent and console, and publish the
  service coverage map
status: In Progress
assignee: []
created_date: '2026-10-26T10:11:00Z'
labels: []
milestone: m-9
dependencies:
  - TASK-73
type: enhancement
ordinal: 84000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-54 points 2 and 5. Operation ids <service>.<operation> everywhere; [tool.qgis-sdk.console] grants (default all); one unknown-grant finding; destructive annotations shared by the agent consent list and the audit log; qgis-sdk check --grants prints the client x operation matrix; doc-22 service coverage map (area, service, operations, fake, native, host, grant, status) created and made the source of truth, with a tests/scripts check that every host operation appears in it.
<!-- SECTION:DESCRIPTION:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-31 (sprint 1 of m-9, on `d751a18`): re-grounded by [decision-71](../decisions/decision-71%20-%20Span-the-grant-vocabulary-across-the-page-the-console-and-the-plugin-HTTP-allowlist-and-defer-the-destructive-annotation.md) before writing code, because the task named an agent grant table that 0.8.0 had removed (decision-49 superseded) and an audit log that was never built. The vocabulary now spans the page, the console and the HTTP allowlist as a *client*; the destructive annotation and its consent/audit consumers move to TASK-105.

What landed: `host_grant_names()` and `host_operation_ids()` in `qgis_sdk.bridge.host` as the one source both sections read; `[tool.qgis-sdk.console] grants` with `ConsoleConfig` (unset = every operation) and one shared `_grants()` reader, so `GRANT001` names the section it appeared in and lists the same remediation; `qgis_sdk_tools.grants` with the client x operation matrix and `check --grants` printing it; doc-22's '## Host operations' table (13 operations, each with its grant, area and the Protocol method it wraps) guarded by `tests/scripts/test_service_coverage.py` in both directions; doc-12's "Grants, the console and the HTTP allowlist" and doc-13's grant bullet.

Known gap, recorded rather than guessed: console grants are declared, validated and printed, but not enforced at runtime - a console session builds a `PluginContext` directly instead of a bridge view registered with `only=`, so narrowing it needs its own seam and its own task.
<!-- SECTION:NOTES:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The grant tables accept the same names, reject the same unknown ones with one finding, and `check --grants` prints the matrix (pure tests). The agent table this named was withdrawn with decision-49; the HTTP allowlist takes its place as a client and names actions (decision-71).
- [x] #2 doc-22 lists every current host operation in its '## Host operations' table, and `tests/scripts/test_service_coverage.py` fails when an operation is missing, stale, duplicated, or a grant name is absent.
- [ ] #3 doc-12/doc-13 describe the single vocabulary. **Half done:** both guides are written. The consent-list/audit half waits on TASK-105 (decision-71 point 3), because decision-49 was withdrawn and no audit log exists yet.
<!-- AC:END -->

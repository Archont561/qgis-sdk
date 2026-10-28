---
id: TASK-117
title: Check worker-job safety with source-only lint rules
status: To Do
assignee: []
created_date: '2026-10-28 14:47'
updated_date: '2026-10-28 16:24'
labels: []
milestone: m-8
dependencies:
  - TASK-115
  - TASK-116
type: enhancement
ordinal: 117000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Extend qgis-sdk check with job-specific source-only AST diagnostics for the 0.9.0 worker-first contract; coordinate with the named job declarations and restricted worker context in decision-65. This is early feedback, not proof of Python thread safety or a security sandbox.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Recognize @job and import aliases, inspect imports and direct API use inside jobs and module-level bindings referenced by jobs, and diagnose known GUI-thread-only Qt widgets, iface and live project access with actionable locations and guidance; tests cover aliases, shadowing and TYPE_CHECKING.
- [ ] #2 Report unresolvable dynamic imports or indirect safety-sensitive usage conservatively where feasible; do not promise transitive analysis, and document helper, dynamic, alias and object-flow limitations. Avoid blanket bans on all qgis.core imports or all module imports; test valid worker-safe code to limit false positives.
- [ ] #3 Exercise qgis-sdk check end-to-end on valid and unsafe named-job plugins with deterministic diagnostics and nonzero exit on errors; document configurable severity or strictness if offered, runtime guards, migration and the worker-safe patterns.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Ecosystem research: TASK-132 explores other QGIS and Qt diagnostics plus a rule catalog; worker-specific analysis remains in this task and must not claim thread-safety proof.
<!-- SECTION:NOTES:END -->

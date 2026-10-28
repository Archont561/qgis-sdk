---
id: TASK-125
title: Design validated owner-scoped actions between plugins
status: To Do
assignee: []
created_date: '2026-10-28 15:58'
labels: []
dependencies: []
priority: medium
type: spike
ordinal: 125000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The owner asked how one plugin can consume another plugin action. Today a QGIS Desktop caller can inspect qgis.utils.plugins but direct runtime handler calls bypass SDK validation and lifetime safeguards. TASK-73 and decision-48 plan a console PluginHandle; extension to cross-plugin calls is not yet specified or implemented.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Design discovery, identity, version and capability negotiation, action allowlisting and authorization, validation and result/error translation without relying on isinstance across independently vendored SDK copies.
- [ ] #2 Specify invocation ownership, GUI-thread dispatch, shutdown, unloading/reloading target plugins and stale handles; do not retain handlers across reload or use unvalidated runtime.actions directly.
- [ ] #3 Evaluate alignment with TASK-73 and decision-48, tests with two built vendored plugins and denied/missing/reloaded targets, and a migration path; select release only after approval.
<!-- AC:END -->

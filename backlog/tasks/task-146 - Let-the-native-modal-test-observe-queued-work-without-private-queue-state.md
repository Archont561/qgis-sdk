---
id: TASK-146
title: Let the native modal test observe queued work without private queue state
status: To Do
assignee: []
created_date: '2026-10-29 13:36'
updated_date: '2026-10-29 13:36'
labels:
  - python
  - testing
milestone: m-7
dependencies: []
priority: low
type: task
ordinal: 146000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
test_zz_plugin_rest_native.py reaches into server._queue._lock and server._queue._items to decide when the nested QDialog may close. The test is about listener re-entrancy, but it couples the native harness to a private queue attribute, so any refactor of GuiQueue breaks a test that is not about GuiQueue.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The nested-dialog test provokes the deferral through a supported signal instead of reading private queue state - for example a public pending-work query on the server, or closing the dialog on a timer while still asserting the dispatch order.
- [ ] #2 The test still fails when nested dispatch is allowed: reintroducing the two-guard mutation (drop _active in _drain and the schedule check in call) makes it fail with an out-of-order or overlapping dispatch.
- [ ] #3 Non-goals: do not weaken the ordering assertion and do not make GuiQueue public API.
<!-- AC:END -->

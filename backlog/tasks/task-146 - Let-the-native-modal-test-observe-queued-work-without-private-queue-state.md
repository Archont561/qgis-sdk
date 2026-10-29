---
id: TASK-146
title: Let the native modal test observe queued work without private queue state
status: Done
assignee: []
created_date: '2026-10-29 13:36'
updated_date: '2026-10-29 13:51'
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
- [x] #1 The nested-dialog test provokes the deferral through a supported signal instead of reading private queue state - for example a public pending-work query on the server, or closing the dialog on a timer while still asserting the dispatch order.
- [x] #2 The test still fails when nested dispatch is allowed: reintroducing the two-guard mutation (drop _active in _drain and the schedule check in call) makes it fail with an out-of-order or overlapping dispatch.
- [x] #3 Non-goals: do not weaken the ordering assertion and do not make GuiQueue public API.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Fixed: the server reports dispatch state publicly - PluginHttpServer.pending_requests and .busy, backed by read-only GuiQueue.pending/.busy. The native modal test now closes the dialog when server.pending_requests is non-empty, with no access to _lock or _items. New pure test test_pending_requests_and_busy_expose_queue_state pins the properties (idle 0/False, busy while a handler runs, one pending caller, back to 0/False). Mutation evidence: deleting the _drain 'if self._active: return' guard together with the _active term of the post guard in call() makes both the native modal test and test_a_nested_event_loop_defers_the_second_call_instead_of_reentering fail; with only the same-thread refusal removed the suite still passes, because ChannelTransport refuses nested receive independently - that is defence in depth, not a tautology.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
The native harness observes queued work through the server's public pending_requests property, and the dispatch-order assertion still fails when nested dispatch is allowed.
<!-- SECTION:FINAL_SUMMARY:END -->

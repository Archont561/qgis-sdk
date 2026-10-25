---
id: TASK-47
title: Release explicit-owner subscription hooks when a job finishes
status: To Do
assignee: []
created_date: '2026-10-25T00:21:00Z'
labels: []
milestone: m-2
dependencies:
  - TASK-15
priority: medium
type: bug
ordinal: 47000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by the 2026-10-25 TASK-15 audit. `JobHandle.on_*(callback, owner=scope)` with an owner other than the job's own registers `scope.on_close(subscription.dispose)` and never removes it: ResourceScope has no unregister, and `_Attempt.finish()` only disposes the subscription. Each closure keeps the JobSubscription -> _Attempt -> Job (and its result) alive for the owner scope's lifetime. Probe: 100 finished view jobs subscribed with owner=plugin_scope left plugin_scope._callbacks at 102 entries (2 before). In a long QGIS session with plugin-owned subscriptions on view jobs this grows without bound. Attempt scopes themselves are released correctly (plugin children stayed at 1).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 After a job settles and is delivered, no callable registered by that job's subscriptions remains in any ResourceScope's close list; the probe above ends with the same count it started with.
- [ ] #2 Disposal through the explicit owner still works while the job is active (closing the owner scope before settlement detaches the callback and delivers nothing), and explicit-owner closures are released on owner_disposed and abandoned paths too.
- [ ] #3 The fix stays inside qgis_sdk.jobs unless a minimal ResourceScope unregister is justified; if ResourceScope changes, tests/test_scope*.py cover it and doc-12's scope paragraph is updated.
- [ ] #4 A regression test counts retained close hooks across N finished jobs; the Hypothesis state machine gains the invariant that a settled, delivered attempt holds no owner hook.
<!-- AC:END -->

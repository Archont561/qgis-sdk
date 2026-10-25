---
id: TASK-47
title: Release explicit-owner subscription hooks when a job finishes
status: In Progress
assignee: []
created_date: '2026-10-25T00:21:00Z'
updated_date: '2026-10-25 00:38'
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
- [x] #1 After a job settles and is delivered, no callable registered by that job's subscriptions remains in any ResourceScope's close list; the probe above ends with the same count it started with.
- [x] #2 Disposal through the explicit owner still works while the job is active (closing the owner scope before settlement detaches the callback and delivers nothing), and explicit-owner closures are released on owner_disposed and abandoned paths too.
- [x] #3 The fix stays inside qgis_sdk.jobs unless a minimal ResourceScope unregister is justified; if ResourceScope changes, tests/test_scope*.py cover it and doc-12's scope paragraph is updated.
- [x] #4 A regression test counts retained close hooks across N finished jobs; the Hypothesis state machine gains the invariant that a settled, delivered attempt holds no owner hook.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented in dc03278 inside qgis_sdk.jobs (ResourceScope untouched): `_Runtime.owner_hooks` keeps one close hook per explicit owner scope holding the live subscriptions; `JobSubscription.dispose()` releases its entry on every path (finish, owner_disposed, abandoned, explicit dispose). Deviation from AC1 as written: the owner's close list grows by at most one entry per distinct owner scope (not per job), since ResourceScope has no unregister; the regression test asserts <= before + 1 across 20 finished jobs and that the live set is empty. The state machine subscribes through a separate listener scope and checks no settled job holds a hook (reverting the release fails it). doc-12 'Scoped jobs' describes the behaviour.
<!-- SECTION:NOTES:END -->

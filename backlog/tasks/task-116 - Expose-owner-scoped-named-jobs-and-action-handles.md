---
id: TASK-116
title: Expose owner-scoped named jobs and action handles
status: To Do
assignee: []
created_date: '2026-10-28 14:47'
updated_date: '2026-10-28 15:59'
labels: []
milestone: m-8
dependencies:
  - TASK-115
  - TASK-67
type: enhancement
ordinal: 116000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Provide the 0.9.0 plugin-declared named job registry and host-integrated scoped submission. The public shape is jobs = {"add": add} on the plugin and ctx.jobs.add.delay(**inputs); bind remains internal. Use an explicit startup-built registry, not module scans or a global current-plugin singleton. Enable native actions to submit jobs and return local JobHandle values. See decision-65.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The runtime validates explicit registry keys, decorated declarations and unique job IDs at startup; invalid, duplicate, reserved or unknown names are refused clearly. The registry performs a prebuilt lookup and does not import or scan arbitrary modules on submission.
- [ ] #2 A plugin action returns ctx.jobs.add.delay(...) immediately, without exposing bind; keyword inputs are validated and a local native surface receives a live handle with progress, success, failure and cancellation callbacks. No blocking GUI-thread get; RunsJobs cancellation and direct-handle behavior are documented and tested.
- [ ] #3 Propagate the invoking owner explicitly and safely per dispatch: a view-launched action submits view-owned work by default, toolbar/plugin calls are plugin-owned, and plugin lifetime from a view is an explicit opt-in. Prove request-scope behavior with fakes here and integrate the server host under TASK-80; concurrent views/requests cannot steal each other’s owner or callbacks.
- [ ] #4 View disposal detaches owned callbacks and requests cancellation, hiding alone does not dispose, plugin-owned work continues without retaining view objects, and unload/reload waits for worker acknowledgement or refuses replacement; cover race and two-view scenarios.
- [ ] #5 Provide 0.9 migration and native action/view examples and specify runtime validation and autocomplete/type-checking limitations. Preserve bridge handle serialization as ID/status; do not imply a web page receives live handle subscriptions or add an unplanned wire protocol.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Session follow-up: dynamic ctx.actions and named jobs do not automatically give IDE autocomplete. TASK-124 explores generated per-plugin action typing separately; retain runtime validation and owner-scoping regardless of typing.
<!-- SECTION:NOTES:END -->

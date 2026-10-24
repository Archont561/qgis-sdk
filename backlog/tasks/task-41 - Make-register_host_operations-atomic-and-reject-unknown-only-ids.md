---
id: TASK-41
title: Make register_host_operations atomic and reject unknown only ids
status: Done
assignee: []
created_date: '2026-10-24 20:14'
updated_date: '2026-10-24 20:26'
labels: []
milestone: m-2
dependencies: []
priority: medium
type: bug
ordinal: 41000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Audit finding (2026-10-24, post-merge audit of the host surface). packages/qgis-sdk/src/qgis_sdk/bridge/host.py:352-355 filters HOST_OPERATIONS by the only= argument with no check that every id in only exists, and registers inside the loop with no pre-check. Evidence: register_host_operations(dispatcher, services, only=["layers.get", "layers.lst"]) succeeds and silently exposes just layers.get; on a dispatcher that already has styles.apply, calling register_host_operations(dispatcher, services) raises duplicate operation id after the other five are already registered, leaving a dispatcher that answers calls the caller believes failed. Impact: only= is an authority-bearing argument, so a typo narrows the surface with no signal, and a failed wiring call leaves the dispatcher in a state nobody asked for - both are the opposite of fail-fast at a boundary. Intended behaviour: every id in only must be a declared host operation or the call raises naming it, and a call that cannot complete registers nothing. Non-goals: changing Dispatcher.register's own duplicate rule, and adding a grant filter (that belongs to TASK-20).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 register_host_operations(only=[...]) raises a QgisSdkBridgeError naming an id that is not in HOST_OPERATIONS.
- [x] #2 A registration that would conflict raises and leaves dispatcher.operations() exactly as it was before the call.
- [x] #3 packages/qgis-sdk/tests/test_bridge_host.py covers both cases, including the pre-registered-conflict path that today leaves five operations behind.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-24 (closed): `register_host_operations` now decides before it registers. `only` is resolved by `_selected`, which refuses any id HOST_OPERATIONS does not declare and names it alongside the ids that do exist; and the ops it is about to add are checked against `dispatcher.operations()` first, so a conflict raises `duplicate operation id X; nothing was registered` with the dispatcher exactly as it was. The pre-check is what makes the old failure impossible to observe from outside: the previous loop registered five operations and then raised on the sixth, leaving a dispatcher that answered calls the caller had been told failed. The dead `authorize_with` parameter on the test helper `_call` went with it - nothing passed it, and a helper signature that promises an authorizer the path never consults is a trap for the next test author. Verification: `test_an_only_id_that_is_not_declared_is_refused_and_registers_nothing` and `test_a_conflicting_registration_leaves_the_dispatcher_untouched` in `packages/qgis-sdk/tests/test_bridge_host.py`; 34 tests in that file, 724 across the package.
<!-- SECTION:NOTES:END -->

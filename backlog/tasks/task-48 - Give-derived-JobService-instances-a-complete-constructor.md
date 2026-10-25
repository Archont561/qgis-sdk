---
id: TASK-48
title: Give derived JobService instances a complete constructor
status: Done
assignee: []
created_date: '2026-10-25T00:22:00Z'
updated_date: '2026-10-25T11:25:00Z'
labels:
  - refactor
milestone: m-2
dependencies:
  - TASK-15
priority: low
type: enhancement
ordinal: 48000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by the 2026-10-25 TASK-15 audit (core-encapsulation, solid-lsp-contracts). Behaviour-preserving refactor, filed as enhancement + label refactor because this backlog's type list has no refactor type. JobService._derived builds a view-owned service with cls.__new__ and sets four attributes, so a derived instance lacks _attempts, _counters, _faults, _gui_thread, _network, _on_fault, _scheduler and _workers (probe: vars() diff). Every method must remember to go through self._root for those; a new method that reads self._x works on the plugin service and raises AttributeError on a view service, and the failure only shows at runtime. Move the root-only state into one explicit shared object (scheduler, attempts, counters, faults, workers, network, gui_thread, on_fault) that both the root and derived services hold, built once by the public constructor, with no object left half-initialised.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 No code path constructs a JobService without running a constructor that sets every attribute the class reads; vars(root) and vars(derived) have the same keys, or the root-only state lives in one shared object both hold.
- [x] #2 Public behaviour is unchanged: tests/test_jobs.py, test_jobs_properties.py and test_jobs_native.py pass without modification, and the public surface (__all__) is unchanged.
- [x] #3 No new abstraction beyond that one shared-state object; the refactor is one commit, lint and coverage gates stay green.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented in dc03278 together with TASK-44/46/47 (they share the same restructuring, so one commit rather than one per task): `_Runtime` dataclass holds scheduler, attempts, counters, faults, owner hooks, workers, network, gui_thread, on_fault and the ticking flag; root and derived services both set exactly `_scope`, `_parent`, `_runtime` through `_bind`. Test: vars(root) == vars(derived) keys. Public __all__ unchanged; existing test files pass with no change except the two tests that pinned the old result contract (TASK-46).

Closed 2026-10-25 at m-3 sprint start (doc-16): the implementation commits (dc03278, 9c74613) merged to main in PR #60 and every criterion was already checked; the status had not been moved.
<!-- SECTION:NOTES:END -->

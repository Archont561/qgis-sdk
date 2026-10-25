---
id: TASK-44
title: Make a re-entrant jobs.tick() a no-op instead of failing the running job
status: To Do
assignee: []
created_date: '2026-10-25T00:21:00Z'
updated_date: '2026-10-25T00:22:00Z'
labels: []
milestone: m-2
dependencies:
  - TASK-15
priority: high
type: bug
ordinal: 44000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by the 2026-10-25 TASK-15 audit. A nested `JobService.tick()` while a job is mid-step fails the running job and every queued job with a raw `ValueError('coroutine already executing')`. This is the QGIS case where a job (or a subscriber callback) opens a modal dialog: the nested Qt event loop fires the host timer that drives `tick()`. TASK-13 explicitly left refusing nested ticks to the TASK-15 host-boundary seam (task-13 notes, 2026-10-21); the jobs runtime did not add the guard. Decision (user, 2026-10-25): a re-entrant tick is a no-op returning 0 - the outer tick completes when the nested loop unwinds; no exception may escape a Qt timer slot. Probe: a sync `run` that calls `jobs.tick()` with a second job queued -> both `failed`, `ValueError`.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A `tick()` (and `quiesce()`) entered while another tick of the same root service is on the stack returns 0 immediately, steps no job and delivers nothing; the outer tick finishes normally.
- [ ] #2 Re-entry from a subscriber callback during delivery is covered as well as re-entry from author code mid-step; neither job fails, and the queued job still runs on the next real tick.
- [ ] #3 doc-12 'Scoped jobs' states that nested ticks are ignored; nothing else in the tick contract changes and the scheduler keeps its existing behaviour (the guard lives in JobService).
- [ ] #4 A unit test in tests/test_jobs.py and a rule in the tests/test_jobs_properties.py state machine (a callback that re-enters tick) pin the behaviour; a Gherkin scenario is added to the jobs feature if TASK-45 lands first.
<!-- AC:END -->

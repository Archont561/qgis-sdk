---
id: TASK-45
title: Add the scoped-jobs Gherkin feature and parametrise the declaration refusals
status: In Progress
assignee: []
created_date: '2026-10-25T00:21:00Z'
updated_date: '2026-10-25 00:38'
labels: []
milestone: m-2
dependencies:
  - TASK-15
priority: medium
type: chore
ordinal: 45000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by the 2026-10-25 TASK-15 audit. Every other core runtime piece ships three test layers - examples, a pytest-bdd feature under tests/features/ with a test_*_bdd.py, and a Hypothesis property file (scope_lifecycle, runtime_lifecycle, step_scheduling, contract_wire, pydantic_contract). The jobs runtime landed with examples (tests/test_jobs.py), a Hypothesis state machine (tests/test_jobs_properties.py) and the native file, but no feature: the decision-13/21 rules (request is not a state, callbacks on the tick, disposal beats delivery) have no scenario-level statement a reader can check against the decisions. Also tests/test_jobs.py uses no pytest.mark.parametrize; test_a_job_class_needs_a_typed_run_of_its_own bundles five declaration refusals in one test, so the first failing case hides the rest. Test-only change; no production behaviour changes.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 tests/features/scoped_jobs.feature exists with a scenario per decision rule at minimum: bind-then-delay runs no author code until a tick; cancellation stays a request until acknowledged; a late subscriber replays once; disposing the view detaches callbacks and requests cancellation while hiding does not; plugin-lifetime work outlives the view; get() is refused on the GUI thread. tests/test_jobs_bdd.py binds them with pytest-bdd through the public JobService/JobHandle API only.
- [x] #2 The five declaration refusals in test_a_job_class_needs_a_typed_run_of_its_own become one parametrised test with ids naming the refusal (no run, untyped inputs, no result, not decorated, duplicate decoration), and the workers/network require_* pair is parametrised the same way.
- [x] #3 The Hypothesis state machine stays; nothing is removed from tests/test_jobs.py beyond the folded cases, and the package coverage gate still passes.
- [x] #4 doc-12 'Scoped jobs' names the feature file next to the other two test routes.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented in 9c74613: tests/features/scoped_jobs.feature (10 scenarios) + tests/test_jobs_bdd.py over the public API with FakeWorkers; declaration refusals are one parametrised table (six named cases) and the workers/network refusals one parametrised test. Package coverage 97.06% via `bun run coverage`; doc-12 names the feature file.
<!-- SECTION:NOTES:END -->

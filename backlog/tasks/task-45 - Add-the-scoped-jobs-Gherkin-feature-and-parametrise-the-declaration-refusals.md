---
id: TASK-45
title: Add the scoped-jobs Gherkin feature and parametrise the declaration refusals
status: To Do
assignee: []
created_date: '2026-10-25T00:21:00Z'
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
- [ ] #1 tests/features/scoped_jobs.feature exists with a scenario per decision rule at minimum: bind-then-delay runs no author code until a tick; cancellation stays a request until acknowledged; a late subscriber replays once; disposing the view detaches callbacks and requests cancellation while hiding does not; plugin-lifetime work outlives the view; get() is refused on the GUI thread. tests/test_jobs_bdd.py binds them with pytest-bdd through the public JobService/JobHandle API only.
- [ ] #2 The five declaration refusals in test_a_job_class_needs_a_typed_run_of_its_own become one parametrised test with ids naming the refusal (no run, untyped inputs, no result, not decorated, duplicate decoration), and the workers/network require_* pair is parametrised the same way.
- [ ] #3 The Hypothesis state machine stays; nothing is removed from tests/test_jobs.py beyond the folded cases, and the package coverage gate still passes.
- [ ] #4 doc-12 'Scoped jobs' names the feature file next to the other two test routes.
<!-- AC:END -->

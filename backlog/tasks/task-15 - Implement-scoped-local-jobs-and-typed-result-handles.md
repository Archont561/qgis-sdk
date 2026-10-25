---
id: TASK-15
title: Implement scoped local jobs and typed result handles
status: Done
assignee: []
created_date: 2026-10-16 12:02
updated_date: '2026-10-25T00:22:00Z'
labels: []
milestone: m-2
dependencies:
  - TASK-13
  - TASK-24
references:
  - >-
    backlog/decisions/decision-13 -
    Use-runtime-bound-Celery-inspired-local-jobs.md
  - >-
    backlog/decisions/decision-21 -
    Bound-job-ownership-and-refuse-unsafe-runtime-replacement.md
priority: medium
type: feature
ordinal: 15000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Implement scoped local jobs and typed result handles. Implement only the documented slice; proposed mechanisms require evidence before finalizing. Focused tests are part of this task, not deferred to a later test milestone.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Provide runtime-bound submission, progress, result/error/cancellation and explicit lifetime semantics.
- [x] #2 View disposal detaches callbacks and requests cancellation; hiding does not dispose; plugin lifetime is explicit.
- [x] #3 Stateful tests cover races/stuck work and acknowledge cancellation; no automatic retries initially.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. qgis_sdk/jobs.py (QGIS-free): @job/describe_job (typed run, sync or async), JobService over the TASK-13 StepScheduler with bind(JobClass).delay(inputs), typed JobHandle (logical id, attempt, status, cancel request vs acknowledgement, typed result/error), disposable progress/success/failure/cancelled subscriptions with late-subscriber replay, owner-scoped detachment, GUI-thread get() refusal.
2. Lifetimes: view-owned by default (service.scoped(view_scope)), explicit plugin-lifetime via the parent service; disposing the owner detaches callbacks and requests cancellation without abandoning the plugin's scheduler; hiding is nothing; plugin unload abandons through the scheduler. JobContext gains optional workers/network; Workers seam with a FakeWorkers for tests.
3. Tests: examples for every rule, a Hypothesis state machine for interleaved submit/tick/cancel/report/dispose, stuck work and cancellation races; no retries anywhere.
4. Native: adapters/qgis/workers.py ThreadPoolWorkers over QThreadPool; test_jobs_native.py proves worker-thread work and GUI-thread callbacks; join CI native step.
5. Docs: doc-12 jobs section, decision-13/21 evidence notes, task notes.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented in `qgis_sdk.jobs` (QGIS-free) over the TASK-13 step scheduler: `@job` + `describe_job`, `JobService` (`bind(...).delay(inputs)`, `scoped(view_scope)`, `parent`, `tick`, `quiesce`, `resume`, `active`, `faults`), typed `JobHandle` (status, cancel, result/error, on_progress/on_success/on_failure/on_cancelled with one-shot replay, `get()` refused on the GUI thread), errors `QgisSdkJobRejectedError` / `QgisSdkJobNotSettledError` / `QgisSdkJobWaitRefusedError`, `Workers` protocol + `JobContext.workers/network` with `require_*`, `testing.FakeWorkers`, `adapters.qgis.ThreadPoolWorkers`. Tests: `test_jobs.py` (39 examples), `test_jobs_properties.py` (Hypothesis state machine; found the finished-handle-after-view-close replay hole, now closed), `test_jobs_native.py` (4, real QThreadPool + Qt event loop, added to CI offscreen step). Docs: doc-12 'Scoped jobs' section, decision-13/21 implementation notes.

Closed 2026-10-25: merged to main via PR #59 (`gh pr merge 59 --merge`) with Linux/macOS/Windows CI green. Final: `qgis_sdk.jobs` runtime, `ThreadPoolWorkers` adapter, example + Hypothesis + native test suites, doc-12 / decision-13 / decision-21 updated. Follow-ups from the 2026-10-25 audit: TASK-44 (re-entrant tick), TASK-45 (Gherkin feature + parametrised refusals), TASK-46 (result mirrors get), TASK-47 (owner hook release), TASK-48 (derived service constructor). Release work stays in TASK-29. (This closure was first recorded on the merged session branch only; re-applied here so main carries it.)
<!-- SECTION:NOTES:END -->

## Comments

<!-- COMMENTS:BEGIN -->
author: qgis-sdk agent
created: 2026-10-24 16:54
---
Moved from m-1 to m-2 on 2026-10-24 during the 0.2.0 re-scope, for the same reasons as TASK-5: nothing in m-1 depends on it, it is not part of the 'native runtime and Processing' surface 0.2.0 is named for, and its job transport still rests on decision-13, which is only proposed. TASK-29 gates 0.3.0 on it.
---

author: qgis-sdk agent
created: 2026-10-24 17:02
---
decision-13 is now accepted (2026-10-24): submission is ctx.jobs.bind(JobClass).delay(inputs) - the delay(JobClass, inputs) alternative is dropped - and late subscribers replay the current state as one synthetic transition, with disposal beating replay. decision-21 still sets the scope: view-owned by default, no automatic retries, cancellation is a request until acknowledged. Implement to that; do not redesign it here.
---
<!-- COMMENTS:END -->

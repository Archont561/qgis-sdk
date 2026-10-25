---
id: TASK-46
title: Make handle.result raise the job's own failure like get() does
status: Done
assignee: []
created_date: '2026-10-25T00:21:00Z'
updated_date: '2026-10-25T11:25:00Z'
labels: []
milestone: m-2
dependencies:
  - TASK-15
priority: medium
type: bug
ordinal: 46000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by the 2026-10-25 TASK-15 audit. `JobHandle.result` on a FAILED job raises `QgisSdkJobNotSettledError` with code `job_not_settled` and the message "Job 'p.boom#1' is still failed; it has no result yet", while `JobHandle.get()` on the same handle re-raises the job's own `RuntimeError`. A failed job has settled, so both the code and the message are wrong, and a caller catching `QgisSdkJobNotSettledError` around `result` cannot tell 'still running' from 'failed'. Decision (user, 2026-10-25): `result` mirrors `get()`.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 handle.result on a FAILED job raises the job's recorded exception (the same object handle.error returns); on a CANCELLED job it raises QgisSdkJobCancelledError; on QUEUED/RUNNING it raises QgisSdkJobNotSettledError as today.
- [x] #2 QgisSdkJobNotSettledError is only ever constructed for queued/running statuses; its message no longer says 'still <terminal state>'.
- [x] #3 Tests cover the three branches through the handle, and the Hypothesis state machine asserts result/get agree for every settled tracked job.
- [x] #4 doc-12 'Scoped jobs' documents the result contract in one sentence next to get().
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented in dc03278: `_Attempt.outcome()` is the single reader behind `result` and `get()`; NotSettled is only raised for queued/running. Examples cover failed (same object as `error`) and cancelled; the state machine asserts result and get agree and that the raised kind matches the status (reverting the change fails it). doc-12 documents the contract next to get().

Closed 2026-10-25 at m-3 sprint start (doc-16): the implementation commits (dc03278, 9c74613) merged to main in PR #60 and every criterion was already checked; the status had not been moved.
<!-- SECTION:NOTES:END -->

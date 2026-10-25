---
id: TASK-58
title: Redesign @job as a plain function with the JobContext injected
status: Done
assignee: []
created_date: '2026-10-25 22:08'
updated_date: '2026-10-25 23:26'
labels: []
milestone: m-5
dependencies: []
type: enhancement
ordinal: 58000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
User request on 2026-10-25: make the job API Celery-like, function-based, with the JobContext injected. decision-38 fixes the shape: @job decorates a plain function def name(ctx: JobContext, ...) -> Result whose keyword parameters are the typed inputs; submission stays ctx.jobs.bind(fn).delay(**inputs) with ctx.jobs.delay(fn, **inputs) as the one-call spelling; the decorator injects nothing; the 0.5 class form is removed (breaking, 0.6.0 of qgis-sdk-runtime) with a refusal that names the migration note. Amends decision-13.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 @job on a function with a JobContext first parameter and typed keyword inputs is described by describe_job/describe without being called; a class, a function without the context, an unannotated parameter, a missing result or a generator is refused with QgisSdkDeclarationError naming the problem.
- [x] #2 bind(fn).delay(**inputs) and jobs.delay(fn, **inputs) check the keywords against the signature before queueing (missing, unexpected, wrong shape -> QgisSdkJobRejectedError listing every problem; positional -> TypeError) and the runtime injects a fresh JobContext per attempt; a wrong-typed result fails the job.
- [x] #3 Every jobs suite (examples, BDD, properties, native, quiesce, describe, declaration defaults) and the devtools exercise use the function form; the Python suite, tests/scripts and the QGIS_SDK_DEVTOOLS harness pass.
- [x] #4 decision-38 recorded, decision-13 carries the amended-by note, doc-12 Scoped jobs rewritten with a 0.6.0 migration note and the class-to-function side-by-side.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Delivered on PR #86 (commit 1ba9add): @job on plain functions with the JobContext injected, kwargs delay checked against the signature, class form removed with a migration refusal; decision-38 + decision-13 amended-by note, doc-12 Scoped jobs rewrite and 0.6.0 migration notes. Validation: lint/format clean, Python suite 1465 passed / 42 skipped, tests/scripts 226, QGIS_SDK_DEVTOOLS harness 9; CI run 40238875870 green (checks, cross-platform windows/macos). Follow-up agreed with the user: hide require_*() behind raising properties on all contexts (option A) in a fresh branch after this merge.
<!-- SECTION:NOTES:END -->

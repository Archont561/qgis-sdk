---
id: decision-38
title: Declare jobs as plain functions with the JobContext injected
date: '2026-10-25 22:30'
status: accepted
---
> **0.9.0 planning:** The submission and context described here are amended for the planned 0.9.0 worker-first named registry by [decision-65](decision-65%20-%20Run-registered-jobs-on-workers-with-owner-scoped-named-submission.md). The text below records the earlier decision and implementation.

## Context

[decision-13](decision-13%20-%20Use-runtime-bound-Celery-inspired-local-jobs.md)
borrowed Celery's *submission* ergonomics - `bind(...).delay(...)`, typed
handles, explicit ownership - but kept a class as the authoring unit: `@job` on
a class with `__init__(self, ctx)` and a typed `run(self, inputs)`, submitted
with one inputs object. That shape was carried over from `@algorithm`, where a
class is natural because Processing wraps it in a `QgsProcessingAlgorithm`.
For a job nothing wraps the class: the runtime constructed it only to call
`run` once and throw it away, every job needed a dataclass just to carry two
integers, and authors asked why a Celery-like API did not decorate a function
the way Celery does.

## Decision

A job is a **plain function** whose first parameter is the `JobContext` the
runtime injects, whose remaining parameters are typed keyword inputs - the same
subset of annotations `@action` accepts, defaults allowed - and whose return
annotation is the result:

```python
@job(id="demo.sum", title="Sum two numbers")
async def add(ctx: JobContext, a: int, b: int = 0) -> SumResult: ...

handle = ctx.jobs.bind(add).delay(a=1, b=2)
```

- **The decorator injects nothing** (decision-6/decision-10 spirit): `@job`
  attaches metadata and returns the same function, so a unit test calls it
  with a fake context. The runtime passes the context when the attempt runs.
- **Inputs are keywords.** `delay(**inputs)` is checked against the signature
  before anything is queued - missing, unexpected and wrong-shape keywords are
  refused with `QgisSdkJobRejectedError` naming every problem - and positional
  arguments are a `TypeError`. A dataclass remains a fine parameter type when
  the inputs are genuinely one object.
- **Ownership stays explicit** (decision-21): `ctx.jobs.bind(fn).delay(...)`
  is the submission form and `ctx.jobs.delay(fn, ...)` its one-call spelling.
  There is no ambient `fn.delay()` - that would be the global current-app
  registry decision-13 forbids.
- **The class form is removed**, not deprecated. Pre-1.0 the surface is
  experimental; carrying both shapes would double every test and guide for a
  form no one preferred. A class handed to `@job` or `bind` is refused with a
  message naming the function form and the 0.6.0 migration note.
- `describe_job(fn)` reads the signature without calling it; `JobDescription`
  carries the parameter names, which are required, the inputs object schema,
  the result type and schema, and `asynchronous`. `describe()` accepts a
  `@job` function alongside `@plugin`/`@algorithm` classes.
- Ids derive from the function name with the same module+qualname suffix a
  class gets (decision-30), so two modules' `count_features` jobs stay apart.

## Consequences

- `qgis-sdk-runtime` 0.6.0 is a breaking release for jobs; the migration note
  in doc-12 shows the 0.5 class next to the 0.6 function. Algorithms and
  plugins are untouched: `@algorithm` keeps its class because Processing
  needs one.
- `JobContext` is unchanged in shape; only how it arrives changed (argument,
  not constructor).
- `tests/test_jobs_functions.py` pins the function form; the existing jobs
  suites were converted rather than duplicated.
- Amends decision-13's authoring shape; its submission, delivery and ownership
  rules stand as written.

---
id: decision-13
title: Use runtime bound Celery inspired local jobs
date: '2026-10-16 08:05'
status: accepted
---
## Context

Long-running downloads/imports/computation need typed results, progress, retries and ownership. Celery provides familiar submission ergonomics, but a QGIS plugin is not automatically a distributed worker.

## Decision

Proposed: one decorated plain class per job, typed `run(inputs) -> Result`, fresh constructor-injected JobContext per execution. Bind declarations through the owner's job service; illustrative APIs are `ctx.jobs.bind(JobClass).delay(inputs)` or `ctx.jobs.delay(JobClass, inputs)`. Avoid a global current-app registry or implicit class-level submission. Return typed handles with identity/state, cancellation and disposable progress/success/failure/cancelled subscriptions. Define delivery for late subscribers. GUI callbacks execute on the GUI thread; blocking get on that thread is not supported.

Separate GUI-thread preparation, worker-safe work and GUI-thread application. JobContext exposes only services supported by the chosen execution backend, not arbitrary live layers/widgets/iface. Initial execution is local; QgsTask and a future Qt-compatible coroutine scheduler are distinct adapters, not interchangeable promises. An algorithm runs through its Processing adapter, not by blindly placing run() on a generic thread.

States include queued/running/succeeded/failed/cancelled; cancellation is a request until acknowledged, with explicit cleanup/partial-output semantics. View/plugin lifetime policies define whether work cancels or only subscriptions detach. Retry only explicitly classified transient errors, bounded with backoff; cancellation is not retried. Keep a logical job ID and per-attempt identity, fresh attempt resources, and explicit idempotency/partial-side-effect handling. A timeout after a remote write does not prove it failed.

## Consequences

- Pure tests use controlled scheduling and scripted services; stateful tests cover retries/cancellation/disposal/late results.
- Share cancellation/progress/resource primitives with algorithms, not their public contexts or lifecycle identity.
- Groups/chains, persistent schedules and brokers are future capabilities. Remote jobs require serializable inputs/results and independently constructed worker services; not all local jobs qualify.

## Confirmed second-interview refinement (2026-10-16)

The second interview narrows initial scope: [decision-21](decision-21%20-%20Bound-job-ownership-and-refuse-unsafe-runtime-replacement.md) accepts view-owned jobs by default, immediate callback detachment on disposal, explicit plugin-lifetime work and no automatic retries initially. Earlier retry/backoff discussion is future design, not an initial implementation requirement.

## Status review (2026-10-24)

**Promoted to `accepted`.** The two things that kept it a proposal were the
undecided submission form and the undefined late-subscriber rule. Both are now
decided; the execution model itself was already pinned by
[decision-21](decision-21%20-%20Bound-job-ownership-and-refuse-unsafe-runtime-replacement.md).

- **Submission is bound, not looked up.** Of the illustrative pair, the surviving
  form is `ctx.jobs.bind(JobClass).delay(inputs)`;
  `ctx.jobs.delay(JobClass, inputs)` is dropped. Rationale: ownership is the
  thing every job needs and the thing a caller must not be able to forget, so it
  is captured once by `bind` from the owning scope instead of being inferred per
  call from ambient state - which is precisely the global current-app registry
  this decision forbids. `bind` is also the single place a future policy (for
  example a group or a bounded concurrency budget) attaches.
- **Late subscribers replay state.** Subscribing after submission delivers the
  current state immediately as one synthetic transition, then subsequent ones;
  for a terminal state the replay is the terminal transition and the subscription
  completes. Detaching on disposal wins over replay: a disposed owner gets no
  callback at all, including a replay
  ([decision-21](decision-21%20-%20Bound-job-ownership-and-refuse-unsafe-runtime-replacement.md)).
- **Handles are typed.** `bind(...).delay(inputs)` returns a handle carrying the
  logical id, the state, `cancel()`, the typed result/failure, and the
  subscriptions above; `get()` on the GUI thread is refused, not emulated with a
  nested event loop.
- **Scope stays as decision-21 narrowed it:** no automatic retries, view-owned by
  default, explicit plugin-lifetime work, cancellation is a request until
  acknowledged. Groups, chains, schedules and brokers remain future capabilities.

What this does **not** claim: no job runtime exists yet. TASK-15 (now m-2)
implements this decision; its criteria carry the execution evidence.

## Status review follow-up (2026-10-24)

Promoted after the 0.2.0 re-scope moved TASK-15 to m-2. The design question and
the delivery question were separated on purpose: this record answers *what the
job API is*, while TASK-15 answers *whether it works*. Keeping the decision
`proposed` until the task closed would have meant m-2 starting against an
unsettled API - the exact failure the re-scope was meant to stop repeating.

## Implementation note (2026-10-25)

TASK-15 implemented this record as `qgis_sdk.jobs` over the TASK-13 step
scheduler, without redesign:

- `@job(id=, title=)` on a class with a typed `async run(inputs) -> Result`;
  `describe_job` reads it without constructing it, reusing the declarations
  schema generator.
- `ctx.jobs.bind(JobClass).delay(inputs)` is the only submission form; the
  handle carries `id`, `attempt`, `status`, `cancel()`, typed `result` /
  `error`, and `on_progress` / `on_success` / `on_failure` / `on_cancelled`.
- Late subscribers replay the current state once, synchronously; a terminal
  replay completes the subscription; a disposed owner gets nothing, including
  a replay - a handle whose view closed after the job finished refuses new
  subscriptions outright (a case the Hypothesis state machine found).
- `get()` on the GUI thread raises `QgisSdkJobWaitRefusedError`; no nested
  event loop.
- Delivery is on `JobService.tick()`, which the host drives from its event
  loop; `adapters.qgis.ThreadPoolWorkers` is the first `Workers`, and
  `tests/test_jobs_native.py` shows every callback on the GUI thread over a
  real `QThreadPool`.

## Amended by decision-38 (2026-10-25)

The authoring shape above - a class with `__init__(self, ctx)` and a typed
`run(self, inputs)` - was replaced in the 0.6.0 line by
[decision-38](decision-38%20-%20Declare-jobs-as-plain-functions-with-the-JobContext-injected.md):
`@job` decorates a plain function `def name(ctx: JobContext, ...) -> Result`
whose keyword parameters are the inputs, submitted as
`ctx.jobs.bind(name).delay(**inputs)`. Everything else here - bound
submission, typed handles, late-subscriber replay, no nested event loop,
view-owned by default - is unchanged.

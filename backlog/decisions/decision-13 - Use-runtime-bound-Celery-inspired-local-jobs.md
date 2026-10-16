---
id: decision-13
title: Use runtime bound Celery inspired local jobs
date: '2026-10-16 08:05'
status: proposed
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

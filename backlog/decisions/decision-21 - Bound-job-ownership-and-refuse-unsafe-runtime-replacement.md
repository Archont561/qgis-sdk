---
id: decision-21
title: Bound job ownership and refuse unsafe runtime replacement
date: '2026-10-16 09:05'
status: accepted
---
## Context

Jobs outlive individual callbacks, cancellation is cooperative, and deleting old runtime resources while code still runs is unsafe. The initial reference slice does not need automatic retry orchestration.

## Decision

Jobs submitted from a view are view-owned by default. Disposing the view requests cancellation and immediately detaches its UI callbacks; hiding a dock is not disposal. Plugin-lifetime work is explicit and must not retain disposed view objects or callbacks. The host delivers completion on the GUI thread and prevents late callbacks into disposed owners. Exact late-subscriber behavior remains to be specified.

The initial job implementation includes submission, progress, results/errors, cancellation and ownership, but no automatic retries. Resubmission is explicit. A later retry policy requires classified failures, bounded attempts/backoff and idempotency/partial-side-effect semantics; an interrupted remote write must not be silently duplicated.

A cancellation request does not imply cancelled terminal state or safe teardown. During development reload, quiesce new calls and wait for acknowledgement/safe completion within a bounded policy. If work does not stop safely, refuse in-process replacement, identify the blocker and require explicit restart. Never kill a worker thread or delete native resources beneath it. Generation guards supplement, not replace, cleanup. Do not silently discard unsaved project state while restarting.

## Consequences

- Update the earlier Celery-inspired proposal (ADR-13): retries remain future design, not initial scope.
- Stateful tests cover disposal vs hiding, cancellation races, stuck work, plugin-owned jobs, old-generation callbacks and refused reload.
- Exact timeout, concurrency limits, scheduler and restart interaction require testing; this decision sets failure behavior, not arbitrary numeric values.

## Implementation note (2026-10-25)

TASK-15 built the job half of this record in `qgis_sdk.jobs`:

- View ownership is `plugin_jobs.scoped(view_scope)`; closing the view disposes
  its subscriptions before anything else runs, then requests cancellation of
  its jobs. Hiding is not disposal (nothing is wired to visibility).
  Plugin-lifetime work is explicit through `ctx.jobs.parent`.
- Cancellation is a request until acknowledged: `cancel_requested` is set at
  once, `status` moves to `cancelled` only when the job sees
  `QgisSdkJobCancelledError` at a suspension point (or before its first step).
  Work that finishes anyway is reported as `succeeded`. `quiesce()` names
  stuck work as a blocker and refuses; no thread is interrupted, and the
  thread-pool adapter only skips callables that have not started yet.
- No retries: `attempt` is always `1`, resubmission is a new `delay`.
- The late-subscriber rule this record left open is now the decision-13
  replay rule, with disposal beating replay.
- Stateful coverage: `tests/test_jobs_properties.py` drives submit / tick /
  cancel / worker reports / close view / close plugin and checks monotonic
  states, a single truthful terminal event, nothing after owner close, and a
  closed plugin leaving nothing active.
- TASK-21 (2026-10-25) wires the refusal to the host: a root `JobService`
  registers `quiesce`/`resume` on its scope through
  `ResourceScope.on_quiesce`, `PluginRuntime.quiesce()` combines children
  first and names every blocker by handle id, and `qgis-sdk dev` waits the
  bound (2 s), then refuses the reload, resumes the revision and asks for
  an explicit restart. The harness proves it with a worker thread blocked
  on an event: refused and named while the thread lives, reloaded once the
  event is released.

---
id: decision-65
title: Run registered jobs on workers with owner-scoped named submission
date: '2026-10-28 14:47'
status: accepted
---
## Context

As of 0.8.0 planning, `@job` marks a plain function, `JobService.delay(fn, ...)`
submits it, and the driving thread executes the job body; authors must explicitly
`await ctx.workers.offload(...)` for worker work. Neither `PluginContext` nor
`UiContext` automatically supplies `jobs` today. Decision-53 planned to keep
that step model under `QgsTaskManager`. The owner now wants the **whole job**
on a worker, a Celery-inspired named `.delay()` without public binding, useful
job lint, and action consumption. These are planned 0.9.0 changes, not existing
behavior or evidence that any release shipped.

## Decision

1. **Worker-first.** A synchronous `@job` remains a plain metadata-decorated
   function with typed keyword inputs and an injected restricted worker context.
   Its entire body runs on a worker; the host/driving thread submits, validates,
   and delivers outcomes. Native QGIS schedules the job as a `QgsTask` under
   `QgsTaskManager` with title, progress and cancellation, without a second pool
   or wrapping a Processing algorithm twice. If a host lacks a worker backend,
   reject submission; never silently run on the driving thread. GUI preparation
   happens before submission; GUI updates happen on delivery.
2. **Explicit named registry.** A plugin declares `jobs = {"add": add}` and an
   action submits `self.ctx.jobs.add.delay(left=1, right=2)`. At startup validate
   keys, duplicate IDs, reserved names and declarations, then look up the name
   in the prebuilt plugin registry. There is no per-call module scanning, global
   current-plugin registry or public binding requirement. Unknown names and bad
   arguments fail clearly before scheduling. Registration key and job ID are
   distinct; use explicit keys to resolve function-name collisions. Bound
   submission and policies remain internal and owner-scoped. Existing legacy
   submission's compatibility/removal must be decided and documented as part of
   the 0.9 migration, not silently assumed.
3. **Ownership follows the invocation, not a mutable singleton.** Actions
   invoked by a view default to that view's scope; toolbar and plugin-level
   invocations default to plugin scope; server calls default to request scope.
   Plugin-lifetime work from a shorter-lived owner is an explicit opt-in.
   Capture the scope per invocation so concurrent views/requests cannot leak
   authority. View disposal detaches its callbacks and requests cancellation;
   hiding a dock is not disposal. Plugin-owned work must not retain view objects.
4. **Safe handoff.** The worker context provides only worker-appropriate
   capabilities such as thread-safe progress and cooperative cancellation; no
   live widgets, `iface` or driving-thread project service. Completion, progress,
   failure and cancellation callbacks, including late-subscriber replay, are
   delivered on the driving thread (GUI on Desktop); owner disposal beats queued
   delivery. This deliberately changes decision-13's synchronous late replay.
   Cancellation is only a request; quiesce waits for worker acknowledgement or
   refuses replacement, never kills a thread or frees resources beneath it.
5. **Lint is early feedback, not a safety proof.** Extend `qgis-sdk check` with
   alias-aware, source-only job checks for known unsafe direct use, including
   module-level imports referenced from a job. Do not ban all `qgis.core` or all
   imports. Dynamic calls, helpers and passed objects can defeat static analysis;
   restricted capabilities, runtime guards and tests remain necessary.
6. **Actions and the bridge.** Native action calls return a local `JobHandle`
   immediately; callbacks observe its result without blocking the GUI. Existing
   bridge serialization is ID/status, not a live Python handle. Remote job
   observation or wire changes require separate design and release decisions.

## Consequences

- 0.9.0 is a breaking Python minor; `TASK-115` decides how existing async jobs
  migrate (explicitly supported under the worker-first contract or refused with
  actionable guidance), and documents the changed context, submission and replay.
  Do not silently preserve driving-thread job execution under the new API.
- `TASK-116` implements named owner-scoped submission and actions, `TASK-117`
  implements lint, and `TASK-82` implements the native task-manager backend.
  `TASK-83` gates 0.9.0 on all of them and on verified migration evidence.
- Amends decision-38's submission form and context, decision-13's binding and
  synchronous replay, and decision-53's offloaded-step execution model. Their
  historical records remain accurate for their original releases. Decision-21's
  ownership, cancellation and reload safety principles remain in force.
- Dynamic Python attributes do not automatically provide static autocomplete;
  generated types or another typed solution may be designed later. The 0.9
  migration must state what IDE/type-checker support actually exists.

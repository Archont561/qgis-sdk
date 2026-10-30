---
id: decision-53
title: Run offloaded job steps as QgsTasks under QgsTaskManager and keep the step scheduler on the driving thread
date: '2026-10-26'
status: accepted
---
> **0.9.0 planning:** The step-offload execution model below is amended for planned 0.9.0 whole-job worker execution by [decision-65](decision-65%20-%20Run-registered-jobs-on-workers-with-owner-scoped-named-submission.md). The text below records the earlier decision and implementation.

## Context

The owner wants jobs scheduled through QGIS's task manager. Today a `@job`
is driven by the `StepScheduler` on the thread that owns the runtime (the GUI
thread on Desktop) and its `offload()` steps run on `ThreadPoolWorkers`
(`QThreadPool`), reporting back through a `Handoff` that resumes the job on
the driving thread (decisions 13, 21). decision-13 already said that
"QgsTask and a future Qt-compatible coroutine scheduler are distinct
adapters, not interchangeable promises". `QgsTaskManager` exists on every
host (`QgsApplication.taskManager()`), shows tasks in the Desktop task bar,
integrates cancellation, supports dependencies and sub-tasks, and runs
`QgsTask.run()` off the GUI thread with `finished()` back on it - the same
two-thread shape the scheduler already assumes.

## Decision

1. **`QgsTaskManager` becomes the native `Workers` adapter.** Each
   `offload(fn)` runs as a `QgsTask` (a small subclass, not
   `fromFunction`, so cancellation and progress are first-class) added to
   `QgsApplication.taskManager()`; completion reports through the existing
   `Handoff`, so the step scheduler, ownership rules and `JobContext` are
   unchanged and author code still resumes on the driving thread.
   `ThreadPoolWorkers` is retired from the native composition; the pure
   fakes stay for QGIS-free tests.
2. **A job is visible as one task.** The job itself registers a parent
   `QgsTask` whose description is the job's title, whose progress mirrors
   `ctx.progress`, and whose cancel button requests the job's cancellation
   through the same `CancellationToken`; offloaded steps are its sub-tasks.
   On Desktop this is the task bar entry; on server and app hosts it is the
   same object without a widget.
3. **Dependencies and limits.** `ctx.jobs.after(handle)` declares a
   dependency the task manager enforces; concurrency comes from the task
   manager's pool, not from a second pool in the SDK. Nothing here changes
   decision-21's rules: cancellation is cooperative, a running callable is
   not interrupted, a view-owned job is cancelled when its view is disposed,
   and reload still quiesces and waits.
4. **Processing stays Processing.** An algorithm runs through its Processing
   adapter (already a `QgsTask` inside Processing); the SDK does not wrap it
   a second time.
5. **No GUI-thread step ever runs inside `QgsTask.run()`.** A job step that
   touches a layer, a widget or `iface` runs on the driving thread as today;
   only `offload()` callables run on the task. The pure tests keep the
   invariant through the scheduler's thread-affinity checks.

## Consequences

- Users see SDK jobs where they see every other QGIS task, and cancel them
  there; authors change nothing.
- The native `Workers` tests move to the task manager (opt-in `qgis`
  harness); the stateful scheduler properties are unchanged.
- decision-13 and decision-21 get status reviews naming this adapter;
  neither is superseded.
- Scheduled as TASK-82 in m-8 (0.9.0).

## Status review (2026-10-30)

Still accepted in its native-adapter choice and superseded in its execution
model, which decision-65 replaced before either shipped.

- The adapter is now **one job body per `QgsTask`**, not one task per offloaded
  step: `qgis_sdk.adapters.qgis.QgsTaskWorkers` creates the task with the
  job's title (`WorkItem.title`), mirrors `ctx.progress` into the task bar
  through `ObservableProgress.observe`, and makes the task bar's cancel button
  call the job's own cooperative request. `native_plugin_context` composes it,
  so a plugin's `ctx.workers` is the task manager.
- There are **no sub-tasks and no parent task**: with the whole body on one
  worker there is nothing to nest. A Processing algorithm keeps being the
  `QgsTask` Processing already starts; the SDK never wraps one twice (AC 3).
- **Dependencies are enforced before the task exists.** `ctx.jobs.after(handle)`
  holds the dependent body until its prerequisite succeeded, so the task
  manager never receives work it must not start - the ordering holds for every
  backend, fakes included, instead of only for the native one. This replaces
  "the task manager enforces" in the text above; the observable rule (a
  dependent job runs only after its prerequisite finished, and fails without
  running if the prerequisite did not succeed) is unchanged.
- `ThreadPoolWorkers` stays available as a plain-pool adapter for hosts without
  a task manager and for the thread evidence in `tests/test_jobs_native.py`,
  but it is no longer part of the native composition.
- decision-13 and decision-21 are unaffected: cancellation is still a request,
  a running body is never interrupted, and disposal still beats delivery.

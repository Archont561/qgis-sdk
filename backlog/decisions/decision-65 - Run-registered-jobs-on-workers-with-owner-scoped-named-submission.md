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

## Implementation note (2026-10-30)

TASK-115 built the worker-first half in `qgis_sdk.jobs` and TASK-82 the native
backend; the named registry is still TASK-116.

- A job body is a plain `def name(ctx: WorkerContext, ...) -> Result`. The whole
  body runs on a worker through `Workers.offload`; the driving thread submits,
  validates inputs and results, and delivers. A host without a worker backend
  refuses submission with `QgisSdkJobRejectedError` instead of running the body
  itself. `async def` and `ctx: JobContext` are refused with migration text, so
  nothing keeps the 0.8 execution semantics.
- `WorkerContext` carries `progress` and `cancellation` and refuses every other
  capability by name (`algorithms`, `files`, `iface`, `layers`, `network`,
  `notifications`, `project`, `scope`, `ui`, `view`, `workers`) with the reason
  a worker cannot have it. It is a guard, not a sandbox: `qgis-sdk check`
  (TASK-117) names the imports it can see.
- Native composition uses `qgis_sdk.adapters.qgis.QgsTaskWorkers`: one job is
  one `QgsTask` under `QgsApplication.taskManager()` with the job's title, its
  progress mirrored into the task bar, and a cancel button that files the
  same cooperative request. `ThreadPoolWorkers` remains for hosts without a
  task manager and is no longer composed natively.
- `ctx.jobs.after(handle)` orders a job behind work already submitted; the
  ordering is enforced before the dependent body reaches a worker, and a
  prerequisite that fails or is cancelled fails the dependent with
  `QgisSdkJobPrerequisiteError` without running its body. This is how
  decision-53's "the task manager enforces" is satisfied without sub-tasks.
- Cancellation is unchanged in principle and sharper in one detail: a request
  that arrives before the worker reports settles the attempt at that report, so
  a body that ignores the request ends `cancelled` rather than publishing a
  result nobody waits for. A task the manager never started reports a
  cancellation instead of leaving the job as a replacement blocker.

## Implementation note: the named registry and action handles (2026-10-30)

TASK-116 added the submission half of §2 and §3.

- `jobs` on a plugin is a mapping (`jobs = {"add": add}`) or a sequence of
  `@job` functions (`jobs = (add, count_features)`). A sequence derives each
  name from the function's own name with `derive_id`, *not* from the job id: a
  bare `@job` id carries a module/qualname suffix, so keying off it would make
  `ctx.jobs.count_features_3f2a91` the only way to reach a job. The mapping form
  stays because it is how two functions with one Python name are told apart and
  how a public name is renamed; a sequence that derives one name twice is
  refused with that instruction. Mixing the two in one value is not a third
  form - the value is either a mapping or a sequence.
- `JobRegistry` validates at runtime construction: every entry is a `@job`
  function, keys are plain identifiers, and names or ids that collide are
  refused by name. Names that would shadow the surface itself (`active`,
  `after`, `delay`, `bind`, `describe`, `faults`, `names`, `plugin`,
  `registry`, `scope`, `scoped`, `watch`, `tick`, `quiesce`, `resume`,
  `parent`, `jobs`) are reserved, and a test keeps `RESERVED_JOB_NAMES` in step
  with the public attributes of `Jobs` and `JobService`. Lookup is a
  dictionary read: descriptions are built once, so submission neither imports
  nor inspects anything.
- A plugin written with `QgisSdkPlugin` has a third spelling next to the two
  declaration forms: `@app.job(id=..., title=...)`, `@app.job()` or
  `@app.job(key=...)` registers the function, applies `@job` when the author
  did not, and derives the name the way a sequence entry does. The three
  spellings land in one registry, so a name declared twice - by assignment and
  by decorator, or by two decorators - is refused where the plugin is defined.
- `ctx.jobs` is a `Jobs` facade over the engine, and deliberately has no
  `bind`: `ctx.jobs.<name>` is a `BoundJob`, `ctx.jobs.after(handle).<name>`
  the ordered one, and `ctx.jobs.watch(handle, on_progress=..., on_success=...,
  on_failure=..., on_cancelled=...)` subscribes the four events to the calling
  owner's scope. `bind` and the function-passing `delay` remain on
  `JobService`, where a host and a test use them.
- Ownership follows the dispatch, not a singleton: `ViewActions` carries the
  view's scope, sets `INVOKING_SCOPE` around the handler call, and a
  plugin-level service resolves a submission made under that variable to the
  invoking view's scoped service (only when the scope is a descendant of the
  plugin's; anything else stays plugin-owned). Two views calling at once keep
  their own owner because a context variable is per thread and per task.
  `ctx.jobs.plugin` is the explicit plugin-lifetime opt-in; the server host
  (TASK-80) sets the same variable for request scope, and nothing else changes
  for it.
- `PluginRuntime` builds the registry and, when it is non-empty, the service
  over the plugin scope with the host's `workers`, then adds `jobs` to the
  context it was given - so hosts must read `runtime.context` back rather than
  keep the context they built, and `DesktopLifecycleAdapter.context` does
  exactly that. A host that provides `jobs` *and* a plugin that declares them
  is refused rather than merged: two registries would mean two answers to
  `ctx.jobs.add`.
- Delivery needed a driver that did not exist: nothing in the Desktop adapters
  ticked a job service. `QgsJobPump` (a `QTimer` calling `tick()` on the GUI
  thread) now starts in `DesktopLifecycleAdapter.initGui` and stops before
  `unload`, and a host with its own event loop uses the same pump.
- Not claimed: `PluginDescription` does not list jobs yet, so `describe()`
  covers actions, streams, surfaces and providers but not the registry;
  generated per-plugin typing (TASK-124) does not exist, so `ctx.jobs.<name>`
  has no IDE autocomplete; and the bridge still carries a handle as `{id,
  status}`, with no live subscription and no wire change.

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

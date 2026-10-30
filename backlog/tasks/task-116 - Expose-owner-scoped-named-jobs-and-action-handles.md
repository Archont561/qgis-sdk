---
id: TASK-116
title: Expose owner-scoped named jobs and action handles
status: Done
assignee: []
created_date: '2026-10-28 14:47'
updated_date: '2026-10-30 16:30'
labels: []
milestone: m-8
dependencies:
  - TASK-115
  - TASK-67
type: enhancement
ordinal: 116000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Provide the 0.9.0 plugin-declared named job registry and host-integrated scoped submission. The public shape is jobs = {"add": add} on the plugin and ctx.jobs.add.delay(**inputs); bind remains internal. Use an explicit startup-built registry, not module scans or a global current-plugin singleton. Enable native actions to submit jobs and return local JobHandle values. See decision-65.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The runtime validates explicit registry keys, decorated declarations and unique job IDs at startup; invalid, duplicate, reserved or unknown names are refused clearly. The registry performs a prebuilt lookup and does not import or scan arbitrary modules on submission.
- [x] #2 A plugin action returns ctx.jobs.add.delay(...) immediately, without exposing bind; keyword inputs are validated and a local native surface receives a live handle with progress, success, failure and cancellation callbacks. No blocking GUI-thread get; RunsJobs cancellation and direct-handle behavior are documented and tested.
- [x] #3 Propagate the invoking owner explicitly and safely per dispatch: a view-launched action submits view-owned work by default, toolbar/plugin calls are plugin-owned, and plugin lifetime from a view is an explicit opt-in. Prove request-scope behavior with fakes here and integrate the server host under TASK-80; concurrent views/requests cannot steal each other’s owner or callbacks.
- [x] #4 View disposal detaches owned callbacks and requests cancellation, hiding alone does not dispose, plugin-owned work continues without retaining view objects, and unload/reload waits for worker acknowledgement or refuses replacement; cover race and two-view scenarios.
- [x] #5 Provide 0.9 migration and native action/view examples and specify runtime validation and autocomplete/type-checking limitations. Preserve bridge handle serialization as ID/status; do not imply a web page receives live handle subscriptions or add an unplanned wire protocol.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Session follow-up: dynamic ctx.actions and named jobs do not automatically give IDE autocomplete. TASK-124 explores generated per-plugin action typing separately; retain runtime validation and owner-scoping regardless of typing.

Implementation (2026-10-30):

- Declaration. `jobs` is a mapping (`{"add": add}`) or a sequence of `@job`
  functions (`(add, count_features)`); a sequence derives each name from the
  function's `__name__` with `derive_id`, not from the job id, because a bare
  `@job` id carries a module/qualname suffix. `QgisSdkPlugin.jobs` validates on
  assignment; `PluginRuntime` validates again when it is built, so a registry
  injected by any route is still refused at startup. Keys that are not plain
  identifiers, entries that are not `@job` functions, reserved names (the
  public surface of `Jobs`/`JobService`, kept in step by a test), two names for
  one name, and two names for one id are all refused by name. Lookup is a dict
  read: descriptions are built once, and a test monkeypatches `describe_job` to
  prove submission never describes anything again.
- A third spelling, added on review: `@app.job(id=..., title=...)`,
  `@app.job()` and `@app.job(key=...)` register the function the way
  `@app.action()` registers an action, apply `@job` when the author did not,
  derive the name from the function (or take `key=`), and merge with an
  `app.jobs` assignment into one registry - a name declared twice is refused
  where the plugin is defined, and `include()` merges both.
- AC2. `ctx.jobs` is a `Jobs` facade with no `bind`: `ctx.jobs.<name>` is a
  `BoundJob`, `ctx.jobs.watch(handle, ...)` subscribes progress/success/failure/
  cancelled to the calling owner's scope, and `bind`/`delay(fn)` stay on
  `JobService` for hosts and tests. `get()` still refuses on the GUI thread.
  `RunsJobs` keeps working unchanged (it goes through `ctx.actions`), and
  `qgis_sdk.testing.fake_ui_context` now builds the same view-scoped facade, so
  an author's own test sees the owner rules.
- AC3. `ViewActions` carries the view's scope and sets `INVOKING_SCOPE` around
  the handler call; a plugin-level service resolves a submission made under it
  to the invoking view's scoped service, and only when that scope descends from
  the plugin's - anything else stays plugin-owned. `ctx.jobs.plugin` is the
  explicit opt-in; the server host sets the same variable under TASK-80.
  Concurrent views are safe because a context variable is per thread and per
  task; the test dispatches from two threads and closes one view.
- AC4. Disposal detaches the view's subscriptions and requests cancellation
  (a `Jobs` facade's `watch` owner is the view scope); plugin-owned work
  submitted through `ctx.jobs.plugin` keeps running after the view closes and
  its callback never fires; a running view job refuses `runtime.quiesce()` with
  its handle id until its worker reports and the service ticks.
- Delivery. Nothing in the Desktop adapters ticked a job service before, so
  `QgsJobPump` (a `QTimer`) now starts in `DesktopLifecycleAdapter.initGui` and
  stops before `unload`; `runtime.jobs` is what it ticks.
- AC5. doc-12 gained "How do I name the jobs my plugin exposes?" (both forms,
  what is refused, no autocomplete, bridge stays `{id, status}`), the hosts
  section now describes the runtime-built service and the pump, and the 0.8 to
  0.9 migration gained the naming and plugin-lifetime bullets. decision-65
  carries the implementation note.
- Not claimed: `PluginDescription` does not list jobs yet, so `describe()` does
  not show the registry; no generated typing (TASK-124); no live handle on the
  bridge and no wire change.
<!-- SECTION:NOTES:END -->

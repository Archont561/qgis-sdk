---
id: decision-15
title: Refresh development through owned runtime generations
date: '2026-10-16 08:05'
status: proposed
---
## Context

Frontend HMR, Python plugin replacement and native runtime restart have different safety boundaries. Reloading methods in place leaves stale references and owned native objects.

## Decision

Proposed: an external watcher debounces/classifies changes and coordinates with a GUI-thread in-QGIS reload coordinator over a local authenticated development-only control channel, separate from the application web bridge. Never ship this control channel in production ZIPs. Frontend HMR preserves Python state; full page reload reconnects/handshakes/resubscribes and fetches current state. Backend contract changes regenerate/validate bindings and reject incompatible frontends.

For Python: preflight syntax/declarations/contracts before disrupting the active plugin. A preflight failure keeps the old revision running and reports it. On success, quiesce actions/endpoints, dispose UI/subscriptions, cancel or safely finish owned work, invalidate old handles and replace only plugin-owned modules. A cancellation request is not completed teardown: old running code/native resources may require waiting or restart. Never reload QGIS/Qt, native extensions, SDK internals or shared third-party modules as plugin source.

Construct fresh contexts/controllers/handlers and register the new runtime. Restore only explicitly serializable presentation state by stable IDs, not live widgets/contexts/bound methods. Unsaved dialog state requires a clear warn/transfer policy. If import/startup fails after teardown, clean partial startup and leave the plugin disabled with logs; rollback is not guaranteed.

Serialize reloads, coalesce intervening edits and assign generation IDs to suppress stale callbacks. Generation guards complement resource cleanup, not replace it. Unsafe dependency/global-state changes require restart. Start with manual reload and frontend HMR; enable automatic Python reload only after lifecycle tests prove cleanup.

## Consequences

- Keep logs accessible when plugin startup fails; report running revision and restart requirements explicitly.
- Test preflight failure, partial startup failure, overlap, active jobs, repeated reload, old-generation events and bridge reconnection.
- Exact control transport, state-transfer hooks and restart implementation remain open.

## Confirmed second-interview refinement (2026-10-16)

[decision-21](decision-21%20-%20Bound-job-ownership-and-refuse-unsafe-runtime-replacement.md) specifies a bounded cancellation wait; when safe completion is not achieved, refuse in-process reload and require explicit restart. Do not delete resources under running code. Exact timeout and restart UI are open.

## Implementation note (TASK-21, 2026-10-25)

The documented slice landed as `qgis_sdk_tools.devtools.reloader` (policy,
tested without QGIS) and `.devtools.bootstrap` (the in-QGIS glue), with
runtime hooks `ResourceScope.on_quiesce` / `PluginRuntime.quiesce`. What
differs from the proposal above, deliberately:

- **No separate control channel.** The coordinator runs on the GUI thread
  inside QGIS and the watcher is an in-process poller (500 ms, `*.py` and
  `metadata.txt` under the plugin package only). Nothing listens on a
  socket, so there is nothing to keep out of a production ZIP. The
  external watcher + authenticated channel stays open for a later need.
- **Preflight** is `compile()` of every module plus `check_project`
  (`SYNTAX*`, `META*`, `PROJECT*`, `CONFIG*` errors inside the package
  refuse; `QGIS001`/`ARCH001` warn; findings outside the package never
  block). Declarations and contracts are checked by the runtime at start,
  which is after teardown - a start failure there disables visibly.
- **Quiesce** is the decision-21 bound: 2 s, event loop pumped between
  checks, refusal names blockers by job handle id, `resume()` restores the
  revision, the message says finish/cancel or restart.
- **Generations** number attempts; old-generation delivery is prevented by
  scope closure (subscriptions disposed, late worker reports dropped), as
  decision-21 already fixed - the guard complements cleanup.
- **Automatic reload is on by default** (`--no-watch` opts out) because the
  lifecycle tests this record asked for exist: the opt-in harness drives
  preflight failure, partial startup failure, a stuck worker thread,
  coalesced bursts and a watcher-triggered reload in a real QGIS.
- Presentation-state restore and unsaved-dialog transfer remain open; a
  reload closes the plugin's views like an unload does.

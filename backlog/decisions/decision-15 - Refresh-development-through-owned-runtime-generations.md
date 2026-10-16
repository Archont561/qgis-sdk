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

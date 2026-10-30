---
id: decision-69
title: Order host hooks, bound the app-host shutdown and guard GUI-bound capabilities at runtime
date: '2026-10-30'
status: accepted
---
## Context

The m-8 hosts (decision-52) still have to be built and the 0.9.0 job contract
(decision-65) already runs whole job bodies off the driving thread, so the
runtime - not the author - decides what a body may touch. Reading Sanic's API
(`sanic/app.py` lifespan and task handling, `sanic/mixins/*`, `sanic/middleware.py`,
`sanic/blueprints.py`, `sanic/request/types.py`, `sanic/types/shared_ctx.py`)
was a pointer for the remaining design, not a mandate to copy: three of its
patterns have a direct analogue here and the rest do not fit a Qt-threaded,
statically declared plugin.

Sanic orders middleware and listeners by an explicit `(priority, -definition)`
key instead of trusting a stable sort, drains running tasks on shutdown for at
most `GRACEFUL_SHUTDOWN_TIMEOUT` and then abandons them, and warns at freeze
time about values that are unsafe to inherit into another process. All three
answer a question this SDK answers badly today: what happens when two hooks
share a priority, what `stop()` does with a job that is still running, and what
happens when a worker thread reaches a capability it may not touch.

## Decision

1. **Hook order is a stated rule, not an accident of sorting** (TASK-80).
   Server filters and services run by `priority` ascending; among equal
   priorities, declarations of the plugin class run in the order the class
   declares them, then the declarations of each plugin the class `include()`s,
   in include order, so an included access-control hook cannot silently
   pre-empt a filter the author wrote first. The order is fixed when the
   runtime starts and is what `check` and the tests reason about; a hook does
   not depend on dictionary iteration or on sort stability.

2. **Shutdown is bounded and says what it abandoned** (TASK-81, TASK-80).
   `qgis_sdk.app.run(...)` stops the job pump, stops the runtime, then waits for
   jobs that are still running up to a deadline (`grace`, fifteen seconds by
   default, then `QgsApplication.exitQgis()`); a job still running at the
   deadline is abandoned, named in a log record and reported as cancelled,
   never waited on forever. The server host has no equivalent wait: a
   request-scoped job is abandoned when its response is sent (decision-52),
   because a request may not hold the server open.

3. **A GUI-bound capability is guarded at runtime, where the lint cannot see**
   (TASK-117). The static lint reads the source it can see; a captured
   reference (`service = ctx.desktop` taken on the driving thread and used
   inside a job) defeats it. A context therefore remembers the thread it was
   assembled on, and reading a GUI-bound capability (`desktop`, `ui`, `layers`,
   `project`, `settings`, `files`, `streams`, `actions`, `notifications`)
   from another thread reports it once per capability and thread - a warning by
   default, a `QgisSdkUnsupportedCapabilityError` when developer mode
   (`QGIS_SDK_DEVTOOLS`) is on - instead of letting Qt crash the process.
   Contexts assembled off a GUI thread, and pure hosts that have no GUI thread,
   are unaffected; the guard never turns a working headless plugin into a
   failing one.

4. **Background loops are named and enumerable** (TASK-81, TASK-83). Every loop
   the SDK starts on a host's behalf - the job pump, the dev reload watcher, an
   app host's own timer - carries a name, and stopping a runtime enumerates
   what is still running instead of assuming it stopped. Sanic's `add_task`/
   `get_task`/`purge_tasks` registry is the source of the discipline, not the
   API.

5. **Not adopted.** A mutable `ctx` and `shared_ctx.lock()` (our contexts are
   frozen and capability-addressed, and nothing here forks); `add_task`'s
   delayed-dispatch machinery as public API; `touchup`'s signature rewriting
   (schema lowering already validates and injects); `app.ext`'s third-party
   extension namespace (there is no extension story - `processing` providers
   are the analogue); `Config.load_environment_vars` (the `settings` service);
   and `include(child, prefix=...)`, the prefix-at-registration option of
   Sanic blueprints, which is deferred rather than scheduled: job and action
   names are global per plugin, so mounting one reusable plugin twice needs a
   naming decision of its own.

## Consequences

- TASK-80 gains the ordering rule, the case-insensitive `ServerRequest`/
  `ServerResponse` helpers and a documented abandonment of request-scoped jobs;
  TASK-81 gains the bounded shutdown and the loop inventory; TASK-117 gains a
  runtime guard beside its lint rules and must document where each one stops.
- The guard adds a thread check to `Capability.__get__` and is the only new
  behaviour every host inherits; the worker-first contract of decision-65 keeps
  its `WorkerContext` refusals unchanged, so nothing that already fails now
  succeeds.
- The bridge, the transports and `HOST_FINGERPRINT` are untouched; no release
  or version is implied by this decision.

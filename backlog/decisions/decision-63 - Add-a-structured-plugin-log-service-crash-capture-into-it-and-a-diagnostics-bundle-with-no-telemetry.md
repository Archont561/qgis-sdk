---
id: decision-63
title: Add a structured plugin log service, crash capture into it, and a diagnostics bundle, with no telemetry
date: '2026-10-26'
status: accepted
---
## Context

Errors surface as refusals with codes, which is good for callers and silent
for everyone else; an unhandled exception in an action is a Python
traceback dialog from QGIS; `LogView` (decision-55) has no defined source;
bug reports arrive without versions or environment. The project has never
decided whether it collects anything from users.

## Decision

1. **`ctx.log`** is a curated service: `debug/info/warning/error(message,
   **fields)` producing structured records (time, plugin, level, message,
   fields, correlation id of the current action/job/request) written to
   `QgsMessageLog` under the plugin's tag, to `LogView`, to the agent
   transport as a stream, and to a rotating file under the profile when
   enabled. Author code never imports `logging`'s Qt handlers.
2. **Crash capture.** An unhandled exception in an action, job step,
   stream, surface slot or server hook is caught at the dispatcher, logged
   with the traceback and correlation id, reported to the user as a
   `critical` notification with "copy details" (never a modal traceback),
   and returned to the caller as the existing error envelope. The runtime
   itself keeps running; the job or request is failed.
3. **`qgis-sdk diagnose`** writes a bundle (SDK and QGIS versions, support
   matrix row, plugin description, recent log, check output, no project
   data) for a bug report, and the plugin's "Report a problem" standard
   action opens the same bundle for the user to attach by hand.
4. **No telemetry, by decision.** The SDK sends nothing anywhere; the
   diagnostics bundle is a file the user chooses to share. Any future
   change is a new decision.

## Consequences

- `LogView` has a defined source from 0.7.0 (TASK-96 shows `ctx.log`
  records); the full service, crash capture and `diagnose` land in m-11.
- Tasks: TASK-106 in m-11; TASK-96 gains the `ctx.log` minimum.

---
id: TASK-106
title: >-
  Add ctx.log, crash capture into it, the Report-a-problem surface and qgis-sdk
  diagnose, with no telemetry
status: To Do
assignee: []
created_date: '2026-10-26T11:13:00Z'
labels: []
milestone: m-11
dependencies:
  - TASK-96
  - TASK-74
type: enhancement
ordinal: 106000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-63. ctx.log debug/info/warning/error(message, **fields) producing structured records with a correlation id of the current action/job/request, written to QgsMessageLog under the plugin tag, LogView, the agent stream and an optional rotating file under the profile; unhandled exceptions in actions, job steps, streams, surface slots and server hooks caught at the dispatcher, logged with traceback and correlation id, reported as a critical notification with copy details, returned as the error envelope, runtime kept alive; qgis-sdk diagnose bundle (versions, matrix row, description, recent log, check output, no project data) and the Report-a-problem standard action; nothing sent anywhere.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Records from an action, a job step on the task manager and a server hook carry the same correlation id across QgsMessageLog, LogView and the agent stream; the file sink rotates (pure + native tests).
- [ ] #2 An exception in each of the five places is captured, notified without a modal, returned as the envelope, and the runtime keeps serving the next call; the job or request is marked failed (native + stateful tests).
- [ ] #3 diagnose writes the bundle without project data and the Report-a-problem action opens it; doc-12 documents the log service, crash handling and the no-telemetry rule.
<!-- AC:END -->

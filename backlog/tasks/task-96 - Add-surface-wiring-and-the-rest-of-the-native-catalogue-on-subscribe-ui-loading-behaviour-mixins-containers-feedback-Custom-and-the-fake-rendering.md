---
id: TASK-96
title: >-
  Add surface wiring and the rest of the native catalogue: @on, @subscribe, ui=
  loading, behaviour mixins, containers, feedback, Custom and the fake rendering
status: To Do
assignee: []
created_date: '2026-10-26T11:01:00Z'
labels: []
milestone: m-6
dependencies:
  - TASK-67
  - TASK-68
type: enhancement
ordinal: 96000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-55 points 2, 3, 5 and 7. @on(name).changed|clicked|toggled|edited and @on(name, signal) connect a surface method to the widget with that objectName after build() and disconnect with the scope; @subscribe(stream) and ctx.on(stream, callback) deliver streams on the GUI thread, scope-bound; on_accept/on_close hooks; ui="file.ui" loads a Qt Designer form before build(); mixins RunsJobs (self.run(action_id, **values) -> handle, progress to a JobProgress, cancel on close), SubscribesStreams, AcceptCancel; containers Panel, Group, Tabs, Row, Column; feedback JobProgress, LogView, ResultTable; buttons Button, RunButton, AcceptCancel; Custom(qwidget) and .widget; a QWidget class taking ctx accepted as a surface; the fake rendering of every component so ui_snapshot builds a tree without Qt; events caused by the view's own call flagged; check UI002 (unknown @on name) and UI004 (Qt imported at module level in the plugin package).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 @on and @subscribe connect after build() and disconnect with the scope on a hand-built tree and on a ui= tree, the methods remain callable directly with a fake ctx, a slot calling UiContext.actions runs on the GUI thread, and a running job from RunsJobs is cancelled when the dialog closes (pure + qgis native tests).
- [ ] #2 Every container, feedback and button component builds natively and under the fake with shared contract tests; Custom wraps an arbitrary QWidget; a plain QWidget subclass taking ctx is accepted as a surface; ui_snapshot of a surface built under the fake lists semantic nodes without Qt installed (pure tests) and matches the native tree's ids (native tests).
- [ ] #3 check reports UI002 for an @on name missing from a .ui tree and UI004 for a module-level qgis.PyQt import; the echo of a view's own call is flagged on the stream event; doc-12 documents wiring, mixins, containers, Custom and the pure-PyQt path; the example's results panel is a Dock built from these components.
<!-- AC:END -->

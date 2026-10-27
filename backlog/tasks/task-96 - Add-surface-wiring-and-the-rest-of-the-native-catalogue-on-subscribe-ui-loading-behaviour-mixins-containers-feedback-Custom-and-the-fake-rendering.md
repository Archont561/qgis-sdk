---
id: TASK-96
title: >-
  Add surface wiring and the rest of the native catalogue: @on, @subscribe, ui=
  loading, behaviour mixins, containers, feedback, Custom and the fake rendering
status: Done
assignee: []
created_date: '2026-10-26T11:01:00Z'
updated_date: '2026-10-27 10:15'
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
- [x] #1 @on and @subscribe connect after build() and disconnect with the scope on a hand-built tree and on a ui= tree, the methods remain callable directly with a fake ctx, a slot calling UiContext.actions runs on the GUI thread, and a running job from RunsJobs is cancelled when the dialog closes (pure + qgis native tests).
- [x] #2 Every container, feedback and button component builds natively and under the fake with shared contract tests; Custom wraps an arbitrary QWidget; a plain QWidget subclass taking ctx is accepted as a surface; ui_snapshot of a surface built under the fake lists semantic nodes without Qt installed (pure tests) and matches the native tree's ids (native tests).
- [x] #3 check reports UI002 for an @on name missing from a .ui tree and UI004 for a module-level qgis.PyQt import; the echo of a view's own call is flagged on the stream event; doc-12 documents wiring, mixins, containers, Custom and the pure-PyQt path; the example's results panel is a Dock built from these components.
- [x] #4 LogView shows ctx.log records: a minimal ctx.log (info/warning/error with fields) exists from this task so the component has a defined source; the full service, crash capture and diagnose follow in TASK-106 (decision-63).
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-26: AC 4 added - minimal ctx.log as LogView's source (decision-63).

2026-10-27: landed in three slices on one branch - 96a 316a6ea (containers, feedback, buttons, Custom, widget-form surface, ui_snapshot, ctx.log minimum), 96b c053bf7 (@on/@subscribe/ctx.on, hooks, ui= loading, RunsJobs/SubscribesStreams/HasAcceptCancel, echo flag, host stream pump), 96c (UI002/UI004, doc-12, the example's ResultsDock, scaffold PingDialog on @on). Pure wiring tests 16, native 5; example 19 pure / 6 native; quick suite 1841 passed. Status goes Done with the ACs once the pull request is merged.

PR #105 also carries two further commits: ceb7ffa test(python) turns seven rule-shaped parametrize tables into Hypothesis properties (the derive_title lower-camel capitalisation came out of it) and 0774928 feat(runtime) adds the declarative surface form (decision-55 amendment: components as class attributes, @on(component), per-window copies; ResultsDock declared). Adoption follow-ups: TASK-108.

Done 2026-10-27: PR #105 merged to main as c92ba2b (slices 96a 316a6ea, 96b c053bf7, 96c 1e772a0, plus the property tests ceb7ffa and the declarative surface form 0774928). Validation on the merged head: CI checks + macOS + Windows green; quick suite 1824 passed / 12 skipped; example 19 pure / 6 native; opt-in SCAFFOLD_DESKTOP 10, REFERENCE 5; test_backlog 20.
<!-- SECTION:NOTES:END -->

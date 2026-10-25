---
id: TASK-52
title: >-
  Bind PluginContext as the ctx class attribute instead of a constructor
  argument
status: Done
assignee:
  - '@agent'
created_date: '2026-10-25T09:44:00Z'
updated_date: '2026-10-25T10:03:00Z'
labels: []
milestone: m-3
dependencies: []
type: feature
ordinal: 52000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
PluginRuntime.start() sets `plugin_class.ctx` to its PluginContext and constructs the class with no arguments; unload and a failed start remove the attribute again. Authors annotate `ctx: PluginContext` for typing. Algorithms and jobs keep constructor injection (fresh per run). decision-31 amends decision-6.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 `start()` binds `ctx` before construction, `self.ctx` works in `__init__`, and `unload()`/failed start remove it
- [x] #2 A constructor that still takes `ctx` fails `start()` with a QgisSdkPluginLifecycleError naming the change; other TypeErrors pass through
- [x] #3 Scaffold template, smokes, tests and doc-12 use the class-attribute form; real-QGIS lifecycle, desktop-adapter, coexistence and scaffold qualifications pass
- [x] #4 decision-31 recorded, decision-6 amended, doc-12 migration note, task in the doc-4 0.4.0 inventory
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Closed via PR #65 (commit a083af5). Runtime binds plugin_class.ctx before a no-argument construction and unbinds on unload/failed start; migration hint for legacy constructors. Real-QGIS lifecycle/desktop-adapter/coexistence/scaffold smokes 60 passed offscreen. decision-31 amends decision-6.
<!-- SECTION:NOTES:END -->

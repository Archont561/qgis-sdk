---
id: TASK-67
title: >-
  Bind actions to the Desktop with @toolbar, @menu, @shortcut and action-named
  surfaces
status: To Do
assignee: []
created_date: '2026-10-26T08:41:00Z'
labels: []
milestone: m-5
dependencies:
  - TASK-64
type: enhancement
ordinal: 67000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-45. Stackable @toolbar(icon, text), @menu(path) and @shortcut(keys) mark an @action; they are refused at import time on anything else (a @job gets 'bind an @action that submits the job'); describe_bindings(cls) exposes them; describe_plugin and the wire contract do not change. host() creates toolbar actions, menu entries and shortcuts on start and removes them on unload; a triggered action with no inputs runs, one with inputs opens its NativeForms dialog, one that submits a job reports the stream on the message bar, and one with dialog=/dock= constructs the named plain surface class with a fresh UiContext, calls build(), parents the widget and disposes the view scope on close or unload (new dialog per opening, one dock per runtime). Icons resolve through qgis_sdk.resources from <plugin>/icons/; a missing icon is a check finding. qgis-sdk new --ui native writes one bound action and one surface class in <plugin>/ui.py.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 @toolbar/@menu/@shortcut stack on @action in any order and are refused on a @job, a @stream or a plain method with the documented messages; describe_bindings reports them; describe_plugin output and HOST_FINGERPRINT are unchanged (pure tests).
- [ ] #2 Under a QgsApplication with a fake iface, host() adds and removes the toolbar action, menu entry and shortcut; triggering runs the no-input action, opens the declared form for a typed one and dispatches the same handler the page calls; a surface class is built with a UiContext, shown as dialog or dock, and its view scope is disposed on close and on unload (qgis / webengine-free native tests; desktop harness updated).
- [ ] #3 qgis-sdk new --ui native produces the decision-43 file list plus <plugin>/ui.py; its starter tests pass without QGIS; check reports a missing icon; qgis-sdk dev reloads an edited surface (headless lifecycle harness).
- [ ] #4 doc-12 documents bindings, surfaces, the trigger rules and the GUI-thread/job/offload guidance; decision-12 carries a status review pointing at decision-45; the Python suite and tests/scripts are green.
<!-- AC:END -->

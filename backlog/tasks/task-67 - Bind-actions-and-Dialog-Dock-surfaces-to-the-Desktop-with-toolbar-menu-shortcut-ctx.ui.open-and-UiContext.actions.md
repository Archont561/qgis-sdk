---
id: TASK-67
title: >-
  Bind actions and Dialog/Dock surfaces to the Desktop with @toolbar, @menu,
  @shortcut; ctx.ui.open and UiContext.actions
status: Done
assignee: []
created_date: '2026-10-26T08:41:00Z'
updated_date: '2026-10-26 18:14'
labels: []
milestone: m-5
dependencies:
  - TASK-64
type: enhancement
ordinal: 67000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-45 points 1, 2, 5 and decision-55 points 1, 2 and 7 (UI003). Stackable @toolbar(icon, text), @menu(path) and @shortcut(keys) mark an @action or a surface class (a Dialog/Dock subclass, or any QWidget class taking ctx); they are refused at import time on anything else (a @job gets 'bind an @action that submits the job'); describe_bindings(cls) covers actions and the surfaces = [...] registry; describe_plugin and the wire contract do not change. host() creates toolbar actions, menu entries and shortcuts on start (declaration order across actions and surfaces) and removes them on unload. Trigger rule: an action with no inputs runs; one that submits a job reports the stream on the message bar; a typed action without a surface is UI003 and a named refusal, never a generated dialog; a Dialog is constructed per opening with its own UiContext bound on the instance before build(), shown, disposed with the scope; a Dock is one instance per runtime behind a checkable toggle whose visibility is remembered in ctx.settings. ctx.ui.open(Surface, initial=) from an action (fake records it; server host refuses by name); UiContext.actions.<id>(**kwargs) calls actions through the validated view-scoped path and returns a result or job handle, refusing re-entry of a running action from the same view. Icons resolve through qgis_sdk.resources from <plugin>/icons/; a missing icon is a check finding. qgis-sdk new --ui native writes one bound action and one bound Dialog built in pure PyQt.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 @toolbar/@menu/@shortcut stack on @action and on Dialog/Dock subclasses in any order and are refused on a @job, a @stream or a plain method with the documented messages; describe_bindings reports actions and registered surfaces; a typed bound action without a surface is UI003; describe_plugin output and HOST_FINGERPRINT are unchanged (pure tests).
- [x] #2 Under a QgsApplication with a fake iface, host() adds and removes the toolbar actions, menu entries and shortcuts of actions and surfaces; triggering runs the no-input action and refuses the typed one by name; a Dialog is built with self.ctx bound on the instance, shown, and disposed with its scope on close and on unload; a Dock is one instance, toggled by its checkable entry, visibility restored from ctx.settings (qgis native tests; desktop harness updated).
- [x] #3 self.ctx.ui.open(Surface, initial=) from an action opens the surface natively and is recorded by the fake; UiContext.actions.buffer(...) from inside a surface dispatches the same handler the page calls with coercion and view authority, returns the job handle for a job-submitting action, and a second call while the first is running from the same view is refused (pure + native tests).
- [x] #4 qgis-sdk new --ui native produces the decision-43 file list plus <plugin>/ui.py with a pure-PyQt Dialog; its starter tests pass without QGIS; check reports a missing icon and UI003; qgis-sdk dev reloads an edited surface (headless lifecycle harness).
- [x] #5 doc-12 documents bindings on actions and surfaces, the trigger rule, Dialog/Dock lifetimes, ctx.ui.open, UiContext.actions and the GUI-thread/job/offload guidance; decision-12 carries a status review pointing at decisions 45 and 55; the Python suite and tests/scripts are green.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-26: rewritten for decision-55 - no generated dialog on trigger (UI003), bindings also on Dialog/Dock surface classes, surfaces registry, ctx.ui.open, UiContext.actions.

2026-10-26 (sprint 5, session branch arena/0d0c6f3e-qgis-sdk): runtime half in feat(runtime) ea7693e - qgis_sdk.bindings (@toolbar/@menu/@shortcut on @action and Dialog/Dock, describe_bindings, refusals), qgis_sdk.ui.{surfaces,actions} (Dialog/Dock, ViewActions with view authority and re-entry refusal), UiContext.actions/settings, PluginContext.ui capability, qgis_sdk.adapters.surfaces (SurfaceHost + DesktopBindings: QAction per binding, trigger rule, dialog per opening, one dock with settings-restored visibility, JobHandle progress on the bar), qgis_sdk.testing.FakeUi/FakeViewControl, resources.icon_path. Tools half in feat(tools): check UI003/ICON001 (check/ui.py), qgis-sdk new --ui native (ui.py PingDialog, surfaces tuple, open_ping toolbar action, FakeUi starter test, README section), dev --exercise opens/edits/reloads the dialog. Evidence: pure (test_bindings, test_ui_context, test_check_ui, test_scaffold_ui), QgsApplication (test_surfaces_native 10, test_desktop_host_native), real Desktop (QGIS_SDK_DEVTOOLS=1 test_devtools_native 7 passed: toolbar action placed, dialog shown, answer 7, closed; after edit initial text 'edited', revision 9). HOST_FINGERPRINT unchanged. Desktop harness evidence is the devtools exercise rather than scripts/desktop_adapter_smoke.py, which builds its own context and does not go through host(). Full Python suite 1650/43, tests/scripts 248, ruff clean. Docs: doc-12 'Desktop bindings and native surfaces', '--ui native' starter, UI003/ICON001 rows, 0.6.0 migration bullet; decision-12 -> superseded (by decision-55), decisions 45/55 status reviews. Done after merge + CI.

Merged #98 -> main 2763cad (2026-10-26); main CI run 40374825948 green (checks, macOS, Windows). ACs 1-5 verified on the merged tree: see the sprint-5 note above. Closure recorded by the 0.6.0 gate sprint.
<!-- SECTION:NOTES:END -->

---
id: decision-45
title: Bind actions to the Desktop with stackable toolbar and menu decorators and plain surface classes
date: '2026-10-26 15:10'
status: accepted
---
## Context

A plugin without a page has no declared way to reach QGIS Desktop. `@action`
describes a callable surface the page, a test or a dialog can invoke; the
only Desktop binding the scaffold writes is the one toolbar button of the
web wrapper. Opening a native dialog for an action exists -
`NativeForms(runtime).run(action_id)` renders a Qt dialog from the action's
input schema and `Annotated` markers (TASK-3) - but the author has to wire the
button, the menu entry and the call by hand in PyQt. Decision-12's controller
per UI surface is still proposed and has no implementation, so a custom dialog
or dock has no SDK shape either. `qgis-sdk dev` already reloads any Python UI
on save; what is missing is the declaration, not the loop.

The repository's decorator rule is that decorators mark and never wrap
(decisions 6/10): `@action`, `@job`, `@stream` attach metadata to a plain
function and return it. That makes a second mark on the same function cheap,
and it makes the mark's presence checkable at import time regardless of the
order the decorators were written in.

## Decision

1. **Bindings are stackable decorators over `@action`.**

   ```python
   @toolbar(icon="buffer.svg")
   @menu("Vector/Field tools")
   @action(title="Buffer selected")
   def buffer_selected(self, distance: Metres) -> VectorLayerInfo: ...
   ```

   `@toolbar(icon=None, text=None)`, `@menu(path)` and `@shortcut(keys)` each
   add one binding to the function's binding list; `@menu` and `@shortcut`
   may repeat. They are refused at import time with a
   `QgisSdkDeclarationError` on anything that is not an `@action` - in
   particular on a `@job` ("bind an `@action` that submits the job") and on a
   `@stream`. Order is free; the documented convention is bindings above,
   `@action` below: how it is reached over what it is.
2. **Bindings are host metadata, not contract.** They are read by the Desktop
   host (`host()`, decision-43) when the plugin starts and are **not** part of
   `describe_plugin()`: the page, the fakes and a bare `QgsApplication` ignore
   them, so the plugin-description contract, the generated schema and
   `HOST_FINGERPRINT` do not move. `describe_bindings(cls)` exposes them to
   tests and to `qgis-sdk check`.
3. **What a bound action does when triggered is the runtime's rule.** No
   inputs: the handler runs on the GUI thread. Typed inputs: the declared form
   (`NativeForms`) opens first and dispatches on accept. A handler that
   submits a job: the message bar reports the job's progress stream. An action
   that names a surface (point 4) opens that instead of the generated form.
4. **Custom UI is a plain surface class, named by the action.**

   ```python
   class SettingsDialog:
       def __init__(self, ctx: UiContext) -> None: ...
       def build(self) -> QWidget: ...          # Qt imported inside, deferred

   @menu("Plugins/Field tools")
   @action(title="Settings", dialog=SettingsDialog)   # or dock=...
   def settings(self) -> None: ...
   ```

   The runtime constructs the class with a fresh `UiContext` (TASK-24: shared
   services, a view scope, `view.request_close()`), calls `build()`, parents
   the widget in a `QDialog` or `QDockWidget`, shows it, and disposes the
   view scope when it closes or the plugin unloads. A new dialog per opening;
   one dock instance per plugin runtime, hidden rather than disposed between
   openings. `build()` may also return a declarative form specification, in
   which case the surface is the declared form with the author's class
   handling accept. This is decision-12 narrowed to what is implemented: no
   decorator on the surface class, no surface registry - the action names it.
5. **Icons resolve through resources, never paths.** `@toolbar(icon=...)`
   names a file under `<plugin>/icons/`, resolved by `qgis_sdk.resources` from
   the installed package; a missing icon is a `check` finding, not a blank
   button at runtime. Menu order follows declaration order within a plugin.

## Consequences

- A native-only plugin is one file: the `@plugin` class with bound actions,
  providers and, when needed, a surface class next to it. `qgis-sdk new --ui
  native` writes one bound action and one surface class in `<plugin>/ui.py`;
  `dev` needs nothing new.
- `host()` grows the Desktop wiring that the web wrapper had, generalised:
  toolbar actions, menu entries and shortcuts created on start and removed on
  unload, each dispatching through `PluginRuntime.actions` /
  `NativeForms.dispatch`, so the page and the button run one handler.
- decision-12 gets a status review: the context seam and this
  action-named surface are what exists; the decorated controller and surface
  registry it described are withdrawn in favour of this form.
- Bindings on the same action as a page keep working: the page calls the
  operation, the toolbar opens the form; both reach the same method.
- Not decided here: canvas map tools and dock panels that live outside an
  action (always-visible panels). They need a surface that no action opens;
  if wanted, that is a `panels = [...]` class attribute in the style of
  `providers`, and a later amendment.

## Amendment (2026-10-26, decision-55)

Points 1, 2 and 5 stand. Point 3 is replaced by decision-55's trigger rule:
a bound action with typed inputs no longer opens a generated form; it needs a
surface of its own or is a `UI003` finding. Point 4 is replaced: there is no
`dialog=`/`dock=` on `@action`; a surface is a `Dialog` or `Dock` subclass
(or any `QWidget` class taking `ctx`) listed in `surfaces = [...]` on the
plugin, and `@menu`/`@toolbar`/`@shortcut` mark surface classes as well as
actions. `self.ctx` on a surface is an instance attribute bound by the runtime
before `build()`. An action opens a surface only through `self.ctx.ui.open`.

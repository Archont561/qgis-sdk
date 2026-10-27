---
id: decision-55
title: Compose plugin UI from curated components and bound surface classes, and generate nothing from an action
date: '2026-10-26'
status: accepted
---
## Context

decisions 45 and 46 made the action the centre of native UI: a bound action
with typed inputs opened a generated dialog (`NativeForms`), an action could
name a surface through `dialog=`/`dock=`, and three "standard surfaces" were
named the same way. In review the owner asked for the opposite emphasis:
bindings stay on actions, **nothing opens by itself**, and everything an
author would otherwise import from `qgis.PyQt` comes from a curated
`qgis_sdk.ui` catalogue of classes, with the form demoted from "the thing
that pops up" to "a component you place in `build()` and feed a schema".
Surfaces are explicit classes that can carry bindings themselves; actions
remain headless commands reachable from the Desktop, the page, the console
and agents alike. The conversation also settled how a surface reaches the
runtime (`self.ctx`, per instance), how widget signals reach actions, and that
pure PyQt inside `build()` must stay possible.

## Decision

1. **Trigger rule.** A bound `@action` with no inputs runs. A bound action
   with typed inputs and no surface of its own is a `check` finding
   (`UI003`) and a named refusal at runtime - never an invented dialog. An
   action opens a surface only explicitly: `self.ctx.ui.open(Surface,
   initial=...)`, a call the fakes record and the server host refuses by
   name. `@action(dialog=|dock=)` does not exist.
2. **Surfaces are classes with a placement and their own bindings.**

   ```python
   @menu("Plugins/Field tools")
   @toolbar(icon="buffer.svg")
   class BufferDialog(Dialog):          # new instance per opening
       ctx: UiContext
       def build(self) -> Panel: ...

   @menu("Plugins/Field tools")
   class ResultsPanel(Dock, area="right"):   # one instance per runtime, checkable toggle,
       ctx: UiContext                        # visibility remembered in ctx.settings
       def build(self) -> Panel: ...

   @plugin
   class FieldTools:
       providers = [tools]
       surfaces = [BufferDialog, ResultsPanel]
   ```

   `@menu`/`@toolbar`/`@shortcut` (decision-45) mark surface classes as well
   as actions; menu order is declaration order across both; `HOST001`
   applies to both. `surfaces = [...]` is the registry (`dev.ui.list`,
   `check`, console `handle.ui.open`). The runtime binds `self.ctx`
   (`UiContext`, one per opening for a dialog, one per runtime for a dock)
   **on the instance** before `build()`; the plugin's class-level `ctx`
   (one per runtime) is unchanged. `build()` returns a catalogue component
   or any `QWidget`; `ui="buffer.ui"` loads a Qt Designer file first. A class
   that is itself a `QWidget` with `__init__(ctx)` is accepted as a surface
   (Protocol form) so existing dialogs migrate without inheriting.
3. **The catalogue: `qgis_sdk.ui` components, composed; a few mixins for
   behaviour.** Containers `Dialog`, `Dock`, `Panel`, `Form`, `Group`,
   `Tabs`, `Row`, `Column`; inputs `LayerPicker(kind=)`, `FieldPicker(of=)`,
   `CrsPicker`, `FileInput(filters=)`, `DirectoryInput`, `Distance`,
   `Number(range=)`, `Text`, `Toggle`, `Choice(options=)`, `Colour`; feedback
   `JobProgress`, `LogView`, `ResultTable`; buttons `Button`, `RunButton`,
   `AcceptCancel`; escape hatch `Custom(qwidget)` and `.widget` on every
   component. Mixins `RunsJobs` (`self.run(action_id, **values)` → handle,
   progress to a `JobProgress`, cancel on close), `SubscribesStreams`,
   `AcceptCancel`. A component is curated when it: wraps QGIS's own widget
   where one exists (`QgsMapLayerComboBox`, `QgsProjectionSelectionWidget`,
   `QgsFileWidget`, `QgsDoubleSpinBox`) rather than re-implementing it;
   speaks models (`LayerId`, `FileRef`, `CrsId`) not strings; stays current
   through streams and unsubscribes with the scope; has a fake rendering
   for pure tests; has a semantic node in UI snapshots (decision-51);
   absorbs the Qt5/Qt6 difference once; and has a web counterpart (point 6).
   Qt is imported lazily inside methods, never at the module top, so
   `check`, the fakes and pure tests import the catalogue freely. The
   catalogue is capped at roughly twenty classes; anything else is
   `Custom`.
4. **`Form` is a helper, not a popup.** `Form.for_action(ctx, action_id,
   initial=)`, `Form.from_schema(schema)` and `Form(fields=[...])` build a
   form component from the pure schema → `FieldSpec` rule
   (`qgis_sdk.ui.form_fields`, kept) using catalogue inputs; `.values()`,
   `.changed`, `.submit()` (through `ctx.actions`). `NativeForms` and
   `DeclaredFormDialog` (public since 0.5.0) are replaced by `Form` in
   0.7.0 as a documented 0.x breaking change in doc-12. The parameter
   kinds of decision-46 point 1 are unchanged: they feed `Form`, Processing,
   the wire and the web.
5. **Wiring.** `@on("name").changed|clicked|toggled|edited` (or
   `@on("name", "signal")`) on a surface method connects the widget with
   that `objectName` after `build()` and disconnects with the scope;
   `@subscribe(stream)` delivers a stream to a method on the GUI thread;
   `on_accept`/`on_close` hooks. `UiContext.actions.<id>(**kwargs)` calls
   actions through the same validated, view-scoped path the page uses and
   returns a result or a job handle; a call while the same action is still
   running from the same view is refused, not re-entered. `ctx.on(stream,
   callback)` is the imperative form of `@subscribe`. Events caused by the
   view's own call are flagged so a surface can ignore its echo. Nothing
   here wraps the author's methods (decisions 6/10); they are callable in
   pure tests with a fake `ctx`.
6. **Web mirror.** `@archont561/qgis-sdk-ui` ships the same names with the
   same semantics - `Form` (from schema), `LayerPicker`, `CrsPicker`,
   `FieldPicker`, `FileInput`, `DirectoryInput`, `Distance`, `Choice`,
   `JobProgress`, `LogView`, `RunButton` - fed by `qgis.host`, disabled with
   a reason when a grant is absent, over the stores of decision-47.
   "DeclaredForm" is renamed `Form` everywhere.
7. **Check rules.** `UI001` interactive widget without `objectName`;
   `UI002` an `@on` name absent from a `.ui` tree (static) or from the tree
   `build()` produced under the fake (test-time); `UI003` bound typed
   action without a surface; `UI004` `qgis.PyQt`/`PyQt*` imported at module
   level in the plugin package (warning: it defeats the fakes and `check`).

## Consequences

- Actions stay commands, so the bridge operations, console handles and
  agent tools list only commands; panels are reached by humans through
  bindings and by developer-mode agents through `dev.ui.open`.
- Supersedes decision-45 points 3 and 4 and decision-46 points 2 and 3's
  naming; decision-12 is fully superseded; decision-47/51 get name and
  node notes. Every component costs five things (native, fake, snapshot
  node, web, docs), which is why the cap and `Custom` exist from day one.
- `check` loses the "a typed action will render" guarantee and gains
  UI002–UI004.
- Tasks: TASK-67 (bindings on actions and surfaces, `Dialog`/`Dock`,
  registry, `ctx.ui.open`, `UiContext.actions`, UI003) in 0.6.0; TASK-68
  (kinds, input components, `Form`, `NativeForms` migration) and TASK-96
  (wiring decorators, mixins, containers, feedback, `Custom`, fake
  rendering, UI002/UI004) in 0.7.0; TASK-69/70/72 adopt the names; TASK-79
  snapshots gain semantic nodes.

## Status review (2026-10-26, TASK-67): surfaces and bindings landed, stays `accepted`

The surface half is implemented: `qgis_sdk.ui.Dialog`/`Dock` base classes,
`surfaces = (...)` on the plugin, instance `ctx`/`initial` bound before
`build()`, `self.ctx.ui.open(Surface, initial=)`, `UiContext.actions` with
view authority, bindings on surfaces, `qgis_sdk.testing.FakeUi`,
`qgis-sdk new --ui native` (pure-PyQt `build()`), `UI003`/`ICON001`, and the
host lifetimes (`qgis_sdk.adapters.surfaces`). Nothing is generated from an
action: a bound typed action is a finding, never a form. Still open under
this decision: the component catalogue and `Form` (TASK-68), wiring
decorators, mixins, containers, feedback, `Custom`, fake rendering and
`UI002`/`UI004` (TASK-96), `.ui` loading and the web mirror.

## Status review (2026-10-27, TASK-96): the catalogue and the wiring landed, stays `accepted`

Points 2, 3, 5 and 7 are implemented as written: `@on(name).<listener>` /
`@on(name, signal)` and `@subscribe(stream)` mark methods that the host (and
`build_surface` under the fake) connects after `build()` and disconnects
with the view's scope; `ctx.on`, `on_accept`/`on_close`; `ui = "file.ui"`
loaded by `uic` natively and read as a `FakeUiTree` purely; the mixins
`RunsJobs`, `SubscribesStreams`, `HasAcceptCancel` (the `AcceptCancel`
*component* keeps that name, the mixin is `HasAcceptCancel`); containers
`Panel`/`Group`/`Tabs`/`Row`/`Column`, feedback
`JobProgress`/`LogView`/`ResultTable`, buttons `Button`/`RunButton`/
`AcceptCancel`, `Custom`, the QWidget-class surface form, `ui_snapshot` of
both renderings; `UI002` and the warning `UI004` (which applies to modules
declared native, where `QGIS001` is lifted). One refinement to point 2: an
event caused by the view's own `ctx.actions` call is flagged `echo` only
when the stream pushed it synchronously during that call - a pull iterator
never echoes. Still open: the web mirror of the catalogue (TASK-70) and the
full `ctx.log` service behind `LogView` (TASK-106, decision-63).

## Status review (2026-10-27, declarative form): amended, stays `accepted`

An amendment to points 2 and 3 that keeps every rule above. A surface may
declare its components as class attributes instead of building them:
`clear = Button(text="Clear")` is `buttons/clear`, `tools = Row([run,
clear])` nests them, the default `build()` returns the declared roots (one
as it is, several stacked in a `Column` named after the class) and
`@on(clear).clicked` wires to the component itself. The class attributes
are prototypes: each opening deep-copies the whole set before `build()`
(`qgis_sdk.ui.declarative.materialise`, called by the host and by
`build_surface`), so two windows never share a widget or a listener and a
method's `self.results` is that window's table. Plain classes, decorators
that mark and never wrap, the fake rendering and `ui_snapshot` all hold;
every catalogue class gained a keyword form, the positional forms stay, and
`qgis-sdk check` leaves component targets to the host (it resolves a
module-level constant for UI002). What was *not* done, on purpose: no
metaclass, no YAML or dict DSL, no widget-creating decorator - the
declaration is ordinary Python attributes and `__set_name__`. The example
shows both forms: `BufferDialog` builds because its `Form` needs `ctx`,
`ResultsDock` is declared. Adoption follow-ups (scaffold starter, static
checks over declared components, `Form` with declared inputs, the web
mirror's keyword forms, attribute names in snapshots) are
[TASK-108](../tasks/task-108%20-%20Adopt-the-declarative-surface-form-across-the-scaffold-the-web-mirror-and-the-snapshot-tooling.md).

## Status review (2026-10-27, TASK-108): the declarative form adopted, stays `accepted`

The follow-ups of the amendment above landed, each as the smallest rule
that keeps the ones before it. `Form` takes inputs declared on the class
and keys them by name the first time anything asks, so a declared surface
can group its inputs under an action without naming them twice; the link
from a field to its form is an object, not a closure, so the per-window
copy reports to the per-window form. The default `build()` seeds the
declared inputs from `initial` by name, at any depth, and refuses a key no
declared input carries - the opener's contract is the same as
`Form.for_action(initial=)`. A snapshot node of a declared component names
its class attribute (`"attribute"`) next to its `name`, which is what an
agent reads back into the source. `qgis-sdk check` reads the declarative
form statically as `UI005` - an `@on(attribute)` over a string or a number
or a name the class never binds, a `Custom` holding a widget built at class
definition - and still leaves to the host what the source does not show (a
helper call, a module-level name). The scaffold's `PingDialog` is declared
(`Number`, `Form`, `Button`, `LogView`; no Qt in the package), and its
README says in one sentence that a `build()` returning any QWidget is the
escape hatch; `BufferDialog` in the example keeps `build()` because
`Form.for_action` needs `ctx`, so the example still shows both forms. The
web catalogue takes the Python keyword spellings for the shared names
(`options`, `required`, `cancellable`, `text`, `of`) and doc-13 lists both
spellings and what each side lacks. Not done, as before: no metaclass, no
DSL, no widget-creating decorator, and `initial` is not applied to an
author's own `build()`.

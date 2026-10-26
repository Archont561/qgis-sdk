---
id: decision-12
title: Use one context injected controller per UI surface
date: '2026-10-16 08:05'
status: proposed
---
## Context

Dialogs/docks should follow plain-class authoring without a giant plugin superclass. UI construction, behavior and ownership have different responsibilities.

## Decision

Proposed: one decorated controller class per meaningful dialog/dock, with constructor-injected `self.ctx: UiContext`, a lazy `build()` content factory and ordinary event-handler methods. Actions normally remain decorated methods on the plugin/controller, not one class per button. Plugin UI services open registered surface classes; the runtime constructs fresh view contexts/controllers, creates and parents outer QDialog/QDockWidget containers, and owns cleanup. A factory returns content widgets or a supported declarative form specification. Runtime callable bindings stay Python-side; serialized descriptions contain validated binding IDs only.

UiContext combines shared services with view-owned subscriptions/tasks and explicit close/visibility operations, not a bag of all widgets/form values. Default proposal: new dialog per opening, one dock instance per plugin runtime, hide distinct from dispose. Request closure rather than synchronously deleting a controller during its handler. Define close-veto, completion and non-blocking modal semantics. Native widgets use qgis.PyQt in deferred factories or explicitly native modules. Disposal disconnects signals, cancels/detaches work and prevents late callbacks; plugin unload disposes all owned views.

## Consequences

- Pure tests inspect declarations and record UI requests; Qt tests construct content and verify ownership; real Desktop tests verify docks/menus/iface.
- Custom widgets remain ordinary composed components; trivial message boxes need not become classes.
- Exact decorators, open APIs, lifecycle hooks and native/web content specification remain proposed.

## Status review (2026-10-24): stays `proposed`

TASK-24 landed the *context* half: `UiContext` exists as a frozen dataclass
carrying `notifications`, `view: ViewControl` and its own `ResourceScope`, and
disposal follows the plugin's scope rather than a global registry. The controller
half — a decorated class per dialog/dock, a lazy `build()` content factory,
registered surface classes opened by a plugin UI service, fresh view
contexts/controllers per opening — has no implementation, because TASK-3 is still
`To Do` in this same milestone.

**Promotion condition:** promote when TASK-3 lands a controller and surface
opening, or when this decision is narrowed by amendment to cover only the context
seam that already exists. Do not promote it on the strength of `UiContext` alone:
the Consequences section's Qt and real-Desktop test obligations are unmet, and
TASK-33 still owns the display-dependent qualification.

## Status review (2026-10-26): narrowed by decision-45, stays `proposed`

decision-45 settles the controller half differently from the proposal above:
there is no decorated controller class per dialog or dock. Surfaces are named
by an action (`@action(dialog=Cls)` / `@action(dock=Cls)`), a surface class is
a plain class with `build() -> QWidget` that receives `UiContext` in its
constructor, and decision-46 adds three standard surfaces (`DeclaredForm`,
`JobProgressDock`, `LogPanel`) plus `ctx.ui.form`. What survives from this
decision is the context seam that already exists (`UiContext` with
notifications, `view`, its own `ResourceScope`), the "new dialog per
opening, one dock per runtime, hide distinct from dispose" lifecycle and the
"request closure, never destroy synchronously" rule, all of which decision-45
restates.

**Promotion condition:** promote when TASK-67 lands the `dialog=`/`dock=`
surface classes under a `QgsApplication`, with the Decision section read as
narrowed to the context seam and the surface lifecycle. The "decorated
controller class" wording is superseded and should not be implemented.

## Status review (2026-10-26, TASK-64): the runtime owns its first surface, stays `proposed`

TASK-64 implemented decision-43: the page a project declares under
`[tool.qgis-sdk.web]` is opened by the runtime (`qgis_sdk.adapters.desktop.host()`
over `qgis_sdk.adapters.webview.open_view`) as a `QDockWidget` or `QDialog`, with
its `Dispatcher`, its `QWebChannel` object and the host operations its grants
select - configured from TOML, never authored. That is the first UI surface the
runtime owns end to end, and it already follows this decision's lifecycle rules:
one view per runtime, `show_view()` raises the existing one, `unload()` closes
and disposes it, the plugin's scope ends what the view started. Nothing of the
controller API (`UiContext`-injected surface classes, `build()`, `ctx.ui.open`)
is touched by it.

**Promotion condition:** unchanged - TASK-67's `dialog=`/`dock=` surface classes
under a `QgsApplication`. When it is promoted, the Decision section should name
the runtime page view as the reference implementation of "the runtime constructs
and parents the outer container and owns cleanup".

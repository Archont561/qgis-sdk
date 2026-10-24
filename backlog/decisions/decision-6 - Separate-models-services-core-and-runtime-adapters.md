---
id: decision-6
title: Separate models services core and runtime adapters
date: '2026-10-16 07:43'
status: proposed
---
## Context

The SDK needs clear responsibilities for plugin declarations, context capabilities, execution, QGIS integration, and optional web UI. Authors should not need Plugin inheritance or PyQGIS plumbing for ordinary workflows. The existing package is a scaffold; this is a proposed architecture, not an implemented API.

## Decision

Proposed: organize the Python package into these responsibility boundaries:

- `models`: standard-library dataclasses, value types, identifiers, description/DTO types, structured diagnostics and errors. No QGIS, Qt, bridge transport, pytest, CLI, or service implementation imports.
- `services`: small QGIS-free Protocol contracts for curated capabilities such as layers, project, notifications, settings, tasks, processing, and networking. Contracts depend on models; production implementations live in adapters. Add services only for actual workflows, not a complete mirror of PyQGIS.
- `core`: declaration decorators/inspection, description validation, PluginContext composition, dispatch, dependency resolution, and lifecycle/resource ownership. Depends on models and service contracts, never concrete QGIS or test adapters. PluginContext is a typed collection of capabilities, not a service locator with arbitrary string lookups. Keep invocation-specific progress/cancellation separate from plugin-lifetime state.
- `adapters/qgis`: PyQGIS-backed services, Desktop lifecycle adapter, runtime discovery/initialization where appropriate, and explicit native access. Qt/WebEngine adapters load only when requested. Do not mix unrelated Qt bindings into the QGIS process.
- `bridge`: endpoint/router declarations, schema contract, authorization and transport-independent dispatch. A dedicated WebEngine/QWebChannel adapter connects it to Qt. DTOs/handles cross the boundary, never raw native objects.
- `testing`: in-memory service fakes, harnesses, and opt-in pytest plugins. Depend on the same contracts; native fixtures import their adapters lazily. Production modules do not import testing.
- `cli`/tooling: project checks, test launching, development orchestration, code generation and packaging. Compose lower-level APIs; core does not import CLI tools.

The dependency direction is models <- services <- core, with adapters/bridge/testing/tooling depending only on the lower-level pieces they need. Services may use other service contracts through explicit construction, not import concrete adapters. Keep models cohesive by feature as they grow rather than forming one miscellaneous models.py or a god service.

Plugin author classes remain plain classes. Inject a typed context once through construction (for example a dataclass ctx field), with an explicit factory escape hatch for custom dependencies. Decorators attach inspectable metadata without rewriting constructors, injecting inherited lifecycle methods, creating Qt objects, or globally registering instances. A separate adapter implements classFactory/initGui/unload and owns cleanup. Use explicit runtime-local registration rather than a process-global registry.

Provide a deliberate native escape hatch for Desktop-specific work; it is unavailable in pure mode and must never be exposed over the bridge. Exact module names, supported capability sets, context types and method signatures remain open.

## Consequences

- Pure models, contracts, declarations and handler logic are importable/testable without QGIS or Qt.
- Native and fake adapters can run common contract tests without claiming the fake emulates QGIS.
- QGIS thread affinity, layer lifetime, output ownership, CRS/units and cancellation must be explicit API semantics.
- Avoid large Layer wrappers reproducing QgsVectorLayer and service managers that hide ownership. Keep domain algorithms as ordinary Python functions when they do not need host services.
- Tests should guard import direction and optional dependency boundaries. Package-private runtime bundling must preserve these boundaries.

## Related scoped runtime refinements

Use separate context lifetimes for plugins, algorithms, views and jobs; algorithms and jobs receive fresh execution instances. See [decision-11](decision-11%20-%20Use-one-context-injected-class-per-Processing-algorithm.md), [decision-12](decision-12%20-%20Use-one-context-injected-controller-per-UI-surface.md), [decision-13](decision-13%20-%20Use-runtime-bound-Celery-inspired-local-jobs.md), [decision-14](decision-14%20-%20Enforce-QGIS-free-import-boundaries-during-check.md).

## Confirmed TASK-24 bounded runtime foundation (2026-10-17)

The user approved the initial runtime seams: a QGIS-free `PluginRuntime` in
`qgis_sdk.core` that constructs a decorated plain class through
`plugin_class(context)` by default, with an explicit `instance_factory`
escape hatch and no constructor inspection or rewriting. Declarations are
validated before construction; declared actions are exposed as a read-only
ID-to-bound-method mapping. `unload()` closes the existing `PluginContext.scope`
once, repeated unload is a no-op, and a partial startup failure disposes
already-registered resources before re-raising the author error. Ownership of
actions, signals, dialogs/docks and work continues to use `ResourceScope`
rather than a new registry or global lookup.

A delegating `DesktopLifecycleAdapter` and `create_class_factory(...)` helper in
`qgis_sdk.adapters.desktop` implement the QGIS `classFactory`/`initGui`/`unload`
shape without importing QGIS or Qt; the author-provided
`context_factory(iface)` supplies typed capabilities. A headless harness runs
this adapter inside a real `QgsApplication` and proves construction, action
binding and disposal. It passes no real Desktop `iface`, renders no UI and is
not a Desktop startup/unload qualification. Real Desktop evidence remains open
and is tracked by TASK-33.

## Status review (2026-10-24): stays `proposed`

Checked because TASK-11 and TASK-24 both cite this decision and are closed, which
reads like a stale status. It is not, and the status is left unchanged. What has
actually landed is the *layering and its guard*: `qgis_sdk.models`,
`qgis_sdk.services`, `qgis_sdk.core` and `qgis_sdk.adapters` exist,
`tests/test_pure_imports.py` enforces the `models <- services <- core` direction
by AST and by a subprocess import that blocks `qgis`, PyQt and pydantic, the
contexts are typed frozen dataclasses rather than a string-keyed service locator,
and the native escape hatch fails closed through
`QgisSdkUnsupportedCapabilityError` when no Desktop adapter is present.

Three responsibility boundaries named in the Decision section are still absent or
relocated, so accepting the decision would ratify them silently:

- `testing` — the in-memory service fakes and opt-in pytest plugins do not exist;
  `qgis_sdk.services` holds five Protocols and no implementations. This is what
  TASK-25.1 delivers.
- `bridge` — endpoint/router declarations live in the separate TypeScript
  package, not in `qgis_sdk`; decision-18 chose that split deliberately, but this
  decision's text still describes an in-package `bridge` boundary.
- `adapters/qgis` — the existing adapters are `desktop`, `webengine` and
  `pydantic`; no PyQGIS service adapter exists yet. TASK-25.2 owns it.

**Promotion condition:** promote to `accepted` when the `testing` and
`adapters/qgis` boundaries exist with the contracts they serve, i.e. after
TASK-25.1 and TASK-25.2 land. Until then the decision is the agreed direction, not
a realized one, and the mismatch is recorded here instead of being papered over by
a status flip.

---
id: doc-28
title: Session synthesis worker jobs API ergonomics and PyQGIS safety
type: other
created_date: '2026-10-28 15:59'
---

# Session synthesis: worker jobs, API ergonomics and PyQGIS safety

**Status at the 2026-10-28 synthesis:** planning and local implementation,
not a release or CI result. Only worker-first jobs were explicitly targeted at
0.9.0; newly recorded proposals and fixes are unassigned until prioritized. The
original 2019 PyQGIS presentation describes historic PyQGIS behavior, not a
claim that this SDK exposes all of it today.

## Worker-first jobs — accepted for 0.9.0

[decision-65](../../decisions/decision-65%20-%20Run-registered-jobs-on-workers-with-owner-scoped-named-submission.md) and [TASK-115](../../tasks/task-115%20-%20Run-whole-jobs-on-workers-with-a-restricted-context.md), [TASK-116](../../tasks/task-116%20-%20Expose-owner-scoped-named-jobs-and-action-handles.md), [TASK-117](../../tasks/task-117%20-%20Check-worker-job-safety-with-source-only-lint-rules.md) and [TASK-82](../../tasks/task-82%20-%20Run-offloaded-job-steps-as-QgsTasks-under-QgsTaskManager-with-the-job-visible-as-a-parent-task.md)
record the approved worker-first design. Today `@job` marks the original
function; synchronous and async job steps run on the driving thread and only
explicit `ctx.workers.offload(...)` runs on a worker. Plugin and UI contexts do
not provide a named job registry. Celery's `task.delay(*args, **kwargs)` is a
shortcut to `apply_async(args, kwargs)`; calling the task directly invokes it
locally. That analogy does not give the SDK a broker or distributed guarantees.

The owner wants entire jobs automatically offloaded, an explicit plugin-named
registry and `ctx.jobs.<name>.delay(...)` from actions, with binding hidden,
view/request/plugin ownership, local handles and worker safety lint. Native
implementation uses one `QgsTask` per job, callback delivery on the driving
thread, cooperative cancellation and safe reload. Async migration, limited
worker capabilities, independent concurrent scopes, refusal when no worker is available,
static-analysis limits and the existing bridge's ID/status-only handle shape
remain release criteria, not already-shipped behavior. The 0.9 gate is
[TASK-83](../../tasks/task-83%20-%20Prepare-and-qualify-0.9.0-release.md); server and standalone host tasks have been coordinated with the
registry. `Depends` is not part of that decision.

## Dependency injection and installation — separate open work

The owner wants third-party-heavy work such as pandas jobs easy to test with
fakes: [TASK-122](../../tasks/task-122%20-%20Design-injectable-worker-job-dependencies-and-test-overrides.md) records provider injection and override design, including
worker-local resolution and no FastAPI/Pydantic requirement. The suggested
`Annotated[Protocol, Depends(provider)]` shape is exploratory, not an SDK API.

The owner also wants an option to prompt end users for approval before using
a QGIS-compatible Python/pip to install missing packages. [TASK-123](../../tasks/task-123%20-%20Decide-opt-in-end-user-dependency-installation-policy.md) records
this request as a policy investigation; [decision-50](../../decisions/decision-50%20-%20Declare-third-party-Python-packages-as-externals-with-a-startup-probe-and-vendor-only-pure-Python-ones.md) and [TASK-77](../../tasks/task-77%20-%20Declare-externals-with-a-startup-probe-vendor-pure-Python-packages-in-build-and-bucket-imports-in-check.md) still
prohibit SDK installation. Explicit approval cannot by itself solve managed
Python, native ABI or shared-interpreter risks. No install capability is
implemented or authorized until a separate decision. Installing Pydantic for a
plugin independently is distinct from SDK support for its retired adapter.

## Unified introspection and adapter retirement — local work, not shipped

- [decision-66](../../decisions/decision-66%20-%20Unify-declaration-introspection-with-describe-and-declaration-methods.md) and [TASK-120](../../tasks/task-120%20-%20Land-and-qualify-the-unified-declaration-describe-API.md): owner selected both
  `qgis_sdk.describe(target)` and `target.describe()`, with one combined action
  result for toolbar/menu/shortcut bindings. The active working tree contains
  an implementation covering plugins, actions, streams, jobs, algorithms,
  provider instances, surfaces and UI handlers; plugin bindings and action
  wires are local metadata, omitted from bridge serialization. Old helpers
  remain. The dynamically added name `describe` is reserved; collisions fail
  at decoration and dynamic IDE typing is not guaranteed.
- [decision-67](../../decisions/decision-67%20-%20Retire-the-optional-Pydantic-controlled-deployment-adapter.md) and [TASK-121](../../tasks/task-121%20-%20Land-and-qualify-removal-of-the-Pydantic-controlled-deployment-adapter.md): owner requested removal of the Pydantic
  controlled-deployment adapter and extras. Removal is implemented locally;
  prior published versions still contain them. There is no drop-in SDK
  replacement and the breaking change needs a future Python minor and migration.
- Latest local validation after both changes: 1,897 Python tests passed, 47
  skipped, 96.99% coverage; 262 release-tool tests passed; generated contracts,
  TypeScript typecheck, Ruff, Pixi lock and inspected wheel metadata passed.
  The docs build and 6,788 internal-link checks passed. Earlier in the session,
  a QGIS Desktop harness loaded two built vendored plugins and exercised their
  descriptions. These are **local** checks, not merge, release or CI evidence.

## UI, actions and cross-plugin access — proposals only

- `@on(ping).clicked` exists; `Button.clicked(listener)` currently subscribes
  and returns an unsubscribe function, so simply writing `@ping.clicked` does
  not work as a decorator. [TASK-126](../../tasks/task-126%20-%20Evaluate-direct-component-event-decorator-syntax.md) evaluates compatible instance-scoped
  syntax and cleanup; no design selected.
- `self.ctx.ui.open(BufferDialog, initial=...)` and class toolbar/menu/shortcut
  bindings exist. `BufferDialog.open()` is not implemented and class-global
  ownership is ambiguous across plugins. [TASK-127](../../tasks/task-127%20-%20Evaluate-class-level-surface-open-convenience.md) evaluates a safe form.
- `UiContext.actions.<id>(...)` validates dynamically but does not automatically
  yield static editor completion. [TASK-124](../../tasks/task-124%20-%20Evaluate-generated-typed-plugin-action-access-for-native-surfaces.md) explores generated per-plugin
  typing without weakening validation.
- Direct `qgis.utils.plugins[name].runtime` access is a current advanced QGIS
  workaround, not a validated cross-plugin API. [TASK-73](../../tasks/task-73%20-%20Add-qgis_sdk.console-ConsoleSession-over-the-curated-services-PluginHandle-and-PluginRuntime.algorithms.md) plans a console
  `PluginHandle`; [TASK-125](../../tasks/task-125%20-%20Design-validated-owner-scoped-actions-between-plugins.md) explores a separate authorized cross-plugin
  interface, ownership, reload and independently vendored SDK versions.

## PyQGIS comparison and high-priority safety findings

The current SDK provides `@provider.algorithm`, typed Processing registry
requests and explicit export; [TASK-94](../../tasks/task-94%20-%20Widen-Processing-discovery-and-help-every-output-kind-model-files-and-batch-runs.md) plans more declared output kinds and
batch/model execution. Features and expression evaluation/editing are planned
for 0.10.0 in [TASK-86](../../tasks/task-86%20-%20Add-the-features-and-expressions-services-paged-iteration-filters-geometry-models-attribute-read-editing-sessions-evaluate-and-validate.md), now refined to examine context managers, geometry
iteration, failure cases and provider-specific atomicity without promising
cross-provider guarantees. [TASK-81](../../tasks/task-81%20-%20Add-the-standalone-app-host-qgis_sdk.app.run-an-optional-canvas-window-qgis-sdk-run-and-build-target-app.md) plans standalone initialization for
0.9.0. Native QGIS 4.2.3 produced `TypeError` for `asPoint()` on a line and
`IndexError` for an out-of-range `geometryN`; these are native QGIS results,
not SDK geometry APIs. Custom expression-function registration and QGIS
validity-check registration are separate **unapproved** explorations in
[TASK-128](../../tasks/task-128%20-%20Explore-owned-custom-QGIS-expression-function-declarations.md) and [TASK-129](../../tasks/task-129%20-%20Explore-owned-QGIS-layout-and-other-validity-check-declarations.md).

Two independently scoped high-priority defects are open:

1. [TASK-118](../../tasks/task-118%20-%20Prevent-layer-exports-from-replacing-their-source-dataset.md): a native QGIS 4.2.3 probe exported a temporary GeoJSON back
   to its own source with `overwrite=True`; the file was replaced despite the
   `Layers` protocol promise. No user dataset was involved.
2. [TASK-119](../../tasks/task-119%20-%20Enforce-honest-Processing-output-safety-for-explicit-destinations.md): a simulated failing Processing backend writing an explicitly
   supplied external path left its partial output, because cleanup removes only
   the SDK-owned run directory. Input/output aliasing is not checked; no input
   corruption was demonstrated. Do not generalize the simulated result into a
   claim about every provider. The QGIS probe emitted missing optional PDAL
   library warnings; it does not qualify PDAL.

Until corrected, avoid same-source exports and prefer SDK-allocated destinations.
These tasks are unassigned, not silently attached to a release gate.

## Earlier session deliverable

Documentation improvements were merged as
[PR #122](https://github.com/Archont561/qgis-sdk/pull/122); GitHub reported
successful CI, autorelease and Pages deployment. The sandbox could not directly
fetch the live Pages site, so live route/redirect verification was not claimed.
The subsequent implementation and backlog work described above were separate from that merged PR. See TASK-120/121 for landing and release status.

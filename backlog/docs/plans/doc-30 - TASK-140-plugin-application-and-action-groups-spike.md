---
id: doc-30
title: TASK-140 plugin application and action groups spike
type: guide
created_date: '2026-10-28 19:51'
---
# Plugin application and action groups: TASK-140 spike

## Status and recommendation

**Historical spike report; implementation migration is now in progress.** After
this research, the owner requested a breaking move to `PluginApp` with removal of
the public class-based authoring API, permitting private class lowering. The
checkout now contains an incomplete implementation: some references and legacy
public exports still need migration, so it is not release-ready. The earlier
research, results and proposed additive recommendation below describe the spike
at the time of the experiment, not the current implementation state.

**Research and prototype, not a shipped API or release commitment.** Recommend an
additive, explicitly owned application object with explicit groups, provided the
qualification gates below pass. Keep class plugins fully supported. A simple
namespace alias is a useful low-risk fallback but does not solve multi-module
composition or dependency injection. Do not ship the prototype in an SDK wheel.
See [proposed decision 68](../../decisions/decision-68%20-%20Explore-additive-plugin-applications-with-explicit-action-groups.md).

The original prototype has been moved into the in-progress implementation in
`packages/qgis-sdk-runtime/src/qgis_sdk/core/_application.py`; its migrated tests
include `packages/qgis-sdk-python/tests/test_plugin_app_declarations.py` and
`packages/qgis-sdk-python/tests/test_plugin_app_native.py`. The real-Desktop
probe is `packages/qgis-sdk-python/scripts/plugin_app_desktop_smoke.py`, with an
opt-in test in `packages/qgis-sdk-python/tests/scripts/test_plugin_app_desktop_smoke.py`.
The results below refer to the original experiment, before this migration.
It is intentionally narrow: synchronous actions and generator streams, first
positional `PluginContext`, explicit IDs/titles, groups, class lowering,
selected Desktop bindings and explicit surface/provider lists. An experimental
`module:app` resolver and describer registrations are **not** SDK integration.
Everything else below is a **design or qualification plan**. No FastAPI or
Pydantic dependency is used.

## Alternatives and examples

### Existing supported class

```python
from qgis_sdk import action, plugin
from qgis_sdk.core import PluginContext

@plugin(id="survey.plugin", title="Survey")
class Survey:
    ctx: PluginContext

    @action(id="double", title="Double")
    def double(self, value: int) -> int:
        self.ctx.notifications.info("Calculating")
        return value * 2
```

The runtime binds `ctx` on the class during its lifetime; instance methods have
ordinary `self`, so grouping across files requires inheritance/composition and
care with declaration discovery. To unit-test, construct a `PluginRuntime` with
a fake `PluginContext` and call its bound action. This is today's supported path.

### Namespace-only alias (illustrative, not implemented)

```python
@plugin(id="survey.plugin", title="Survey")
class Survey:
    ctx: PluginContext

    @plugin.action(id="double", title="Double")  # hypothetical alias of @action
    def double(self, value: int) -> int:
        return value * 2
```

This is cosmetic: the class, method contract, lifecycle, schemas and tests are
unchanged. It does not register independent functions or solve grouping. Adding
attributes to the existing decorator has discoverability and typing costs.

### Application with explicit groups (experiment)

For clarity these imports refer to the non-shipping script, **not** `qgis_sdk`.
Files are normal Python modules; importing them executes trusted author code.

```python
# survey/actions.py
from qgis_sdk.core import PluginContext
from plugin_app_spike import ActionGroup

reports = ActionGroup()

@reports.action(id="double", title="Double")
def double(ctx: PluginContext, value: int) -> int:
    ctx.notifications.info("Calculating")
    return value * 2
```

```python
# survey/plugin.py
from plugin_app_spike import PluginApp
from .actions import reports

app = PluginApp(id="survey.plugin", title="Survey")
app.include(reports)              # explicit: no module scan or current-plugin global
Plugin = app.plugin_class()       # prototype-only export for existing tools
```

```toml
# pyproject.toml, prototype class export only
[tool.qgis-sdk]
plugin = "survey.plugin:Plugin"
```

An isolated unit test can call `double(fake_context, 21) == 42` with the SDK's
`PluginContext`, `ResourceScope` and `RecordingNotifications`; a host-path test
creates `PluginRuntime(app.plugin_class(), fake_context)`, starts it, calls
`runtime.actions["double"](value=21)`, and unloads it. The experiment proves
both paths. A future production API might use `plugin = "survey.plugin:app"`,
but current discovery rejects the app object; the example class export is not
a recommendation to depend on this script.

| Choice | Benefit | Cost / boundary |
| --- | --- | --- |
| Class (today) | Supported lifecycle, host, generators and binding semantics | Grouping requires class composition; context lives on instance/class |
| Namespace alias | Minimal additive spelling change | No registered function ownership or reusable groups |
| Application + group | Explicit multi-file composition, ordinary typed functions and direct fake tests | New discovery, introspection, lifecycle and compatibility surface; more qualification |

## Ownership, IDs and context

The experiment requires explicit IDs and titles, returns the original decorated
function, snapshots group membership at inclusion and rejects duplicate IDs or
handler names before changing the receiver. Descriptions are sorted by action
ID. Including a group twice is an error, not idempotent. Each app has an
independent registry; the same group may be included in two apps, each lowered
to a separate class/context. It does not scan modules, register a global
"current plugin", or auto-include imported groups. Module caching, cycles,
late additions and repeated imports need documented diagnostics: an included
group's later additions do not appear in an existing snapshot. Metadata attached
to a referenced function is still mutable; a production design must snapshot or
freeze it and reject mutation/re-inclusion deterministically.

Recommend explicit IDs initially; if defaults or group prefixes are later
supported, specify normalization, collision rules and a stable mapping before
release. Actions and streams share a namespace. Detect duplicates across all
included groups and app declarations atomically before startup; distinguish
handler-name collisions from public IDs. Registry construction and validation
must not instantiate the plugin or invoke handlers.

A declared first parameter is a typed host-injected `PluginContext`, not a wire
parameter; other typed inputs remain explicit and validated using the existing
schema subset. The experiment requires a positional `PluginContext` annotation,
resolves annotations, excludes that parameter from the lowered signature, and
uses a closure to bind the original handler. Its synthetic class method is not
the author's function; decorator registration itself preserves identity. Test
contexts are explicitly assembled, not global overrides. For TASK-122, explore
per-runtime explicitly keyed dependency providers and overrides; do not silently
inject arbitrary annotations, put injected values in schemas, share overrides
across plugins, or introduce a framework dependency. Define lifetime, async
cleanup, typing, errors and worker restrictions before implementing it.

The prototype reserves an input named `self` because current class description
requires a synthetic `self` parameter. It rejects keyword-only context and is
not a complete signature validator. `get_type_hints` evaluates trusted Python
annotations and can execute code. Neither import nor introspection is a sandbox.

## Composition and lifecycle design

The following is **proposed pseudocode**, not an executable prototype or SDK API:

```python
# reporting.py: definitions, not implicit registrations
reporting = ActionGroup()

@reporting.stream(id="ticks", events={"data": int})
def ticks(ctx: PluginContext, count: int):
    for number in range(count):
        yield {"kind": "data", "payload": number}

@menu("Plugins/Survey")
class ReportDialog(Dialog):
    # A real surface defines its components and build method here.
    @subscribe("ticks", count=5)
    def on_tick(self, event: int) -> None:
        ...

provider = Provider(id="survey.provider", title="Survey")

# plugin.py: explicit ownership and composition
app = Plugin(id="survey.plugin", title="Survey")
app.include(reporting)
app.add_surface(ReportDialog)
app.add_provider(provider)

@app.action(id="show_report", title="Show report")
@toolbar(icon="survey.svg")
@menu("Plugins/Survey")
@shortcut("Ctrl+Alt+S")
def show_report(ctx: PluginContext) -> None:
    ctx.ui.open(ReportDialog)
```

Names, event payload conversion and surface wiring in this sketch are open to
qualification; it only illustrates who owns which declaration. A production app
should have explicit, owned lists of surfaces and providers; its lowered class
could expose the existing `surfaces` and `providers` fields.
Surface classes keep their own `@on`/`@subscribe` wire metadata; app actions
may stack `@toolbar`, `@menu` and `@shortcut` in either order. Pure tests exercise
copying binding and `@on` metadata onto a lowered action and both stacking
orders while omitting them from bridge JSON. The native headless test also
places real Qt actions, opens a real Qt dialog and registers a real QGIS
provider. Its Desktop interface is a fake; it is not a running QGIS Desktop.
Copying metadata is not proof that a function with a UI wire executes correctly
as a surface handler. Async actions and exhaustive decorator combinations remain
unsupported or unproven.
Use the existing UI003 rule for a bound action with inputs but no surface.

For streams, use an explicit declaration such as illustrative
`@group.stream(id="ticks", events={"data": int})`; inject context outside its
request, preserve stream event schemas and disposal, and reject binding a stream
directly. The prototype lowers one generator stream and tests its fake runtime output and
shared action/stream ID collision. Bridge subscription, subscriber lifetime,
event validation and decorator ordering still need executable proof. Providers and all surfaces belong to the
runtime scope, not the module import. Construction must roll back registrations
on failure; unload/reload must unregister only that owner, cancel subscriptions,
remove Desktop objects, close scopes and invalidate generation-bound handles.
In addition to fake runtime tests, an offscreen QGIS test starts two SDK
Desktop hosts concurrently with separate compiled app classes, installs actual
QActions and dialogs through a fake interface, and registers two empty providers
in the real Processing registry. It verifies one owner's unload does not remove
the other's provider or bindings, a duplicate-provider startup fails without
removing the incumbent, and restarting a stopped host works. It is not an
installed plugin, real QGIS Desktop session, source-edit reload, or cross-platform
qualification. The separate Desktop executable probe below exercises the first
three in a temporary profile, still without a visible display.

### Real QGIS Desktop executable (offscreen)

On the same Linux/QGIS 4.2.3, Qt 6.11.2 and Python 3.14.8 stack, the opt-in
probe launched the actual `qgis` Desktop executable with a clean temporary
profile, `--noplugins`, and Qt's offscreen platform. Two throwaway plugin package
directories were installed into the profile and discovered via QGIS's own
`updateAvailablePlugins`, then loaded, started and unloaded through its plugin
manager. Their class factories use the experimental resolver to lower app objects
and hand class specs to the unchanged SDK Desktop host. The probe verified the
real `qgis.utils.iface` and SDK context, both Processing providers, toolbar actions
on the GUI thread, actual dialogs, independent unload, final cleanup and source-edit
reload. For reload, it edited a fixture action from doubling to tripling, changed
the source size to invalidate bytecode, and observed a fresh module and the result
change from 42 to 63 without manually deleting modules from `sys.modules`. QGIS
plugin discovery must populate its available-plugin list for its import tracker to
unload modules correctly.

Reproduce in an environment with the QGIS Desktop executable:

```sh
QGIS_SDK_PLUGIN_APP_DESKTOP=1 pixi run -e default pytest -q packages/qgis-sdk-python/tests/scripts/test_plugin_app_desktop_smoke.py
```

This was an offscreen session, not a human-visible GUI; the profile used
directories rather than built plugin ZIPs. It does not qualify visible rendering,
UI-wire execution, provider algorithms, WebEngine, other QGIS versions or
Windows/macOS. The production SDK still rejects `module:app`; direct discovery
here is only the experimental resolver.

Actions remain allowlisted and pass through `Dispatcher.from_runtime` and the
same per-view authorization, request validation and generation checks. A
function decorator must not grant access or bypass file/network capabilities.
Native callbacks and UI/service operations retain the host's GUI-thread rules;
this proposal does not run a whole action on a worker. TASK-115/116 worker-first
named jobs stay in 0.9.0; an action may eventually submit an owner-scoped named
job without passing a QGIS-bound context into worker code.

## Description, schema and discovery evidence

For an equivalent single `double` class action, the prototype test compares the
complete `describe(...).to_dict()` and the entire generated TypeScript schema
text; both match, and `ctx` is absent from request properties. A separate
single-stream example also matches the full description and generated schema.
It also calls a real SDK `Dispatcher` with one permitted action, an invalid payload and a denied
operation. This is one representative pure case, not proof for every schema,
stream, binding or frontend. The wrapper-argument collision test verifies an
input named `_function` cannot replace the registered handler.

The experimental script registers its own describers with the SDK dispatcher:
`describe(app)` and `app.describe()` return the same description; for an
original registered action or stream, `describe(function)` and
`function.describe()` agree. Pure tests cover both orders of stacked menu and
`@on` metadata, an existing `describe` collision and unchanged JSON fields.
This registration mutates the process-wide **describer registry**, not a
current-plugin registry; it happens only if the prototype script is imported
and is not shipped. Conflicting metadata for the same original function is
refused; shared groups with the same metadata work. Dynamic typing and all
possible marker-order interactions remain unqualified. Production must integrate
these kinds deliberately and maintain compatibility. TASK-137 diagnostic JSON
should consume the same description, not invent a separate schema. Local-only
binding and wire metadata must stay out of `PluginDescription.to_dict()` unless
a separately versioned bridge change is approved.

`qgis_sdk_tools.generate.describe_plugin_spec` currently imports
`module:attribute` and calls `describe_plugin`, while Desktop
`resolve_plugin_spec` explicitly requires a class and uses `__import__` so QGIS
can track modules for unload. Artifacts call the same resolver and inspect
class providers; `PluginRuntime` and Desktop binding description also expect a
class. Tests confirm a missing module/attribute fails, the lowered class works
with the generator, and the current SDK resolver rejects the app object. The
experiment's `resolve_spike_spec("module:app")` uses `__import__`, returns a
lowered class with the author module as `__module__`, and can feed the existing
generator. A native test exposes the lowered class as `module:Plugin` and uses
the real SDK `host()`; this is an **adapter proof**, not direct SDK support for
`module:app`. No tests establish QGIS import-tracker reload or all module import
edge cases. A production app resolver must preserve import tracking and error
handling for check, test, dev, build, `classFactory`, CLI bridge generation and
tooling project discovery. Scaffolds and web schema generation need explicit
changes if they emit app forms; keep existing class targets and generated
clients compatible.

## Headless native proof (follow-up)

On Linux x86-64, QGIS 4.2.3-Belém do Pará, Qt 6.11.2 and Python 3.14.8,
`test_plugin_app_spike_native.py` runs two prototype apps lowered to classes
through the real SDK `host()` in an offscreen `QgsApplication`. A fake `iface`
records placement while a real `QMainWindow`, `QAction`, `QDialog`,
`QgsMessageBar`, native context and Processing registry are used. The test
checks toolbar/menu/shortcut setup, triggered actions on the Qt application
thread, dialogs, two providers, collision refusal/cleanup, independent unload,
and restart. The registered providers are empty; algorithm execution is not
proved. The test does not install ZIPs, start QGIS Desktop, edit code through
QGIS reload, test WebEngine or qualify Windows/macOS.

## Expression functions and future scope

TASK-128 explores a possible `app.expression_function` only after its ownership,
collision and thread model is decided. Host-supplied read-only SDK
`ExpressionContext` would be per-evaluation and excluded from expression
arguments, schema and bridge inputs; it must not expose raw PyQGIS or mutable
`PluginContext` to authors. Define typed feature/geometry/variable access,
null and lifetime handling, referenced-column/geometry metadata, cleanup,
collision rollback, reentrancy and native thread safety first. Registration is
not implemented here, no bridge or release target is promised, and this does
not move the 0.9.0 job work. Whether expression functions appear in `describe`
and diagnostic JSON is a TASK-128 decision; they should not become bridge
operations merely by being describable.

## Implementation slices and 0.8.0 qualification gates

1. Agree the public app/group and injection surface; resolve ID, duplicate,
   snapshot, signature, annotation and error semantics. Keep class projects
   unchanged and add no FastAPI/Pydantic requirement.
2. Implement registry/lowering or a native app runtime, unified `describe` and
   schema parity for actions, streams, UI metadata and groups. Test conflicts,
   direct fake contexts, explicit overrides, import errors, deterministic
   serialization, lifecycle rollback, failed/duplicate includes and separate
   plugin owners. Test both decorator orders, async/generators if supported, and
   collisions between names and IDs.
3. Qualify project resolver, check/test/dev/build, scaffold, bridge generation,
   classFactory and dev reload with app and legacy fixtures; compare full bridge
   descriptions, fingerprints and generated TypeScript for equivalent projects.
4. Run native QGIS tests: two built plugins concurrently, startup failure and
   rollback, provider and surface registration, stacked actions, GUI-thread
   behavior, streams, unload/reload, and verify one plugin cannot unregister or
   invoke the other's owned resources. Exercise real Desktop with a display and
   Windows/macOS QGIS when those hosts are available; headless/fake tests do not
   establish those claims.
5. Update migration and release notes and TASK-78. Its no-bridge-release premise
   is a hypothesis to verify, not an assumption. If parity fails, version and
   qualify the bridge or postpone the feature. Explicit approval is required
   for implementation/release; the spike neither bumps versions nor releases.

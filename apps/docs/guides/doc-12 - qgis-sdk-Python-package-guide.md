---
id: doc-12
title: qgis-sdk Python package guide
type: guide
created_date: '2026-10-24 21:20'
---
# qgis-sdk Python package guide

The reference for the `qgis-sdk` Python package: the declarations, the pure
contract layer, the scoped runtime, the Desktop host, forms and native
surfaces, Processing, the bridge host side, networking, scoped jobs, the
project scaffold and the `qgis-sdk` command, with the migration notes of every
release at the end. The documentation site at
[archont561.github.io/qgis-sdk](https://archont561.github.io/qgis-sdk/)
renders it one page per section. Status at the time of writing: Python `0.7.0`
(`python-v0.7.0`: `qgis-sdk`, `qgis-sdk-runtime` and `qgis-sdk-tools` on PyPI
and prefix.dev) released as a triple with the bridge `@archont561/qgis-sdk`
`0.5.0` (`ts-v0.5.0`) and the web components `@archont561/qgis-sdk-ui`
`0.1.0` (`ui-v0.1.0`), all tagged on one merge commit; the previous pair was
`0.6.0` + `0.4.0`.

Companion guides: [doc-13](doc-13%20-%20qgis-sdk-TypeScript-package-guide.md)
(TypeScript bridge) and [doc-14](doc-14%20-%20Workspace-development-qualification-harnesses-and-evidence.md)
(workspace tooling, harnesses and qualification evidence).

## Installation

Install from [PyPI](https://pypi.org/project/qgis-sdk/) or from the [`prefix.dev` Conda channel (`archont561/archont561`)](https://prefix.dev/channels/archont561/packages/qgis-sdk-python):

```sh
pip install qgis-sdk
# or in a Pixi workspace via the prefix.dev Conda channel:
pixi add --channel https://prefix.dev/archont561/archont561 qgis-sdk
```

Since the 0.5.0 development line the Python side is three distributions
([decision-35](../../../backlog/decisions/decision-35%20-%20Split-the-Python-SDK-into-a-runtime-a-tools-package-and-a-meta-kit-behind-one-contract.md),
[decision-36](../../../backlog/decisions/decision-36%20-%20Cut-the-three-Python-distributions-before-the-contract-freeze.md)):
`qgis-sdk` is a code-free kit that pins `qgis-sdk-runtime` (`import qgis_sdk`,
stdlib-only, what a plugin imports and `qgis-sdk build` vendors) and
`qgis-sdk-tools` (`import qgis_sdk_tools`, the `qgis-sdk` command, Typer) at
the version it was released with. `pip install qgis-sdk` keeps meaning "the
developer kit"; a QGIS console user installs `qgis-sdk-runtime` by name; a
plugin installs nothing because the ZIP carries its own copy.

## Supported targets

### What the matrix says

Where the kit is qualified is stated once, in `qgis_sdk_tools.targets`
and rendered here from that source; the test
`test_targets.py::test_the_python_guide_renders_the_same_matrix` fails when
the table and the module disagree, and `test_targets_native.py` fails when
the host the native suite runs on stops being a qualified row. `qualified`
means the workspace demonstrated the kit on that combination and the record
names how; `unqualified` means the combination is reachable but not
demonstrated, with the blocker named. Rows match on the series a user reads
off their installation (QGIS `4.2`, Qt `6.11`, Chromium `140`), not on a
patch level; `-` means the component is not on the target, and a row without
QGIS is the QGIS-free kit (`pip install`, scaffold, check, bridge generation).
`qgis-sdk targets` prints the same table and where the current host stands in
it; `qgis-sdk targets --json` is the machine-readable form.

<!-- support-matrix:begin -->
| OS | Arch | Python | QGIS | Qt | Chromium | Status | Evidence |
| :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- |
| linux | x86-64 | 3.14 | 4.2 | 6.11 | 140 | qualified | the locked Pixi environment (QGIS 4.2.3, Qt 6.11.2, Chromium 140, CPython 3.14): native suite, headless Desktop harnesses, the reference plugin through the toolchain and the release gate (workspace guide) |
| linux | x86-64 | 3.11 | - | - | - | qualified | the QGIS-free suite on CPython 3.11.2, the `requires-python` floor |
| windows | x86-64 | 3.14 | - | - | - | qualified | ci.yml `cross-platform (windows-latest)`: `pip install` of the kit and the QGIS-free suite |
| macos | arm64 | 3.14 | - | - | - | qualified | ci.yml `cross-platform (macos-latest)`: `pip install` of the kit and the QGIS-free suite |
| windows | x86-64 | 3.14 | 4.2 | - | - | unqualified | no Windows QGIS 4 installation in CI or the sandbox |
| macos | arm64 | 3.14 | 4.2 | - | - | unqualified | no macOS QGIS 4 installation in CI or the sandbox |
<!-- support-matrix:end -->

### The bridge pair

The TypeScript bridge is qualified as a pair with a Python release, never
alone: `@archont561/qgis-sdk` 0.4.0 ran inside a real `QWebEngineView` against
`qgis-sdk` 0.6.0 on the Linux row above, 0.3.0 against 0.5.0 before it
(`tests/test_reference_example_native.py`, the workspace bridge, contract
version 1 on both sides - `HOST_SCHEMA_VERSION` and
`PLUGIN_DESCRIPTION_SCHEMA_VERSION`, what `VERSION002` checks a generated
client against). A plugin author pinning that pair may assume what the matrix
says; the package numbers are otherwise independent
([decision-25](../../../backlog/decisions/decision-25%20-%20Version-each-package-independently-behind-a-shared-contract-version.md)).

### Where the evidence is recorded

The release workflow records this table in its job summary next to the
metadata and build checks it runs, so a release says on which targets its
qualification holds. The
detailed per-requirement evidence stays in [doc-14](doc-14%20-%20Workspace-development-qualification-harnesses-and-evidence.md#headless-qgis-and-webengine-qualification).

The companion TypeScript package [`@archont561/qgis-sdk`](https://www.npmjs.com/package/@archont561/qgis-sdk) is published on npm and [GitHub Packages](https://github.com/Archont561/qgis-sdk/pkgs/npm/qgis-sdk); the bridge guide is [doc-13](doc-13%20-%20qgis-sdk-TypeScript-package-guide.md).

## Declarations

Declare an application and register ordinary functions. The first argument is
an injected `PluginContext`; it is not part of the request sent over the bridge.
Plugin `id` and `title` are optional; actions and streams require both.

```python
from dataclasses import dataclass
from qgis_sdk import QgisSdkPlugin, describe
from qgis_sdk.core import PluginContext

@dataclass
class RunRequest:
    count: int
    label: str | None = None

reports = QgisSdkPlugin(id="example.reports")

@reports.action(id="run", title="Run")
def run(ctx: PluginContext, request: RunRequest) -> int:
    return request.count

app = QgisSdkPlugin(id="example.tools", title="Example tools")
app.include(reports)

print(describe(app).to_json())   # app.describe() uses the same implementation
print(describe(run).bindings)   # run.describe() also works
```

`app.include(reports)` snapshots the child's actions, streams, surfaces and
providers into the parent. It creates no child runtime: the parent's identity,
context, grants, lifecycle and authority apply to all included declarations.
The child must not have a `context_factory`. IDs are not prefixed. Duplicate
action/stream IDs or handler names, surface IDs, provider IDs, repeated
inclusion (including a shared descendant), and cycles are rejected without
partially changing the parent. Later additions to a child are not included in
an earlier snapshot; functions and their decorator metadata are shared objects.
No global current plugin or module scanning is used. Registration keeps each
function intact so it can also be called directly with a fake context.

Use `@app.stream(id=..., title=..., events=...)` for generator streams. Actions
and streams share an ID namespace. Provider algorithms and jobs retain their
own default ID and title rules.

### Ids and titles default from the name

`QgisSdkPlugin()` derives its ID from the declaring module's qualified name;
the title is derived from the last component (or the package component when
the last component is `plugin`). Explicit `id=` and `title=` override these
defaults independently. Pass an explicit ID in `__main__` or when the module
name is unavailable. Moving or renaming a module changes the generated ID,
and multiple instances in one module get the same default ID. Use explicit,
stable IDs for published plugins and to distinguish same-module instances.
Actions and streams still require explicit IDs and titles.

### What does `describe_plugin` do, and not do?

`describe_plugin` was removed with the class API; use the unified `describe`.
`describe(app)`, `app.describe()`, `describe(run)` and `run.describe()` use the
same dispatcher. It also describes jobs, algorithms, providers, surfaces and UI
handlers. A plugin description exposes registered surfaces and bindings; an
action description exposes its stacked toolbar/menu/shortcut bindings and UI
wires. These are local metadata, not additions to the bridge JSON contract.
Wires execute on handlers declared on a `Dialog` or `Dock`; attaching `@on`
to an application action records its metadata but does not automatically
connect the action to a surface. Use a surface handler and call
`self.ctx.actions.<id>(...)` to dispatch an application action.

Description does not invoke handlers or dataclass default factories. Annotation
resolution can execute forward references: inspect **trusted Python code only**.
Put DTOs in module scope so postponed annotations resolve. An author-defined
`describe` attribute is not overwritten; registration fails rather than replacing it.

### Version 1 description contract

The public `PluginDescription` contains `schema_version: 1`, `id`, `title`, and
an action tuple. Each `ActionDescription` contains `id`, `title`, `handler` (a
Python binding name), `request`, and `result`. `to_dict()` returns an independent
JSON-compatible value; `to_json()` sorts keys and uses compact JSON. Actions sort
by ID, not discovery order. The schema version is independent of package versions
and future bridge protocol versions. Consumers must reject unsupported versions;
no compatibility negotiation or reader-extension policy is implemented here.

#### Which schema subset is supported?

Request/result schemas use the JSON Schema 2020-12 keyword subset `type`,
`properties`, `required`, `additionalProperties`, `anyOf`, `enum`, `items`,
`minimum`, and `maximum`. Supported annotations are `str`, `bool`, `float`, `int`,
`None`, parameterized `list[T]`, unions (including nullable unions), JSON-valued
`Literal` (strings, safe integers, booleans, null), and nonrecursive dataclasses.
Integers are bounded to ±9007199254740991, consistent with ADR-22. `Any`, arbitrary
host/native objects, mappings, recursive DTOs, and `Annotated` metadata (including
backend-specific constraints in the test-only spike sample) are rejected rather
than silently weakened. No validation dependency or runtime backend is selected.

#### What makes a valid action?

Each action must be a synchronous function whose first positional parameter is
annotated `PluginContext`, followed by annotated inputs and an explicit result
annotation (`-> None` for no result). Inputs may be positional-or-keyword or
keyword-only; variadic and positional-only inputs are unsupported. Generator
streams use the same injected context and require declared event types. The
context is omitted from the request schema. Duplicate IDs are errors.

#### Defaults, nullability and unknown properties

A default makes an input omittable, not nullable; only a union with `None` makes
it nullable. Dataclass request fields without defaults are required; result
writer schemas require **all** dataclass fields, including defaulted fields.
Defaults are not executed, validated, or emitted as schema values. Unknown object
properties are disallowed. These are structural writer/request schemas, not an
extensible result-reader policy or a serializer for result instances. Runtime
validation must additionally reject nonfinite numbers and implement ADR-22's
explicit integer normalization; JSON Schema alone is not a Python validator.

#### What fails, and how

Invalid declarations raise `QgisSdkDeclarationError` (a `QgisSdkError` with code
`invalid_declaration`), naming the action/binding/field where applicable. IDs must
match `[a-zA-Z][a-zA-Z0-9_.-]*` and titles must be nonblank strings. The public API
is experimental 0.x. Runtime dispatch, lifecycle hooks, native UI declarations,
bridge routing and TypeScript generation use the resulting declarations.

## Pure contract layer

The public `qgis_sdk.models`, `qgis_sdk.services`, and `qgis_sdk.core` modules import without QGIS or Qt. Dependencies flow **models ← services ← core**; the pure layers do not import native adapters, bridge transports, testing fakes, or CLI tools. These are contracts, not a runnable plugin or a replacement for PyQGIS.

| Module | Current contract |
| :-- | :-- |
| `declarations` | `QgisSdkPlugin` and the shared `describe(target)` dispatcher; plugin, algorithm, job and provider descriptions satisfy `Description` (`id`, `title`, `schema_version`, `to_dict()`, canonical `to_json()`); decorated targets gain `describe()` without wrapping |
| `models` | `QgisSdkError`, `QgisSdkScopeClosedError`, `QgisSdkUnsupportedCapabilityError`, `QgisSdkOptionalDependencyError`, `QgisSdkValidationIssue`, and safe `QgisSdkContractValidationError` metadata; the algorithm requests `BufferRequest` and `CentroidRequest` with their refusals `QgisSdkAlgorithmRejectedError` and `QgisSdkAlgorithmCancelledError`; the parameter aliases `LayerInput`, `CrsInput`, `Metres`, `FileInput(filters=)`, `DirectoryInput()`, `FieldInput(of=)`, `Range(min, max)`, `Colour()` over the markers `LayerParameter`, `CrsParameter`, `MetresParameter`, `FileParameter`, `DirectoryParameter`, `FieldParameter`, `RangeParameter`, `ColourParameter`, the registry `parameter_kinds()`/`ParameterKind`, and the branded `FileRef` with its `FILE_REF` schema |
| `services` | Structural `Notifications`, `ViewControl`, `Progress`, `Cancellation`, `DesktopAccess`, `Layers`, `Project`, `Settings`, `Styles`, `Algorithms`, `Workers` and `Processing` protocols; implementations are supplied by the host or by tests |
| `core` | `PluginContext`, `UiContext`, `AlgorithmContext`, `JobContext`, `WorkerContext`, `ResourceScope`, `PluginRuntime`, and lifecycle errors |
| `algorithms` | `describe_algorithm`, `invoke` and `AlgorithmDescription` for functions declared with `@provider.algorithm`, plus `parameter_kind` - which host parameter an input annotation deserves; input and result schemas come from the same generator the plugin declarations use |
| `processing` | The generated Processing registry (decision-64): `native`, `qgis`, `gdal`, `p3d`, `pdal` modules of `TypedDict` shapes, request classes and `REGISTRY`; `codegen` (the pure emitters), `snapshot` (`core_catalogue()`), `runs` (request coercion and destination allocation); the models (`AlgorithmInfo`, `AlgorithmRun`, `RunResult`, `validate_parameters`) live in `qgis_sdk.models` |
| `jobs` | `@job`, `describe_job`, `JobService`, `JobHandle`, `JobStatus`, and `JobSubscription` - scoped local jobs over the step scheduler, with typed handles and owner-bound delivery |
| `providers` | `Provider` and `@provider.algorithm`, `ProviderDescription`, and `declared_providers` - providers explicitly added to an application |
| `ui` | `form_fields` and `coerce_values` - the QGIS-free rules that turn a declared action into renderable fields and submitted values back into Python types |

SDK-defined Python exceptions always begin with `QgisSdk` (including the base and internal subclasses). No unprefixed aliases are exported; their `code` strings remain independent of class names. Built-in exceptions such as `ExceptionGroup` retain their standard names.

Plugin authors receive explicit, typed capabilities rather than retrieving services from a global registry. For example, a pure test or runtime can supply a fake notification service:

```python
from qgis_sdk.core import PluginContext, ResourceScope
from qgis_sdk.models import QgisSdkUnsupportedCapabilityError


class Messages:
    def info(self, message: str) -> None:
        print(message)


plugin_scope = ResourceScope()  # the runtime owns and eventually closes it
ctx = PluginContext(notifications=Messages(), scope=plugin_scope)
ctx.notifications.info("ready")
try:
    ctx.desktop
except QgisSdkUnsupportedCapabilityError as error:
    assert error.code == "unsupported_capability"
    assert error.capability == "desktop"
```

`PluginContext` is plugin-lifetime state. Beside `notifications` and `scope` it
carries the curated services as *capabilities* — `layers`, `project`,
`settings`, `styles`, `algorithms`, `workers`, plus `desktop` and `network` —
the very Protocols the web-view host surface wraps (decision-27, decision-32),
and `processing`, the host-side registry the runtime advertises the plugin's
`providers` with (decision-42).
A capability is a plain attribute typed as the service: reading one the host
did not supply raises `QgisSdkUnsupportedCapabilityError(capability=<name>)`
instead of handing back `None`, and every one of them refuses on a closed
scope ([decision-39](../../../backlog/decisions/decision-39%20-%20Expose-optional-services-as-capability-attributes-that-refuse-by-name.md)).
`ctx.has("workers")` and `ctx.capabilities` are the probes for code that must
ask rather than use; a typo in `has()` is a `ValueError`, not a `False`. A
handler therefore writes `ctx.project.layer_ids()` and a page calls
`host.project.layerIds()`, and when the host built the bridge with
`HostServices.from_context(ctx)` both read the same object:

```python
from qgis_sdk.bridge.host import HostServices, register_host_operations

services = HostServices.from_context(ctx)      # same layers/project/settings/styles
register_host_operations(dispatcher, services) # instances the plugin's handlers use
```

`from_context` takes the transport under `ctx.network` (`NetworkClient.transport`)
for `network.fetch` unless a `network=` is passed, and an `authority=` for file
refs and grants. Inside QGIS, `qgis_sdk.adapters.qgis.native_plugin_context(scope,
settings_prefix=..., iface=iface)` assembles every PyQGIS-backed service into one
context owned by that scope; `host()`'s `default_context` calls it whenever a
`QgsApplication` is running and falls back to a notifications-only context in a
bare interpreter, which is what the scaffold's starter tests exercise.

Create a child scope for each `UiContext`; `view.request_close()` requests closure but does not synchronously dispose the view. Give every `AlgorithmContext`, `JobContext` and `WorkerContext` a fresh child scope plus execution-specific `Progress` and read-only `Cancellation` services. Jobs submitted from a view are view-owned by default; plugin-owned work requires an explicit plugin child scope. `JobContext` also carries the optional `workers` and `network` capabilities, refused by name on access when the host lacks them; the job runtime itself lives in `qgis_sdk.jobs` (see [Scoped jobs](#scoped-jobs)). `WorkerContext` is different by design: it is what a `@job` body receives on its worker, so it carries `progress` and `cancellation` and refuses every driving-thread capability by name (decision-65).

The runtime owns the scopes: `scope.on_close(cleanup)` registers synchronous cleanup, `scope.child()` creates an owned scope, and `scope.close()` closes children before local callbacks (last registered first). Closing is idempotent. A child closed on its own stops being owned by its parent. New registrations/children after closure raise `QgisSdkScopeClosedError` (`code="scope_closed"`); reading a capability such as `ctx.desktop` also rejects a disposed scope. If cleanup fails, remaining children and callbacks still run and the failures are raised as an `ExceptionGroup`. Scope closure is **not** proof that an in-flight task stopped; adapters must request cancellation, detach callbacks and wait for safe completion where needed. The scope does not make services thread-safe or automatically revoke references to them.

Only a Desktop runtime may inject `DesktopAccess`. Its `iface` is deliberately typed as opaque `object`: consumers must opt in via `ctx.desktop`, and must not serialize it or expose it through a bridge or worker context. Pure/standalone runtimes leave it absent and raise `QgisSdkUnsupportedCapabilityError` rather than silently fabricating a native capability. Both `QgisSdkScopeClosedError` and `QgisSdkUnsupportedCapabilityError` extend `QgisSdkError`; `code` is available to downstream adapters, but structured bridge errors are not implemented here.

Pure tests check declared import direction throughout the three layers and import the public modules in a fresh subprocess that rejects native imports. This is not a security sandbox or a full dynamic-import/side-effect analyzer; the CLI static checker and real QGIS adapters are separate backlog work.

The package root exports nothing beyond the declarations API, which is what `tests/test_init.py` pins:

```python
import qgis_sdk

print(qgis_sdk.__all__)
# Includes 'QgisSdkPlugin', 'describe', 'toolbar', 'menu' and 'shortcut'.
```

Importing the package with native modules forbidden is the real wiring check, so a placeholder API is no longer needed to prove it.

## Scoped plugin runtime

`PluginRuntime` owns one application for its lifetime. Each runtime has an
independent context and resource scope, even when two runtimes use the same app:

```python
from qgis_sdk import QgisSdkPlugin
from qgis_sdk.core import PluginContext, PluginRuntime, ResourceScope

app = QgisSdkPlugin(id="example.tools", title="Example tools")

@app.action(id="run", title="Run")
def run(ctx: PluginContext, value: int) -> int:
    return value

context = PluginContext(notifications=..., scope=ResourceScope())
runtime = PluginRuntime(app, context)
runtime.start()
runtime.actions["run"](3)
runtime.unload()
```

The host supplies `PluginContext`; it is injected into each handler and never
exposed as a bridge input. Register scope cleanup through `ctx.scope` and use
explicit fake contexts to test handlers directly. The runtime uses a private
lowering implementation; authors do not construct a plugin class.

`PluginRuntimeState` is `new`, `running`, `stopped` or `failed`. `start()` is
valid only from `new`; starting twice or restarting a stopped runtime raises
`QgisSdkPluginLifecycleError`. `unload()` is valid from `new` and `running`,
closes the context scope and drops the instance and action bindings. Repeated
`unload()` calls are no-ops, including after a failed startup.

Ownership stays with the existing `ResourceScope`: actions, signal connections,
dialogs/docks and work register cleanup through `ctx.scope`. A partial startup
failure closes that scope, releases resources in reverse registration order,
sets the runtime to `failed` and re-raises the original author error; a cleanup
failure is attached as its `__cause__`. If cleanup fails during `unload`, the
runtime still reaches `stopped`, all remaining callbacks run, and the failures
are raised as an `ExceptionGroup`. Scope closure is not proof that in-flight work
stopped, and the runtime does not create Qt actions, dialogs, docks or jobs.

**Quiescing before a replacement** (decision-15, decision-21). A development
host that wants to swap the revision in place asks first:
`runtime.quiesce()` returns a `QuiesceOutcome`; `safe_to_replace` means
everything the plugin owns reached a safe point, `refused` names the
`blockers`. The answer comes from the scope: owners that hold work register
a check with `scope.on_quiesce(check, resume=...)`, and `scope.quiesce()`
asks children first (a view's work before the plugin's), then every
registered owner, and combines all blockers so the host can report them at
once. A root `JobService` registers itself on the scope it is built on, so
jobs are cancelled and ticked up to the bound and anything still waiting on
a worker handoff is named by its handle id (`job sum#1 is waiting on an
unresolved worker handoff`). A refusal leaves the runtime `running`;
`runtime.resume()` (`scope.resume()`) lets every owner accept work again.
A runtime that is not running refuses with `the plugin is not running
(state new)`. Nothing here kills a thread or closes a scope: the host
decides whether to `unload()`.

### Exporting a layer safely

`ctx.layers.export_vector(layer_id, destination, overwrite=False)` writes a
GeoJSON or GeoPackage export. It refuses the source dataset itself, including
relative paths, symbolic links, hard links and the containing GeoPackage, even
when `overwrite=True`. If the source is missing, changed or cannot be identified,
the export is refused. The native adapter currently verifies direct local OGR
GeoJSON, GeoPackage and ESRI Shapefile sources; indirect sources such as VRT and
other unverified providers are refused rather than guessed. Opening those sources
is unchanged. Choose a verified local source before exporting. If a source
symlink is retargeted or a relative source resolves differently after the working
directory changes, reopen the intended dataset (preferably by absolute path)
before exporting.

The output is staged beside the destination and the source identity is checked
again before commit. With no overwrite permission, publication requires
filesystem hard-link support and atomically refuses an output created during the
write. With `overwrite=True`, a different existing file may be replaced. Keep
source and destination paths stable during an export: the checks cannot prevent
another process changing the filesystem between the final check and commit.
These guarantees apply to `Layers.export_vector`, not arbitrary Processing output
destinations (see the separate Processing safety limitations).

## Desktop host: `host()` and the project manifest

Since 0.6.0 a plugin project carries no `metadata.txt`, no `classFactory`
and no view module
([decision-43](../../../backlog/decisions/decision-43%20-%20Generate-the-QGIS-host-artifacts-in-build-and-dev-instead-of-scaffolding-them.md)).
`pyproject.toml` names the application and the tools derive what QGIS
needs from it:

```toml
[project]
name = "field-tools"
version = "0.1.0"
description = "Field Tools: a minimal qgis-sdk plugin."
authors = [{ name = "Ada", email = "ada@example.test" }]
dependencies = ["qgis-sdk-runtime>=0.6,<0.7"]   # the runtime `build` resolves

[tool.qgis-sdk]
plugin = "field_tools.plugin:app"  # the application QGIS runs
qgis-minimum-version = "4.0"
experimental = true
# qgis-prefix = "/path/to/qgis"                 # where `test`/`dev` find QGIS

[tool.qgis-sdk.metadata]                        # optional, passed through
homepage = "https://example.org/field-tools"

[tool.qgis-sdk.web]                             # optional: the page in web/
placement = "dock"                              # dock | dialog
grants = ["layers.read", "project.layer_ids"]   # host grants or operation ids
```

`qgis_sdk.adapters.desktop.host(spec, *, placement=None, grants=())` is the
runtime half - the `classFactory` QGIS calls:

```python
from qgis_sdk.adapters.desktop import host

classFactory = host("field_tools.plugin:app", placement="dock")
```

It resolves the application (a typo fails by name, with `QgisSdkHostError`),
validates its declarations, and returns a factory. The
`DesktopHost` it makes starts the runtime from `initGui()`, registers the
application's providers with Processing, and unloads everything from `unload()`
(safe to repeat). The context comes from one of two places: a
`context_factory(iface)` attribute on the application when the author
wants to assemble services; otherwise `default_context`, which is
`native_plugin_context(iface, ...)` whenever a `QgsApplication` is running
and a bare `PluginContext` (messages dropped, settings scoped by plugin id)
when none is - so the same factory runs the starter tests without QGIS, and
`ctx.desktop` is refused by name there instead of inventing a host.

With a `placement`, `initGui()` adds one toolbar button and `show_view()`
opens the built page from `<package>/web/index.html` in a `QWebEngineView`
as a `QDockWidget` or `QDialog` (view id `<plugin id>.main`), with a
`Dispatcher` over the running runtime and the curated host operations the
`grants` select - a grant such as `layers.read` selects every operation that
needs it, an operation id selects one (`granted_operations`, then
`register_host_operations(only=...)`): no grants, no host operation on the
channel at all. `qgis-sdk dev` serves the same page from
Vite when it has started one (`QGIS_SDK_DEV_SERVER`). `host.view` is the
widget while it is open, `None` after `unload()`.

`create_class_factory(app, context_factory=...)` and
`DesktopLifecycleAdapter` remain for a plugin that supplies its own entry
point; `host()` is built on them. Neither imports Qt at module level; the
adapter never serialises `iface`.

The headless harnesses and the real-Desktop evidence for this adapter are in [doc-14](doc-14%20-%20Workspace-development-qualification-harnesses-and-evidence.md).

## Forms: an action's inputs as a window

A declared action already describes its inputs as JSON Schema and its handler
as a *binding name*, never a callable, so nothing in the description can carry
Python code. `qgis_sdk.ui.Form` turns that description into the catalogue's
input components and submits them through the view's `ctx.actions`; the
plugin never imports Qt for it:

```python
from qgis_sdk import menu
from qgis_sdk.ui import Button, Column, Dialog, Form


@menu("Plugins/Demo")
class BufferDialog(Dialog):
    def build(self):
        self.form = Form.for_action(self.ctx, "buffer", initial=self.initial)
        run = Button("run", "Buffer")
        run.clicked(self.run)
        return Column("buffer_dialog", [self.form, run])

    def run(self) -> None:
        output = self.form.submit()          # coerced, through ctx.actions
        self.ctx.notifications.success(f"Buffered into {output.name}")
        self.ctx.view.request_close()
```

Three constructors build the same tree. `Form.for_action(ctx, action_id,
initial=)` reads the action's description from `ctx.actions.describe(...)`,
builds one input per field, attaches the form to the context and applies
`initial` (an unknown name is refused). `Form.from_schema(schema |
ActionDescription, action_id=, initial=)` does the same from a request schema
- a page's generated one, say - without a context; attach it yourself.
`Form(fields=[Text("name", required=True), ...], action_id=)` takes the inputs
an author placed by hand. The field-to-input rule is `qgis_sdk.ui.input_for`
over the kept `form_fields`/`schema_fields` rule: text -> `Text`, integer ->
`Number(integer=True)`, number -> `Number`, metres -> `Distance`, boolean ->
`Toggle`, layer -> `LayerPicker`, crs -> `CrsPicker`, choice -> `Choice`,
field -> `FieldPicker(of=<the sibling layer input>)` (a `FieldInput(of=)`
whose layer is not in the same schema is refused), range -> `Number(range=)`,
colour -> `Colour`, file -> `FileInput(filters=)`, directory ->
`DirectoryInput`. Required fields (`spec.required`) are marked on the input
and `*` on the row label.

A form is a `Component`: `fields` (display order), `field(name)`, `values()`
(every field's model value), `set_values(mapping)` (an unknown name refused
before any change), `changed(listener)` called with `(name, value)` after any
field changes, `snapshot()` with its `fields`, `attach(ctx)`/`mount()`/
`dispose()`. `submit()` refuses an empty required field by name first
(`QgisSdkFormError`), then calls `ctx.actions.call(action_id, **values)` -
the same coercion a page or a button goes through - leaving out fields whose
value is `None` so the handler's defaults apply; a form built without an
action, or not attached, refuses with `QgisSdkUiError`. Mounted, a form is a
`QWidget` with a `QFormLayout` of labelled rows and *no buttons*: place a
`Button` (`buttons/<name>`, `clicked(listener)`, `click()`) next to it inside
a `Column(name, [...])`, the one container of this slice; `Column.find(name)`
walks the tree. The widget's `objectName` is the form's `name` (`form` by
default), its fields' `form/<field>`.

Under the fakes a form is state: build the surface, assign `ctx` and
`initial`, call `build()`, `set_values`, `click()` the button and assert on
`RecordingNotifications.records` and `FakeViewControl.close_requests` - the
example's `test_the_buffer_dialog_is_the_buffer_action_as_a_form` does
exactly that. `coerce_values` stays strict in the other direction: `"3"`
becomes `3` for an integer field, `"three"` is refused with the field name and
the expected type, and the submitted value is never echoed because a field can
hold a path or a credential.

The escape hatch is not a second API: `PluginRuntime.actions` is keyed by
action id and holds ordinary bound methods, so conventional PyQt code can
build its own dialog and call `self.ctx.actions.<id>(...)` with the same
validation - name every interactive widget (`UI001`), because the snapshots
agents read and the tests that drive a window find widgets by `objectName`.

## Desktop bindings and native surfaces

A plugin reaches QGIS Desktop through bindings and registered native surfaces.
A binding places an action or surface on the toolbar, under a menu or behind a
shortcut; a surface is a `Dialog` or `Dock` subclass. `@app.surface` registers
and returns the original class, so it stacks with bindings in either order.
For a class declared in another module, `app.add_surface(TheSurface)` also works.

```python
from qgis_sdk import QgisSdkPlugin, menu, shortcut, toolbar
from qgis_sdk.core import PluginContext
from qgis_sdk.ui import Button, Dialog, Dock, on

app = QgisSdkPlugin(id="field_tools", title="Field tools")

@app.surface
@menu("Plugins/Field tools")
class BufferDialog(Dialog):
    title = "Buffer a layer"

    def build(self):
        return Button("buffer", "Buffer 25 m")

    @on("buffer").clicked
    def buffer(self) -> None:
        self.ctx.actions.buffer(layer_id=self.initial["layer_id"], distance=25)

@app.surface
class LayerPanel(Dock, area="left"):
    def build(self): ...

@toolbar(icon="buffer.svg", text="Buffer")
@shortcut("Ctrl+Alt+B")
@app.action(id="open_buffer", title="Open buffer")
def open_buffer(ctx: PluginContext) -> None:
    ctx.ui.open(BufferDialog, initial={"layer_id": ctx.project.layer_ids()[0]})

@app.action(id="buffer", title="Buffer")
def buffer(ctx: PluginContext, layer_id: str, distance: float) -> str: ...
```

`@toolbar`, `@menu` and `@shortcut` stack with `@app.action` in either order
or apply to a surface class. `describe_bindings(app)` and
`describe(app).bindings` report placements and registered surfaces; an action's
own `describe()` reports its stacked bindings. Bindings are not serialized into
the bridge contract. Icon paths are relative to the package's `icons/` directory.

**The trigger rule.** A placed action for a *surface* opens it. A placed
action for an *action* calls the handler with no arguments; an action that
takes inputs cannot be run from a button, so `qgis-sdk check` reports it as
`UI003` and the Desktop warns in the message bar instead of guessing. Give it
a surface that collects the inputs and calls `self.ctx.actions.<id>(...)`, as
`BufferDialog` does above. A handler that raises a `QgisSdkError` is reported
in the bar and re-raised; one that returns a `JobHandle` (an action that
submits a job and returns its handle) gets a progress widget in the bar and a
"finished"/"failed" message when the job settles - the handler itself stays on
the GUI thread, so offload the work with a `@job` and return the handle rather
than blocking the button.

**Lifetimes.** A `Dialog` is a fresh instance per opening: the host
constructs it, binds `self.ctx` (a `UiContext`) and `self.initial` on the
instance, calls `build()`, shows the window parented to the QGIS main window,
and on close calls `on_close()`, closes the view's scope (jobs, timers and
network it owned) and deletes the widget. A `Dock` is one instance per
running plugin, created lazily, placed with `iface.addDockWidget` in its
`area`; its binding is a checkable toggle, its visibility is written to
`ctx.settings` under `ui.<surface id>.visible` and restored on the next start,
and `unload` removes it. `self.ctx.view.request_close()` closes a dialog or
hides a dock.

**Surface-first: services without actions.** A plugin can consist entirely of
registered surfaces; an action is not needed just to open a dialog or use an
SDK service. A view's `UiContext` exposes `algorithms`, `styles`, `desktop`
and `ui` when its host supplies them, in addition to `layers`, `project`,
`files`, `settings`, `network` and `log`. `ctx.ui.open(...)` opens another
registered surface, and `ctx.desktop.iface` is the native QGIS escape hatch,
not a portable or sandboxed interface. For example:

```python
from qgis_sdk import QgisSdkPlugin, menu
from qgis_sdk.ui import Button, Dialog, Text, on

app = QgisSdkPlugin(id="field_tools", title="Field tools")

@app.surface
class Details(Dialog):
    algorithm = Text()

@app.surface
@menu("Plugins/Field tools")
class Tools(Dialog):
    inspect = Button(text="Inspect buffer")

    @on(inspect).clicked
    def show_details(self) -> None:
        algorithm = self.ctx.algorithms.describe("native:buffer")
        self.ctx.ui.open(Details, initial={"algorithm": algorithm.id})
```

The Desktop host shares the plugin's service instances with each view, not
copies. `ctx.has(name)` probes availability; reading an absent capability raises
`QgisSdkUnsupportedCapabilityError` and reading through a closed view context
raises `QgisSdkScopeClosedError`. Services retained before the view closes
still have their own plugin-level lifetime: do not use a retained service or
schedule callbacks on behalf of a closed view. Opening a second dialog creates
its own view scope, which does not close just because the first dialog closes.
Surface handlers and direct algorithm calls are synchronous, usually on the GUI
thread; `UiContext` does not automatically offload work. Provider registration
and worker ownership are not exposed by this extension. `fake_ui_context`
accepts the same capabilities as keyword arguments for pure surface tests.

**`ctx.ui.open` and `UiContext.actions`.** From an action,
`ctx.ui.open(Surface, initial={...})` opens a registered surface (an
unlisted class is refused by name); outside QGIS Desktop the `ui` service is
absent and `ctx.ui` raises `QgisSdkUnsupportedCapabilityError` naming it.
Inside a surface, `self.ctx.actions.<id>(**values)` (or
`self.ctx.actions.call("<id>", **values)`) dispatches the plugin's own action
through the same validated path a bridge call takes - unknown ids and fields
refused by name, values coerced with the form rules - with the *view's*
authority: while that action still runs from this view (a plain handler, or
a job whose handle has not settled) a second call from the same view is
refused, so a double-click cannot submit twice. `ctx.actions.ids` and
`ctx.actions.running("<id>")` are the introspection.

**Testing without QGIS.** `qgis_sdk.testing.FakeUi(scope,
app=app)` stands in for the service: `ctx.ui.open(...)` records an
`OpenedSurface` (`surface`, `initial`, `id`) instead of building anything,
and `FakeViewControl` records `request_close`. `qgis-sdk new --ui native`
writes this shape with a passing starter test; `qgis-sdk check` adds `UI002`,
`UI003`, `UI004` and `ICON001` (a `@toolbar` icon that is not a file under
`<package>/icons/`). `build()` may return plain PyQt, one catalogue component
or nothing at all when `ui = "file.ui"` names a Designer form; *Wiring*,
*Containers, feedback, buttons and `Custom`* and *Testing surfaces without
QGIS* below are the rest of the picture.

### Input components

`qgis_sdk.ui` ships the eleven input components of the catalogue
(decision-55 point 3). Each is *state first, widget second*: it holds a
model value without Qt - a layer id, a field name, a CRS authority id, a
`FileRef`, a number, a `str`, a `bool`, a colour string - and `mount()`
builds the QGIS widget that mirrors it. Importing `qgis_sdk.ui` loads no
Qt; the Qt half lives in `qgis_sdk.adapters.qgis.components` and is looked
up by name when a component is mounted.

| Component | Value | Native widget |
|---|---|---|
| `LayerPicker(name, kind="vector"\|"raster"\|"any")` | layer id or `None` | `QgsMapLayerComboBox` (follows the project) |
| `FieldPicker(name, of=<LayerPicker>)` | field name or `None` | `QgsFieldComboBox` (follows `of`) |
| `CrsPicker(name)` | `"EPSG:4326"` or `None` | `QgsProjectionSelectionWidget` |
| `FileInput(name, filters=("*.csv",))` | file `FileRef` or `None` | `QgsFileWidget` |
| `DirectoryInput(name)` | directory `FileRef` or `None` | `QgsFileWidget` (directory mode) |
| `Distance(name)` | `float` metres, 0 or more | `QDoubleSpinBox` with ` m` |
| `Number(name, range=(low, high), step=, integer=)` | `int` for an integral range, else `float` | `QSpinBox`/`QDoubleSpinBox` |
| `Text(name)` | `str` | `QLineEdit` |
| `Toggle(name)` | `bool` | `QCheckBox` |
| `Choice(name, options=(...))` | one of the options (the first by default) | `QComboBox` |
| `Colour(name, alpha=True)` | `#rrggbbaa` (`#rrggbb` when `alpha=False`) | `QgsColorButton` |

Every component has `name` (the handler's parameter name), `label`,
`object_name` (`form/<name>`, set on the widget so a test or an agent
selects it by path), `value()`, `set_value(value)`, `changed(listener)`
returning the unsubscribe, `refresh()`, `snapshot()` (the semantic node of
decision-51: `type`, `name`, `label`, `objectName`, `kind`, `value` and the
component's details such as `minimum`/`maximum`, `options`, `filters`, `of`)
and `spec` (the `FieldSpec` it validates with). `set_value` refuses what a
declared form refuses, with the same words (`QgisSdkFormError` from
`qgis_sdk.ui.coerce_value`), and a refused value changes nothing. Pickers
add `options()` -> `(Option(id, label), ...)`; a `LayerPicker` refuses an id
the project does not hold and a `FieldPicker` a name its layer lacks.

**Attach, then mount.** `component.attach(self.ctx)` binds it to the
surface's `UiContext` (once; a second context is refused): pickers list from
`ctx.project`/`ctx.layers`, `FileInput`/`DirectoryInput` mint through
`ctx.files`, and when the context's scope closes every listener is dropped
and the widget disconnected. `mount(parent=None)` builds the widget and
returns it (`.widget` afterwards; idempotent); without QGIS it refuses by
name. When `build()` returns a component the host attaches and mounts it
for you:

```python
from qgis_sdk.ui import Dialog, LayerPicker


class PickLayer(Dialog):
    def build(self):
        self.layer = LayerPicker("layer")
        self.layer.changed(lambda layer_id: self.ctx.notifications.info(str(layer_id)))
        return self.layer
```

`Input` is the base of the eleven; `Component` above it is what `Button`,
`Column` and `Form` share (`attach` reaches every child, `dispose` disposes
them). Every input accepts `required=`; `Form` sets it from the schema. To
compose components, return a `Column(name, [form, button])` from `build()`
or `mount(parent)` each into a layout of your own.

**Files.** `FileInput.set_path(path)` / `DirectoryInput.set_path(path)` mint
a `FileRef` through `ctx.files` and make it the value - this is what the
native file widget does when the user picks - so a handler receives a ref,
never a path (decision-20), and `ctx.files.resolve(ref)` is how it reaches
the file (see *`ctx.files`* below). `set_value(ref)` accepts a ref `ctx.files`
can resolve and refuses a stranger; `path()` is the resolved path of the
current ref.

**Under the fake.** A pure test attaches a component to a `UiContext` built
over `FakeLayers`/`FakeProject`/`FakeFiles` and never mounts it; the same
contract tests the runtime runs natively (`tests/ui_component_contract.py`)
pass against that state. `LayerPicker.refresh()` re-reads the project under
the fake (natively `QgsMapLayerComboBox` follows the project on its own);
`kind="raster"` lists nothing under the fake until the all-layer-types
service lands. Note the names `FileInput`, `DirectoryInput` and
`Colour` exist twice: as parameter *markers* in `qgis_sdk.models` (what a
handler's signature declares) and as *components* in `qgis_sdk.ui` (what a
surface shows); import the one you mean, or alias.

### Wiring: `@on`, `@subscribe`, `ctx.on`

A surface's methods are connected to its widgets *after* `build()` and
disconnected when the window goes, by the host under QGIS and by
`build_surface` under the fake (decision-55 point 2). Nothing is connected
by hand and nothing is wrapped: the decorators mark the method and add `describe()`, so a
test calls it directly.

```python
from qgis_sdk.ui import Column, Dialog, Distance, LogView, RunButton, StreamEvent, on, subscribe


class Buffer(Dialog):
    def build(self):
        return Column("buffer", [Distance("distance"), RunButton("run", "buffer"), LogView("log")])

    @on("distance").changed            # the component's listener; the value is the argument
    def distance_changed(self, metres: float) -> None: ...

    @on("run").finished                # what the action returned, or its job handle
    def ran(self, result) -> None: ...

    @on("distance", "editingFinished") # any Qt signal of the widget behind the name
    def committed(self) -> None: ...

    @subscribe("progress", layer="roads")   # a plugin @stream, with its request
    def progress(self, event: StreamEvent) -> None: ...
```

**`@on(name).<signal>`** names a component or widget by the `name` it was
built with (`"distance"`, which is `form/distance` on the Qt side; a bare
`objectName` of a hand-built or Designer widget also works) and one of the
catalogue's listener names: `changed`, `clicked`, `toggled`, `edited`,
`selected`, `accepted`, `cancelled`, `finished`. On a component the
listener is used (`Component.changed(...)`, `RunButton.finished(...)`); on
a plain widget the matching Qt signal is (`valueChanged`, `textChanged`,
`toggled`, `clicked`, ...). An unknown listener name is an `AttributeError`
at class creation. **`@on(name, "signal")`** connects a Qt signal by its
own name. Both pass as many positional arguments as the method declares,
so `def go(self)` on a `clicked(bool)` signal is fine. A name `build()` did
not produce, or a widget without that signal, is refused when the surface
opens, naming both; `qgis-sdk check` reports the Designer-file case
statically as `UI002`.

**`@subscribe(stream, **request)`** subscribes the method to one of the
application's `@app.stream` functions for the view's lifetime with the request
validated the way a page's subscribe is (unknown or ill-typed arguments
refused by name). The method receives a `StreamEvent(stream, kind,
payload, echo, terminal)`: `kind` is the declared event kind, `"complete"`
or `"error"`; `echo` is `True` when the event was caused by this view's own
`ctx.actions` call (a synchronous push during the call - a pull iterator
never echoes), so a panel can ignore what it just did. Events reach the
method on the GUI thread only: a push from another thread waits for the
host's pump (every 50 ms while something is pending; nothing runs once the
view's scope closed). **`ctx.on(stream, callback, **request)`** is the
imperative form and returns the `ViewSubscription` (`open`, `pending`,
`dispose()`); `ctx.streams.open` lists the view's live subscriptions. Closing the window closes every subscription and asks a
`PushSource` to `close()`.

**Hooks.** `on_accept()` is what the Accept button of a `HasAcceptCancel`
surface runs (returning `False` keeps the window open); `on_close()` runs
once the window closes, before the view's scope disposes.

### The declarative form: components as class attributes

A surface whose tree does not depend on `ctx` can skip `build()` and the
names altogether. A component assigned to a class attribute takes the
attribute's name; the default `build()` returns the declared components no
other declared component contains (one root as it is, several stacked in a
`Column` named after the class); `@on` accepts the component itself:

```python
from qgis_sdk.ui import Button, Dock, Group, LogView, ResultTable, Row, RunButton, on


class ResultsDock(Dock, area="right"):
    fixture = RunButton(action_id="open_fixture", text="Open the fixture")   # buttons/fixture
    clear = Button(text="Clear")                                             # buttons/clear
    tools = Row([fixture, clear])                                            # tools
    results = ResultTable(columns=[("name", "Layer"), ("crs", "CRS")])       # feedback/results
    log = LogView()                                                          # feedback/log
    log_group = Group([log], label="Log", collapsible=True)                  # log_group

    @on(fixture).finished
    def opened(self, layer) -> None:
        self.results.set_rows([*self.results.rows(), {"name": layer.name, "crs": layer.crs}])

    @on(clear).clicked
    def cleared(self) -> None:
        self.results.set_rows([])
```

The class attributes are prototypes. Every opening gets its own deep copy
of the whole set before `build()` - the host and `build_surface` both do
this - so `self.results` in a method is that window's table, two docks never
share a listener or a widget, and a `RunButton(progress=progress)` on the
instance points at the instance's `JobProgress`. Shared state belongs on
the plugin, not on a component. A `Custom` declared this way needs a
factory (a widget instance cannot be copied; the refusal names the
attribute). Every catalogue class takes its arguments by keyword for this
(`Row([a, b])`, `Group([...], label=)`, `RunButton(action_id=)`,
`Button(text=)`, `ResultTable(columns=)`, `Custom(widget=)`); the
positional `Name("name", ...)` forms are unchanged, and an explicit name
wins over the attribute's. A component without a name refuses to attach or
snapshot and says what to do.

A `Form` takes declared inputs too: `Form([value, note], action_id="ping")`
in the class body keys its fields by name the first time anything asks
(`fields`, `values()`, `attach`) - by then the inputs have their attribute
names - and refuses two of one name then. The form's copy holds the
window's copies of the inputs, and a field's change reaches the window's
form, not the prototype. `Form.for_action` still needs `ctx` and so a
`build()`; `Form.from_schema(schema)` can be declared.

`initial` reaches the declared inputs by name: the default `build()` sets
every declared `Input` (at any depth - inside a declared `Form`, `Group` or
`Row` too) whose name is a key of `self.initial`, and refuses a key no
declared input carries (`PingDialog has no input 'typo'; it has: ...`), the
way `Form.for_action(initial=)` does. An author's `build()` reads
`self.initial` as it pleases, as before.

A snapshot node of a declared component carries `"attribute"`, the class
attribute it came from, next to `"name"` - the two differ only when the
name was given explicitly (`explicit = Button("named")`) - which is what an
agent that reads the snapshot back can address in the source.

`@on(component)` on a component the class does not declare is refused when
the surface opens unless `build()` placed that very object in the tree.
`qgis-sdk check` reads the declarative form as far as the source shows it
(`UI005`): an `@on(attribute)` whose attribute is a string or a number, or a
bare name the class never binds, and a `Custom` declared with a widget
built at class definition (`Custom(widget=QLabel(...))`); a call it cannot
see into (`helper = make_button()`) and a module-level name are left to the
host, and a module-level `NAME = "..."` constant resolves for `UI002`.
Mixing is fine: an author's `build()` sees the copies
(`Column("root", [self.note, ...])`), and `BufferDialog` in the example
keeps `build()` because `Form.for_action` needs `ctx`, while `ResultsDock`
and the scaffold's `PingDialog` are declared.

### Containers, feedback, buttons and `Custom`

The rest of the catalogue (decision-55 point 3), each a `Component` with a
state and a semantic `snapshot()`, mounted as QGIS widgets by the host:

| Component | Holds | Native widget / objectName |
|---|---|---|
| `Row(name, children)` / `Column(name, children)` | children | `QWidget` with `QHBoxLayout`/`QVBoxLayout`, `objectName = name` |
| `Panel(name, children, scrollable=False)` | children | `QWidget`, or a `QScrollArea` around it |
| `Group(name, children, label=, collapsible=False)` | children | `QGroupBox` / `QgsCollapsibleGroupBox` |
| `Tabs(name, children)` | one child per tab, each child's `label` the title; `current()`/`set_current(name)`/`changed` | `QTabWidget` |
| `Button(name, text)` | `clicked(listener)`, `click()` | `QPushButton`, `buttons/<name>` |
| `RunButton(name, action_id, values=, progress=)` | runs the action through `ctx.actions` with `values` (a `Form`, a mapping or a callable); `last`, `finished(listener)` | `QPushButton`, `buttons/<name>` |
| `AcceptCancel(name="dialog_buttons")` | `accepted(listener)`, `cancelled(listener)`, `accept()`, `cancel()` | `QDialogButtonBox`, `buttons/<name>` |
| `JobProgress(name)` | `bind(handle)` follows a job handle: `status`, `progress`, `message`; the Cancel button cancels it | progress bar + label + button, `feedback/<name>` |
| `LogView(name, limit=500)` | the plugin's `ctx.log` records as they arrive: `records()`, `lines()`, `clear()` (refused by name without `ctx.log`) | `QPlainTextEdit`, `feedback/<name>` |
| `ResultTable(name, columns)` | rows of mappings under `columns` (keys or `(key, heading)`): `set_rows`, `rows()`, `cells()`, `select(i)`, `selected()`, `selected_row()`, `changed` | `QTableWidget`, `feedback/<name>` |
| `Custom(name, widget_or_factory)` | any `QWidget` you built, or a zero-argument factory called at mount | the widget itself, `custom/<name>` |

`Container.find(name)` reaches a descendant by name; `attach(ctx)` and
`dispose()` walk the children. `ui_snapshot(widget_or_component)` (decision-51)
lists the semantic nodes of a mounted tree or of an unmounted component tree,
so an agent and a pure test read the same structure.

**The widget form.** A plain class - typically a `QWidget` subclass you
already have - with `kind = "dialog"` or `kind = "dock"` and a constructor
taking the `UiContext` is accepted in `surfaces` as it is; the host shows the
instance, binds `initial` when it can and calls `on_close()` if present.
It opens only under a host (the class *is* Qt), so keep it in a module
declared native and reach it from tests through the desktop harness.

### Behaviour mixins

Three mixins add the common behaviours to a `Dialog`/`Dock` (decision-55
point 5); list them before the base class:

```python
from qgis_sdk.ui import AcceptCancel, Column, Dialog, HasAcceptCancel, JobProgress, RunsJobs


class Export(RunsJobs, HasAcceptCancel, Dialog):
    def build(self):
        self.progress = JobProgress("job")
        return Column("export", [..., self.progress, AcceptCancel()])

    def on_accept(self):
        self.run("export_layer", layer_id=..., file_name="out.gpkg")  # a job: tracked, shown, cancelled on close
        return False  # keep the window open while it runs
```

- **`RunsJobs`**: `self.run(action_id, **values)` calls the action through
  `ctx.actions`; a returned job handle is tracked (`self.jobs`), bound to
  the `JobProgress` stored as `self.progress` (`progress_attribute` renames
  it) and cancelled when the window closes; `cancel_jobs()` does it early.
- **`SubscribesStreams`**: `self.subscribe(stream, callback, **request)`
  and `self.subscriptions`/`unsubscribe_all()` over `ctx.on`.
- **`HasAcceptCancel`**: wires the `AcceptCancel` row named `buttons`
  (`"dialog_buttons"` by default; a `QDialogButtonBox` of that `objectName`
  in a hand-built or Designer tree works too): Accept runs `on_accept()`
  and closes unless it returned `False`; Cancel runs `on_cancel()` and
  closes.

### Designer files and the pure-PyQt path

`ui = "buffer.ui"` on a surface names a Qt Designer file relative to the
class's module; the default `build()` loads it with `uic` under the host,
and `@on` names are the file's `objectName`s. Under the fake,
`build_surface` reads the same XML into a `FakeUiTree` of `FakeWidget`s
whose signals (`clicked`, `valueChanged`, ... by widget class) a test
`emit`s. `qgis_sdk.ui.load_ui(cls)` is the loader when a `build()` wants to
add to the loaded form. The pure-PyQt path stays: `build()` may construct
Qt widgets itself (import Qt *inside* `build()`), name the interactive ones
(`UI001`) and still use `@on(name, "signal")` and the mixins over them -
the scaffold's `PingDialog` is written that way.

### Testing surfaces without QGIS: `build_surface`

`qgis_sdk.testing.build_surface(Surface, ctx, initial=)` runs `build()`
exactly as the host would, minus Qt: the instance gets `ctx` and `initial`,
the returned component is attached (never mounted), a `ui =` surface gets
the fake tree, and the `@on`/`@subscribe` methods and the mixins are wired.
It returns a `BuiltSurface` (`surface`, `root`, `ctx`, `find(name)`,
`close()`); `fake_ui_context(scope, runtime=started_runtime, **services)`
builds the `UiContext` over `RecordingNotifications`, `FakeViewControl`,
`RecordingLog` and - given the runtime - real `ViewActions`/`ViewStreams`,
so a button click under the fake dispatches the plugin's own handler and a
`@subscribe` receives what the plugin's stream pushes. The example's
`tests/test_workflow_pure.py` drives `BufferDialog` and `ResultsDock` this
way; its `test_workflow_qgis.py` opens them under the host and checks the
same names on the Qt tree.

### Snapshots: the tree, the PNG and the tools

`SurfaceHost.snapshot(surface_id=None, *, screenshot=True)` captures the
surfaces *this plugin's host* opened: a dialog it showed, a dock it built and
left visible. That is the whole scope rule (decision-51 point 6) - there is no
tree-walk of the QGIS main window, so a capture can never hold another plugin's
window. An unknown id is refused with the ids that are open.

Each capture is canonical JSON (sorted keys, no spaces, one trailing newline)
plus a PNG taken with `QWidget.grab()` under the offscreen QPA as well, so two
captures of an unchanged surface are byte-identical:

```json
{
  "surface": "buffer_dialog", "kind": "dialog", "title": "Buffer",
  "size": {"width": 420, "height": 180}, "scale": 1.0,
  "screenshot": "sha256:...",
  "nodes": [
    {"id": "form/distance", "role": "spinbox", "type": "QgsDoubleSpinBox",
     "value": 25.0, "label": "Distance", "state": {"enabled": true,
     "visible": true, "focus": false}, "geometry": {"x": 8, "y": 8,
     "width": 200, "height": 24}, "declared": {"field": "distance"}}
  ],
  "findings": []
}
```

`role` is the semantic node - `textbox`, `combobox`, `spinbox`, `checkbox`,
`button`, `label`, `group`, `map`, `crs`, `colour`, `file`, `slider`, … - and
sits in front of the Qt class in `type`, so a snapshot reads as the catalogue
component that made it rather than as whatever widget the adapter chose.
`value` is the role's own value (a spin box's number, a combo box's current
text, a button's text), `label` comes from `QLabel.buddy()` and the form's rows,
`geometry` is in surface coordinates, and `declared` links `form/<field>` back
to the field and `buttons/<name>` to the button. An actionable widget with no
`objectName` gets a positional id (`#0/1`) and a `UI001` finding, which is the
same rule `qgis-sdk check` reports before the plugin ever runs.

**Driving a surface from the command line.** The surfaces are Qt objects that
only exist where the plugin runs, so each command writes a request into
`.qgis-sdk/ui/` and runs the probe in a QGIS interpreter - the CLI process never
touches a widget:

```sh
qgis-sdk ui list                          # the surfaces the plugin declares
qgis-sdk ui open buffer_dialog            # build it and report the window
qgis-sdk ui snapshot buffer_dialog        # JSON + PNG, --no-screenshot for the tree alone
qgis-sdk ui act buffer_dialog \
    --step form/distance:set:25 --step buttons/run:click
qgis-sdk ui diff .qgis-sdk/ui/buffer_dialog.json tests/__snapshots__/buffer_dialog.json
```

`act` sends `click`, `focus`, `select`, `set` and `type` through `QTest` - the
same event path a user's click takes - and then captures the surface again, so
the second file (`<surface>.json`, after `<surface>-before.json`) shows the new
state. It reports the value each widget holds afterwards. `diff` exits `1` when
anything but the image changed and prints one line per difference. Every
command takes `--format yaml` for reading; the files on disk are always the
canonical JSON, and YAML lives in the tools, never in the runtime.

`act` is developer tooling: the runtime a plugin ZIP vendors never mentions
`QtTest`, and the MCP server marks it `DEVELOPER_ONLY`. The reading tools -
`list`, `open`, `snapshot`, `diff` - are what a client gets without that
tooling. Nothing of this reaches the plugin's HTTP API, which can name only
declared actions and streams.

**Approving a surface in a test.** The `ui_snapshot` fixture captures a surface
and compares it with what the project approved under the test module's
`__snapshots__` directory:

```python
def test_buffer_dialog(ui_snapshot, host):
    host.open(BufferDialog)
    ui_snapshot(host.snapshot("buffer_dialog")[0])   # fails with the diff
```

Pass the `SurfaceCapture` the host made and the capture stays inside the
plugin's scope; a widget the test built itself also works, with a name:
`ui_snapshot(dialog, name="standalone")`. After the test the fixture fails any
surface that changed structurally, and prints where the approval is:

```text
buffer_dialog (tests/__snapshots__/buffer_dialog.json):
form/distance: value 0.0 -> 25.0
```

A different PNG does **not** fail: a screenshot is for a human or an agent to
look at, and a renderer bump is not a regression. To write or refresh an
approval, call `approve()` on what the fixture returned - it writes
`<surface>.json` and `<surface>.png` and the run passes:

```python
def test_buffer_dialog(ui_snapshot, host):
    host.open(BufferDialog)
    ui_snapshot(host.snapshot("buffer_dialog")[0]).approve()
```

Commit the two files. A snapshot that has no approval fails with the path it
expected, so a forgotten `approve()` is visible in CI rather than silent.
`qgis_sdk_tools.ui_diff.diff_snapshots(before, after)` is the comparison behind
both the fixture and `qgis-sdk ui diff`, and `SnapshotDiff.render()` is the text
a failure shows.

### `ctx.log`

`ctx.log.info|warning|error(message, **fields)` is the plugin's structured
log (decision-63): a `LogRecord(level, message, fields, plugin, time)` goes to the
QGIS message log under the plugin's tab on the Desktop (`NativeLog`) and to
`RecordingLog.records`/`.messages` in tests; `subscribe(listener)` is how
`LogView` follows it. `UiContext` carries `log` as well, so a surface logs
what it did and every `LogView` of the plugin shows it.

### `ctx.notifications`

Four levels and one button (decision-55 point 3). `info`, `success`,
`warning` and `critical` take a message; `with_action(label, action_id,
**arguments)` returns the same service with a button attached, and pressing
it runs that declared action with those arguments through the plugin's own
`runtime.actions`:

```python
self.ctx.notifications.with_action("Undo", "undo_buffer", layer_id=output.id).success(
    f"Buffered into {output.name}"
)
```

On the Desktop the message lands on the QGIS message bar at its level with a
`QPushButton` named `notifications/<action_id>`; headless (`NativeNotifications`)
it goes to the message log with the label written after the message; under
`RecordingNotifications` every text is in `messages`, every
`Notification(level, message, action)` in `records`, and `press(index=-1)`
runs the button once `bind_actions(...)` named the dispatcher (the Desktop
host binds it at `initGui`). The wire keeps `notifications.info` only: a page
draws its own buttons over `actions.call`, and levelled feedback for pages
arrives with the bridge store slice so `HOST_FINGERPRINT` does not
move mid-train.

### `ctx.files`

`ctx.files` is the plugin's door from a `FileRef` to the filesystem, and the
one place its own code mints refs: `grant_file(path, operations=("read",),
overwrite=False)`, `grant_directory(path)` and `resolve(ref, operation="read")
-> Path`. It is backed by the runtime's one `HostAuthority` (decision-20),
the same instance the Processing toolbox mints picker refs through and the
WebEngine host (`HostServices.from_context`) grants a page's refs with, so a
ref a handler received from any of them resolves here - and only here: a
forged ref, a ref minted for another view, a read ref asked to write or a
ref whose grant has expired is refused (`QgisSdkUnknownHandleError`,
`QgisSdkGrantRefusedError`, ...). Closing the plugin's scope revokes what the
service minted. `qgis_sdk.testing.FakeFiles(scope)` is the same class over a
private authority (there is no simpler rule to fake); `granted` lists its
live refs. `UiContext` carries `files`, `layers` and `project` as well, so a
surface's components reach them without the plugin context.

## Processing algorithms and safe outputs

`qgis_sdk.algorithms` is the authoring surface
[decision-42](../../../backlog/decisions/decision-42%20-%20Declare-algorithms-as-plain-functions-on-providers-the-plugin-owns.md)
settled on: an algorithm is a plain function declared on a `Provider`, the
same shape as a `@job`. Its first parameter is the `AlgorithmContext` the
runtime injects, the remaining parameters are typed keyword inputs, and it
returns the `VectorLayerInfo` of the layer it produced. Describing one never
calls it, and every invocation builds a **fresh** context over a child scope
that is closed again when the invocation ends:

```python
from qgis_sdk.algorithms import describe_algorithm, invoke
from qgis_sdk.core import AlgorithmContext
from qgis_sdk.models import BufferRequest, CrsInput, LayerInput, Metres, VectorLayerInfo
from qgis_sdk.providers import Provider

tools = Provider(id="field_tools", title="Field tools")


@tools.algorithm(title="Buffer in a projected CRS", group="Geometry")
def buffer(
    ctx: AlgorithmContext, layer_id: LayerInput, distance: Metres, crs: CrsInput
) -> VectorLayerInfo:
    return ctx.algorithms.execute(
        BufferRequest(layer_id=layer_id, distance_metres=distance, working_crs=crs)
    )


described = describe_algorithm(buffer)
print(described.qualified_id, described.kinds, described.required)
# field_tools:buffer {'layer_id': 'layer', 'distance': 'metres', 'crs': 'crs'} ('layer_id', 'distance', 'crs')
```

### How do I run one from a context?

`invoke(function, ctx, **inputs)` runs one from the context the caller already
holds - the `PluginContext` of an action or the `AlgorithmContext` of another
algorithm. A `@job` body cannot: it runs on a worker, so its `WorkerContext`
carries neither `algorithms` nor `project` (decision-65) - invoke the algorithm
from the subscriber that hears the job succeed. It reads `algorithms`, `project`
and `scope` from that context, builds the invocation's own `AlgorithmContext`,
and adds the output to `ctx.project` after success:

```python
# inside an @app.action function
output = invoke(
    buffer, ctx, layer_id=source_id, distance=500.0, crs="EPSG:3857"
)
# invoke already added `output` to the project - after success only.
```

`progress=` and `cancellation=` left out are inherited from a job or algorithm
context (so a job's cancellation reaches the algorithm it runs); a plugin
context has neither, and the call runs silently and uncancelled.
`add_to_project=False` is for a caller that owns the destination itself: the
Processing bridge hands the layer to a feature sink, and the reference workflow
styles the output before presenting it. A context without the service a call
needs refuses by name (`QgisSdkUnsupportedCapabilityError("algorithms")`)
before anything runs.

No execution context is injected at decoration time, so a unit test needs no runner: call
`buffer(fake_context, layer_id=..., distance=..., crs=...)` with an
`AlgorithmContext` built over the `qgis_sdk.testing` fakes.

### What does the description carry?

The input schemas come from the same `qgis_sdk.declarations` generator that
describes plugin actions, so an algorithm's inputs are held to one documented
typing subset. `AlgorithmDescription` carries `parameters`, `required`,
`annotations`, `kinds` (input name to host parameter kind), `inputs_schema`,
`result_type` / `result_schema`, `group`, `provider_id` and `qualified_id`;
`to_dict()["inputs"]` is the object schema itself.

### Safe outputs

#### Non-destructive by construction (decision-19)

`Algorithms.execute` directs the built-in buffer and centroid operations to a
new SDK-owned output, then opens it as a layer. The SDK attempts to remove its
run directory on failure and its intermediate buffer reprojection on success;
filesystem cleanup can itself fail. The reference native algorithms are tested
for source preservation, but Processing providers are trusted code, not a
sandbox: the SDK cannot prevent a provider from editing inputs or writing
elsewhere, or roll back those side effects. `invoke` adds the returned output to
the project only after success, type validation and a cancellation check; an
algorithm or provider may still have its own project side effects.

#### Explicit CRS and units where a distance is involved

`BufferRequest` requires `working_crs` and `distance_metres`; the native
backend refuses a working CRS that is geographic (a distance there would be
degrees) or whose units are not metres, instead of converting behind the
caller's back. `CentroidRequest` has no distance and therefore no working CRS:
decision-19 requires a projected CRS *where the operation has one*, not
everywhere.

Two honest limits of this slice: cancellation is observed at phase boundaries (before the function runs, and after it before the project is touched), not by aborting a native operation mid-flight; and an algorithm's result is a vector layer - other layer kinds arrive with the services that produce them.

### Any registered algorithm: `list`, `describe`, `run` and the generated registry

`BufferRequest` and `CentroidRequest` are the hand-written predecessors of a
generated family. Since 0.7.0
([decision-64](../../../backlog/decisions/decision-64%20-%20Generate-the-Processing-catalogue-from-the-host-registry-and-run-any-registered-algorithm-through-one-typed-surface.md))
`ctx.algorithms` reaches **every** algorithm the host's Processing registry
holds - native, qgis, gdal, 3d, pdal, GRASS, SAGA, a third-party plugin's -
through one surface:

```python
from qgis_sdk.processing import native

providers = ctx.algorithms.providers()           # ProviderInfo per registered provider
summaries = ctx.algorithms.list(provider="gdal")  # AlgorithmInfo, help and all
info = ctx.algorithms.describe("native:buffer")   # parameters, outputs, defaults

# Three spellings of one run; all return a RunResult.
result = ctx.algorithms.run(native.Buffer(input=layer.id, distance=25.0))
result = ctx.algorithms.run("native:buffer", {"INPUT": layer.id, "DISTANCE": 25.0})
result = ctx.algorithms.run(AlgorithmRun("native:buffer", {"INPUT": layer.id}))

buffered = result.vector("OUTPUT")      # an owned VectorLayerInfo
stats = ctx.algorithms.run(
    "native:basicstatisticsforfields", {"INPUT_LAYER": layer.id, "FIELD_NAME": "id"}
)
stats.value("COUNT")                    # 3
report = stats.file("OUTPUT_HTML_FILE")  # a read-only FileRef; ctx.files.resolve(report)
```

The request is validated against the algorithm's description before execution
(`QgisSdkAlgorithmRejectedError` describes a refusal; an unknown id is
`QgisSdkAlgorithmNotFoundError`). A layer input is an owned layer id, a
`FileRef`, or a path the plugin already holds. A destination left out is
allocated under a fresh SDK-owned run directory: vector sinks return as
`VectorLayerInfo`, files and folders as read-only `FileRef` objects, and scalar
outputs as values.

**Named destination safety (unreleased change).** A run may name at most one
new local GeoJSON or GeoPackage vector destination, as a path string or a
write-authorized `FileRef`. Existing files, including input aliases and
write-granted files with overwrite permission, are refused; so are multiple,
remote, memory, folder, raster and other named destinations. The native adapter
writes to a private directory beside the destination, verifies a single readable
independent file with no sidecars, then atomically publishes it without replacing
an existing name. This requires hard-link support; a `FileRef` write grant is
rechecked before publication. Leave a destination unspecified and export the
resulting vector with `ctx.layers.export_vector` when you need
explicit overwrite consent; for other output types use SDK-allocated output and
handle publication separately with suitable safeguards.

Cleanup of SDK-owned run and staging directories is best-effort. The SDK never
intentionally deletes an existing destination, but a complete file already
published may remain if later result conversion fails. Keep paths stable during a
run. Processing providers are trusted code and can modify inputs, project state
or other files outside the SDK's directories; the SDK cannot prevent or roll
back such side effects. The fake uses scripted answers and validates destination
requests but does not run Processing or prove filesystem behavior. `run` is
synchronous on the GUI thread, like `processing.run`; a long algorithm belongs
in a `@job`.

#### The generated modules

`qgis_sdk.processing.native`, `.qgis`, `.gdal`, `.p3d` and `.pdal` are
**generated**, never edited: each carries a `TypedDict` per algorithm (the
shape `run(id, params)` is typed by), a request class per algorithm
(`native.Buffer`, `native.Centroids`, ... - frozen dataclasses whose fields
are the parameters in snake case, destinations defaulting to `None`) and a
`REGISTRY` of `AlgorithmInfo`. They come from a snapshot of the registry of
the QGIS the SDK release was qualified with
(`qgis_sdk/processing/catalogue.json`; `QGIS_VERSION` says which), kept
fresh by `scripts/generate_processing_snapshot.py` and a CI drift check. A
host whose registry differs is what `describe` reports; the host's
description, not the snapshot, is what a run is validated against.

#### Over the fakes

Over the fakes, `FakeAlgorithms.list`/`describe` answer from that snapshot
(or a `Catalogue` the test passes as `catalogue=`), and `run` answers from
what the test scripted with `script_run(id, outputs)` - a mapping of output
name to a `Path` (becomes the registered layer or a `FileRef`, by the
output's kind) or a scalar, or a callable of the `AlgorithmRun` - and
records every run in `.runs`. A run nobody scripted fails with
`QgisSdkAlgorithmFailedError`, never with an invented layer.

#### Generating modules for another provider

A project that depends on a provider the runtime does not ship generates its
own modules with the developer tools:

```sh
qgis-sdk processing generate --provider grass --provider saga   # reads the project's QGIS
qgis-sdk processing generate --check                            # CI: fail on drift
```

The reader runs *inside* the project's QGIS interpreter (the tools never
import QGIS); the output is `<plugin package>/processing/` in Python
(`--out`) and `web/src/processing.schema.ts` for the page (`--web-out`),
each skippable (`--no-python`, `--no-web`). Pass `--catalogue <json>` to
render from a catalogue a reader already wrote.

## Providers: algorithms in the QGIS Processing toolbox

A provider is both an algorithm namespace and the registration that makes its
algorithms visible. Add it explicitly to the application:

```python
from qgis_sdk import QgisSdkPlugin
app = QgisSdkPlugin(id="field_tools", title="Field tools")
app.add_provider(tools)  # a Provider declared in your algorithms module
```

In QGIS, startup registers the owned providers with Processing and unload removes
them. Startup rolls back on a duplicate provider ID. Over a context without the
Processing capability no provider is registered. `runtime.providers` and
`runtime.registered_providers` report owned and currently registered providers.
Provider registration does not add bridge-callable actions to `describe(app)`.

`Annotated` markers say what an input *means* to the host while the wire schema keeps describing the stored value. The aliases are the usual spelling; the long form (`Annotated[str, LayerParameter()]`, `Annotated[float, MetresParameter(minimum=1.0)]`) describes identically and is how you add a bound. Each kind is complete across hosts (decision-46 point 1): one marker, one widget family in `qgis_sdk.ui`, one Processing parameter, one `x-qgis-sdk` annotation on the wire. `qgis_sdk.models.parameter_kinds()` is the registry the describers, the form rule and the Processing adapter all read.

| Spelling | Stored | Handler receives | Processing parameter | Widget family |
| --- | --- | --- | --- | --- |
| `LayerInput` | `str` | a layer id, opened through `Layers` | `QgsProcessingParameterVectorLayer` | `layer` |
| `CrsInput` | `str` | an authority code | `QgsProcessingParameterCrs` | `crs` |
| `Metres` | `float` | metres, bounded at zero | `QgsProcessingParameterNumber` | `metres` |
| `FileInput(filters=("*.gpkg",))` | `FileRef` | a `file` `FileRef`, never a path | `QgsProcessingParameterFile` (File) | `file` |
| `DirectoryInput()` | `FileRef` | a `directory` `FileRef` | `QgsProcessingParameterFile` (Folder) | `directory` |
| `FieldInput(of="layer")` | `str` | a field name of the layer input `of` names | `QgsProcessingParameterField(parentLayerParameterName=of)` | `field` |
| `Range(0.0, 1.0, step=None)` | `float` (or `int` when both bounds are ints) | a number inside the bounds | `QgsProcessingParameterNumber` with min/max | `range` |
| `Colour(alpha=True)` | `str` | `#RRGGBB` or `#RRGGBBAA` | `QgsProcessingParameterColor` | `colour` |
| `Literal["fast", "safe"]` | `str` | one of the choices | `QgsProcessingParameterEnum` | `choice` |
| `str` / `int` / `float` / `bool` | itself | itself | string / number / number / boolean | `text` / `integer` / `number` / `boolean` |

A marker on a type it does not fit (`Annotated[int, LayerParameter()]`), a `Literal` of non-strings, a `FieldInput` whose `of` is not a layer input of the same declaration, or a bare `FileRef` input without `FileInput`/`DirectoryInput` is refused at declaration with the input name. A dataclass or a list input is still refused for an algorithm (a toolbox has no widget for it); an action may declare one. `FileRef` (`qgis_sdk.models`) is the branded reference of decision-20: the toolbox mints it from the dialog's picker through the host authority for the duration of the run, a page sends the ref the host minted and the handler receives the `FileRef` object, and a wrong-kind ref (a `file` where a `directory` was declared) is refused before the handler runs. Resolving a ref to a path from plugin code arrives with the `FileInput` component of the `Form` helper.

The bridge builds an `AlgorithmContext` over the dialog's feedback and calls the function through the same `invoke` an action uses, then copies the produced layer's features into the destination the user chose. That QGIS sink is separate from `Algorithms.run`'s staged named destinations; the SDK does not verify that the chosen sink is distinct from every input or roll back provider side effects. `FlagNoThreading` is deliberate: worker-thread execution of these adapters has not been qualified, so the bridge asks QGIS to run on the thread it was qualified on rather than claim a safety it cannot demonstrate.

`providers` and the bridge stay inside the same rules as the rest of the layer: no QGIS import in `qgis_sdk.providers`, and the native bridge (`qgis_sdk.adapters.qgis.NativeProcessing`) is only importable where PyQGIS exists. `qgis_sdk.testing.FakeProcessing` is the registry double for a pure test of the lifecycle.

## WebEngine bridge, host side

`qgis_sdk.bridge` is the QGIS-free host half of the transport a web view speaks.
Nothing in it imports Qt or QGIS, and nothing in it takes a callable from the
wire: a view names an operation id, and the host decides whether that view may
have it.

```python
from qgis_sdk.bridge import Dispatcher

runtime = PluginRuntime(MyPlugin, context).start()
dispatcher = Dispatcher.from_runtime(
    runtime,
    authorize=lambda binding, operation: binding.origin == "qgis://desktop",
)

binding, handshake = dispatcher.handshake(view_id="view-1", origin="qgis://desktop")
reply = dispatcher.dispatch(binding, request)     # never raises
```

- **One manifest, three views.** `from_description`/`from_runtime` project the
  allowlist from the plugin's own declarations, so the operations a view may
  call, the operations the handshake advertises and the schemas a generated
  client will be built from are the same object (decision-26). A declared action
  without a handler is refused when the dispatcher is wired, not when a view
  calls it.
- **Strict inputs, lenient results.** A declared request schema is validated
  before the handler runs - unknown properties, missing required ones, mistyped
  values and integers outside the safe range are refused as `invalid_payload`
  with the field path - and the payload is bound as keyword arguments. A
  declared result schema is checked afterwards: extra properties are tolerated,
  a missing or mistyped one is `invalid_result` naming the field, never the
  value.

- **One narrow entry point.** Protocol, generation, authorization, allowlist,
  payload and serialization are decided in that order. Authorization runs before
  the allowlist lookup, so a refused view cannot enumerate operations by
  watching which refusals differ.
- **Trusted identity only.** `ViewBinding` is minted by the host; a forged
  `view_id` or `generation` inside the payload is ignored, and
  `advance_generation()` retires every live binding with `stale_generation`.
- **Subscriptions.** `@app.stream` on the application or `register_stream(operation,
  factory)` on the dispatcher declares a stream, and `dispatch` accepts
  `{"kind": "subscribe"}`. Frames carry a per-subscription
  `seq`, the queue is bounded (`MAX_QUEUED_EVENTS`), a pushed stream that
  overruns it ends with a `gap` terminal carrying the dropped count, progress may
  be coalesced while it is still queued and data never is, and `pump(binding)`
  hands the frames to whatever transport owns the view.
- **Release by kind.** `{"kind": "release"}` disposes handles the way their kind
  requires: a borrowed layer is never deleted, an owned temporary output is
  deleted once, and a subscription that already ended reports
  `already_released` instead of failing.
- **Transport.** `qgis_sdk.bridge.transport.ChannelTransport` moves JSON strings
  in and out; `qgis_sdk.adapters.webchannel.create_channel_object` wraps it in
  the `QObject` a `QWebChannel` registers, importing Qt only when asked.

### Generated TypeScript schema module

The declarations a plugin already writes are the only source of the page's
types. One command renders the value types, an `Operations` and a `Streams`
interface and the parsed description as `web/src/bridge.schema.ts` - no QGIS,
no Qt, no handler ever runs - and the page builds its `QgisSdk` on it
([decision-44](../../../backlog/decisions/decision-44%20-%20Generate-a-typed-bridge-schema-module-and-build-the-client-from-it-at-runtime.md);
the TypeScript side is in [doc-13](doc-13%20-%20qgis-sdk-TypeScript-package-guide.md)):

```console
$ qgis-sdk bridge generate --plugin my_plugin.bridge:app
wrote web/src/bridge.schema.ts
```

`--out web/src/bridge.ts` still renders the 0.3.0 client - validators and
`createOperations(client)` - for one minor, with a note.

- **Deterministic.** The same declarations produce the same bytes, so the file is
  reviewed and committed like source, and CI regenerates it and fails on any
  difference (`--check` reports the drift without writing).
- **A description works too.** `--plugin` imports `module:Attribute` from the
  working directory; `--description plugin-description.json` does the same from a
  description a host already shipped, for a frontend with no Python at hand.
- **Closed subset.** A schema outside the declaration subset (`$ref`, an object
  inside a union) fails the build instead of emitting `any`.
- **Strict in, lenient out.** The SDK refuses unknown arguments and accepts a
  response that gained a field, so a newer host does not break an older view;
  the generator emits no validator of its own.
- **Ids are the method tree.** `QgisSdk` nests methods by the dots in an id
  (`sites.summary` is `qgis.sites.summary`), so the generator refuses an id
  that is a prefix of another declared id and one whose first segment is a
  `QgisSdk` member (`client`, `host`, `schema`, `ready`, `close`).
- **Streams come from the same declarations (decision-28).** `@app.stream(id=...,
  events={"data": SiteChange, "progress": ScanProgress})` marks a method that
  returns an iterator of `StreamEvent`s; its request schema is bound like an
  action's, and each declared event kind is a dataclass schema. The runtime
  registers the stream under its id in the same namespace as the actions, the
  host advertises the event schemas in the handshake and refuses to emit an
  event the stream did not declare (the subscription ends with `error`), and the
  page calls `qgis.sites.watch(input, handlers)` with a typed event union. The frame envelope (`seq`, `gap`) is not generated: it is
  the protocol's, owned by the TypeScript kernel.

### Host surface

A view can reach the curated services the plugin already implements - and nothing
else of the QGIS API. The inventory is a declaration, not a convention:

```python
from qgis_sdk.bridge import Dispatcher
from qgis_sdk.bridge.host import HostServices, host_grants, register_host_operations

dispatcher = Dispatcher(
    description=runtime.description,
    authorize=lambda binding, operation: host_grants()[operation] in grants_for(binding),
)
register_host_operations(
    dispatcher,
    HostServices(layers=layers, project=project, settings=settings,
                 styles=styles, notifications=notifications),
)
```

- **Six operations, each with a canonical grant.** `layers.list`, `layers.get`,
  `project.layer_ids`, `settings.get`, `notifications.info`, `styles.apply`.
  Grants are per operation (`layers.read`, `project.read`, ...), never per
  namespace, so a method added later is not automatically allowed.
- **Everything is declared.** Each entry names the Protocol method it wraps, its
  `gui` affinity and its request/result schema. Every other method of the curated
  Protocols - `open_vector`, `selection`, `add_layer`, `set`, `execute` - is
  listed in `DEFERRED_HOST_METHODS` with the task that owns it, and a test
  reflects the Protocols so a new method cannot appear unaccounted for.
- **Nothing unbounded, nothing by path.** Every list is paged
  (`{limit?, cursor?}` in, `{items, truncated, next_cursor?}` out; 50 by default,
  200 at most), a cursor the host never issued is refused rather than silently
  read as the first page, and no operation takes a filesystem path.
- **Versioned with the client.** The handshake advertises `host_schema_version`
  and the registered ids, and the TypeScript side ships generated inside the npm
  package as `@archont561/qgis-sdk/host`.

## Networking

`ctx.network` is one injected HTTP client over one injected transport, the shape
[decision-4](../../../backlog/decisions/decision-4%20-%20QGIS-aware-networking-uses-an-async-first-transport.md)
fixed: coroutine methods are the UI-facing form, a blocking form exists for
worker threads only, every response is fully buffered, and the live
`QNetworkReply` never leaves the adapter. The host composes it; plugin code
only ever sees `Network`.

```python
from qgis_sdk.adapters.qgis import NativeNetworkTransport
from qgis_sdk.core import PluginContext, ResourceScope
from qgis_sdk.network import NetworkClient

scope = ResourceScope()
context = PluginContext(
    notifications=notifications,
    scope=scope,
    network=NetworkClient(NativeNetworkTransport(scope), scope),
)
```

```python
async def load(self, ctx):
    api = ctx.network.configure(
        base_url="https://example.org/api/",
        headers={"Accept": "application/json"},
        timeout=10,
        auth_config="abc1234",          # a QGIS authentication configuration id
    )
    response = await api.get("collections", params={"limit": 20})
    return response.raise_for_status().json()
```

### How does a request run?

#### Coroutines, scheduled by the host

`get`/`post`/`request` are `async def` and suspend on a `Handoff` from
`qgis_sdk.core.scheduling`: the job waits, the GUI thread does not. Cancelling
the job aborts the reply; closing the owning scope aborts everything the client
still has in flight, so a disposed plugin never gets a callback.

#### Blocking is explicit and off the GUI thread

`ctx.network.blocking.get(...)` runs the same exchange on the calling thread
under a local event loop and raises `QgisSdkBlockingOnGuiThreadError` on the
GUI thread instead of nesting an event loop into the host's. Use it from
`QThreadPool`, `QgsTask` or a plain thread.

#### Derived, immutable clients

`configure(base_url, headers, timeout, auth_config, max_redirects,
max_body_bytes)` returns a new client; nothing mutates a shared default, so a
typed service client carries its own base URL without touching the plugin's.

### What comes back?

#### One `Response`

`status_code`, `reason`, `headers` (case-insensitive, credentials redacted in
`repr`), `content`, `text`, `json()`, `ok` and `raise_for_status()`. A `404` is
a response; only `raise_for_status()` turns it into `QgisSdkHttpStatusError`.

#### Errors you can tell apart by `code`

`QgisSdkRequestRejectedError` (bad URL, user-info in the URL, unsupported
method), `QgisSdkRequestCancelledError`, `QgisSdkConnectionError`,
`QgisSdkRequestTimeoutError`, `QgisSdkTlsError`, `QgisSdkAuthenticationError`,
`QgisSdkRedirectError`, `QgisSdkResponseTooLargeError`,
`QgisSdkHttpStatusError`, `QgisSdkDecodeError`, all under `QgisSdkNetworkError`
with the method and the URL in the message.

### Which limits and configuration apply?

#### Defaults from measurement

30 s timeout, 20 redirects, 16 MiB buffered body; the last two were measured
against `QgsNetworkAccessManager` on loopback servers, not chosen. A body over
the ceiling is aborted while downloading, not buffered and then refused.

#### QGIS owns the configuration

The native transport goes through `QgsNetworkAccessManager`, so the proxy, the
certificate trust and the authentication database a user set in QGIS apply;
`auth_config` is handed to `QgsAuthManager.updateNetworkRequest`, and no
credential passes through the SDK. Trust changes made at runtime need
`rebuildTrustedCaCertsCache()` and, for a host Qt already talked to,
`clearConnectionCache()`; both are QGIS calls, not SDK ones.

#### Redirects are followed by the transport, not by Qt

The manager was measured forwarding `Authorization` and `Cookie` to another
origin, so the transport follows hops itself and drops `Authorization`,
`Cookie`, `Proxy-Authorization` and the auth configuration when scheme, host or
port changes; `https` → `http` is refused.

### What builds on it?

#### Typed services compose over it

`qgis_sdk.network.OgcApiFeatures(network, base_url)` is the first:
`collections()`, `items(collection_id, limit, bbox)` and `next_page(page)`
return dataclasses, and a malformed document is a
`QgisSdkServiceResponseError`. WMS/WFS layers stay on QGIS providers.

#### Tests inject a fake

`qgis_sdk.testing.FakeNetworkTransport` is scripted with `expect(method, url,
response | exception | responder, hold=False)`; an unexpected request fails the
test with `QgisSdkNetworkFakeError`, a held request is released from the test
with `pending[0].deliver()`, and `assert_satisfied()` reports unmet
expectations. It never opens a socket. The native transport is covered by
`tests/test_network_native.py` against loopback servers, including the QGIS
proxy setting, a Basic authentication configuration, and a certificate trusted
through the auth manager.

## Scoped jobs

`ctx.jobs` is the local job runtime
[decision-13](../../../backlog/decisions/decision-13%20-%20Use-runtime-bound-Celery-inspired-local-jobs.md)
shaped,
[decision-38](../../../backlog/decisions/decision-38%20-%20Declare-jobs-as-plain-functions-with-the-JobContext-injected.md)
made function-based,
[decision-21](../../../backlog/decisions/decision-21%20-%20Bound-job-ownership-and-refuse-unsafe-runtime-replacement.md)
scoped and
[decision-65](../../../backlog/decisions/decision-65%20-%20Run-registered-jobs-on-workers-with-owner-scoped-named-submission.md)
worker-first: a job is a decorated plain function whose first parameter is the
`WorkerContext` the runtime injects and whose remaining keyword parameters are
typed the way an action's are, submission is `bind(fn).delay(**inputs)` and
nothing else, and the handle you get back is typed end to end. Since 0.9.0 the
whole body runs on a worker: the driving thread submits, validates and
delivers, and never calls your function. `qgis_sdk.jobs` is QGIS-free; it runs
on the step scheduler and a host drives `JobService.tick()` from whatever event
loop it already has.

```python
from dataclasses import dataclass

from qgis_sdk.core import WorkerContext
from qgis_sdk.jobs import job


@dataclass(frozen=True)
class SumResult:
    total: int


@job(id="demo.sum", title="Add two numbers")
def add(ctx: WorkerContext, left: int, right: int = 0) -> SumResult:
    # The whole body is on a worker: blocking work is already off the GUI
    # thread, and there is nothing to await.
    ctx.progress.report(0.5)
    return SumResult(left + right)


handle = ctx.jobs.bind(add).delay(left=1, right=2)
handle.on_progress(lambda fraction: bar.setValue(int(fraction * 100)))
handle.on_success(lambda result: label.setText(str(result.total)))
handle.on_failure(lambda error: label.setText(str(error)))
handle.on_cancelled(lambda: label.setText("cancelled"))
```

The decorator adds `describe()` but does not wrap `add`, so a unit
test calls `add(fake_context, left=1, right=2)` directly. A bare `@job`
derives its id and title from the function name. A plain `def` is the only
accepted form: `async def` and a generator are refused at bind time, because a
worker runs no event loop. GUI work belongs in a subscriber, which runs on the
driving thread. `ctx.jobs.delay(add, left=1, right=2)` is the one-call spelling
of `bind` then `delay`; there is no ambient `add.delay(...)`, because the owner
is always explicit (decision-21).

### What is checked before a job runs?

`describe_job(add)` returns the `JobDescription` (`id`, `title`, the parameter
names, which are required, the result type, and the object schema of the
inputs plus the result schema from the declarations generator) without calling
the function; a function without `@job`, without a `WorkerContext` first
parameter, with an unannotated parameter or without a declared result is
refused at bind time with `QgisSdkDeclarationError`, and so is a class
(the class form was removed in 0.6.0 - see the migration note below). An
`async def` body and a `JobContext` annotation are refused the same way, each
with the migration it needs. `JobDescription.asynchronous` stays in the
transport description and is always `False` since 0.9.0, so a 0.8 reader still
parses one.
Keywords that do not fit the signature - missing, unexpected or of the wrong
shape - are refused by `delay` with `QgisSdkJobRejectedError` naming every
problem before anything runs; positional arguments are a `TypeError`; a
result of the wrong type fails the job, not the tick.

### Migrating from the 0.5 class form

Up to `qgis-sdk-runtime` 0.5 a job was a class with `__init__(self, ctx)` and
a typed `run(self, inputs)`, submitted as `bind(Cls).delay(InputsDataclass(...))`.
In 0.6 the same job is the body of `run` as a module-level function:

```python
# 0.5
@job(id="demo.sum", title="Sum")
class Sum:
    def __init__(self, ctx: JobContext) -> None:
        self.ctx = ctx

    def run(self, inputs: SumInputs) -> SumResult:
        self.ctx.progress.report(0.5)
        return SumResult(inputs.a + inputs.b)


handle = ctx.jobs.bind(Sum).delay(SumInputs(1, 2))

# 0.6
@job(id="demo.sum", title="Sum")
def add(ctx: JobContext, a: int, b: int) -> SumResult:
    ctx.progress.report(0.5)
    return SumResult(a + b)


handle = ctx.jobs.bind(add).delay(a=1, b=2)
```

Move `self.ctx` to the injected `ctx` argument, spread the inputs dataclass
into keyword parameters (a dataclass is still a fine parameter type when the
inputs are genuinely one object), and call `delay` with keywords. A class
handed to `@job` or `bind` is refused with a message that points here.

### Three rules decide everything else

#### A request is not a state

`handle.cancel()` returns whether the job was still active and sets
`cancel_requested`; `status` becomes `cancelled` only when the job acknowledges
it (or before the worker ever started it). Nothing interrupts a worker thread:
the body polls `ctx.cancellation.is_cancelled()`, the request is forwarded to
the backend, and a callable still queued on a real pool reports without
running. A request that arrives before the worker reports settles the attempt
at that report, so a body that runs to the end after being asked to stop ends
`cancelled` rather than publishing a result nobody is waiting for. Work that
never reports stays `running`; `quiesce()` names it as a blocker instead of
pretending it stopped.

#### Callbacks run on the tick, never on a worker

Progress reported from a worker thread is coalesced to the latest fraction and
delivered on the next tick; each terminal outcome is delivered exactly once, in
subscription order. Subscribing late replays the current state synchronously as
one transition; a terminal replay completes the subscription. A callback that
raises is detached and reported through `faults` / `on_fault`, never raised
into the tick. `handle.get(timeout)` blocks only off the GUI thread - on it,
`QgisSdkJobWaitRefusedError`; a timeout is `QgisSdkJobNotSettledError`.
`handle.result` reads the same outcome without waiting: the typed result, the
job's own exception for a failed job, `QgisSdkJobCancelledError` for a
cancelled one, and `QgisSdkJobNotSettledError` only while the job is queued or
running. A `tick()` entered while another is on the stack - a job or a callback
opened a modal dialog and its nested event loop fired the host timer - is
ignored and returns `0`; a nested `quiesce()` is refused with the blocker `a
tick is already in progress on this thread`.

#### Disposal beats delivery

`ctx.jobs` in a view is `plugin_jobs.scoped(view_scope)`: closing the view
disposes every subscription it owns first, then asks each of its jobs to stop.
Hiding a dock is not disposal. A finished handle whose view closed afterwards
refuses new subscriptions rather than replaying into it. Plugin-lifetime work
is explicit - `ctx.jobs.parent.bind(...)` - and outlives the view. Closing the
plugin scope abandons everything through the scheduler's existing rule; nobody
is called. A subscription may name another owner (`handle.on_success(cb,
owner=other_scope)`); that owner's closure detaches it, and the service keeps
one close hook per such owner, released as the job finishes, so a long-lived
owner does not accumulate finished jobs.

There are no automatic retries: resubmission is `delay` again, with a new
logical id, and `attempt` is carried as `1` so a later, explicit retry policy
has somewhere to count.

### How do hosts compose the service?

Hosts compose the service once per plugin:

```python
from qgis_sdk.adapters.qgis import QgsTaskWorkers
from qgis_sdk.jobs import JobService

jobs = JobService(plugin_scope, workers=QgsTaskWorkers(plugin_scope), network=network)
timer.timeout.connect(jobs.tick)  # the GUI thread's event loop drives delivery
```

`workers` is not optional any more: a `JobService` built without one refuses
every submission with `QgisSdkJobRejectedError` instead of quietly running the
body on the driving thread (decision-65). A job is driven in three moves:
`tick()` submits, the worker runs the body, `tick()` delivers.

`QgsTaskWorkers` is the native backend, and `native_plugin_context` already
gives you one as `ctx.workers`. It runs each job body as **one `QgsTask` under
`QgsApplication.taskManager()`**, so the job is a single entry in the QGIS task
bar: the title is the job's `title`, its bar follows `ctx.progress` (the worker
reports, the task bar draws), and pressing cancel files the same cooperative
request `handle.cancel()` does - the body stops when it next polls
`ctx.cancellation`, and nothing is interrupted. There are no sub-tasks and no
parent task; a Processing algorithm keeps being the `QgsTask` Processing
already started. `ThreadPoolWorkers` stays available for a host without a task
manager (and is what `tests/test_jobs_native.py` drives); both report through
the scheduler's `Handoff`, so nothing about delivery changes between them.

In tests, `qgis_sdk.testing.FakeWorkers` holds the bodies until the test says
`run_one()` / `run_all()` - which is how the suite stages races between
workers, ticks and disposal, and a test passes `run_all` to a thread of its own
when it wants the body to run off the driving thread - and
`qgis_sdk.testing.ThreadWorkers` is a real `ThreadPoolExecutor` for the cases
that want one. `tests/features/scoped_jobs.feature` states the rules as
scenarios (bound by `tests/test_jobs_bdd.py`), `tests/test_jobs.py` holds the
examples, `tests/test_jobs_properties.py` a Hypothesis state machine over
submit / tick / cancel / worker reports / close view / close listener / close
plugin, `tests/test_jobs_native.py` the thread evidence over a real pool and a
real Qt event loop, and `tests/test_jobs_tasks_native.py` the task-manager
evidence (one task per job, its title, mirrored progress, the cancel button).

### How do I order one job after another?

`ctx.jobs.after(handle)` submits work that runs only after the jobs you name
succeeded:

```python
prepare = ctx.jobs.bind(load_layer).delay(layer_id=layer_id)

second = ctx.jobs.after(prepare).bind(run_report).delay(output=path)
# the same thing, chained: ctx.jobs.bind(run_report).after(prepare).delay(...)
```

The ordering is enforced before the dependent body is handed to a worker, so it
holds for every backend and the task bar never shows work it must not start
yet: the dependent job is `queued`, then `running` while it waits, and its body
runs after the prerequisite's. A prerequisite that fails or is cancelled fails
the dependent job with `QgisSdkJobPrerequisiteError` naming the prerequisite
and its outcome, and the dependent body never runs. A chain works the same way
- each `after` takes the handles of what it waits for - and a dependent job can
still be cancelled while it waits.

### Migrating a 0.8 job to 0.9

0.8 ran the body on the driving thread and left worker work to the author:
`async def` plus `await ctx.workers.offload(work)`. 0.9 does the offloading
itself, so a job becomes a plain `def` and the `await` goes away. Both old
shapes are refused at bind time with an actionable message; nothing silently
keeps the old execution.

```python
# 0.8
@job(id="demo.count", title="Count")
async def count(ctx: JobContext, layer_id: str) -> CountResult:
    def work() -> int:
        return len(feature_ids(layer_id))

    total = await ctx.workers.offload(work)
    return CountResult(total)


# 0.9
@job(id="demo.count", title="Count")
def count(ctx: WorkerContext, layer_id: str) -> CountResult:
    return CountResult(total=len(feature_ids(layer_id)))
```

What to move:

- **The context.** `ctx: JobContext` becomes `ctx: WorkerContext`, which
  carries `progress` and `cancellation` only. `project`, `algorithms`, `layers`,
  `iface`, `network`, `notifications`, `ui`, `view`, `files`, `scope` and
  `workers` are gone, and reading one raises
  `QgisSdkUnsupportedCapabilityError` naming the capability and why a worker
  cannot have it.
- **GUI preparation, before submission.** Read the project, resolve a path,
  collect plain values and let the user confirm - all on the driving thread,
  before `delay`. Pass plain values (ids, numbers, dataclasses) into the body,
  not live layers or widgets.
- **GUI updates, after delivery.** Anything that touches a widget or the
  message bar belongs in `on_success` / `on_failure` / `on_cancelled`, which
  run on the driving thread.
- **Long work, in the body.** A blocking call that used to need an offload is
  now simply called; the whole body is already off the GUI thread. There is no
  reason to create a second pool, and `ctx.workers` is absent.
- **Cancellation, cooperatively.** Poll `ctx.cancellation.is_cancelled()` in a
  loop and stop; the request is a signal, never a killed thread.
- **A host without a worker backend** (a script that only wants to call the
  function, a test double) should call the function directly or run the code
  without `JobService`; submitting is refused rather than silently degrading.
- **Ordering, if you needed it.** `ctx.jobs.after(handle)` replaces any
  hand-rolled "start the second job from the first one's success callback": the
  dependency is declared where the job is submitted, and a failed prerequisite
  fails the dependent job instead of silently skipping it.
- **The task bar.** On Desktop each job is now one task there. A job whose
  title reads well in a user interface is worth naming in `@job(title=...)`,
  and a long job should report `ctx.progress` so its bar moves.

## Project scaffold

`qgis-sdk new <directory>` writes a minimal but genuinely loadable QGIS plugin
project, built from the public declaration API instead of generated boilerplate.
The command is a thin Typer layer in `src/qgis_sdk_tools/__main__.py` over the
public `qgis_sdk_tools.scaffold` API, so a pip or `pixi add --pypi` install gets
the console script and `python -m qgis_sdk_tools` reaches the identical entry
point. The tools tree is separate from the runtime package `qgis_sdk` a plugin
imports (decision-35): it may use Typer and pytest, the runtime may not, and the
runtime never imports it. Typer is a
runtime dependency of the wheel for this command alone:

```sh
qgis-sdk new /tmp/demo --title "Demo Tools"            # installed console script
python -m qgis_sdk_tools new /tmp/demo --title "Demo Tools"  # same command via -m
pixi run -e default python -m qgis_sdk_tools new /tmp/demo   # from workspace source
```

`scaffold` was the command's name through 0.3.0; it still runs, hidden from
`--help` and marked deprecated, and goes away in a later minor.

`ScaffoldOptions.resolve` validates everything before a single byte is written: the
plugin name must be a lowercase Python identifier that neither QGIS nor the
standard library already owns, and the version fields must be dot-separated
digits. The result is an in-memory plan written with LF endings, so the same
options always produce the same bytes: `.gitignore`, `README.md`,
`pyproject.toml`, `<plugin>/__init__.py` (empty), `<plugin>/plugin.py` and
`tests/test_plugin.py`. There is no template directory to keep in sync;
`--dry-run` prints the plan without touching disk, and an existing file is refused
unless `--force` is passed.

There is no `metadata.txt` and no `classFactory` in the project (decision-43):
`pyproject.toml` carries `[project]` (name, version, description, authors, the
`qgis-sdk-runtime` requirement) and `[tool.qgis-sdk]` (`plugin`,
`qgis-minimum-version`, `experimental`); `build` renders `metadata.txt` from
them and `build`/`dev` bind `classFactory` through `host()`. `<plugin>/plugin.py`
is one `QgisSdkPlugin` with two actions receiving a `PluginContext`, and imports no Qt or QGIS module. `tests/test_plugin.py` runs
`host("<plugin>.plugin:app")(None)` through start, action and unload
without QGIS. Tests pin that the generated project imports nothing native.

### Choosing Desktop or standalone Qt mode

The README the scaffold writes teaches both modes; they differ in one thing, whether a host
`iface` exists:

| Mode | How it runs | What the SDK sees |
| :-- | :-- | :-- |
| Desktop | copy `<plugin>/` into a profile's `python/plugins/` and enable it under Plugins, Manage and Install Plugins, or launch `qgis --profiles-path <dir> --profile <name>` | `iface` is present, so `context.desktop` succeeds and messages reach the real message bar |
| Standalone Qt | call `host("<plugin>.plugin:app")(None)` from a plain Qt application or the starter tests, with `QT_QPA_PLATFORM=offscreen` for a display-free run | no `iface`, so reading `context.desktop` raises `QgisSdkUnsupportedCapabilityError` (`code="unsupported_capability"`) instead of inventing a host, and informational messages are dropped |

The starter tests are the standalone mode: in the generated project,
`PYTHONPATH=<this workspace>/packages/qgis-sdk-runtime/src pytest -q` runs load, action and
unload through the SDK runtime with no QGIS installation at all.

### Processing starter: `--algorithm`

`qgis-sdk new --algorithm` adds `<plugin>/algorithms.py` - one
`Provider(id="<plugin>", title=...)` and one function algorithm,
`buffer_layer(ctx: AlgorithmContext, layer_id: LayerInput, distance_metres:
Metres, working_crs: CrsInput) -> VectorLayerInfo`, the same shape as
`examples/simple` (decision-42) - lists it on the class
(`providers = (algorithms.provider,)`) and exposes the same operation as a
`buffer` action through `invoke(algorithms.buffer_layer, ctx, ...)`.
`tests/test_plugin.py` gains a fourth test that runs the function over
`FakeLayers`/`FakeAlgorithms`/`FakeProject` and asserts the exact
`BufferRequest` Processing would have received. `build` renders
`hasProcessingProvider=yes` from the declaration, and the
scaffold Desktop smoke test (`pytest -m smoke`) scaffolds this variant so real QGIS
Desktop proves the provider is in `processingRegistry()` while the plugin runs
and gone after unload. The README gets a "Processing" section naming the
toolbox entry `<plugin>:buffer`. It combines with `--web`.

### Native UI starter: `--ui native`

`qgis-sdk new --ui native` adds `<plugin>/ui.py` with `PingDialog`, a
`Dialog` subclass bound to `Plugins/<Title>` in the declarative form: a
`Number` (`form/value`), a `Form([value], action_id="ping")`, a `Button`
(`buttons/ping`) and a `LogView` over `ctx.log` as class attributes, no
`build()` and no Qt import anywhere in the package; `@on(ping).clicked`
submits the form and logs the answer. `plugin.py` lists it on the class
(`surfaces = (PingDialog,)`) and binds a no-input `open_ping` action to the
toolbar that calls `ctx.ui.open(PingDialog, initial={"value": 7})`,
which the default `build()` seeds into `form/value`. `tests/test_plugin.py`
gains a test that runs the action under `FakeUi` and asserts what was
opened. The README gets a "Native UI" section naming `UI001`-`UI005` and
`ICON001`, and says in one sentence that a `build()` returning any QWidget
(plain PyQt, imported inside the method) is the escape hatch.
It combines with `--algorithm` and `--web`; the `QGIS_SDK_DEVTOOLS=1`
harness scaffolds this variant so `qgis-sdk dev` inside real QGIS Desktop
proves the toolbar action opens the dialog and an edit to `ui.py` is what
the next opening builds after a reload.

### Web UI: vanilla or React, dialog or dock

`new` can add a page (decision-18). On a terminal it asks four questions -
web UI (`none`/`vanilla`/`react`), placement (`dialog`/`dock`), package
manager (`npm`/`pnpm`/`bun`), install now (`no`/`yes`) - and the answers feed
the same `ScaffoldOptions.resolve(web=, placement=, package_manager=)` the
flags do, so a script and a human get one validated plan. Any web flag
silences the questions; `--no-input` or a pipe means no questions and, without
flags, no page.

```sh
qgis-sdk new field_tools --web react --placement dock --package-manager bun --install
qgis-sdk new field_tools --no-input          # a plain plugin, as before
```

`--sdk-dependency SPEC` replaces the one value a plugin inside this repository
needs changed: what `web/package.json` depends on for `@archont561/qgis-sdk`.
Without it the page gets the exact bridge release this `qgis-sdk-tools` was
qualified with (`SDK_NPM_VERSION` in `scaffold/web.py`, moved by every bridge
release through `release.py stamp --scope typescript`); with it, any npm spec
you pass - the example plugin and the workspace harnesses use `workspace:*`
and a `file:<tarball>` of the checkout's bridge respectively, never a guessed
path (decision-41). Like `--placement`, it is refused without `--web`.

What the web plan adds:

- `web/` - a Vite app: `package.json` (every dependency pinned exactly,
  `@archont561/qgis-sdk` at the version this release was qualified with
  unless `--sdk-dependency` says otherwise; Vite and Vitest for every
  manager, never Bunup), `vite.config.ts` (`base: "./"`
  for `file:` pages, output into `<plugin>/web`, Chromium target of the
  oldest supported QGIS), `tsconfig.json`, `index.html` (loads Qt's
  `qwebchannel.js`), `src/bridge.schema.ts` (the schema module rendered from
  the plugin's declarations and checked in - `<pm> run bindings` is the CI
  drift check), the page (`main.ts`/`app.ts` or `main.tsx`/`App.tsx`, three
  statements on `QgisSdk.fromBridgeSchema`) and a Vitest test against
  `@archont561/qgis-sdk/testing`.
- `[tool.qgis-sdk.web]` in `pyproject.toml` - `placement` and an empty
  `grants` list. No Python is added: `host()` opens the built page (see
  *Desktop host* above), and the starter test binds `classFactory` with the
  same placement.

Installing is opt-in: `--install` (or answering `yes`) runs the manager's
install in `web/` after every file is written. A failure keeps the project and
prints the retry (`cd <target>/web && npm install`) with exit code 1; nothing
is rolled back and nothing else is ever downloaded. A package named `web` or
`tests` is refused because the project owns those directories.

## Project checks

`qgis-sdk check [PATH]` reads a plugin project and reports what would stop it
from loading in QGIS or from being inspected without QGIS. It is non-mutating
and QGIS-free by design (decision-8): it imports nothing from the project,
installs nothing and runs no handler. The command is a thin layer over
`qgis_sdk_tools.check.check_project(root, native_modules=...)`, which `qgis-sdk build`
will call in-process rather than through a subprocess.

```sh
qgis-sdk check                       # the working directory
qgis-sdk check my_tools --json       # the same report as data
qgis-sdk check my_tools --native "my_tools.native.*"
qgis-sdk check my_tools --imports     # every import root, with its bucket
```

Every finding is a `Diagnostic` with a stable `rule`, a root-relative `path`,
1-based `line`/`column` (`0` for whole-file findings), a `message` and a
`remediation`; text output prints `path:line:col: RULE message` with the
remediation indented beneath, and ends with `checked N files: ...`. The exit
code is `1` when any error was found and `2` when the path is not a directory.

`--imports` prints the bucket of every import root, and every finding below
still prints with it:

```text
json                     stdlib    field_tools/plugin.py:5
qgis                     host      field_tools/plugin.py:6
qgis_sdk                 runtime   field_tools/plugin.py:4
fixture_pure             vendored  field_tools/plugin.py:7
pandas                   external  field_tools/plugin.py:8
mystery_package          unknown   field_tools/plugin.py:9
```

The buckets are `stdlib`, `host` (QGIS, Qt, `processing`, `osgeo`),
`runtime` (`qgis_sdk`), `plugin` (the package itself), `vendored` (a
distribution declared under `[tool.qgis-sdk.build] vendor`), `external` (a
root declared under `external`) and `unknown`. Only `unknown` costs anything:
it is `DEP001`, and it is reported here rather than first at `build`
(decision-50 point 3). `--json` carries the same listing under `imports`
(`counts` per bucket plus one entry per root).

| Rule | Meaning |
| :-- | :-- |
| `QGIS001` | `qgis`, `PyQt5/6` or `PySide2/6` is imported when the module loads: module scope, a class body, a `try`, a `with` or a module-level `if` all count. Imports inside a function and under `if TYPE_CHECKING:` are fine. |
| `ARCH001` | `qgis_sdk.adapters.qgis` (the PyQGIS-backed adapters) is imported when a pure module loads; let `host()` build the context, or reach the adapter inside the function that runs in QGIS. |
| `PROJECT001` | No directory with an `__init__.py` under the root (other than `tests/`). |
| `PROJECT002` | No `pyproject.toml`, or no `[tool.qgis-sdk] plugin = "<package>.plugin:app"` in it; `build` and `dev` derive `metadata.txt` and `classFactory` from that line (decision-43). |
| `CONFIG001` | `[tool.qgis-sdk]`, `[tool.qgis-sdk.check]`, `[tool.qgis-sdk.web]` or `[tool.qgis-sdk.metadata]` in `pyproject.toml` is malformed (`plugin` not `pkg.module:app`, `placement` not `dock`/`dialog`, `grants` not a list of strings, a passthrough value that is not a scalar). |
| `META001` | The plugin package has a hand-written `metadata.txt`; `build` renders it, so delete the file (or move extra keys under `[tool.qgis-sdk.metadata]`). |
| `META002` | `pyproject.toml` lacks a key `metadata.txt` needs: `[project] name`, `version`, `description`, `authors[0].name`/`.email`, or `[tool.qgis-sdk] qgis-minimum-version`. |
| `ENTRY002` | A module of the plugin package defines or imports `classFactory`; `build` and `dev` bind it through `host()`. |
| `GRANT001` | `[tool.qgis-sdk.web] grants` names something that is neither a host grant (`layers.read`, selecting every operation that needs it) nor a host operation id (`project.layer_ids`); see `qgis_sdk.bridge.host.granted_operations`. |
| `VERSION003` (warning) | `pyproject.toml` declares no `qgis-sdk-runtime` (or `qgis-sdk`) requirement; `build` ships the installed runtime and says so in the NOTICE. |
| `VERSION004` | The installed `qgis-sdk-runtime` does not satisfy the project's requirement. The finding names both and the `pip install` line; the tools never install. |
| `UI001` | A method of a `Dialog`/`Dock` subclass constructs an interactive Qt or QGIS widget (`QPushButton`, `QLineEdit`, `QSpinBox`, `QgsMapLayerComboBox`, ... - `qgis_sdk_tools.check.ui.INTERACTIVE_WIDGETS`) and never calls `setObjectName` on the name holding it; a constructor passed straight to `addWidget` is flagged too. Name it, or use a `qgis_sdk.ui` component, which names its widget (`form/<field>`, `buttons/<name>`). |
| `UI002` | A `Dialog`/`Dock` subclass with `ui = "file.ui"` has an `@on(name)` whose `name` is not an `objectName` the Designer file declares, or the file is not next to the module. The wiring would refuse the surface when it opens; the finding lists the names the file does declare. |
| `UI003` | An application action carrying `@toolbar`/`@menu`/`@shortcut` takes inputs beyond `ctx`; a button collects nothing. Drop the inputs, or bind a surface that collects them and calls `self.ctx.actions.<id>(...)`. |
| `UI004` (warning) | A module of the plugin package that is *declared native* still imports `qgis.PyQt`, `PyQt5/6` or `PySide2/6` when it loads: the exemption lifts `QGIS001`, but Qt at module level defeats the fakes (`build_surface`, `ui_snapshot`) and `check`'s inspection of that module. Keep Qt inside `build()`; the catalogue needs no Qt import. |
| `UI005` | The declarative form, read statically: `@on(attribute)` in a `Dialog`/`Dock` subclass names a class attribute that is a string, a number or a literal container rather than a component, or a bare name the class never binds; or a `Custom` declared on the class holds a widget built when the class is defined (`Custom(widget=QLabel(...))`), which cannot be copied for each window. Assign a catalogue component to the attribute (or pass the `objectName` as a string), and give `Custom` the widget class or a factory. A call the checker cannot see into and a module-level name are left to the host. |
| `ICON001` | `@toolbar(icon="...")` names something that is not a file under `<package>/icons/` (a bare file name is required). |
| `SYNTAX001` | A file does not parse. |
| `VERSION001` | `pyproject.toml` pins `qgis-sdk-runtime` (or the `qgis-sdk` kit, which installs the runtime at the same number) in `project.dependencies`, an extra or a dependency group, and no version the pin admits lies in the runtime range this `qgis-sdk-tools` release was tested with (its own `qgis-sdk-runtime>=X,<Y` requirement). Release segments only; `!=` is ignored; a specifier the arithmetic does not know is never reported. Skipped when the range cannot be read. |
| `VERSION002` | A TypeScript file starting with `// Generated by qgis-sdk. Do not edit.` declares a `PLUGIN_DESCRIPTION_SCHEMA_VERSION` or `HOST_SCHEMA_VERSION` other than the one this release generates; regenerate with `qgis-sdk bridge generate`. `node_modules` is never read. |
| `DEP001` | An import root is `unknown`: neither the standard library, QGIS, the SDK runtime, the plugin itself, a declared `vendor` distribution nor a declared `external` provides it. The ZIP cannot carry it, so the plugin would fail on a clean QGIS; the remediation names both exits (vendor it, or declare it external). `qgis_sdk_tools` is unknown with its own message - the tooling never ships. |
| `DEP002` | `qgis_sdk.testing` is imported; the fakes are for the project's tests and a built plugin never carries them (decision-35). |
| `DEP003` | A `[tool.qgis-sdk.build] vendor` distribution ships a compiled extension (`.so`, `.pyd`, `.dylib`); a compiled package cannot be vendored, so it is an external with a probe instead. |
| `DEP004` | A declared `vendor` distribution is not installed in the environment `check` runs in, or one of its requirements is neither vendored, declared external, nor something QGIS ships. The finding names the missing distribution. |

A module that must import QGIS when it loads (a widget module, a native
adapter of your own) is declared native so `QGIS001`/`ARCH001` do not apply:
list dotted module globs under `[tool.qgis-sdk.check] native-modules` in the
project's `pyproject.toml`, or pass `--native` for one run. Tooling trees
(`.venv`, `node_modules`, `.pixi`, `build`, `dist`, caches) are never checked.

## Running tests: `qgis-sdk test`

`qgis-sdk test [PYTEST_ARGS]... [--project PATH] [--target pure|qgis|desktop|web]
[--qgis-prefix PATH]` is a thin, environment-aware pytest runner (decision-8,
decision-7): it decides *where* pytest runs and forwards everything else.
Unknown arguments go to pytest unchanged (`qgis-sdk test -x -k ping`,
`qgis-sdk test -- --lf`), pytest's output is pytest's and its exit code is the
command's. A plain `pytest` in the project keeps working: the generated
`pyproject.toml` loads the same plugin through
`addopts = "-p qgis_sdk_tools.pytest_plugin"`.

| Target | Where pytest runs | Selection |
| :-- | :-- | :-- |
| `pure` (default) | this interpreter | `-m "not qgis and not desktop"`; importing `qgis`, `PyQt*` or `PySide*` fails the test that did it |
| `qgis` | the located QGIS's Python with its bindings on `PYTHONPATH`, headless by default | `-m qgis`; the `qgis_app` fixture is a `QgsApplication` |
| `desktop` | pytest **inside** the QGIS Desktop binary, temporary profile | `-m desktop`; `qgis_iface` is the real `iface`, `qgis_app` the running application |
| `web` | the project's package manager (`bun`/`pnpm`/`npm` from the lockfile) | `run test` in `web/`, i.e. the generated Vitest suite |

`qgis_sdk_tools.pytest_plugin` registers the `qgis` and `desktop` markers, provides
the fixtures, applies the pure-target import guard and fails a native target
in which every selected test skipped (exit 1 with the reason), so a required
gate cannot pass by skipping. A native target whose QGIS cannot be found
exits 2 naming what was tried; nothing is downloaded. Temporary profiles and
the request file live under a per-run directory that is removed afterwards;
`QT_QPA_PLATFORM`, `QTWEBENGINE_CHROMIUM_FLAGS` and a placeholder `DISPLAY`
are set only when the shell has no display (`DISPLAY`/`WAYLAND_DISPLAY`
unset on Linux); an exported `QT_QPA_PLATFORM` wins.

QGIS is located the same way for `test` and `dev` (decision-14, in
`qgis_sdk_tools.devtools.installs.find_qgis_install`): `--qgis-prefix`, then
`[tool.qgis-sdk] qgis-prefix` in `pyproject.toml`, then `QGIS_PREFIX_PATH`,
then `qgis` on `PATH`, then the interpreter's own prefix. An explicit answer
that lacks the bindings (`share/qgis/python`, `apps/qgis*/python`) is an
error, not a fall-through. `plan_tests(...)` / `plan_dev(...)` return the
process plan (argv, cwd, env, notes) without running it, which is what the
unit tests assert on; the commands print the notes to stderr before running.

## Developing against QGIS: `qgis-sdk dev`

`qgis-sdk dev [PATH] [--mode desktop|standalone] [--qgis-prefix PATH] [--no-web]
[--port N] [--no-watch]` runs the plugin from source in a real QGIS
(decision-8, decision-15, decision-21):

- **desktop** (default) starts the located QGIS Desktop binary with
  `--profiles-path <root>/.qgis-sdk --profile dev`, so the profile is the
  project's own and survives between runs (`.gitignore`d by the scaffold),
  and puts the generated **host package** on `QGIS_PLUGINPATH`:
  `<root>/.qgis-sdk/dev/host/<plugin>/` holds the rendered `metadata.txt`
  and an `__init__.py` that extends its `__path__` to the source package,
  runs the author's `__init__.py` and binds `classFactory = host(...)` -
  so QGIS imports the sources in place (no copy, no symlink) and the
  project tree is never written to. The host package is static for one
  run: a `pyproject.toml` change means restarting `dev`. The
  SDK's own packages join that process's `PYTHONPATH`, so the bootstrap
  (`qgis_sdk_tools.devtools.bootstrap`, running the policy in
  `.devtools.reloader`) imports inside QGIS's interpreter
  whichever Python runs the CLI. It enables the plugin, installs a
  **Reload** toolbar action (Ctrl+Shift+R), watches `<plugin>/` for saved
  `*.py` changes (polling every 500 ms; `web/` and caches
  excluded - the page is Vite's business) and reports to the terminal.
  `--no-watch` leaves reloads to the button.

  Every reload, however triggered, follows one policy:

  1. **Preflight** without touching the running revision: every module of
     the package compiles and `check_project` finds nothing QGIS would
     refuse (`SYNTAX*` errors inside the package; `PROJECT*`, `CONFIG*`,
     `META*`, `GRANT*`, `VERSION*` errors on `pyproject.toml`);
     `QGIS001`/`ARCH001` only warn, findings in `tests/` never
     block. A problem is *refused* - `reload refused, revision N keeps
     running: ...` - and nothing is unloaded.
  2. **Quiesce** through `PluginRuntime.quiesce()`: owned jobs are
     cancelled and given up to 2 s (pumping the event loop between checks)
     to reach a safe point. A refusal names the blockers, resumes the
     revision exactly as it was and says that finishing or cancelling the
     work, or restarting `qgis-sdk dev`, is the way out. No thread is
     killed, nothing unsaved is discarded.
  3. **Replace**: unload (drops every `<plugin>.*` module, including those
     the host package reached through its extended path), then load and
     start the current source. A failure after teardown cannot be undone: the
     partially imported modules are dropped, the plugin stays *disabled*,
     and the message bar and terminal say so until a Reload succeeds.

  Requests are serialised and coalesced: a burst of saves becomes one reload
  (300 ms debounce), and a request that lands while a reload is in flight is
  folded into exactly one follow-up. Each attempt carries a generation
  number in its report. Old-generation work cannot deliver into the new
  revision because the old scope is closed on unload (subscriptions
  disposed, late worker reports counted as dropped).
- **standalone** runs the host package's `classFactory(None)` +
  `initGui()` - `host()` with no `iface` - in a bare `QgsApplication` under
  the QGIS Python. It is the documented reduced mode: no `iface`, no plugin
  lifecycle hooks beyond the two calls, no reload; close the window to stop.
- **web**: when the project has `web/` with installed dependencies, the
  command starts the project's Vite dev server (`<manager> run dev --host
  127.0.0.1 --port N --strictPort`) on loopback, waits for the port, and
  hands its origin to the QGIS process as `QGIS_SDK_DEV_SERVER`. The
  runtime's view (`qgis_sdk.adapters.webview`, opened by `host()`) reads that
  variable, loads the page from the origin
  and grants it in `BrowserPolicy(origins=...)`; the bridge binding carries
  the same origin, so hot module replacement works and the bridge keeps
  answering across updates. A built plugin never sees the variable and
  `bun run build` never references the server. `--no-web` skips it; a
  server that does not answer within 60 s stops the command with exit 2.

Both modes exit with the QGIS process's code; QGIS not found is exit 2 with
the discovery report, a directory without `[tool.qgis-sdk] plugin` is exit 2
(`PROJECT002`). `qgis-sdk test --target desktop` stages the same host
package, and its pytest plugin makes `import <plugin>` resolve to it inside
the Desktop run, so a desktop test loads the plugin exactly as QGIS does.

## From the QGIS Python console

Your plugin's curated services are reachable from QGIS's own Python console
(`Plugins > Python Console`) without the plugin importing anything for you and
without this package re-exposing `QgisInterface` one method at a time
(decision-48). There are two routes, and both hand back the same object:

```python
# 1. the plugin you just started, from QGIS itself
import qgis.utils

session = qgis.utils.plugins["field_tools"].console()

# 2. the whole Desktop, anywhere `qgis_sdk` is importable
from qgis_sdk.console import connect

with connect() as session:
    session.ctx.layers.list_layers()
    session.plugin("field_tools").run("buffer", distance=25.0)
```

`qgis-sdk dev` prints both lines when it starts, with the plugin's own name in
the first. Route 1 needs nothing but the plugin QGIS loaded: it is what
`classFactory` returned, so an installed, vendored plugin answers it.
Route 2 builds a `PluginContext` through `native_plugin_context` over
`qgis.utils.iface` - or over the `iface` passed - and owns the scope it builds.

### `session.ctx`: the services a plugin gets

`ctx` is a full `PluginContext`: `layers`, `project`, `settings`, `styles`,
`algorithms`, `network`, `processing`, `files`, `log`, `notifications`, and
`desktop` where the host had an `iface`. A service this host cannot offer
refuses by name (`QgisSdkUnsupportedCapabilityError`), exactly as it does inside
a plugin; a standalone `QgsApplication` therefore has a working `ctx.layers` and
a `ctx.desktop` that says it is unavailable. `iface` itself stays behind
`ctx.desktop`: there is no proxy object, nothing is imported into the console
namespace, and no plugin code is `eval`ed.

`session.close()` - or leaving the `with` block - disposes what the session
started: its subscriptions, temporary outputs and jobs. A second `close()` is a
no-op, and reading a closed session refuses by name. Sessions never own project
layers. A session a plugin handed out with `console()` borrows *that plugin's*
context and scope instead: the console and the plugin read one project and one
settings prefix, closing the session does not stop the plugin, and the plugin's
`unload()` closes the session.

### `session.plugin(name)`: one running plugin

`session.plugins()` lists the names QGIS holds; `session.plugin(name)` returns a
`PluginHandle` with:

| Member | What it gives you |
| --- | --- |
| `description` | the validated declaration: id, title, version, actions, streams |
| `actions`, `streams` | the declared ids, sorted |
| `surfaces()` | the surface ids the plugin registers |
| `algorithms` | the Processing ids it registered, `provider:algorithm` (`PluginRuntime.algorithms`) |
| `state` | `new`, `running`, `stopped` or `failed` |
| `ctx` | the plugin's own context, the same service instances |
| `run(action_id, **inputs)` | call one action as a page or a surface would |
| `open(target)` | open one of its surfaces through its own host |
| `reload()` | unload and load it again - `qgis-sdk dev` only |

`run` takes the bridge dispatcher's path without the transport (decision-27):
the value becomes wire data, is checked against the request schema the
declaration already published, and only then is spread as keyword arguments -
so a missing field, an unknown one or a wrong type raises the same
`QgisSdkBridgeError` a page would see, naming the field
(`payload.distance: expected a number, got a string`). An unknown action refuses
listing the ids the plugin declares. A handler that raises keeps its own
exception, traceback and all, because in a console that traceback points at the
plugin's line. The call runs on the console's thread, so it blocks the GUI
exactly as pressing the plugin's button does.

`open("buffer_dialog")` reaches a surface by id, by class name
(`"BufferDialog"`), or by the action id whose surface follows the scaffold's
naming (`"buffer"` for a `BufferDialog` or a `buffer_dialog`). It opens through
the plugin's own host, so the window gets the plugin's context, scope and
lifetime; it belongs on the GUI thread, which the console's thread is. An
unknown name refuses listing both the surface ids and the action ids.

`reload()` exists only in a QGIS started by `qgis-sdk dev` (`QGIS_SDK_DEV_REQUEST`
set); an installed plugin refuses by name. Inside a dev session it follows the
same policy as the Reload button: the running revision is asked to quiesce
first, and a plugin with work in flight is left as it is rather than cut off
mid-run.

A handle works across vendored SDK copies: it reads the object QGIS holds by
attribute, so a plugin built by an older runtime keeps working while it has the
attributes read here, and a missing one (`algorithms`, `surfaces`, `runtime`)
refuses by name with "built by an older qgis-sdk" (decision-39). It is a
developer's view of one plugin, not an authorization for one plugin to call
another - validated plugin-to-plugin actions are TASK-125.

## Building an installable ZIP: `qgis-sdk build`

`qgis-sdk build [PATH] [--out DIR] [--no-web] [--json]` writes
`dist/<plugin>-<version>.zip` (version from `[project] version`) for Plugins >
Manage and Install Plugins > *Install from ZIP* (decision-8: the command is
argument parsing over `qgis_sdk_tools.bundle.build_plugin`). In order:

1. **Validate.** `check_project` runs first - the same rules and output as
   `qgis-sdk check`, so a project without `[tool.qgis-sdk] plugin`
   (`PROJECT002`), with a hand-written `metadata.txt` (`META001`) or
   `classFactory` (`ENTRY002`), or whose installed runtime misses its
   requirement (`VERSION004`) is refused - plus `WEB001` when a web project
   has no built page. The dependency rules are `check`'s now (decision-50):
   `DEP001` for an unknown import root, `DEP002` for `qgis_sdk.testing`,
   `DEP003` for a compiler-carrying `vendor` distribution, `DEP004` for a
   missing vendored distribution or requirement. Any error refuses the
   build (exit 1, nothing written).
2. **Web page.** With `web/package.json` the command runs the project's own
   `build` script through its lockfile's manager (`bun run build`, `npm run
   build`, `pnpm build`) in `web/`; Vite writes to `<plugin>/web/`, which
   ships. It never installs: missing `node_modules` is exit 2 with the
   install command to run. `--no-web` skips the step and ships
   `<plugin>/web/` as it is.
3. **Stage and archive.** The plugin package is copied without
   `__pycache__`, `*.pyc`, `tests/`, `.qgis-sdk/`, `.pytest_cache/`,
   `node_modules/` (the project's `web/` sources and `tests/` sit outside
   the package and were never candidates). Into the staged copy only -
   the source tree is untouched - go the two artifacts QGIS needs
   (decision-43): `metadata.txt`, rendered from `pyproject.toml` with every
   key QGIS requires plus `hasProcessingProvider` from the application's
   providers and the `[tool.qgis-sdk.metadata]` passthrough; and, appended
   to `<plugin>/__init__.py`, `classFactory = host("<spec>", placement=...,
   grants=...)` importing `host` from the vendored runtime. The plugin
   application is imported once, in isolation, to read its title and providers
   (an import error is a plain build error). The runtime `qgis_sdk` - every
   module except `qgis_sdk.testing` - is copied to
   `<plugin>/_vendor/qgis_sdk` with a `NOTICE` (the requirement the project
   declared and the runtime version resolved from it, MIT), and
   every absolute `qgis_sdk` import in the copy *and* in the plugin's own
   sources is rewritten to `<plugin>._vendor.qgis_sdk` (decision-35,
   decision-3: the plugin runs in a QGIS without qgis-sdk and coexists with
   plugins built against other versions; `rewrite_imports` is AST-located,
   touches only import statements and keeps line numbers). The ZIP's only
   root entry is `<plugin>/`; entries are sorted, timestamps fixed
   (`SOURCE_DATE_EPOCH` or 1980-01-01), modes normalised, so the same tree
   gives the same bytes.

`BuildResult` carries the archive path, plugin, version, file list, the
combined `CheckReport`, the vendored runtime version and the requirement it
was resolved from (`None` under `VERSION003`), the web outcome
(`none` / `built` / `prebuilt`), the declared externals and the vendored
distributions; `--json` prints its `to_json()`.

### Packages the plugin needs: externals and vendoring

Two exits, both under `[tool.qgis-sdk.build]` (decision-50):

```toml
[tool.qgis-sdk.build]
external = [
  "numpy",                                              # every QGIS ships it
  { import = "pandas", requirement = "pandas>=2", reason = "reads spreadsheets" },
]
vendor = ["shapely"]                                    # pure Python, copied in
```

**An external is declared and probed.** `build` renders the declaration into
`metadata.txt` (`Requires: pandas (pandas>=2) - reads spreadsheets`), so the
plugin manager says it before installation. It also emits a `classFactory`
that imports each external *before* anything of the plugin is imported: when
one is missing, the user sees one message-bar error naming the package and
the install command for their host - `python -m pip install` in the OSGeo4W
Shell on Windows, `/Applications/QGIS.app/Contents/MacOS/bin/pip3` on macOS,
`python3 -m pip install --user` elsewhere - and the plugin stays unloaded
instead of failing with a traceback half-way through `initGui`. The SDK
still installs nothing on the user's machine.

**A vendored distribution is copied.** `vendor` names installed
distributions; `build` copies each one under `<plugin>/_vendor/`, rewrites
its imports of the other vendored roots (and the plugin's own imports of
them) to `<plugin>._vendor.<root>` exactly as it rewrites `qgis_sdk`, puts
its licence in `<plugin>/_vendor/LICENSES/<name>-<version>-<file>`, and
records the name and version in `_vendor/NOTICE`. The rewrite is a textual,
AST-located change to import statements: a package that resolves a
dependency by name at runtime (`importlib.import_module("numpy")`) is out of
its reach, so vendor code that does that stays a test-time concern.

`pandas`, `scipy`, `shapely` and their kind are **externals with a probe,
never vendored**: they carry compiled extensions, so `build` refuses them
with `DEP003`, and a user whose QGIS lacks one has to be told how to install
it - which is what the probe does. A vendored package's own requirements must
be vendored or external too; anything else is `DEP004` naming the missing
distribution, and `check` reports it before you build.

The runtime is **resolved, never installed**: `build` reads the project's
`qgis-sdk-runtime` (or `qgis-sdk`) requirement and ships the installed
runtime when it satisfies it. A mismatch is `VERSION004` and the build is
refused with the `pip install` line to run; no requirement is `VERSION003`
(a warning) and the installed runtime ships with that fact in the NOTICE.

### CLI runtime

Commands that read or write anything beyond their arguments receive a
`qgis_sdk_tools.cli.CliRuntime` (`cwd`, `env`, `out`, `err`) through Typer's
`ctx.obj` (decision-34). The shell seeds it with `CliRuntime.for_process()`;
a test passes `qgis_sdk_tools.testing.FakeCliRuntime(cwd=..., env=...)` as
`CliRunner().invoke(app, args, obj=runtime)` and reads `runtime.stdout` /
`runtime.stderr` back.

## Optional controlled-deployment adapter

**Unreleased breaking change:** the optional Pydantic adapter and the
`controlled-deployment` extras are retired in the next Python minor release.
The last published `0.7.0` packages still contain them. Remove imports of
`qgis_sdk.adapters.pydantic` and `qgis_sdk.adapters.pydantic_types` and remove
the extra from installation requirements. No drop-in replacement is provided
for `PydanticContractAdapter` or `SafeJsonInteger`: migrate to supported SDK
declarations and their validation where applicable, or explicitly implement,
provision and test your own Pydantic integration. SDK contract integer limits
remain available as `qgis_sdk.models.MAX_SAFE_INTEGER`.

This does not prevent a plugin from using a separately provisioned Pydantic
package; it removes the SDK's adapter and dependency extra. Historical release
and qualification records below describe the old release, not current support.
See [decision-67](../../../backlog/decisions/decision-67%20-%20Retire-the-optional-Pydantic-controlled-deployment-adapter.md).

## 0.1.0 experimental release and migration policy

- **Experimental `0.x` SemVer:** `0.1.0` (and prereleases such as `0.1.0-alpha.1`,
  `0.1.0-beta.1`, `0.1.0-rc.1`) is an experimental milestone target; no `1.0.0`
  stability promise is made. Breaking changes during `0.x` require a documented minor
  version bump (`0.Y.0`) with migration notes; compatible bug fixes and additive
  changes use patch releases (`0.Y.Z`).
- **Scoped manifests, independent versions:** `scripts/release.py`
  (`pixi run release-stamp --scope python|typescript|all`) updates only the manifests
  in the selected scope. `qgis-sdk` and `@archont561/qgis-sdk` both shipped
  `0.1.0`/`0.1.1` because they were built together; they version independently from
  0.2.0 onward, so the 0.2.0 Python release leaves the bridge at `0.1.1`.
  A Python-scope stamp also moves `examples/simple/pyproject.toml`'s
  `qgis-sdk-runtime>=X.Y,<X.Y+1` / `qgis-sdk-tools>=X.Y,<X.Y+1` windows to the
  released minor (the `runtime` and `tools` scopes move their own line), and
  `verify-versions` refuses a release the example's window excludes - the
  example is the project the released tools are qualified against, and a stale
  window would be VERSION004 on it. The scaffold derives the same windows from
  the installed distributions at `new` time, so nothing in the templates is
  stamped.
- **Independent protocol versions:** `PluginDescription.schema_version = 1`
  (`PLUGIN_DESCRIPTION_SCHEMA_VERSION` in `qgis_sdk.declarations`) and future
  WebEngine IPC protocol versions are versioned independently of the package
  versions. The bridge declares the same
  `PLUGIN_DESCRIPTION_SCHEMA_VERSION`, and `scripts/release.py verify-versions`
  refuses a workspace where the two declarations disagree.
- **0.1.0 surface & migration note:** The placeholder `qgis_sdk.hello()` and bridge
  `hello()` smoke functions were removed prior to the first release (PR #23); the
  public root surface of `qgis_sdk` is `qgis_sdk.__all__` (`ActionDescription`,
  `PluginDescription`, `QgisSdkDeclarationError`, `action`, `describe_plugin`,
  `plugin`), plus the explicit submodules `qgis_sdk.models`, `qgis_sdk.services`,
  `qgis_sdk.core`, `qgis_sdk.adapters.desktop`, `qgis_sdk.adapters.webengine`,
  the then-optional Pydantic modules (retired in the next Python minor), and
  `qgis_sdk.scaffold` (`qgis-sdk new` CLI, spelled `scaffold` until 0.3.0). All packages and the repository root
  are licensed under MIT (`LICENSE`).

## 0.2.0 migration notes

`0.2.0` is the first release where the two packages carry different numbers: the
Python SDK moves to `0.2.0` and `@archont561/qgis-sdk` stays at `0.1.1`,
because no task in this milestone changes the bridge's source. Nothing is
published for the bridge, and no `ts-v*` tag exists.

- **Breaking, and the only one:** `AlgorithmContext.algorithms` is now a required
  field. Code that receives a context from the runtime is unaffected, because the
  runtime always supplies it; code that builds an `AlgorithmContext` by hand has
  to pass the algorithm service it wants the author class to use
  (`FakeAlgorithms` in tests, the native backend on a QGIS host).
- **`PLUGIN_DESCRIPTION_SCHEMA_VERSION` stays `1`.** The wire description is
  unchanged, so a web view using bridge `0.1.1` reads a `0.2.0` plugin
  description without any change. This is what
  `scripts/release.py verify-versions` checks across the two languages.
- **Additive:** curated native services with QGIS-free protocols and in-memory
  fakes (`qgis_sdk.services`, `qgis_sdk.testing`), schema-driven native forms
  (`qgis_sdk.ui`, `adapters.qgis.NativeForms`, `DeclaredFormDialog`,
  `QgisSdkFormError`), class-based Processing algorithms with typed outputs
  (`qgis_sdk.algorithms`, `qgis_sdk.reference.algorithms` - the latter removed
  again in 0.6.0) and their toolbox
  registration (`qgis_sdk.providers`).
- **Unchanged:** the package-root `__all__` still exports exactly six names, and
  everything above is reachable through its documented submodule.
- **Manifests:** `pyproject.toml` and `recipe.yaml` carry `0.2.0`; the bridge's
  `package.json` carries `0.1.1`. Verify with
  `python scripts/release.py verify-versions --scope python --version 0.2.0`.

## 0.3.0 migration notes

`0.3.0` closes the m-2 milestone. It is released together with
`@archont561/qgis-sdk` `0.2.0` - two tags, `python-v0.3.0` and
`ts-v0.2.0`, two numbers that are not meant to match
([decision-25](../../../backlog/decisions/decision-25%20-%20Version-each-package-independently-behind-a-shared-contract-version.md)).

- **No breaking change.** Every public name of `0.2.0` is still there with the
  same signature; what the diff adds are optional fields with defaults
  (`AlgorithmContext.network`, `JobContext.workers` / `network`,
  `PluginContext.network`, `UiContext.network`, `PluginDescription.streams`,
  `BridgeOperation.request` / `result` / `events`, `Dispatcher(ledger=...)`,
  `Handoff(on_cancel=...)`). Code written against `0.2.0` runs unchanged.
- **`PLUGIN_DESCRIPTION_SCHEMA_VERSION` stays `1`.** A description now carries a
  `streams` list beside `actions`; bridge `0.1.1` ignores the key, bridge
  `0.2.0` reads it. `BRIDGE_PROTOCOL_VERSION` and `HOST_SCHEMA_VERSION` are
  both `1` and are versioned independently of the packages.
- **Package root:** `qgis_sdk.__all__` grows from six names to eight -
  `StreamDescription` and `stream` join `ActionDescription`,
  `PluginDescription`, `QgisSdkDeclarationError`, `action`, `describe_plugin`
  and `plugin`.
- **Additive:** the WebEngine bridge host side (`qgis_sdk.bridge`: `Dispatcher`,
  protocol and refusal codes, bounded streams, `HostAuthority` file refs and
  network grants, the release ledger, `register_host_operations`, the
  TypeScript client generator) with `qgis_sdk.adapters.webchannel` and the
  restricted page in `qgis_sdk.adapters.webengine` (`BrowserPolicy`,
  `create_restricted_page`); the QGIS-aware HTTP client and typed services
  (`qgis_sdk.network`); scoped jobs with typed handles (`qgis_sdk.jobs`,
  `qgis_sdk.adapters.qgis` thread-pool workers); `@stream` declarations
  (`qgis_sdk.declarations`, with `describe` and the `Description` protocol
  shared by plugins, algorithms and jobs); `qgis_sdk.testing` fakes for all of
  it.
- **Manifests:** `pyproject.toml` and `recipe.yaml` carry `0.3.0`; the bridge's
  `package.json` carries `0.2.0`. Verify with
  `python scripts/release.py verify-versions --scope python --version 0.3.0`
  and `--scope typescript --version 0.2.0`.

## 0.8.0 migration notes

### Application authoring replaces plugin classes

The public `plugin`, `action`, `stream` and `describe_plugin` imports have been
removed. Replace a decorated plugin class with `app = QgisSdkPlugin(id=..., title=...)`
and turn each action or stream method into a module function registered with
`@app.action(...)` or `@app.stream(...)`. Give each function a first positional
`ctx: PluginContext` argument and use `ctx` rather than `self.ctx`. Actions
and streams need explicit IDs and titles; plugin metadata can default from the
module, but explicit stable IDs are recommended. Register surfaces with
`@app.surface` or `app.add_surface(...)` and providers with `app.add_provider(...)`;
compose other `QgisSdkPlugin` objects using `app.include(child)`. Change the manifest and bridge generation target from
`module:Class` to `module:app`, and use `describe(app)` or `app.describe()`.
`PluginRuntime`, `DesktopLifecycleAdapter`, `create_class_factory` and
`describe_bindings` now take an application rather than a plugin class;
`FakeUi(scope, app=app)` checks its registered surfaces in pure tests. The
class-specific `PluginFactory`, `instance_factory` and `declared_providers`
APIs have been removed. For per-host context construction, assign
`app.context_factory`. The old class-constructor hooks have no direct replacement;
construct testable dependencies in the context factory or in ordinary functions.

### The plugin HTTP API, and MCP for development only

This release adds one runtime interface for clients outside QGIS and keeps MCP
strictly on the development side. No released version shipped the experimental
`qgis_sdk.agent` module, so there is nothing to migrate: it is not part of this
release, and there is no `[tool.qgis-sdk.agent]` metadata, `AGENT` check rule,
`dev --agent` mode or consent surface.

**Calling a plugin from outside QGIS.** A host starts the listener itself,
after `runtime.start()` and on the runtime's owner thread:

```python
from qgis_sdk.http import PluginHttpServer

server = PluginHttpServer(
    runtime,
    post=post_to_owner_thread,
    token_file=private_directory / "plugin.token",
    actions=("buffer", "watch_progress"),   # an allowlist, not a view filter
)
server.start()
# ... serve ...
server.close()
```

`actions` must name IDs the plugin actually declared; an unknown ID is refused
at construction. Nothing is exposed that the host does not name, construction
opens no socket and creates no token, and only one server may serve a runtime.

- New names: `qgis_sdk.http.PluginHttpServer`, `QgisSdkHttpError`;
  `qgis_sdk_tools.rest.PluginClient`, `PluginClientError`; and the developer
  commands `qgis-sdk plugin describe|call|stream`.
- Endpoints: `GET /plugin` (the plugin description filtered to the allowlist),
  `POST /actions/<id>` (a JSON object in, the action's return value out), and
  `POST /streams/<id>` (server-sent events, ending with a terminal frame).
- Calls are serialized per runtime. A second call waits for its turn for up to
  the server's deadline and then fails with `503` and the `host_busy` code; it
  never runs inside another handler, including one that opened a modal dialog.
  Work queued from the thread already running plugin work is refused at once.
  A reload fails an in-flight call with `host_reloaded` without undoing effects
  it already had.
- Closing withdraws queued work, and the callers it withdrew answer `503` with
  `host_reloaded` before the connections are shut down: `close()` waits for the
  handlers already running, for up to `close_grace` seconds (2 by default). A
  handler still running after that grace is cut off, so a close never hangs on a
  stuck action.
- Refusals carry `{"error": {"code": ..., "message": ...}}`. `host_busy`,
  `host_reloaded` and the per-plugin session `capacity` budget answer `503`,
  because waiting or retrying can succeed; malformed input and failed
  operations answer `400`. `PluginClient` raises `PluginClientError` carrying the
  status for any non-`200` reply, refuses a response larger than 1 MiB instead
  of parsing a truncated body, and reports a `200` action reply without a
  `value` as `PluginClientError` rather than leaking a `KeyError`.
- `PluginHttpServer.pending_requests` and `PluginHttpServer.busy` report the
  dispatch state without exposing the internal queue: how many requests wait
  for the owner thread and whether one is running right now.
- Every dispatch still runs on the QGIS owner thread and through the same
  dispatcher, authority and protocol version as the page and the console. The
  bridge, `BRIDGE_PROTOCOL_VERSION` and `HOST_FINGERPRINT` do not move.

**Security model.** The listener binds to `127.0.0.1` only, refuses a foreign
`Host` header and any browser `Origin`, and requires a bearer token that the
host writes to a mode-`0600` file, unlinks on close, and never puts on a
command line the plugin controls. Connections, request size, read and write
deadlines, event-stream slots and buffered bytes are all bounded. The allowlist
is a permission list, not a sandbox: an exposed action runs with the plugin's
own authority, and the token holder can call anything the host named.

**Support boundary: POSIX only.** Creating a private token file relies on POSIX
permissions, and Windows credential storage is not implemented. On a non-POSIX
platform `PluginHttpServer.start()` refuses with a `QgisSdkHttpError` naming the
limitation, and creates no token or listener, rather than starting one whose
token another local account could read. This is a deliberate scope decision for
this release, not a transient bug; every other SDK feature, including the CLI
MCP server, works on Windows.

**`qgis-sdk mcp`.** `pip install 'qgis-sdk[mcp]'` adds the official `mcp`
package as an optional extra, and `qgis-sdk mcp` serves the developer CLI
commands over stdio. The dependency is imported only when that command runs; a
missing extra exits with the install line. This server never connects to a
running plugin, and the plugin REST commands are deliberately absent from its
inventory: use `qgis-sdk plugin` or `PluginClient` for that.

### Externals with a probe, and pure-Python vendoring

`[tool.qgis-sdk.build]` gains two keys (decision-50):

- `external` accepts tables beside bare roots:
  `{ import = "pandas", requirement = "pandas>=2", reason = "reads spreadsheets" }`.
  `requirement` defaults to the import root; `reason` is the sentence the
  startup probe shows. The declared roots move the matching `DEP001` finding
  into the `external` bucket, appear in `metadata.txt` as
  `Requires: pandas (pandas>=2) - ...`, and the generated `classFactory` -
  for `build` and `dev` alike - imports each one before anything of the
  plugin, explains a missing package in one message-bar error with the
  install command for the host, and returns `None` so QGIS leaves the plugin
  unloaded. Nothing is installed on the user's machine.
- `vendor` lists installed pure-Python distributions the build copies into
  `<plugin>/_vendor/`, with imports of those roots rewritten (in the plugin
  and inside the vendored code), licences under `_vendor/LICENSES/` and
  name/version in `_vendor/NOTICE`. A compiled distribution is `DEP003`; a
  requirement that is neither vendored nor external is `DEP004`.

New names: `qgis_sdk_tools.project.BuildConfig` and `ExternalPackage`
(`ProjectConfig.build`, `external_roots`), `qgis_sdk_tools.distributions`
(`Distribution`, `read_distribution`, `normalize`, `file_path`,
`QGisSdkDistributionError`), `qgis_sdk_tools.check.buckets` (`BucketReport`,
`ImportEntry`, `bucket_imports`, `import_findings`, the `BUCKETS` constants),
`CheckReport.imports`, `BuildResult.vendored`, and `check --imports`. An
import of a declared vendored root is now `vendored` instead of `unknown`, so
a project that vendored by hand and declared nothing keeps its `DEP001`
until it declares the distribution.

### Processing destinations

`Algorithms.run` no longer forwards arbitrary named destinations directly to
Processing. Use an omitted destination for an SDK-owned output, or provide one
new local `.geojson` or `.gpkg` vector destination. Existing files (even with an
overwrite-enabled `FileRef`), multiple named destinations, memory/remote URIs,
raster, folder and other named outputs are refused. For intentional vector
replacement, run into an allocated output and use `Layers.export_vector` with
explicit overwrite consent. Other formats need a separately qualified
publication workflow. See [Processing output safety](#safe-outputs) for the
provider trust and cleanup limitations.

## 0.7.0 migration notes

**Parameter kinds (decision-46 point 1).** Six kinds join
`LayerInput`/`CrsInput`/`Metres`: `FileInput(filters=)`, `DirectoryInput()`,
`FieldInput(of=)`, `Range(min, max)`, `Colour()` and `Literal[...]` choices
(the table under "Providers" above). What changes for existing code:

- A `Literal[...]` of strings is now the `enum` kind for algorithms: it was
  refused at declaration in 0.6 and now renders a `QgsProcessingParameterEnum`.
  Actions and jobs already accepted `Literal`; they are unchanged.
- Declared inputs with a marker carry `"x-qgis-sdk": {"kind": ...}` in their
  schema (a `Range` also carries `minimum`/`maximum`). The keyword is accepted
  by both validators and the generator; a generated `bridge.schema.ts` gains
  `/** @qgis-sdk-kind ... */` on those fields and its `CONTRACT_FINGERPRINT`
  moves - regenerate with `qgis-sdk bridge generate`. Pages reading
  `request.properties[...]` see one more key.
- `FileRef` moved to `qgis_sdk.models` (`qgis_sdk.bridge.authority` still
  re-exports it) and gained `kind = "directory"`; `FILE_REF` lists both kinds,
  so the host contract's `HOST_FINGERPRINT` moved (`sha256:af91deac…`); the
  schema and protocol versions did not. `HostAuthority.grant_directory` mints a
  directory read ref; `resolve_file` checks the ref's kind against the grant.
- `NativeProcessing(..., authority=)` and `register_provider(...,
  authority=)` accept the host authority the toolbox mints picker refs
  through; without one each provider owns its own.
- `FieldSpec` gained `details`; `FieldSpec.to_dict()` emits it.
- `qgis_sdk.algorithms.input_refusal` is the one rule a toolbox run, a page
  call and a form use to refuse a value; `parameter_kind` keeps its name and
  now delegates to `qgis_sdk.declarations.resolve_kind`.

**Input components and `ctx.files`.**

- `qgis_sdk.ui` exports the eleven input components (`LayerPicker`,
  `FieldPicker`, `CrsPicker`, `FileInput`, `DirectoryInput`, `Distance`,
  `Number`, `Text`, `Toggle`, `Choice`, `Colour`), `Component`, `Option`
  and `coerce_value`; see *Input components* above. `Surface.build()` may
  return a component; the host attaches and mounts it.
- `PluginContext` gained the `files` capability (`qgis_sdk.services.Files`,
  implemented by `qgis_sdk.files.FilesService`); `UiContext` gained `files`,
  `layers` and `project`. A context that lacks them refuses by name as
  before, and `has("layers")` on a `UiContext` is now a real probe rather
  than a `ValueError`.
- The Desktop host builds one `HostAuthority` per runtime and hands it to
  Processing (`NativeProcessing(authority=)`), to `ctx.files` and - through
  `HostServices.from_context`, which now defaults to the context's
  `files.authority` - to the WebEngine host. A host that built its own
  `HostServices(authority=...)` keeps it; pass none to share.
- `qgis_sdk.testing.FakeFiles`.
- Form coercion (`coerce_values`, and so `UiContext.actions`, the declared
  form dialog and the bridge) now refuses a negative `Metres` value
  ("a distance of 0 or more metres"), matching the spin box and the
  Processing parameter; refusal messages keep their `action '<id>': field
  <name> expects ...` shape.

**`Form`, `Button`, `Column`; `NativeForms` and `DeclaredFormDialog`
removed.** See *Forms: an action's inputs as a window*.

- `qgis_sdk.adapters.qgis.ui` is gone: `NativeForms(runtime)`,
  `.fields(id)`, `.render(id)`, `.run(id)`, `.dispatch(id, values)` and
  `DeclaredFormDialog`. Migration, line by line:

  | 0.6 | 0.7 |
  |---|---|
  | `NativeForms(runtime).fields("buffer")` | `Form.for_action(ctx, "buffer").fields` (components; `form_fields(description)` still gives the `FieldSpec`s) |
  | `dialog = forms.render("buffer")`; `dialog.widget("layer_id")` | `form = Form.for_action(self.ctx, "buffer")` inside a `Dialog.build()`; `form.field("layer_id").widget` after mount |
  | `dialog.values()` | `form.values()` |
  | `forms.dispatch("buffer", values)` | `form.submit()` (or `self.ctx.actions.buffer(**values)`) |
  | `forms.run("buffer")` (modal, `None` on cancel) | a `Dialog` subclass returning `Column([form, Button])`, opened by a binding or `ctx.ui.open`; add your own cancel `Button` calling `self.ctx.view.request_close()` |

  A form carries the view's authority, so `FileInput`/`DirectoryInput`
  fields, which the 0.6 dialog refused by name, now render and submit
  `FileRef`s.
- `qgis_sdk.ui` exports `Form`, `Button`, `Column`, `Input`, `input_for`,
  `schema_fields`, `ViewActions`, `ActionCall`. `Component` is now the
  identity/lifecycle base shared with containers; the eleven inputs subclass
  `Input` and accept `required=`. `Component.attach(ctx)` with the *same*
  context is a no-op (a container attaches its children); a second context
  is still refused.
- `ViewActions.describe(action_id)` is public: the declared description a
  form builds from.
- `form_fields` refusals name their owner (`action 'x': field ...`) as
  before; `schema_fields(schema, owner=)` is the same rule for a bare
  schema (`form: field ...`).
- `ctx.notifications` gained `success`, `warning`, `critical` and
  `with_action(label, action_id, **arguments)`; `info` is unchanged. A
  hand-written `Notifications` double with `info` only keeps working for
  code that calls `info`; subclass `qgis_sdk.services.NotificationsBase`
  and implement `_deliver(notification)` to get all four plus the button.
  `RecordingNotifications.messages` is unchanged; `records`, `press()` and
  `bind_actions()` are new. `NativeNotifications(sink=)` now receives a
  `Notification`, not a string. `MessageBarNotifications` pushes at the
  level and grows `bind_actions`, which `DesktopHost.initGui` calls.
- `qgis-sdk check` reports `UI001`; the scaffold's `PingDialog` already
  names its widgets. The desktop-adapter qualification fixture gained a
  `Form`-built dialog and the `form_submitted` stage.

**Wiring, mixins, containers, feedback, `Custom`, `ctx.log`.**
See *Wiring*, *Containers, feedback, buttons and `Custom`*, *Behaviour
mixins*, *Designer files and the pure-PyQt path* and *Testing surfaces
without QGIS* above.

- `qgis_sdk.ui` exports `on`, `subscribe`, `wire_surface`, `wires_of`,
  `StreamEvent`, `ViewStreams`, `ViewSubscription`, `load_ui`, the
  containers `Panel`/`Group`/`Tabs`/`Row` (next to `Column`), the feedback
  `JobProgress`/`LogView`/`ResultTable`, the buttons `RunButton`/`AcceptCancel`
  (next to `Button`), `Custom`, `ui_snapshot` and the mixins
  `RunsJobs`/`SubscribesStreams`/`HasAcceptCancel`. `Surface` gained the
  `ui` class attribute and the `on_accept()`/`on_close()` hooks; a plain
  class with `kind` and a `ctx` constructor argument is accepted in
  `surfaces` (the widget form).
- A `Button`/`Form` listener connected by hand inside `build()` keeps
  working; the `@on` form is the one the fake wires for you, so a test that
  called `build()` directly and clicked should move to `build_surface`.
- `UiContext` gained `log` and `streams` and the `on(stream, callback)`
  method; `PluginContext` gained `log` (`qgis_sdk.services.Log`,
  `NativeLog` on the Desktop, `RecordingLog` in `qgis_sdk.testing`).
  `fake_ui_context(runtime=)` builds `actions` *and* `streams`.
- A view's own synchronous push during `ctx.actions.<id>()` is delivered
  with `StreamEvent.echo = True`; bridge subscribers are unchanged.
- `qgis-sdk check` reports `UI002` and the warning `UI004`;
  `check_bindings(..., directory=)` is how the Designer file is found.
- The `simple` example gained `ResultsDock`, a `Dock` of the catalogue;
  the scaffold's `PingDialog` uses `@on("ping").clicked` instead of
  `button.clicked.connect`.

**The declarative surface form (decision-55 amendment).** See *The
declarative form* above.

- Every component's `name` is optional and every catalogue class has a
  keyword form; `Component` gained `__set_name__`, `named`, lazy `label`
  and `object_name`, `Button.text` is a property, `RunButton.progress` is
  readable. A `Container` checks for clashing child names when built *and*
  when attached (declared children get their names after the class body).
- `Surface.build()`'s default returns the declared tree before refusing;
  `qgis_sdk.ui.declarative` (`declared_components`, `materialise`,
  `declared_root`, `resolve_declared`) is what the host, `build_surface`
  and `wire_surface` use; `Wire.target` may be a `Component`.
- `derive_title` capitalises a lower-camel name (`fieldTools` → `Field
  Tools`); it read `field Tools` before.
- `ResultsDock` in the example is declared; its button is `buttons/fixture`
  (was `buttons/open`) and the table `self.results` (was `self.table`).
- Adoption: `Form` accepts unnamed inputs and keys them by name
  lazily (`Form._fields` resolves on first use; a form of inputs that never
  get a name refuses when read); the default `build()` seeds declared
  inputs from `initial` and refuses an unknown key
  (`qgis_sdk.ui.declarative.apply_initial`, `declared_inputs`); snapshot
  nodes of declared components carry `"attribute"` (`Component.attribute`);
  `qgis-sdk check` gained `UI005`; the scaffold's `PingDialog` is declared
  (`form/value`, `buttons/ping`, `feedback/answers`; it was `value`, `ping`
  and `answer` built in PyQt).

**Any registered algorithm (decision-64).** See *Any registered
algorithm* above. Nothing existing breaks; what is new:

- `Algorithms` gains `providers()`, `list(provider=None)`, `describe(id)`
  and `run(request, params=None)`; `execute` and `BufferRequest` /
  `CentroidRequest` stay as they are and are documented as the predecessors
  of `native.Buffer` / `native.Centroids`. `FakeAlgorithms` answers
  `list`/`describe` from the shipped snapshot and `run` from
  `script_run(...)`; its `runs` list records every `run` as an
  `AlgorithmRun`.
- New generated subpackage `qgis_sdk.processing` (`native`, `qgis`, `gdal`,
  `p3d`, `pdal`, `catalogue.json`) and new models `ProviderInfo`,
  `AlgorithmInfo`, `ParameterInfo`, `OutputInfo`, `AlgorithmRun`,
  `RunResult`, `RunOutput`; new errors `QgisSdkAlgorithmNotFoundError`,
  `QgisSdkAlgorithmRejectedError`, `QgisSdkAlgorithmFailedError`.
- Host operations `algorithms.providers/list/describe/run` behind the grants
  `algorithms.read` / `algorithms.run`; `HOST_FINGERPRINT` moved once to
  `sha256:16790dc8…`. `qgis-sdk new --web` grants `algorithms.run`, writes
  `web/src/processing.schema.ts` and runs `qgis-sdk processing generate
  --check` from `bindings`.
- New developer command `qgis-sdk processing generate` (tools never import
  QGIS: the reader runs in the project's interpreter) and the repo script
  `scripts/generate_processing_snapshot.py` with a CI drift check.

## 0.6.0 migration notes

**Project shape (decision-43).** A 0.6 project carries no
`metadata.txt`, `classFactory` or `webview.py`; `qgis-sdk check` reports the
old files as `META001`/`ENTRY002`. To migrate a 0.5 project:

1. Delete `<plugin>/metadata.txt` and `<plugin>/webview.py`; remove
   `classFactory`, the `build_context`/notifications glue and the desktop
   wrapper class from `<plugin>/plugin.py` and the `from .plugin import
   classFactory` line from `<plugin>/__init__.py`. What remains is the
   `@plugin` class (plus your own modules).
2. Add to `pyproject.toml`: `[project]` `name`, `version`, `description`,
   `authors` and `dependencies = ["qgis-sdk-runtime>=0.6,<0.7"]`;
   `[tool.qgis-sdk] plugin = "<package>.plugin:<Class>"`,
   `qgis-minimum-version`, `experimental`; any extra `metadata.txt` keys
   under `[tool.qgis-sdk.metadata]`; with a page, `[tool.qgis-sdk.web]
   placement = "dock" | "dialog"` and `grants = [...]` naming the host
   operations the page calls (the former `webview.py` registered them all;
   list the ones you use - `qgis-sdk check` names an unknown id).
3. In the project's own tests, bind the entry point the way `build` does:
   `classFactory = host("<package>.plugin:<Class>", placement=...)` from
   `qgis_sdk.adapters.desktop`.

`qgis-sdk build` and `qgis-sdk dev` then produce `metadata.txt` and
`classFactory` themselves; see *Desktop host* above.

0.6.0 of `qgis-sdk-runtime` changes how a job is written
([decision-38](../../../backlog/decisions/decision-38%20-%20Declare-jobs-as-plain-functions-with-the-JobContext-injected.md))
and how optional services are reached on every context
([decision-39](../../../backlog/decisions/decision-39%20-%20Expose-optional-services-as-capability-attributes-that-refuse-by-name.md)).
Everything about submission, handles, delivery and ownership is as
in 0.5.

- **`require_<name>()` is gone; the attribute refuses by name.** On
  `PluginContext`, `UiContext`, `AlgorithmContext` and `JobContext` every
  optional service (`desktop`, `network`, `layers`, `project`, `settings`,
  `styles`, `algorithms`, `workers`) is now typed as the service itself and
  reading one the host did not provide raises
  `QgisSdkUnsupportedCapabilityError(capability=<name>)` — the same error
  `require_<name>()` raised, now on `ctx.workers.offload(...)` directly.
  Replace `ctx.require_workers()` with `ctx.workers`, `ctx.require_native()`
  with `ctx.desktop`, and so on; constructor keyword arguments are unchanged.
  Code that *probed* a slot (`if ctx.network is not None:`) uses
  `ctx.has("network")` or `ctx.capabilities` instead - the attribute no longer
  evaluates to `None`, and `has()` raises `ValueError` for a name the context
  does not carry. Contexts are no longer dataclasses: they stay immutable
  (`AttributeError` on assignment) but `dataclasses.replace`/`asdict` do not
  apply to them.

- **`@job` decorates a function, not a class.** The first parameter is the
  `JobContext` the runtime injects, the remaining parameters are typed
  keyword inputs (defaults allowed, the same annotations an `@action`
  accepts) and the return annotation is the result. `delay` takes the inputs
  as keywords and refuses a submission that does not fit the signature with
  `QgisSdkJobRejectedError` before anything is queued. `ctx.jobs.delay(fn,
  **inputs)` is the one-call spelling of `bind` then `delay`. The class form
  is refused by `@job` and `bind` with a message that names the change; see
  [Migrating from the 0.5 class form](#migrating-from-the-05-class-form) for
  the side-by-side.
- **`JobDescription` describes a signature.** `inputs_type` is gone;
  `parameters`, `required` and `annotations` describe the keyword inputs and
  `inputs_schema` is their object schema (so `to_dict()["inputs"]` is the
  schema itself, not `{"type": ...}`). `result_type` / `result_schema` are
  unchanged. `describe(fn)` answers for a `@job` function; the refusal for an
  undecorated class now reads "describe requires a class declared with
  @plugin, or a function declared with @job or @provider.algorithm".

Algorithms follow the same move
([decision-42](../../../backlog/decisions/decision-42%20-%20Declare-algorithms-as-plain-functions-on-providers-the-plugin-owns.md)).
Every rename, in one list:

- **`@provider.algorithm` decorates a function, not a class.** `run(self,
  inputs: Request) -> Result` becomes `def name(ctx: AlgorithmContext,
  **typed inputs) -> VectorLayerInfo`; the request dataclass's fields become
  the keyword parameters and the result dataclass's `output` becomes the
  return value. The class form is refused with a message naming the change.
  The bare `@algorithm` decorator and `qgis_sdk.algorithms.algorithm` are
  gone: a provider is the only container. A derived algorithm id is now the
  plain function name (no hash suffix); pass `id=` to keep an old suffixed id.
  The class-form inspectors `declarations.RunSignature` /
  `describe_run_method` (never in `__all__`) went with it; `describe(fn)` is
  the one inspector.
- **`invoke(Class, Request, algorithms=, project=, scope=, ...)`** becomes
  **`invoke(function, ctx, **inputs)`**: pass the `PluginContext`,
  `JobContext` or `AlgorithmContext` you hold instead of its three services,
  and the inputs as keywords. It returns the `VectorLayerInfo` directly;
  `AlgorithmResult` and `result.output` are gone. `progress=`,
  `cancellation=` and `add_to_project=` keep their meaning; left out, progress
  and cancellation now come from a job or algorithm context.
- **`register_provider(...)` / `bridge.unregister()` leave the plugin.** Delete
  those lines from `initGui`/`unload` and add `providers = [tools]` to the
  `@plugin` class; `PluginRuntime.start()`/`unload()` register and remove them
  through the new `processing` capability of `PluginContext`
  (`native_plugin_context` supplies `NativeProcessing`; `qgis_sdk.testing`
  gains `FakeProcessing`). `register_provider` is no longer exported from
  `qgis_sdk.adapters.qgis`.
- **`LayerInput`, `CrsInput`, `Metres` are annotation aliases.**
  `Annotated[str, LayerInput()]` becomes `LayerInput` (or `Annotated[str,
  LayerParameter()]`), `Annotated[str, CrsInput()]` becomes `CrsInput`
  (`CrsParameter`), `Annotated[float, Metres()]` becomes `Metres`
  (`MetresParameter`); a bound moves to `Annotated[float,
  MetresParameter(minimum=..., maximum=...)]`. This applies to `@action`
  parameters too - `qgis_sdk.ui` and `NativeForms` read the new markers.
- **`AlgorithmDescription` describes a signature.** `inputs_type` is gone;
  `parameters`, `required`, `annotations` and `kinds` describe the inputs,
  `inputs_schema` is their object schema, and `group`, `provider_id` and
  `qualified_id` are on the description. `ProviderDescription.algorithms` is
  a tuple of `AlgorithmDescription` (`RegisteredAlgorithm` is gone), and
  `Provider.class_for` is `Provider.function_for`. `parameter_kinds(dataclass)`
  is `qgis_sdk.algorithms.parameter_kind(path, annotation)`;
  `LAYER_PARAMETER`, `CRS_PARAMETER`, `METRES_PARAMETER` live there too.
- **`qgis_sdk.reference` is gone.** `BufferLayer`/`BufferResult`/
  `CentroidLayer`/`CentroidResult` have no runtime replacement: what a plugin
  computes is the plugin's, so the two operations live in the example as
  `examples/simple/simple/algorithms.py` (`provider = Provider(id="simple",
  ...)`, `buffer_layer`, `centroid_layer`; toolbox ids `simple:buffer` and
  `simple:centroid`). Copy that module into your plugin and rename the
  provider; the request models `BufferRequest`/`CentroidRequest` and the
  native service behind `ctx.algorithms.execute` are unchanged. The runtime
  keeps no Processing algorithms of its own.
- **Contexts gain capabilities, additively.** `JobContext` carries
  `algorithms` and `project` (`JobService(..., algorithms=, project=)`),
  `AlgorithmContext` carries `project`, and `PluginContext` carries
  `processing`; all are optional constructor keywords that refuse by name
  when a host leaves them out. The wire contract, `describe_plugin` output
  and `HOST_FINGERPRINT` do not move.
- **Desktop bindings and surfaces (decisions 45 and 55),
  additively.** `qgis_sdk` exports `toolbar`, `menu`, `shortcut` and
  `describe_bindings`; `qgis_sdk.ui` exports `Dialog`, `Dock` and `Surface`
  next to the 0.5 form-field helpers, which moved to
  `qgis_sdk.ui.form_fields` and are re-exported from `qgis_sdk.ui`
  unchanged. `PluginContext` gains an optional `ui` capability (`host()`
  supplies it inside QGIS Desktop; `qgis_sdk.testing.FakeUi` elsewhere) and
  `UiContext` gains `actions` and `settings`. A plugin that places its own
  `QAction`s in `initGui` keeps working; moving them to `@toolbar`/`@menu`
  lets `host()` add and remove them with the plugin. See
  [Desktop bindings and native surfaces](#desktop-bindings-and-native-surfaces).

`qgis-sdk-tools` 0.6.0 changes one thing in what `qgis-sdk bridge generate`
emits ([decision-40](../../../backlog/decisions/decision-40%20-%20Make-the-root-entry-the-page-import-and-keep-generated-plugin-clients-import-free.md)):

- **The generated contract error is `QgisSdkContractError`** (was
  `ContractError`). It still extends `Error` - the module stays import-free -
  and now carries `code: "contract_validation_failed"` next to `operation`.
  Regenerate the client (CI fails on the stale file anyway) and rename the
  class in `catch` clauses, or match on `error.code`. The bridge package this
  release pairs with is `@archont561/qgis-sdk` 0.4.0, whose own notes are in
  [doc-13](doc-13%20-%20qgis-sdk-TypeScript-package-guide.md#040-migration-notes).

## 0.5.0 migration notes

0.5.0 splits the one `qgis-sdk` wheel into three
distributions ([decision-35](../../../backlog/decisions/decision-35%20-%20Split-the-Python-SDK-into-a-runtime-a-tools-package-and-a-meta-kit-behind-one-contract.md)
step 2, un-gated by [decision-36](../../../backlog/decisions/decision-36%20-%20Cut-the-three-Python-distributions-before-the-contract-freeze.md)),
adds the reference workflow (`qgis_sdk.exports`,
`Layers.export_vector`, the `reference/polygon-output` style, `examples/simple`),
the support matrix and `qgis-sdk targets`
([decision-37](../../../backlog/decisions/decision-37%20-%20State-support-as-a-matrix-of-demonstrated-targets.md)),
and `dev --exercise`'s smoke report. The bridge is unchanged: `@archont561/qgis-sdk`
stays 0.3.0 and was qualified inside a real `QWebEngineView` against this
release ([doc-14](doc-14%20-%20Workspace-development-qualification-harnesses-and-evidence.md#050-release-gate-2026-10-25)).

**Who installs what.**

| You are | Install | You get |
| :-- | :-- | :-- |
| a plugin developer | `pip install qgis-sdk` (unchanged) | the `qgis-sdk` command plus the runtime it was tested with, pinned exactly (`qgis-sdk-runtime==X`, `qgis-sdk-tools==X`) |
| a QGIS console user who wants the typed services without the tooling | `pip install qgis-sdk-runtime` into QGIS's interpreter | `import qgis_sdk`, no Typer, no pytest, nothing else |
| a plugin | nothing | `qgis-sdk build` vendors the runtime under `<plugin>/_vendor`; the ZIP does not depend on any installed distribution |
| a CI job that only runs the tools | `pip install qgis-sdk-tools` | the command and whichever runtime its range admits (`>=X,<X+0.1`) |

- **Import names are unchanged.** `qgis_sdk` comes from `qgis-sdk-runtime`,
  `qgis_sdk_tools` from `qgis-sdk-tools`; the kit has no code. No two wheels
  write the same top-level directory, so the three coexist in one
  environment and `pip check` is clean.
- **Historical extra.** The `controlled-deployment` extra shipped in 0.5.0;
  it is retired in the next Python minor release (see above).
- **Versions.** Until the contract freeze the three release together under
  the `python` scope at one version (`python-vX` publishes three wheels and
  three Conda outputs); `runtime-vX` and `tools-vX` tags exist for a release
  of one distribution alone. The tools declare the runtime range they were
  tested with; `qgis-sdk check` reports a project pin outside it
  (`VERSION001`) and a generated client from another contract version
  (`VERSION002`). The contract constants stay `1`.
- **Source checkouts.** The trees moved to `packages/qgis-sdk-runtime/src`
  and `packages/qgis-sdk-tools/src`; `packages/qgis-sdk-python` keeps the
  shared tests, scripts and the recipe. `pip install -e` the runtime and the
  tools before the kit's `dev` extra (the pins resolve against the editables).
- **PyPI placeholders.** `qgis-sdk-runtime` and `qgis-sdk-tools` existed at
  `0.0.0` before 0.5.0, as name reservations with no code; do not pin
  `0.0.0`. 0.5.0 is their first real publish.

## 0.4.0 migration notes

`0.4.0` closes the m-3 milestone (developer workflow and plugin packaging).
It is a Python-only release, tag `python-v0.4.0`: no file under
`packages/qgis-sdk-typescript` or `packages/qgis-sdk-alias` changed since
`ts-v0.3.0`, so `@archont561/qgis-sdk` stays at `0.3.0` and generated web
projects keep pinning it ([decision-25](../../../backlog/decisions/decision-25%20-%20Version-each-package-independently-behind-a-shared-contract-version.md)).
`PLUGIN_DESCRIPTION_SCHEMA_VERSION`, `BRIDGE_PROTOCOL_VERSION` and
`HOST_SCHEMA_VERSION` all stay `1`.

Two changes are breaking for code written against `0.3.0`, each documented
below with its one-line fix: the developer tools moved to `qgis_sdk_tools`
(`python -m qgis_sdk` is gone, the pytest plugin path changed), and the
runtime binds `PluginContext` as the `ctx` class attribute instead of passing
it to the constructor. Everything a plugin imports from `qgis_sdk.*` at
`0.3.0` is still there; the additions are listed. The notes are in reverse
landing order.

- **Manifests:** `pyproject.toml` and `recipe.yaml` carry `0.4.0`; the
  bridge's `package.json` and the alias carry `0.3.0`. Verify with
  `python scripts/release.py verify-versions --scope python --version 0.4.0`
  and `--scope typescript --version 0.3.0`.
- **`qgis-sdk build`** is new; see "Building an installable ZIP".
  Projects generated by `qgis-sdk new` now ignore `dist/`. A plugin that
  imports `qgis_sdk_tools` or `qgis_sdk.testing` from package code is
  refused at build time (`DEP001`/`DEP002`): those never ship.
- **`qgis-sdk dev` reloads on save and quiesces first**. The
  Desktop bootstrap is now the importable module
  `qgis_sdk_tools.devtools.reloader` (policy, tested without QGIS) plus
  `.devtools.bootstrap` (the QGIS glue the `--code` probe reaches);
  `plan_dev(...)` and the `qgis`/`desktop` test plans put the SDK's own
  import locations on the QGIS process's `PYTHONPATH`. The request JSON
  gains `watch` (default `True`; `--no-watch`). New runtime API, additive:
  `ResourceScope.on_quiesce(check, *, resume=None)`, `scope.quiesce()`,
  `scope.resume()`, `PluginRuntime.quiesce()` / `resume()`;
  `QuiesceOutcome` now lives in `qgis_sdk.core.scope` (still exported from
  `qgis_sdk.core`). A root `JobService` registers on its scope, and its
  blockers name the handle id (`job sum#1 ...`) instead of the scheduler's
  number.
- **The developer tools moved to `qgis_sdk_tools`** (decision-35, step 1).
  `qgis_sdk.scaffold`, `qgis_sdk.check`, `qgis_sdk.cli`, `qgis_sdk.devtools`,
  `qgis_sdk.pytest_plugin` and `qgis_sdk.bridge.generate` are now
  `qgis_sdk_tools.scaffold`, `.check`, `.cli`, `.devtools`, `.pytest_plugin`
  and `qgis_sdk_tools.generate`; `FakeCliRuntime` is
  `qgis_sdk_tools.testing.FakeCliRuntime`. `python -m qgis_sdk` is gone -
  use the `qgis-sdk` script or `python -m qgis_sdk_tools`. Generated projects
  now carry `addopts = "-p qgis_sdk_tools.pytest_plugin"`; a project generated
  from an unreleased build with the old path repoints that one line. The
  runtime API (`qgis_sdk.*` that a plugin imports) is unchanged;
  `qgis_sdk.environment` is new and holds the `QGIS_SDK_DEV_SERVER` /
  `QGIS_SDK_TEST_TARGET` names the generated `webview.py` and the tools
  share. The one wheel still ships both trees until the distributions split.
- **`qgis-sdk test` and `qgis-sdk dev`.** New commands over
  `qgis_sdk_tools.devtools` (`installs`, `testrun`, `dev`) and the pytest
  plugin `qgis_sdk_tools.pytest_plugin` (both landed under `qgis_sdk.` and
  moved in the same release, see the previous note); see "Running tests" and
  "Developing against QGIS". Projects generated by `qgis-sdk new` now carry a
  `.gitignore`, `addopts = "-p qgis_sdk_tools.pytest_plugin"` and a commented
  `[tool.qgis-sdk] qgis-prefix`; the generated `webview.py` honours
  `QGIS_SDK_DEV_SERVER`. Existing projects opt in by adding the `addopts`
  line (or passing `-p qgis_sdk_tools.pytest_plugin`). `CliRuntime` gains
  `start_process`; `FakeCliRuntime` records started processes in
  `.started` and the environments passed to `run_process` in
  `.environments`.
- **Curated services on `PluginContext`.** `layers`, `project`, `settings`,
  `styles`, `algorithms` and `workers` are new optional fields with
  `require_<name>()` accessors; existing constructor calls are unaffected.
  `HostServices.from_context(ctx)` builds the web-view surface over the same
  instances, `NetworkClient.transport` is public, and
  `qgis_sdk.adapters.qgis.native_plugin_context` wires all of them inside QGIS.
  Projects generated by `qgis-sdk new` now carry a `project_layers` action and
  a `build_context` that uses it when a `QgsApplication` is running.
- **`PluginContext` is a class attribute.** The runtime no longer calls
  `plugin_class(context)`; it sets `plugin_class.ctx = context` and calls
  `plugin_class()`. Replace `def __init__(self, ctx): self.ctx = ctx` with a
  bare `ctx: PluginContext` annotation (and `def __init__(self)` if you still
  need one — `self.ctx` is already there). A constructor that keeps the `ctx`
  parameter fails `start()` with a `QgisSdkPluginLifecycleError` naming the
  change. `AlgorithmContext` and `JobContext` are unchanged: they are built
  fresh per invocation/attempt and still arrive through the constructor
  (decision-11, decision-13).
- **Declaration ids and titles are optional.** `@plugin`, `@action`, `@stream`,
  `@algorithm` (removed again in 0.6.0), `@job` and `@provider.algorithm` derive a missing `id=` /
  `title=` from the decorated name (see "Ids and titles default from the name")
  and the class and method decorators accept the bare form. Existing explicit
  declarations are unchanged; `events=` is now the only required keyword of
  `@stream`.
- **`qgis-sdk new --web`.** The scaffold grows a questionnaire and the
  `--web`, `--placement`, `--package-manager`, `--install/--no-install` and
  `--no-input` flags; `ScaffoldOptions` gains `web: WebOptions | None` and
  the plan a `web/` Vite app plus `<plugin>/webview.py` (see "Web UI").
  Without `--web` the plan is unchanged. `web` and `tests` join the reserved
  package names. `CliRuntime` gains `inp`, `interactive` and `run_process`;
  `FakeCliRuntime(input=, interactive=, run_process=)` records spawned
  processes in `.processes`.
- **`qgis-sdk check` and `qgis_sdk.check`.** New non-mutating project check
  with stable diagnostics (`QGIS001`, `ARCH001`, `META00x`, `PROJECT001`,
  `CONFIG001`, `SYNTAX001`); see "Project checks". Commands now receive a
  `qgis_sdk.cli.CliRuntime` through `ctx.obj`; `qgis_sdk.testing` gains
  `FakeCliRuntime`.
- **CLI rename:** the project generator is `qgis-sdk new <directory>`
  (`python -m qgis_sdk new`). `qgis-sdk scaffold` keeps working as a hidden,
  deprecated alias so existing scripts do not break; it will be removed in a
  later minor. The Python API (`qgis_sdk.scaffold`) is unchanged.

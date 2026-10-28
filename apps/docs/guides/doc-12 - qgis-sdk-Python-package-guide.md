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

Declare structure on plain classes; keep behavior in ordinary instance methods:

```python
from dataclasses import dataclass

from qgis_sdk import action, describe, plugin


@dataclass
class RunRequest:
    count: int
    label: str | None = None


@plugin(id="example.tools", title="Example tools")
class Tools:
    @action(id="run", title="Run")
    def run(self, request: RunRequest) -> int:
        return request.count


description = describe(Tools)  # also Tools.describe()
print(description.to_json())
```

`plugin` and `action` attach metadata and a `describe()` convenience method,
then return their original targets. No base class, constructor rewrite, host
imports or runtime registration is required.

### Ids and titles default from the name

Every declaration decorator (`@plugin`, `@action`, `@stream`, `@job`,
`@provider.algorithm`) takes `id=` and `title=` as optional keywords and
derives whichever is missing from the decorated name
([decision-30](../../../backlog/decisions/decision-30%20-%20Derive-declaration-ids-and-titles-from-names-deterministically-never-randomly.md)),
so the class and method decorators also work bare:

```python
@plugin                       # id "field_tools_<6 hex>", title "Field Tools"
class FieldTools:
    @action                   # id "list_layers", title "List layers"
    def list_layers(self) -> list[str]: ...

    @action(id="layers.count")  # explicit id, derived title "Count layers"
    def count_layers(self) -> int: ...
```

- A **class** id (`@plugin`) and a **job** id (`@job`) is the snake_case name
  plus `_` and six hex digits of `sha256("<module>.<qualname>")`. The suffix
  keeps two plugins or jobs that share a name apart without being random: the
  same class in the same module derives the same id on every import, so
  generated clients and the contract fingerprint stay valid until the class
  itself is renamed or moved. Pin `id=` before publishing a contract you do
  not want to track the class name.
- A **provider algorithm** id (`@provider.algorithm`) is the plain snake_case
  function name, without a suffix: the provider is its namespace and refuses a
  duplicate, and the toolbox shows `field_tools:buffer` rather than a hash.
- A **method** id (action, stream) is the plain method name, without a suffix:
  it is already unique inside its class, and the TypeScript client spells it as
  a property (`client.list_layers(...)`), so it stays an identifier. Leading
  underscores are dropped. Use a dotted `id=` to group actions into namespaces.
- A **title** keeps CamelCase words (`FieldTools` -> "Field Tools") and reads a
  snake_case name as a sentence (`list_layers` -> "List layers").
- An explicit `id=` or `title=` is validated when the decorator is called, before
  the class exists, exactly as before; `derive_id` and `derive_title` in
  `qgis_sdk.declarations` expose the conversion for tools that need it.
  `Provider(...)` itself has no class to derive from and keeps requiring both.
### What does `describe_plugin` do, and not do?

`describe_plugin` does not instantiate the class, dispatch handlers, evaluate
properties, or call dataclass default factories. It resolves annotations with
`typing.get_type_hints`, which may evaluate forward references: inspect **trusted
Python code only**, not untrusted modules. Put DTOs in module scope so postponed
annotations resolve normally; function-local forward-reference names are not
reconstructed from vanished local scopes.

Use the same helper for plugins, actions, streams, algorithms, jobs, providers,
surfaces and UI handlers. Decorated targets also have `.describe()`:

```python
from qgis_sdk import describe

plugin_info = describe(Tools)               # also Tools.describe()
action_info = describe(Tools.run)           # also Tools.run.describe()
# describe(buffer) or buffer.describe() for a @provider.algorithm function
print(plugin_info.bindings)                  # registered surfaces and bindings
print(action_info.bindings)                  # stacked toolbar/menu/shortcut
```

The descriptions remain kind-specific: actions carry `request` and `result`,
algorithms have `qualified_id` and `kinds`, and UI handlers expose `wires`.
The existing narrow `describe_plugin`, `describe_algorithm` and `describe_job`
remain available. Plugin, algorithm, job and provider descriptions implement
`Description` with canonical `to_json()`. UI bindings and handler wires are
**local introspection metadata**; they do not appear in the plugin bridge's
`to_dict()`/`to_json()` output and do not change its fingerprint. Standalone
surface and wiring descriptions are not bridge documents.

Adding `.describe()` reserves that name on decorated classes and functions.
An existing author-defined `describe` is not overwritten: decoration fails
with a migration message. Type checkers may not infer the dynamically added
method; `describe(target)` is always available without a dynamic attribute.

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

Each action must be an ordinary synchronous instance method with first parameter
`self`, annotated inputs and an explicit result annotation (`-> None` for no
result). Inputs may be positional-or-keyword or keyword-only; variadic and
positional-only inputs, static/class/property actions, coroutines and generators
are unsupported. Constructor dependencies are not described. The request schema
is an object keyed by parameter name (the example has a `request` property).
Inherited actions follow Python MRO and ordinary overrides; each inspected class
must have its own `@plugin` metadata. Duplicate action IDs are errors.

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
bridge routing and TypeScript generation are separate follow-up work.

## Pure contract layer

The public `qgis_sdk.models`, `qgis_sdk.services`, and `qgis_sdk.core` modules import without QGIS or Qt. Dependencies flow **models ← services ← core**; the pure layers do not import native adapters, bridge transports, testing fakes, or CLI tools. These are contracts, not a runnable plugin or a replacement for PyQGIS.

| Module | Current contract |
| :-- | :-- |
| `declarations` | `@plugin`, `@action`, `@stream`, `describe_plugin` and the shared `describe(target)` dispatcher; plugin, algorithm, job and provider descriptions satisfy `Description` (`id`, `title`, `schema_version`, `to_dict()`, canonical `to_json()`); decorated targets gain `describe()` without wrapping |
| `models` | `QgisSdkError`, `QgisSdkScopeClosedError`, `QgisSdkUnsupportedCapabilityError`, `QgisSdkOptionalDependencyError`, `QgisSdkValidationIssue`, and safe `QgisSdkContractValidationError` metadata; the algorithm requests `BufferRequest` and `CentroidRequest` with their refusals `QgisSdkAlgorithmRejectedError` and `QgisSdkAlgorithmCancelledError`; the parameter aliases `LayerInput`, `CrsInput`, `Metres`, `FileInput(filters=)`, `DirectoryInput()`, `FieldInput(of=)`, `Range(min, max)`, `Colour()` over the markers `LayerParameter`, `CrsParameter`, `MetresParameter`, `FileParameter`, `DirectoryParameter`, `FieldParameter`, `RangeParameter`, `ColourParameter`, the registry `parameter_kinds()`/`ParameterKind`, and the branded `FileRef` with its `FILE_REF` schema |
| `services` | Structural `Notifications`, `ViewControl`, `Progress`, `Cancellation`, `DesktopAccess`, `Layers`, `Project`, `Settings`, `Styles`, `Algorithms`, `Workers` and `Processing` protocols; implementations are supplied by the host or by tests |
| `core` | `PluginContext`, `UiContext`, `AlgorithmContext`, `JobContext`, `ResourceScope`, `PluginRuntime`, and lifecycle errors |
| `algorithms` | `describe_algorithm`, `invoke` and `AlgorithmDescription` for functions declared with `@provider.algorithm`, plus `parameter_kind` - which host parameter an input annotation deserves; input and result schemas come from the same generator the plugin declarations use |
| `processing` | The generated Processing registry (decision-64): `native`, `qgis`, `gdal`, `p3d`, `pdal` modules of `TypedDict` shapes, request classes and `REGISTRY`; `codegen` (the pure emitters), `snapshot` (`core_catalogue()`), `runs` (request coercion and destination allocation); the models (`AlgorithmInfo`, `AlgorithmRun`, `RunResult`, `validate_parameters`) live in `qgis_sdk.models` |
| `jobs` | `@job`, `describe_job`, `JobService`, `JobHandle`, `JobStatus`, and `JobSubscription` - scoped local jobs over the step scheduler, with typed handles and owner-bound delivery |
| `providers` | `Provider` and `@provider.algorithm`, `ProviderDescription`, and `declared_providers` - the `providers = [...]` a `@plugin` class lists |
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
handler therefore writes `self.ctx.project.layer_ids()` and a page calls
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

Create a child scope for each `UiContext`; `view.request_close()` requests closure but does not synchronously dispose the view. Give every `AlgorithmContext` and `JobContext` a fresh child scope plus execution-specific `Progress` and read-only `Cancellation` services. Jobs submitted from a view are view-owned by default; plugin-owned work requires an explicit plugin child scope. `JobContext` also carries the optional `workers` and `network` capabilities, refused by name on access when the host lacks them; the job runtime itself lives in `qgis_sdk.jobs` (see [Scoped jobs](#scoped-jobs)).

The runtime owns the scopes: `scope.on_close(cleanup)` registers synchronous cleanup, `scope.child()` creates an owned scope, and `scope.close()` closes children before local callbacks (last registered first). Closing is idempotent. A child closed on its own stops being owned by its parent. New registrations/children after closure raise `QgisSdkScopeClosedError` (`code="scope_closed"`); reading a capability such as `ctx.desktop` also rejects a disposed scope. If cleanup fails, remaining children and callbacks still run and the failures are raised as an `ExceptionGroup`. Scope closure is **not** proof that an in-flight task stopped; adapters must request cancellation, detach callbacks and wait for safe completion where needed. The scope does not make services thread-safe or automatically revoke references to them.

Only a Desktop runtime may inject `DesktopAccess`. Its `iface` is deliberately typed as opaque `object`: consumers must opt in via `ctx.desktop`, and must not serialize it or expose it through a bridge or worker context. Pure/standalone runtimes leave it absent and raise `QgisSdkUnsupportedCapabilityError` rather than silently fabricating a native capability. Both `QgisSdkScopeClosedError` and `QgisSdkUnsupportedCapabilityError` extend `QgisSdkError`; `code` is available to downstream adapters, but structured bridge errors are not implemented here.

Pure tests check declared import direction throughout the three layers and import the public modules in a fresh subprocess that rejects native imports. This is not a security sandbox or a full dynamic-import/side-effect analyzer; the CLI static checker and real QGIS adapters are separate backlog work.

The package root exports nothing beyond the declarations API, which is what `tests/test_init.py` pins:

```python
import qgis_sdk

print(qgis_sdk.__all__)
# Includes 'describe', 'action', 'plugin', 'toolbar', 'menu' and 'shortcut'.
```

Importing the package with native modules forbidden is the real wiring check, so a placeholder API is no longer needed to prove it.

## Scoped plugin runtime

`PluginRuntime` owns one decorated plain class for the plugin lifetime:

```python
from qgis_sdk import action, plugin
from qgis_sdk.core import PluginContext, PluginRuntime, ResourceScope

@plugin(id="example.tools", title="Example tools")
class Tools:
    ctx: PluginContext           # bound by the runtime; the annotation is for the type checker

    def __init__(self) -> None:
        self.ctx.scope.on_close(lambda: print("disposed"))

    @action(id="run", title="Run")
    def run(self, value: int) -> int:
        return value


context = PluginContext(notifications=..., scope=ResourceScope())
runtime = PluginRuntime(Tools, context)
instance = runtime.start()   # sets Tools.ctx = context, then calls Tools() once
runtime.actions["run"](3)    # read-only action ID -> bound method
runtime.unload()             # closes the owned scope once and removes Tools.ctx
runtime.unload()             # safe no-op
```

The context is a **class attribute, not a constructor argument** (decision-31).
`start()` sets `plugin_class.ctx` to the runtime's `PluginContext` before
constructing the class with no arguments, so `self.ctx` is available everywhere
including `__init__`; `unload()` (and a failed start) removes the attribute
again, so the class is plain outside a running lifecycle and never retains a
closed scope. Annotate `ctx: PluginContext` in the class body for IDEs and type
checkers — it declares the attribute without initialising it, exactly like a
dataclass field. A constructor that still takes `ctx` fails `start()` with a
`QgisSdkPluginLifecycleError` that says so. One class runs under one runtime at
a time; the most recently started runtime owns the attribute. Pass
`PluginRuntime(..., instance_factory=factory)` when a plugin needs custom
dependencies: the factory still receives the context, and `ctx` is already
bound on the class when it runs. Declarations are validated at construction
time, but no author code runs until `start()`. After construction, every declared action must resolve to a callable
on the instance; otherwise `QgisSdkPluginLifecycleError`
(`code="invalid_plugin_lifecycle"`) is raised and startup is rolled back.

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
`pyproject.toml` names the class and the tools derive what QGIS
needs from it:

```toml
[project]
name = "field-tools"
version = "0.1.0"
description = "Field Tools: a minimal qgis-sdk plugin."
authors = [{ name = "Ada", email = "ada@example.test" }]
dependencies = ["qgis-sdk-runtime>=0.6,<0.7"]   # the runtime `build` resolves

[tool.qgis-sdk]
plugin = "field_tools.plugin:FieldToolsPlugin"  # the class QGIS runs
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

classFactory = host("field_tools.plugin:FieldToolsPlugin", placement="dock")
```

It resolves the class (a typo fails by name, with `QgisSdkHostError`),
validates it with `describe_plugin`, and returns a factory. The
`DesktopHost` it makes starts the runtime from `initGui()`, registers the
class's `providers` with Processing, and unloads everything from `unload()`
(safe to repeat). The context comes from one of two places: a
`context_factory(iface)` class attribute on the plugin class when the author
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

`create_class_factory(Tools, context_factory=...)` and
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

A plugin reaches the QGIS Desktop in two ways, both declared on the class and
both headless until a host places them (decisions 45 and 55): a *binding*
puts an action or a surface on the toolbar, under a menu or behind a shortcut,
and a *surface* is a plain `Dialog` or `Dock` subclass whose `build()` returns
the widget to show. Nothing an author writes outside `build()` imports Qt.

```python
from qgis_sdk import action, menu, plugin, shortcut, toolbar
from qgis_sdk.ui import Button, Dialog, Dock, on


@menu("Plugins/Field tools")
class BufferDialog(Dialog):
    title = "Buffer a layer"

    def build(self):
        return Button("buffer", "Buffer 25 m")

    @on("buffer").clicked
    def buffer(self) -> None:
        self.ctx.actions.buffer(layer_id=self.initial["layer_id"], distance=25)


class LayerPanel(Dock, area="left"):
    def build(self): ...


@plugin(id="field_tools", title="Field tools")
class FieldTools:
    surfaces = (BufferDialog, LayerPanel)

    @toolbar(icon="buffer.svg", text="Buffer")
    @shortcut("Ctrl+Alt+B")
    @action
    def open_buffer(self) -> None:
        self.ctx.ui.open(BufferDialog, initial={"layer_id": self.ctx.project.layer_ids()[0]})

    @action
    def buffer(self, layer_id: str, distance: float) -> str: ...
```

**Bindings.** `@toolbar` (bare or `@toolbar(icon="name.svg", text="...")`),
`@menu("Top/Sub")` and `@shortcut("Ctrl+Alt+B")` stack in any order on an
`@action` method and on a `Dialog`/`Dock` subclass, and repeat for a second
place. They are refused with a message on anything else: a `@job` ("bind an
`@action` that submits the job"), a `@stream`, a plain method (`@plugin`
reports it at class creation) or a class that is not a surface. `icon` is a
file name under the package's `icons/` directory, resolved through
`qgis_sdk.resources.icon_path`. `describe_bindings(cls)` is the pure view:
`entries` lists the registered surfaces (in `surfaces` order) then the bound
actions, each with its `bindings`; `typed_without_surface` names bound actions
that take inputs. The unified `describe(cls).bindings` exposes the same view,
and `describe(cls.action).bindings` describes a single action. Binding decorators
on a function need an `@action` declaration before the function can be described;
they can be stacked in either order. Serialized plugin output and
`HOST_FINGERPRINT` do not change: bindings are placement, not contract.

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

**`ctx.ui.open` and `UiContext.actions`.** From an action,
`self.ctx.ui.open(Surface, initial={...})` opens a registered surface (an
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
plugin_class=...)` stands in for the service: `ctx.ui.open(...)` records an
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
plugin's `@stream` methods for the view's lifetime with the request
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
holds - the `PluginContext` of an action, the `JobContext` of a job, or the
`AlgorithmContext` of another algorithm. It reads `algorithms`, `project` and
`scope` from that context, builds the invocation's own `AlgorithmContext`, and
adds the output to `ctx.project` after success:

```python
# inside an @action on a @plugin class
output = invoke(
    buffer, self.ctx, layer_id=source_id, distance=500.0, crs="EPSG:3857"
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

A provider is both the namespace an algorithm is declared in and what makes it
*visible*. A `@plugin` class lists the providers it owns, and the runtime does
the rest:

```python
from qgis_sdk import plugin
from qgis_sdk.core import PluginContext


@plugin(id="field_tools", title="Field tools")
class FieldTools:
    ctx: PluginContext

    providers = [tools]  # a tuple also works; Ruff's RUF012 prefers one
```

While the plugin runs inside QGIS, `PluginRuntime.start()` registers every
listed provider with `QgsApplication.processingRegistry()` through the
context's `processing` capability (the native context built by
`native_plugin_context` carries it), so `field_tools:buffer` appears in the
toolbox, the modeler and `processing.run(...)`; `unload()` removes them again,
and a start that fails removes whatever it had registered. Over the fakes or a
standalone Qt host the context has no `processing`, and the same class
registers nothing. Two plugins that list providers with the same id are
refused by name when the second one starts. `runtime.providers` and
`runtime.registered_providers` tell a host or a test what is listed and what is
currently advertised; `describe_plugin` does not change, because a provider is
a host-side registration rather than a page-callable operation.

Declaration is validated **when it happens**: the function must take the
`AlgorithmContext` first, every input must map to a host parameter kind, the
result must be the produced `VectorLayerInfo`, and the id must be unique inside
the provider. A mistake fails at import time, not on the first run, and a
refused function keeps no marker. `providers = ...` that is not a list or tuple
of `Provider` instances, or lists one id twice, is refused when the
`PluginRuntime` is built.

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
- **Subscriptions.** `@stream` on the plugin or `register_stream(operation,
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
$ qgis-sdk bridge generate --plugin my_plugin.bridge:MyPlugin
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
- **Streams come from the same declarations (decision-28).** `@stream(id=...,
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
made function-based and
[decision-21](../../../backlog/decisions/decision-21%20-%20Bound-job-ownership-and-refuse-unsafe-runtime-replacement.md)
scoped: a job is a decorated plain function whose first parameter is the
`JobContext` the runtime injects and whose remaining keyword parameters are
typed the way an action's are, submission is `bind(fn).delay(**inputs)` and
nothing else, and the handle you get back is typed end to end. `qgis_sdk.jobs`
is QGIS-free; it runs on the step scheduler and a host drives
`JobService.tick()` from whatever event loop it already has.

```python
from dataclasses import dataclass

from qgis_sdk.core import JobContext
from qgis_sdk.jobs import job


@dataclass(frozen=True)
class SumResult:
    total: int


@job(id="demo.sum", title="Add two numbers")
async def add(ctx: JobContext, left: int, right: int = 0) -> SumResult:
    def work() -> int:  # runs on a worker thread, reports from there
        ctx.progress.report(0.5)
        return left + right

    total = await ctx.workers.offload(work)
    return SumResult(total)


handle = ctx.jobs.bind(add).delay(left=1, right=2)
handle.on_progress(lambda fraction: bar.setValue(int(fraction * 100)))
handle.on_success(lambda result: label.setText(str(result.total)))
handle.on_failure(lambda error: label.setText(str(error)))
handle.on_cancelled(lambda: label.setText("cancelled"))
```

The decorator adds `describe()` but does not wrap `add`, so a unit
test calls `add(fake_context, left=1, right=2)` directly. A bare `@job`
derives the id and title from the function name the way `@plugin` does for a
class; `async def` is allowed and suspends on the scheduler at every `await`,
a plain `def` runs in one step on the driving thread, a generator is refused.
`ctx.jobs.delay(add, left=1, right=2)` is the one-call spelling of `bind` then
`delay`; there is no ambient `add.delay(...)`, because the owner is always
explicit (decision-21).

### What is checked before a job runs?

`describe_job(add)` returns the `JobDescription` (`id`, `title`, the parameter
names, which are required, the result type, and the object schema of the
inputs plus the result schema from the declarations generator) without calling
the function; a function without `@job`, without a `JobContext` first
parameter, with an unannotated parameter or without a declared result is
refused at bind time with `QgisSdkDeclarationError`, and so is a class
(the class form was removed in 0.6.0 - see the migration note below).
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
it at a suspension point (or before it ever started). A job that finishes
anyway reports `succeeded`, honestly. Work that never reaches a suspension
point stays `running`; `quiesce()` names it as a blocker instead of pretending
it stopped, and nothing kills a thread.

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
from qgis_sdk.adapters.qgis import ThreadPoolWorkers
from qgis_sdk.jobs import JobService

jobs = JobService(plugin_scope, workers=ThreadPoolWorkers(plugin_scope), network=network)
timer.timeout.connect(jobs.tick)  # the GUI thread's event loop drives delivery
```

`ThreadPoolWorkers` runs offloaded callables on a `QThreadPool` and reports
through the scheduler's `Handoff`; a callable still queued when its job is
cancelled reports without running, a callable already running is left to
finish. In tests, `qgis_sdk.testing.FakeWorkers` holds offloaded callables
until the test says `run_one()` / `run_all()`, which is how the suite stages
races between workers, ticks and disposal. `tests/features/scoped_jobs.feature`
states the rules as scenarios (bound by `tests/test_jobs_bdd.py`),
`tests/test_jobs.py` holds the examples, `tests/test_jobs_properties.py` a
Hypothesis state machine over submit / tick / cancel / worker reports / close
view / close listener / close plugin, and `tests/test_jobs_native.py` the
thread evidence over a real pool and a real Qt event loop.

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
is one `@plugin` class with two `@action`s and a `ctx: PluginContext`
annotation, and imports no Qt or QGIS module. `tests/test_plugin.py` runs
`host("<plugin>.plugin:<Class>")(None)` through start, action and unload
without QGIS. Tests pin that the generated project imports nothing native.

### Choosing Desktop or standalone Qt mode

The README the scaffold writes teaches both modes; they differ in one thing, whether a host
`iface` exists:

| Mode | How it runs | What the SDK sees |
| :-- | :-- | :-- |
| Desktop | copy `<plugin>/` into a profile's `python/plugins/` and enable it under Plugins, Manage and Install Plugins, or launch `qgis --profiles-path <dir> --profile <name>` | `iface` is present, so `context.desktop` succeeds and messages reach the real message bar |
| Standalone Qt | call `host("<plugin>.plugin:<Class>")(None)` from a plain Qt application or the starter tests, with `QT_QPA_PLATFORM=offscreen` for a display-free run | no `iface`, so reading `context.desktop` raises `QgisSdkUnsupportedCapabilityError` (`code="unsupported_capability"`) instead of inventing a host, and informational messages are dropped |

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
`buffer` action through `invoke(algorithms.buffer_layer, self.ctx, ...)`.
`tests/test_plugin.py` gains a fourth test that runs the function over
`FakeLayers`/`FakeAlgorithms`/`FakeProject` and asserts the exact
`BufferRequest` Processing would have received. `build` renders
`hasProcessingProvider=yes` from the declaration, and the
`QGIS_SDK_SCAFFOLD_DESKTOP=1` harness scaffolds this variant so real QGIS
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
toolbar that calls `self.ctx.ui.open(PingDialog, initial={"value": 7})`,
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
```

Every finding is a `Diagnostic` with a stable `rule`, a root-relative `path`,
1-based `line`/`column` (`0` for whole-file findings), a `message` and a
`remediation`; text output prints `path:line:col: RULE message` with the
remediation indented beneath, and ends with `checked N files: ...`. The exit
code is `1` when any error was found and `2` when the path is not a directory.

| Rule | Meaning |
| :-- | :-- |
| `QGIS001` | `qgis`, `PyQt5/6` or `PySide2/6` is imported when the module loads: module scope, a class body, a `try`, a `with` or a module-level `if` all count. Imports inside a function and under `if TYPE_CHECKING:` are fine. |
| `ARCH001` | `qgis_sdk.adapters.qgis` (the PyQGIS-backed adapters) is imported when a pure module loads; let `host()` build the context, or reach the adapter inside the function that runs in QGIS. |
| `PROJECT001` | No directory with an `__init__.py` under the root (other than `tests/`). |
| `PROJECT002` | No `pyproject.toml`, or no `[tool.qgis-sdk] plugin = "<package>.plugin:<Class>"` in it; `build` and `dev` derive `metadata.txt` and `classFactory` from that line (decision-43). |
| `CONFIG001` | `[tool.qgis-sdk]`, `[tool.qgis-sdk.check]`, `[tool.qgis-sdk.web]` or `[tool.qgis-sdk.metadata]` in `pyproject.toml` is malformed (`plugin` not `pkg.module:Class`, `placement` not `dock`/`dialog`, `grants` not a list of strings, a passthrough value that is not a scalar). |
| `META001` | The plugin package has a hand-written `metadata.txt`; `build` renders it, so delete the file (or move extra keys under `[tool.qgis-sdk.metadata]`). |
| `META002` | `pyproject.toml` lacks a key `metadata.txt` needs: `[project] name`, `version`, `description`, `authors[0].name`/`.email`, or `[tool.qgis-sdk] qgis-minimum-version`. |
| `ENTRY002` | A module of the plugin package defines or imports `classFactory`; `build` and `dev` bind it through `host()`. |
| `GRANT001` | `[tool.qgis-sdk.web] grants` names something that is neither a host grant (`layers.read`, selecting every operation that needs it) nor a host operation id (`project.layer_ids`); see `qgis_sdk.bridge.host.granted_operations`. |
| `VERSION003` (warning) | `pyproject.toml` declares no `qgis-sdk-runtime` (or `qgis-sdk`) requirement; `build` ships the installed runtime and says so in the NOTICE. |
| `VERSION004` | The installed `qgis-sdk-runtime` does not satisfy the project's requirement. The finding names both and the `pip install` line; the tools never install. |
| `UI001` | A method of a `Dialog`/`Dock` subclass constructs an interactive Qt or QGIS widget (`QPushButton`, `QLineEdit`, `QSpinBox`, `QgsMapLayerComboBox`, ... - `qgis_sdk_tools.check.ui.INTERACTIVE_WIDGETS`) and never calls `setObjectName` on the name holding it; a constructor passed straight to `addWidget` is flagged too. Name it, or use a `qgis_sdk.ui` component, which names its widget (`form/<field>`, `buttons/<name>`). |
| `UI002` | A `Dialog`/`Dock` subclass with `ui = "file.ui"` has an `@on(name)` whose `name` is not an `objectName` the Designer file declares, or the file is not next to the module. The wiring would refuse the surface when it opens; the finding lists the names the file does declare. |
| `UI003` | A method carrying `@toolbar`/`@menu`/`@shortcut` and `@action` takes inputs beyond `self`; a button collects nothing. Drop the inputs, or bind a surface that collects them and calls `self.ctx.actions.<id>(...)`. |
| `UI004` (warning) | A module of the plugin package that is *declared native* still imports `qgis.PyQt`, `PyQt5/6` or `PySide2/6` when it loads: the exemption lifts `QGIS001`, but Qt at module level defeats the fakes (`build_surface`, `ui_snapshot`) and `check`'s inspection of that module. Keep Qt inside `build()`; the catalogue needs no Qt import. |
| `UI005` | The declarative form, read statically: `@on(attribute)` in a `Dialog`/`Dock` subclass names a class attribute that is a string, a number or a literal container rather than a component, or a bare name the class never binds; or a `Custom` declared on the class holds a widget built when the class is defined (`Custom(widget=QLabel(...))`), which cannot be copied for each window. Assign a catalogue component to the attribute (or pass the `objectName` as a string), and give `Custom` the widget class or a factory. A call the checker cannot see into and a module-level name are left to the host. |
| `ICON001` | `@toolbar(icon="...")` names something that is not a file under `<package>/icons/` (a bare file name is required). |
| `SYNTAX001` | A file does not parse. |
| `VERSION001` | `pyproject.toml` pins `qgis-sdk-runtime` (or the `qgis-sdk` kit, which installs the runtime at the same number) in `project.dependencies`, an extra or a dependency group, and no version the pin admits lies in the runtime range this `qgis-sdk-tools` release was tested with (its own `qgis-sdk-runtime>=X,<Y` requirement). Release segments only; `!=` is ignored; a specifier the arithmetic does not know is never reported. Skipped when the range cannot be read. |
| `VERSION002` | A TypeScript file starting with `// Generated by qgis-sdk. Do not edit.` declares a `PLUGIN_DESCRIPTION_SCHEMA_VERSION` or `HOST_SCHEMA_VERSION` other than the one this release generates; regenerate with `qgis-sdk bridge generate`. `node_modules` is never read. |

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

## Building an installable ZIP: `qgis-sdk build`

`qgis-sdk build [PATH] [--out DIR] [--no-web] [--json]` writes
`dist/<plugin>-<version>.zip` (version from `[project] version`) for Plugins >
Manage and Install Plugins > *Install from ZIP* (decision-8: the command is
argument parsing over `qgis_sdk_tools.bundle.build_plugin`). In order:

1. **Validate.** `check_project` runs first - the same rules and output as
   `qgis-sdk check`, so a project without `[tool.qgis-sdk] plugin`
   (`PROJECT002`), with a hand-written `metadata.txt` (`META001`) or
   `classFactory` (`ENTRY002`), or whose installed runtime misses its
   requirement (`VERSION004`) is refused - plus build-only rules:
   `DEP001` for a top-level import that neither the standard library,
   QGIS/Qt (`qgis`, `PyQt5/6`, `PySide2/6`, `osgeo`, `processing`), the SDK
   runtime nor the plugin provides, and for any `qgis_sdk_tools` import;
   `DEP002` for `qgis_sdk.testing`; `WEB001` when a web project has no
   built page. Any error refuses the build (exit 1, nothing written). A
   dependency every target QGIS ships is declared as
   `[tool.qgis-sdk.build] external = ["numpy"]`.
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
   key QGIS requires plus `hasProcessingProvider` from the class's
   `providers` and the `[tool.qgis-sdk.metadata]` passthrough; and, appended
   to `<plugin>/__init__.py`, `classFactory = host("<spec>", placement=...,
   grants=...)` importing `host` from the vendored runtime. The plugin
   class is imported once, in isolation, to read its title and providers
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
(`none` / `built` / `prebuilt`) and the declared externals; `--json` prints
its `to_json()`.

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

## Next minor (unreleased) migration notes

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

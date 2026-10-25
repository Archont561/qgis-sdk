---
id: doc-12
title: qgis-sdk Python package guide
type: guide
created_date: '2026-10-24 21:20'
---
# qgis-sdk Python package guide

The reference prose for the `qgis-sdk` Python package. It used to live in
`packages/qgis-sdk-python/README.md`; [decision-29](../../decisions/decision-29%20-%20Keep-READMEs-minimal-and-hold-reference-prose-in-backlog-guides-until-the-docs-site.md)
moved it here, where it is the source the documentation site
([TASK-43](../../tasks/task-43%20-%20Publish-a-Starlight-documentation-site-from-the-backlog-guides.md))
will render. The headings dropped the task tags they carried in the README;
the records that landed each surface are TASK-2 (declarations), TASK-11 (pure
contract layer), TASK-24 (runtime and Desktop adapter), TASK-3 (native forms),
TASK-14 (algorithms), TASK-39 (providers), TASK-4 with decisions 26 and 27
(bridge host side, generated client, host surface), TASK-17 and decision-28
(generated client and streams), TASK-5 and decision-4 (networking), TASK-1
(scaffold), TASK-27 and TASK-28 (release
policy and migration notes, TASK-29 for 0.3.0, TASK-30 for 0.4.0). Status at
the time of writing: Python `0.4.0` stamped at the m-3 close; the bridge stays
at `0.3.0`, unchanged since its rename release.

Companion guides: [doc-13](doc-13%20-%20qgis-sdk-TypeScript-package-guide.md)
(TypeScript bridge) and [doc-14](doc-14%20-%20Workspace-development-qualification-harnesses-and-evidence.md)
(workspace tooling, harnesses and qualification evidence).

## Installation

Install from [PyPI](https://pypi.org/project/qgis-sdk/) or from the [`prefix.dev` Conda channel (`archont561/archont561`)](https://prefix.dev/channels/archont561/packages/qgis-sdk-python):

```sh
pip install qgis-sdk
# or with the optional Pydantic controlled-deployment adapter:
pip install "qgis-sdk[controlled-deployment]"
# or in a Pixi workspace via the prefix.dev Conda channel:
pixi add --channel https://prefix.dev/archont561/archont561 qgis-sdk
```

The companion TypeScript package [`@archont561/qgis-sdk`](https://www.npmjs.com/package/@archont561/qgis-sdk) is published on npm and [GitHub Packages](https://github.com/Archont561/qgis-sdk/pkgs/npm/qgis-sdk); the bridge guide is [doc-13](doc-13%20-%20qgis-sdk-TypeScript-package-guide.md).

## Declarations

Declare structure on plain classes; keep behavior in ordinary instance methods:

```python
from dataclasses import dataclass

from qgis_sdk import action, describe_plugin, plugin


@dataclass
class RunRequest:
    count: int
    label: str | None = None


@plugin(id="example.tools", title="Example tools")
class Tools:
    @action(id="run", title="Run")
    def run(self, request: RunRequest) -> int:
        return request.count


description = describe_plugin(Tools)
print(description.to_json())
```

`plugin` and `action` attach metadata and return their original targets. No base
class, constructor rewrite, host imports or runtime registration is required.

### Ids and titles default from the name

Every declaration decorator (`@plugin`, `@action`, `@stream`, `@algorithm`,
`@job`, `@provider.algorithm`) takes `id=` and `title=` as optional keywords and
derives whichever is missing from the decorated name
([decision-30](../../decisions/decision-30%20-%20Derive-declaration-ids-and-titles-from-names-deterministically-never-randomly.md)),
so the class and method decorators also work bare:

```python
@plugin                       # id "field_tools_<6 hex>", title "Field Tools"
class FieldTools:
    @action                   # id "list_layers", title "List layers"
    def list_layers(self) -> list[str]: ...

    @action(id="layers.count")  # explicit id, derived title "Count layers"
    def count_layers(self) -> int: ...
```

- A **class** id is the snake_case class name plus `_` and six hex digits of
  `sha256("<module>.<qualname>")`. The suffix keeps two plugins, algorithms or
  jobs that share a class name apart without being random: the same class in
  the same module derives the same id on every import, so generated clients and
  the contract fingerprint stay valid until the class itself is renamed or
  moved. Pin `id=` before publishing a contract you do not want to track the
  class name.
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
`describe_plugin` does not instantiate the class, dispatch handlers, evaluate
properties, or call dataclass default factories. It resolves annotations with
`typing.get_type_hints`, which may evaluate forward references: inspect **trusted
Python code only**, not untrusted modules. Put DTOs in module scope so postponed
annotations resolve normally; function-local forward-reference names are not
reconstructed from vanished local scopes.

`describe_algorithm` and `describe_job` follow the same rules, and
`qgis_sdk.declarations.describe(cls)` picks the right one from the class's
decorator marker when a tool does not know which kind it holds. All four
descriptions share the `Description` protocol, so one `to_json()` canonical form
(sorted keys, compact separators, no NaN) feeds the bridge generator's
fingerprint and every CLI dump.

### Version 1 description contract

The public `PluginDescription` contains `schema_version: 1`, `id`, `title`, and
an action tuple. Each `ActionDescription` contains `id`, `title`, `handler` (a
Python binding name), `request`, and `result`. `to_dict()` returns an independent
JSON-compatible value; `to_json()` sorts keys and uses compact JSON. Actions sort
by ID, not discovery order. The schema version is independent of package versions
and future bridge protocol versions. Consumers must reject unsupported versions;
no compatibility negotiation or reader-extension policy is implemented here.

Request/result schemas use the JSON Schema 2020-12 keyword subset `type`,
`properties`, `required`, `additionalProperties`, `anyOf`, `enum`, `items`,
`minimum`, and `maximum`. Supported annotations are `str`, `bool`, `float`, `int`,
`None`, parameterized `list[T]`, unions (including nullable unions), JSON-valued
`Literal` (strings, safe integers, booleans, null), and nonrecursive dataclasses.
Integers are bounded to ±9007199254740991, consistent with ADR-22. `Any`, arbitrary
host/native objects, mappings, recursive DTOs, and `Annotated` metadata (including
backend-specific constraints in the test-only spike sample) are rejected rather
than silently weakened. No validation dependency or runtime backend is selected.

Each action must be an ordinary synchronous instance method with first parameter
`self`, annotated inputs and an explicit result annotation (`-> None` for no
result). Inputs may be positional-or-keyword or keyword-only; variadic and
positional-only inputs, static/class/property actions, coroutines and generators
are unsupported. Constructor dependencies are not described. The request schema
is an object keyed by parameter name (the example has a `request` property).
Inherited actions follow Python MRO and ordinary overrides; each inspected class
must have its own `@plugin` metadata. Duplicate action IDs are errors.

A default makes an input omittable, not nullable; only a union with `None` makes
it nullable. Dataclass request fields without defaults are required; result
writer schemas require **all** dataclass fields, including defaulted fields.
Defaults are not executed, validated, or emitted as schema values. Unknown object
properties are disallowed. These are structural writer/request schemas, not an
extensible result-reader policy or a serializer for result instances. Runtime
validation must additionally reject nonfinite numbers and implement ADR-22's
explicit integer normalization; JSON Schema alone is not a Python validator.

Invalid declarations raise `QgisSdkDeclarationError` (a `QgisSdkError` with code
`invalid_declaration`), naming the action/binding/field where applicable. IDs must
match `[a-zA-Z][a-zA-Z0-9_.-]*` and titles must be nonblank strings. The public API
is experimental 0.x. Runtime dispatch, lifecycle hooks, native UI declarations,
bridge routing and TypeScript generation are separate follow-up work.

## Pure contract layer

The public `qgis_sdk.models`, `qgis_sdk.services`, and `qgis_sdk.core` modules import without QGIS or Qt. Dependencies flow **models ← services ← core**; the pure layers do not import native adapters, bridge transports, testing fakes, or CLI tools. These are contracts, not a runnable plugin or a replacement for PyQGIS.

| Module | Current contract |
| :-- | :-- |
| `declarations` | `@plugin`, `@action`, `@stream`, `describe_plugin`, and the shared describer surface the other declaration layers build on: `describe(cls)` dispatches on the `@plugin`/`@algorithm`/`@job` marker, and every description (`PluginDescription`, `AlgorithmDescription`, `JobDescription`, `ProviderDescription`) satisfies the `Description` protocol (`id`, `title`, `schema_version`, `to_dict()`, canonical `to_json()`); decorators attach metadata without wrapping the class (TASK-2, TASK-49) |
| `models` | `QgisSdkError`, `QgisSdkScopeClosedError`, `QgisSdkUnsupportedCapabilityError`, `QgisSdkOptionalDependencyError`, `QgisSdkValidationIssue`, and safe `QgisSdkContractValidationError` metadata; the algorithm requests `BufferRequest` and `CentroidRequest` with their refusals `QgisSdkAlgorithmRejectedError` and `QgisSdkAlgorithmCancelledError` |
| `adapters.pydantic` | Optional controlled-deployment adapter; Pydantic is imported only when the adapter is constructed |
| `adapters.pydantic_types` | Explicit Pydantic field annotation for finite JavaScript-safe integers |
| `services` | Structural `Notifications`, `ViewControl`, `Progress`, `Cancellation`, `DesktopAccess`, `Layers`, `Project`, `Settings`, `Styles`, `Algorithms`, and `Workers` protocols; implementations are supplied by the host or by tests |
| `core` | `PluginContext`, `UiContext`, `AlgorithmContext`, `JobContext`, `ResourceScope`, `PluginRuntime`, and lifecycle errors |
| `algorithms` | `@algorithm`, `describe_algorithm`, `invoke`, and `AlgorithmResult`; request and result schemas come from the same generator the plugin declarations use (TASK-14) |
| `jobs` | `@job`, `describe_job`, `JobService`, `JobHandle`, `JobStatus`, and `JobSubscription` - scoped local jobs over the step scheduler, with typed handles and owner-bound delivery (TASK-15) |
| `providers` | `Provider` and `@provider.algorithm` registration, plus `parameter_kinds` - which host parameter each request field deserves (TASK-39) |
| `reference` | `BufferLayer` and `CentroidLayer`, the two operations the reference workflow runs (decision-19) |
| `ui` | `form_fields` and `coerce_values` - the QGIS-free rules that turn a declared action into renderable fields and submitted values back into Python types (TASK-3) |

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
    ctx.require_native()
except QgisSdkUnsupportedCapabilityError as error:
    assert error.code == "unsupported_capability"
    assert error.capability == "desktop"
```

`PluginContext` is plugin-lifetime state. Beside `notifications` and `scope` it
carries the curated services as optional fields — `layers`, `project`,
`settings`, `styles`, `algorithms`, `workers`, plus `desktop` and `network` —
the very Protocols the web-view host surface wraps (decision-27, decision-32).
Each optional one has a `require_<name>()` that raises
`QgisSdkUnsupportedCapabilityError(capability=<name>)` on a host that did not
supply it, and every one of them refuses on a closed scope. A handler therefore
writes `self.ctx.require_project().layer_ids()` and a page calls
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
context owned by that scope; the scaffold's `build_context` calls it whenever a
`QgsApplication` is running and falls back to a notifications-only context in a
bare interpreter, which is what its starter tests exercise.

Create a child scope for each `UiContext`; `view.request_close()` requests closure but does not synchronously dispose the view. Give every `AlgorithmContext` and `JobContext` a fresh child scope plus execution-specific `Progress` and read-only `Cancellation` services. Jobs submitted from a view are view-owned by default; plugin-owned work requires an explicit plugin child scope. `JobContext` also carries the optional `workers` and `network` capabilities with `require_workers()` / `require_network()` refusals; the job runtime itself lives in `qgis_sdk.jobs` (see [Scoped jobs](#scoped-jobs)).

The runtime owns the scopes: `scope.on_close(cleanup)` registers synchronous cleanup, `scope.child()` creates an owned scope, and `scope.close()` closes children before local callbacks (last registered first). Closing is idempotent. A child closed on its own stops being owned by its parent. New registrations/children after closure raise `QgisSdkScopeClosedError` (`code="scope_closed"`); `require_native()` also rejects a disposed scope. If cleanup fails, remaining children and callbacks still run and the failures are raised as an `ExceptionGroup`. Scope closure is **not** proof that an in-flight task stopped; adapters must request cancellation, detach callbacks and wait for safe completion where needed. The scope does not make services thread-safe or automatically revoke references to them.

Only a Desktop runtime may inject `DesktopAccess`. Its `iface` is deliberately typed as opaque `object`: consumers must opt in via `PluginContext.require_native()`, and must not serialize it or expose it through a bridge or worker context. Pure/standalone runtimes leave it absent and raise `QgisSdkUnsupportedCapabilityError` rather than silently fabricating a native capability. Both `QgisSdkScopeClosedError` and `QgisSdkUnsupportedCapabilityError` extend `QgisSdkError`; `code` is available to downstream adapters, but structured bridge errors are not implemented here.

Pure tests check declared import direction throughout the three layers and import the public modules in a fresh subprocess that rejects native imports. This is not a security sandbox or a full dynamic-import/side-effect analyzer; the CLI static checker and real QGIS adapters are separate backlog work.

The package root exports nothing beyond the declarations API, which is what `tests/test_init.py` pins:

```python
import qgis_sdk

print(qgis_sdk.__all__)
# ['ActionDescription', 'PluginDescription', 'QgisSdkDeclarationError', 'action', 'describe_plugin', 'plugin']
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

## Desktop lifecycle adapter

A QGIS plugin package can expose the adapter through its normal entry point:

```python
from qgis_sdk.adapters.desktop import create_class_factory

classFactory = create_class_factory(Tools, context_factory=build_context)
```

`build_context(iface)` returns the typed `PluginContext` for that host,
including any `DesktopAccess` service — in a Desktop host, usually
`native_plugin_context(...)` from `qgis_sdk.adapters.qgis` (see above). The adapter imports neither QGIS nor Qt,
never serializes `iface`, calls `runtime.start()` from `initGui()` and
`runtime.unload()` from `unload()`. Repeated `unload()` calls are safe. It is
lifecycle glue, not a complete plugin template: plugin metadata, native action
registration, menus and dialogs remain the caller's or later tasks' work.

The headless harnesses and the real-Desktop evidence for this adapter are in [doc-14](doc-14%20-%20Workspace-development-qualification-harnesses-and-evidence.md).

## Native forms and handler dispatch

A declared action already describes its inputs as JSON Schema and its handler as a
*binding name*, never a callable, so nothing in the description can carry Python
code. `qgis_sdk.ui` turns that description into renderable fields, and
`qgis_sdk.adapters.qgis.NativeForms` builds the Qt dialog and dispatches the
validated values:

```python
from typing import Annotated
from qgis_sdk import action, plugin
from qgis_sdk.adapters.qgis import NativeForms
from qgis_sdk.models import LayerInput

@plugin(id="demo:forms", title="Form demo")
class Demo:
    @action(id="demo:buffer", title="Buffer layer")
    def buffer(self, layer_id: Annotated[str, LayerInput()], distance: float) -> str:
        return layer_id

forms = NativeForms(runtime)          # needs a started runtime
result = forms.run("demo:buffer")     # dialog, coercion, handler; None when cancelled
```

The split is deliberate. `form_fields` maps a schema (plus the author's
`Annotated` markers) to a widget *family* - text, integer, number, metres, layer,
CRS, boolean, choice - and refuses anything else, so the adapter never has to
guess a widget at run time. `coerce_values` is strict in the other direction:
`"3"` becomes `3` for an integer field, `"three"` is refused with the field name
and the expected type, and the submitted value is never echoed because a field
can hold a path or a credential. Optional fields that were not submitted are
absent from the result, so the handler's own defaults apply.

Widget selection follows `models.parameters`: an `Annotated[str, LayerInput()]`
becomes a vector-layer combo box, `CrsInput()` a CRS selector, `Metres()` a
spin box labelled in metres, a `Literal` a combo box, and the rest the obvious
primitive widget.

The escape hatch is not a second API: `PluginRuntime.actions` is keyed by action
id and holds ordinary bound methods, so conventional PyQt code can build its own
dialog and call `NativeForms.dispatch(action_id, values)` - or the handler
directly - with the same validation.

## Processing algorithms and safe outputs

`qgis_sdk.algorithms` is the authoring surface decision-11 settled on: one decorated plain class per algorithm, one typed `run(inputs) -> Result` entry point, and a constructor-injected `AlgorithmContext`. Describing an algorithm never constructs it, and every invocation constructs a **fresh** author instance and a **fresh** context over a child scope that is closed again when the invocation ends:

```python
from pathlib import Path

from qgis_sdk.algorithms import describe_algorithm, invoke
from qgis_sdk.core import ResourceScope
from qgis_sdk.models import BufferRequest
from qgis_sdk.reference import BufferLayer

print(describe_algorithm(BufferLayer).to_dict()["inputs"]["schema"]["required"])
# ['layer_id', 'distance_metres', 'working_crs']

scope = ResourceScope()
result = invoke(
    BufferLayer,
    BufferRequest(layer_id=source_id, distance_metres=500.0, working_crs="EPSG:3857"),
    algorithms=algorithms,  # qgis_sdk.services.Algorithms
    project=project,        # qgis_sdk.services.Project
    scope=scope,
)
# invoke already added result.output to the project - after success only.
```

The request schemas come from the same `qgis_sdk.declarations` generator that describes plugin actions, so an algorithm's inputs are held to one documented typing subset and are bridge-eligible for TASK-17.

**Non-destructive by construction (decision-19).** `Algorithms.execute` writes a *new* output and opens it as a layer the runtime owns; no method edits the source dataset. A run that fails deletes its own temporary directory before re-raising, so no partial output survives a failure, and the intermediate reprojection a buffer needs is scaffolding that never outlives the run either. `invoke` adds the output to the project only after the operation succeeded, the result matched its declared type *and* cancellation was not requested in between; a failure or cancellation at any point leaves the project as it was.

**Explicit CRS and units where a distance is involved.** `BufferRequest` requires `working_crs` and `distance_metres`; the native backend refuses a working CRS that is geographic (a distance there would be degrees) or whose units are not metres, instead of converting behind the caller's back. `CentroidRequest` has no distance and therefore no working CRS: decision-19 requires a projected CRS *where the operation has one*, not everywhere.

Two honest limits of this slice: cancellation is observed at phase boundaries (before the operation, and after it before the project is touched), not by aborting a native operation mid-flight; and an algorithm class on its own is described and invoked directly - grouping comes from a provider, below.

## Providers: algorithms in the QGIS Processing toolbox

An algorithm class is useful on its own; a provider is what makes it *visible*. Declare one object, register algorithms on it the way a route is registered on an app, and give it to the QGIS adapter:

```python
from dataclasses import dataclass
from typing import Annotated

from qgis_sdk.models import LayerInput, Metres, VectorLayerInfo
from qgis_sdk.providers import Provider

mine = Provider(id="my.plugin", title="My plugin")


@dataclass(frozen=True, slots=True)
class SmoothRequest:
    layer_id: Annotated[str, LayerInput()]      # a layer picker in the dialog
    tolerance: Annotated[float, Metres()]       # a spin box labelled in metres


@dataclass(frozen=True, slots=True)
class SmoothResult:
    output: VectorLayerInfo


@mine.algorithm(id="smooth", title="Smooth geometries", group="Geometry")
class Smooth:
    def __init__(self, ctx):  # AlgorithmContext, fresh per invocation
        self.ctx = ctx

    def run(self, inputs: SmoothRequest) -> SmoothResult:
        ...
```

```python
from qgis_sdk.adapters.qgis import register_provider

bridge = register_provider(
    mine, layers=layers, algorithms=algorithms, project=project, scope=scope
)
# "my.plugin:smooth" is now in the toolbox, the modeler and `processing.run`
bridge.unregister()  # ...if the plugin unloads
```

Registration is validated **when it happens**: the class must describe, every request field must map to a host parameter, and the id must be unique inside the provider. A mistake fails at import time, not on the first run.

`Annotated` markers say what a field *means* to the host while the wire schema keeps describing the stored value: `LayerInput()` makes a field a vector-layer picker (the picked layer is opened through the same `Layers` service, so it arrives as an owned layer id), `CrsInput()` makes it a CRS chooser, and `Metres()` gives a distance a metre-labelled, non-negative spin box. Plain `str`/`int`/`float`/`bool` fields become text, integer, double and boolean parameters. Anything else - a nested dataclass, a list, a `Literal` - is refused at registration with the field name and the supported kinds.

The bridge copies the produced layer's features into the destination the user chose, so the temporary output the operation wrote stays the SDK's business and the source dataset is never touched. `FlagNoThreading` is deliberate: worker-thread execution of these adapters has not been qualified, so the bridge asks QGIS to run on the thread it was qualified on rather than claim a safety it cannot demonstrate.

`providers` and the bridge stay inside the same rules as the rest of the layer: no QGIS import in `qgis_sdk.providers`, and the native bridge is only importable where PyQGIS exists.

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

### Generated TypeScript client

The declarations a plugin already writes are the only source of its client. One
command renders the value types, the operation map, the runtime validators and
`createOperations(client)` from them - no QGIS, no Qt, no handler ever runs:

```console
$ qgis-sdk bridge generate --plugin my_plugin.bridge:MyPlugin --out web/src/bridge.ts
wrote web/src/bridge.ts
```

- **Deterministic.** The same declarations produce the same bytes, so the file is
  reviewed and committed like source, and CI regenerates it and fails on any
  difference (`--check` reports the drift without writing).
- **A description works too.** `--plugin` imports `module:Attribute` from the
  working directory; `--description plugin-description.json` does the same from a
  description a host already shipped, for a frontend with no Python at hand.
- **Closed subset.** A schema outside the declaration subset (`$ref`, an object
  inside a union) fails the build instead of emitting `any`.
- **Strict in, lenient out.** A generated validator refuses unknown arguments and
  accepts a response that gained a field, so a newer host does not break an older
  view.
- **Streams come from the same declarations (decision-28).** `@stream(id=...,
  events={"data": SiteChange, "progress": ScanProgress})` marks a method that
  returns an iterator of `StreamEvent`s; its request schema is bound like an
  action's, and each declared event kind is a dataclass schema. The runtime
  registers the stream under its id in the same namespace as the actions, the
  host advertises the event schemas in the handshake and refuses to emit an
  event the stream did not declare (the subscription ends with `error`), and the
  generated client exposes `operations.sites.watch(input, handlers)` with a
  typed event union. The frame envelope (`seq`, `gap`) is not generated: it is
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
[decision-4](../../decisions/decision-4%20-%20QGIS-aware-networking-uses-an-async-first-transport.md)
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
    api = ctx.require_network().configure(
        base_url="https://example.org/api/",
        headers={"Accept": "application/json"},
        timeout=10,
        auth_config="abc1234",          # a QGIS authentication configuration id
    )
    response = await api.get("collections", params={"limit": 20})
    return response.raise_for_status().json()
```

- **Coroutines, scheduled by the host.** `get`/`post`/`request` are
  `async def` and suspend on a `Handoff` from `qgis_sdk.core.scheduling`: the
  job waits, the GUI thread does not. Cancelling the job aborts the reply;
  closing the owning scope aborts everything the client still has in flight, so
  a disposed plugin never gets a callback.
- **Blocking is explicit and off the GUI thread.** `ctx.network.blocking.get(...)`
  runs the same exchange on the calling thread under a local event loop and
  raises `QgisSdkBlockingOnGuiThreadError` on the GUI thread instead of nesting
  an event loop into the host's. Use it from `QThreadPool`, `QgsTask` or a
  plain thread.
- **Derived, immutable clients.** `configure(base_url, headers, timeout,
  auth_config, max_redirects, max_body_bytes)` returns a new client; nothing
  mutates a shared default, so a typed service client carries its own base URL
  without touching the plugin's.
- **One `Response`.** `status_code`, `reason`, `headers` (case-insensitive,
  credentials redacted in `repr`), `content`, `text`, `json()`, `ok` and
  `raise_for_status()`. A `404` is a response; only `raise_for_status()` turns
  it into `QgisSdkHttpStatusError`.
- **Errors you can tell apart by `code`.** `QgisSdkRequestRejectedError`
  (bad URL, user-info in the URL, unsupported method),
  `QgisSdkRequestCancelledError`, `QgisSdkConnectionError`,
  `QgisSdkRequestTimeoutError`, `QgisSdkTlsError`,
  `QgisSdkAuthenticationError`, `QgisSdkRedirectError`,
  `QgisSdkResponseTooLargeError`, `QgisSdkHttpStatusError`,
  `QgisSdkDecodeError`, all under `QgisSdkNetworkError` with the method and the
  URL in the message.
- **Defaults from measurement.** 30 s timeout, 20 redirects, 16 MiB buffered
  body; the last two come from
  [doc-15](../plans/doc-15%20-%20TASK-5-network-limits-measurement-evidence.md).
  A body over the ceiling is aborted while downloading, not buffered and then
  refused.
- **QGIS owns the configuration.** The native transport goes through
  `QgsNetworkAccessManager`, so the proxy, the certificate trust and the
  authentication database a user set in QGIS apply; `auth_config` is handed to
  `QgsAuthManager.updateNetworkRequest`, and no credential passes through the
  SDK. Trust changes made at runtime need `rebuildTrustedCaCertsCache()` and,
  for a host Qt already talked to, `clearConnectionCache()`; both are QGIS
  calls, not SDK ones.
- **Redirects are followed by the transport, not by Qt.** The manager was
  measured forwarding `Authorization` and `Cookie` to another origin, so the
  transport follows hops itself and drops `Authorization`, `Cookie`,
  `Proxy-Authorization` and the auth configuration when scheme, host or port
  changes; `https` → `http` is refused.
- **Typed services compose over it.** `qgis_sdk.network.OgcApiFeatures(network,
  base_url)` is the first: `collections()`, `items(collection_id, limit, bbox)`
  and `next_page(page)` return dataclasses, and a malformed document is a
  `QgisSdkServiceResponseError`. WMS/WFS layers stay on QGIS providers.
- **Tests inject a fake.** `qgis_sdk.testing.FakeNetworkTransport` is scripted
  with `expect(method, url, response | exception | responder, hold=False)`;
  an unexpected request fails the test with `QgisSdkNetworkFakeError`, a held
  request is released from the test with `pending[0].deliver()`, and
  `assert_satisfied()` reports unmet expectations. It never opens a socket.
  The native transport is covered by `tests/test_network_native.py` against
  loopback servers, including the QGIS proxy setting, a Basic authentication
  configuration, and a certificate trusted through the auth manager.

## Scoped jobs

`ctx.jobs` is the local job runtime
[decision-13](../../decisions/decision-13%20-%20Use-runtime-bound-Celery-inspired-local-jobs.md)
shaped and
[decision-21](../../decisions/decision-21%20-%20Bound-job-ownership-and-refuse-unsafe-runtime-replacement.md)
scoped: a job is a decorated class with a typed `run`, submission is
`bind(JobClass).delay(inputs)` and nothing else, and the handle you get back is
typed end to end. `qgis_sdk.jobs` is QGIS-free; it runs on the TASK-13 step
scheduler and a host drives `JobService.tick()` from whatever event loop it
already has.

```python
from dataclasses import dataclass

from qgis_sdk.core import JobContext
from qgis_sdk.jobs import job


@dataclass(frozen=True)
class SumInputs:
    left: int
    right: int


@dataclass(frozen=True)
class SumResult:
    total: int


@job(id="demo.sum", title="Add two numbers")
class Sum:
    def __init__(self, ctx: JobContext) -> None:
        self.ctx = ctx

    async def run(self, inputs: SumInputs) -> SumResult:
        def work() -> int:  # runs on a worker thread, reports from there
            self.ctx.progress.report(0.5)
            return inputs.left + inputs.right

        total = await self.ctx.require_workers().offload(work)
        return SumResult(total)


handle = ctx.jobs.bind(Sum).delay(SumInputs(1, 2))
handle.on_progress(lambda fraction: bar.setValue(int(fraction * 100)))
handle.on_success(lambda result: label.setText(str(result.total)))
handle.on_failure(lambda error: label.setText(str(error)))
handle.on_cancelled(lambda: label.setText("cancelled"))
```

`describe_job(Sum)` returns the `JobDescription` (`id`, `title`, the inputs
and result types, and their schemas from the declarations generator) without
constructing the class; a class without `@job`, without `run`, or with an
untyped `run` is refused at bind time with `QgisSdkDeclarationError`. Inputs of
the wrong type are refused by `delay` with `QgisSdkJobRejectedError` before
anything runs; a result of the wrong type fails the job, not the tick.

Three rules decide everything else:

- **A request is not a state.** `handle.cancel()` returns whether the job was
  still active and sets `cancel_requested`; `status` becomes `cancelled` only
  when the job acknowledges it at a suspension point (or before it ever
  started). A job that finishes anyway reports `succeeded`, honestly. Work
  that never reaches a suspension point stays `running`; `quiesce()` names it
  as a blocker instead of pretending it stopped, and nothing kills a thread.
- **Callbacks run on the tick, never on a worker.** Progress reported from a
  worker thread is coalesced to the latest fraction and delivered on the next
  tick; each terminal outcome is delivered exactly once, in subscription
  order. Subscribing late replays the current state synchronously as one
  transition; a terminal replay completes the subscription. A callback that
  raises is detached and reported through `faults` / `on_fault`, never
  raised into the tick. `handle.get(timeout)` blocks only off the GUI thread -
  on it, `QgisSdkJobWaitRefusedError`; a timeout is
  `QgisSdkJobNotSettledError`. `handle.result` reads the same outcome
  without waiting: the typed result, the job's own exception for a failed
  job, `QgisSdkJobCancelledError` for a cancelled one, and
  `QgisSdkJobNotSettledError` only while the job is queued or running.
  A `tick()` entered while another is on the stack - a job or a callback
  opened a modal dialog and its nested event loop fired the host timer - is
  ignored and returns `0`; a nested `quiesce()` is refused with the blocker
  `a tick is already in progress on this thread`.
- **Disposal beats delivery.** `ctx.jobs` in a view is
  `plugin_jobs.scoped(view_scope)`: closing the view disposes every
  subscription it owns first, then asks each of its jobs to stop. Hiding a
  dock is not disposal. A finished handle whose view closed afterwards refuses
  new subscriptions rather than replaying into it. Plugin-lifetime work is
  explicit - `ctx.jobs.parent.bind(...)` - and outlives the view. Closing the
  plugin scope abandons everything through the scheduler's existing rule;
  nobody is called. A subscription may name another owner
  (`handle.on_success(cb, owner=other_scope)`); that owner's closure detaches
  it, and the service keeps one close hook per such owner, released as the
  job finishes, so a long-lived owner does not accumulate finished jobs.

There are no automatic retries: resubmission is `delay` again, with a new
logical id, and `attempt` is carried as `1` so a later, explicit retry policy
has somewhere to count.

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
options always produce the same bytes: `README.md`, `pyproject.toml`,
`<plugin>/__init__.py`, `<plugin>/metadata.txt`, `<plugin>/plugin.py` and
`tests/test_plugin_smoke.py`. There is no template directory to keep in sync;
`--dry-run` prints the plan without touching disk, and an existing file is refused
unless `--force` is passed.

`<plugin>/__init__.py` exposes only `classFactory`, because that is the one name
QGIS calls. `<plugin>/plugin.py` carries the whole design in plain view - one
`@plugin` class, one `@action`, a `build_context` that hands the host `iface` to
the SDK exactly once, and `classFactory` produced by
`qgis_sdk.adapters.desktop.create_class_factory` - and imports no Qt or QGIS
module. `metadata.txt` carries the nine fields QGIS reads, and tests pin that the
generated project imports nothing native.

### Choosing Desktop or standalone Qt mode

The README the scaffold writes teaches both modes; they differ in one thing, whether a host
`iface` exists:

| Mode | How it runs | What the SDK sees |
| :-- | :-- | :-- |
| Desktop | copy `<plugin>/` into a profile's `python/plugins/` and enable it under Plugins, Manage and Install Plugins, or launch `qgis --profiles-path <dir> --profile <name>` | `iface` is present, so `context.require_native()` succeeds and messages reach the real message bar |
| Standalone Qt | call `build_context(None)` from a plain Qt application or the starter tests, with `QT_QPA_PLATFORM=offscreen` for a display-free run | no `iface`, so `require_native()` raises `QgisSdkUnsupportedCapabilityError` (`code="unsupported_capability"`) instead of inventing a host, and informational messages are dropped |

The starter tests are the standalone mode: in the generated project,
`PYTHONPATH=<this workspace>/packages/qgis-sdk-python/src pytest -q` runs load, action and
unload through the SDK runtime with no QGIS installation at all.

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

What the web plan adds:

- `web/` - a Vite app: `package.json` (every dependency pinned exactly,
  `@archont561/qgis-sdk` at the version this release was qualified with; Vite
  and Vitest for every manager, never Bunup), `vite.config.ts` (`base: "./"`
  for `file:` pages, output into `<plugin>/web`, Chromium target of the
  oldest supported QGIS), `tsconfig.json`, `index.html` (loads Qt's
  `qwebchannel.js`), `src/transport.ts` (the QWebChannel `WireTransport`),
  `src/bridge.ts` (the typed client rendered from the plugin's declarations
  and checked in - `<pm> run bindings` is the CI drift check), the page
  (`main.ts`/`app.ts` or `main.tsx`/`App.tsx`) and a Vitest test against
  `@archont561/qgis-sdk/testing`.
- `<plugin>/webview.py` - opens the built page in a `QWebEngineView` behind
  `BrowserPolicy(asset_roots=(<plugin>/web,))` and a `Dispatcher` built from
  the running `PluginRuntime`, as a `QDialog` or a `QDockWidget`; Qt is
  imported inside the functions, so `qgis-sdk check` stays clean with no
  native exemption and the starter tests still run without QGIS.
- `<plugin>/plugin.py` - `classFactory` returns a small wrapper around the
  SDK lifecycle that adds one toolbar button opening the view.

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
| `ARCH001` | `qgis_sdk.adapters.qgis` (the PyQGIS-backed adapters) is imported when a pure module loads; reach it inside the function that runs in QGIS, as the scaffold's `build_context` does. |
| `META001` / `META002` / `META003` | A plugin package has no `metadata.txt`, lacks a required key (`name`, `description`, `about`, `version`, `qgisMinimumVersion`, `author`, `email`), or has no `[general]` section. |
| `PROJECT001` | No directory with an `__init__.py` under the root (other than `tests/`). |
| `CONFIG001` | `[tool.qgis-sdk.check]` in `pyproject.toml` is malformed. |
| `SYNTAX001` | A file does not parse. |

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
  and puts the project root on `QGIS_PLUGINPATH`, which is how QGIS finds and
  imports `<plugin>/` in place: no copy, no symlink, no `sys.path` edit. The
  SDK's own packages join that process's `PYTHONPATH`, so the bootstrap
  (`qgis_sdk_tools.devtools.bootstrap`, running the policy in
  `.devtools.reloader`) imports inside QGIS's interpreter
  whichever Python runs the CLI. It enables the plugin, installs a
  **Reload** toolbar action (Ctrl+Shift+R), watches `<plugin>/` for saved
  `*.py` and `metadata.txt` changes (polling every 500 ms; `web/` and caches
  excluded - the page is Vite's business) and reports to the terminal.
  `--no-watch` leaves reloads to the button.

  Every reload, however triggered, follows one policy:

  1. **Preflight** without touching the running revision: every module of
     the package compiles and `check_project` finds nothing QGIS would
     refuse (`SYNTAX*`, `META*`, `PROJECT*`, `CONFIG*` errors inside the
     package); `QGIS001`/`ARCH001` only warn, findings in `tests/` never
     block. A problem is *refused* - `reload refused, revision N keeps
     running: ...` - and nothing is unloaded.
  2. **Quiesce** through `PluginRuntime.quiesce()`: owned jobs are
     cancelled and given up to 2 s (pumping the event loop between checks)
     to reach a safe point. A refusal names the blockers, resumes the
     revision exactly as it was and says that finishing or cancelling the
     work, or restarting `qgis-sdk dev`, is the way out. No thread is
     killed, nothing unsaved is discarded.
  3. **Replace**: unload (drops the package's modules), then load and start
     the current source. A failure after teardown cannot be undone: the
     partially imported modules are dropped, the plugin stays *disabled*,
     and the message bar and terminal say so until a Reload succeeds.

  Requests are serialised and coalesced: a burst of saves becomes one reload
  (300 ms debounce), and a request that lands while a reload is in flight is
  folded into exactly one follow-up. Each attempt carries a generation
  number in its report. Old-generation work cannot deliver into the new
  revision because the old scope is closed on unload (subscriptions
  disposed, late worker reports counted as dropped).
- **standalone** runs `classFactory(None)` + `initGui()` in a bare
  `QgsApplication` under the QGIS Python. It is the documented reduced mode:
  no `iface`, no plugin lifecycle hooks beyond the two calls, no reload;
  close the window to stop.
- **web**: when the project has `web/` with installed dependencies, the
  command starts the project's Vite dev server (`<manager> run dev --host
  127.0.0.1 --port N --strictPort`) on loopback, waits for the port, and
  hands its origin to the QGIS process as `QGIS_SDK_DEV_SERVER`. The
  generated `webview.py` reads that variable, loads the page from the origin
  and grants it in `BrowserPolicy(origins=...)`; the bridge binding carries
  the same origin, so hot module replacement works and the bridge keeps
  answering across updates. A built plugin never sees the variable and
  `bun run build` never references the server. `--no-web` skips it; a
  server that does not answer within 60 s stops the command with exit 2.

Both modes exit with the QGIS process's code; QGIS not found is exit 2 with
the discovery report, a directory without a plugin package is exit 2.

## Building an installable ZIP: `qgis-sdk build`

`qgis-sdk build [PATH] [--out DIR] [--no-web] [--json]` writes
`dist/<plugin>-<version>.zip` (version from `metadata.txt`) for Plugins >
Manage and Install Plugins > *Install from ZIP* (decision-8: the command is
argument parsing over `qgis_sdk_tools.bundle.build_plugin`). In order:

1. **Validate.** `check_project` runs first - the same rules and output as
   `qgis-sdk check` - plus build-only rules: `ENTRY001` when
   `<plugin>/__init__.py` neither defines nor imports `classFactory`;
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
   the package and were never candidates). The runtime `qgis_sdk` - every
   module except `qgis_sdk.testing` - is copied to
   `<plugin>/_vendor/qgis_sdk` with a `NOTICE` (runtime version, MIT), and
   every absolute `qgis_sdk` import in the copy *and* in the plugin's own
   sources is rewritten to `<plugin>._vendor.qgis_sdk` (decision-35,
   decision-3: the plugin runs in a QGIS without qgis-sdk and coexists with
   plugins built against other versions; `rewrite_imports` is AST-located,
   touches only import statements and keeps line numbers). The ZIP's only
   root entry is `<plugin>/`; entries are sorted, timestamps fixed
   (`SOURCE_DATE_EPOCH` or 1980-01-01), modes normalised, so the same tree
   gives the same bytes.

`BuildResult` carries the archive path, plugin, version, file list, the
combined `CheckReport`, the vendored runtime version, the web outcome
(`none` / `built` / `prebuilt`) and the declared externals; `--json` prints
its `to_json()`.

### CLI runtime

Commands that read or write anything beyond their arguments receive a
`qgis_sdk_tools.cli.CliRuntime` (`cwd`, `env`, `out`, `err`) through Typer's
`ctx.obj` (decision-34). The shell seeds it with `CliRuntime.for_process()`;
a test passes `qgis_sdk_tools.testing.FakeCliRuntime(cwd=..., env=...)` as
`CliRunner().invoke(app, args, obj=runtime)` and reads `runtime.stdout` /
`runtime.stderr` back.

## Optional controlled-deployment adapter

`qgis_sdk.adapters.pydantic.PydanticContractAdapter` provides a narrow JSON-request → strict validation → typed handler → result-serialization slice for deployments that explicitly provision Pydantic. Models use standard-library dataclasses with Pydantic configuration; `qgis_sdk.adapters.pydantic_types.SafeJsonInteger` provides the agreed finite ±9007199254740991 wire bound, which both it and the schema generator take from the one `qgis_sdk.models.MAX_SAFE_INTEGER` constant while accepting integral JSON numbers such as `2.0`. Request, result-reader, and result-writer schemas remain distinct. Validation errors expose structured field paths and validator codes without copying rejected input values.

Pydantic **is not a base runtime dependency**. The explicit `controlled-deployment` extra pins `pydantic==2.14.1` (which installs native `pydantic-core`); administrators/developers provision it in their managed environment. The SDK never downloads or installs it at startup, and ordinary QGIS-free imports work without it. The adapter is a prototype, not a mandatory production backend selection. Current persistent tests exercise Linux with CPython 3.14.8 (which carries PyQGIS in the workspace), the QGIS-free suite on CPython 3.11.2 (the minimum supported version), and GitHub Actions `macos-latest` (`arm64`) and `windows-latest` (`x86_64`) on CPython 3.14 (`pip install -e "packages/qgis-sdk-python[dev]"`). In-process coexistence with another Pydantic-using plugin inside the real QGIS 4.2.3 Desktop application is proven on Linux by `scripts/plugin_coexistence_smoke.py`; Windows/macOS QGIS installations, display-server Desktop/WebEngine rendering, and Conda delivery remain explicit qualification gates.

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
  `qgis_sdk.adapters.pydantic`, `qgis_sdk.adapters.pydantic_types`, and
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
  (`qgis_sdk.algorithms`, `qgis_sdk.reference.algorithms`) and their toolbox
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
([decision-25](../../decisions/decision-25%20-%20Version-each-package-independently-behind-a-shared-contract-version.md)).

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

## 0.4.0 migration notes

`0.4.0` closes the m-3 milestone (developer workflow and plugin packaging).
It is a Python-only release, tag `python-v0.4.0`: no file under
`packages/qgis-sdk-typescript` or `packages/qgis-sdk-alias` changed since
`ts-v0.3.0`, so `@archont561/qgis-sdk` stays at `0.3.0` and generated web
projects keep pinning it ([decision-25](../../decisions/decision-25%20-%20Version-each-package-independently-behind-a-shared-contract-version.md)).
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
- **`qgis-sdk build`** (TASK-8) is new; see "Building an installable ZIP".
  Projects generated by `qgis-sdk new` now ignore `dist/`. A plugin that
  imports `qgis_sdk_tools` or `qgis_sdk.testing` from package code is
  refused at build time (`DEP001`/`DEP002`): those never ship.
- **`qgis-sdk dev` reloads on save and quiesces first** (TASK-21). The
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
  `@algorithm`, `@job` and `@provider.algorithm` derive a missing `id=` /
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

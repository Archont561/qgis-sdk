---
id: doc-12
title: qgis-sdk Python package guide
type: guide
created_date: '2026-10-24 21:20'
---
# qgis-sdk Python package guide

The reference prose for the `qgis-sdk` Python package. It used to live in
`packages/qgis-sdk/README.md`; [decision-29](../../decisions/decision-29%20-%20Keep-READMEs-minimal-and-hold-reference-prose-in-backlog-guides-until-the-docs-site.md)
moved it here, where it is the source the documentation site
([TASK-43](../../tasks/task-43%20-%20Publish-a-Starlight-documentation-site-from-the-backlog-guides.md))
will render. The headings dropped the task tags they carried in the README;
the records that landed each surface are TASK-2 (declarations), TASK-11 (pure
contract layer), TASK-24 (runtime and Desktop adapter), TASK-3 (native forms),
TASK-14 (algorithms), TASK-39 (providers), TASK-4 with decisions 26 and 27
(bridge host side, generated client, host surface), TASK-17 and decision-28
(generated client and streams), TASK-5 and decision-4 (networking), TASK-1
(scaffold), TASK-27 and TASK-28 (release
policy and migration notes). Status at the time of writing: Python `0.2.0`
published, `0.3.0` in progress.

Companion guides: [doc-13](doc-13%20-%20qgis-sdk-bridge-TypeScript-package-guide.md)
(TypeScript bridge) and [doc-14](doc-14%20-%20Workspace-development-qualification-harnesses-and-evidence.md)
(workspace tooling, harnesses and qualification evidence).

## Installation

Install from [PyPI](https://pypi.org/project/qgis-sdk/) or from the [`prefix.dev` Conda channel (`archont561/archont561`)](https://prefix.dev/channels/archont561/packages/qgis-sdk):

```sh
pip install qgis-sdk
# or with the optional Pydantic controlled-deployment adapter:
pip install "qgis-sdk[controlled-deployment]"
# or in a Pixi workspace via the prefix.dev Conda channel:
pixi add --channel https://prefix.dev/archont561/archont561 qgis-sdk
```

The companion TypeScript package [`@archont561/qgis-sdk-bridge`](https://www.npmjs.com/package/@archont561/qgis-sdk-bridge) is published on npm and [GitHub Packages](https://github.com/Archont561/qgis-sdk/pkgs/npm/qgis-sdk-bridge); the bridge guide is [doc-13](doc-13%20-%20qgis-sdk-bridge-TypeScript-package-guide.md).

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
    def __init__(self, ctx):
        self.ctx = ctx

    @action(id="run", title="Run")
    def run(self, request: RunRequest) -> int:
        return request.count


description = describe_plugin(Tools)
print(description.to_json())
```

`plugin` and `action` attach metadata and return their original targets. No base
class, constructor rewrite, host imports or runtime registration is required.
`describe_plugin` does not instantiate the class, dispatch handlers, evaluate
properties, or call dataclass default factories. It resolves annotations with
`typing.get_type_hints`, which may evaluate forward references: inspect **trusted
Python code only**, not untrusted modules. Put DTOs in module scope so postponed
annotations resolve normally; function-local forward-reference names are not
reconstructed from vanished local scopes.

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

`PluginContext` is plugin-lifetime state. Create a child scope for each `UiContext`; `view.request_close()` requests closure but does not synchronously dispose the view. Give every `AlgorithmContext` and `JobContext` a fresh child scope plus execution-specific `Progress` and read-only `Cancellation` services. Jobs submitted from a view are view-owned by default; plugin-owned work requires an explicit plugin child scope. `JobContext` also carries the optional `workers` and `network` capabilities with `require_workers()` / `require_network()` refusals; the job runtime itself lives in `qgis_sdk.jobs` (see [Scoped jobs](#scoped-jobs)).

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
    def __init__(self, ctx: PluginContext) -> None:
        self.ctx = ctx
        ctx.scope.on_close(lambda: print("disposed"))

    @action(id="run", title="Run")
    def run(self, value: int) -> int:
        return value


context = PluginContext(notifications=..., scope=ResourceScope())
runtime = PluginRuntime(Tools, context)
instance = runtime.start()   # calls Tools(context) exactly once
runtime.actions["run"](3)    # read-only action ID -> bound method
runtime.unload()             # closes the owned scope once
runtime.unload()             # safe no-op
```

The default factory calls `plugin_class(context)`. Pass
`PluginRuntime(..., instance_factory=factory)` when a plugin needs custom
dependencies; the runtime never inspects or rewrites the constructor.
Declarations are validated at construction time, but no author code runs until
`start()`. After construction, every declared action must resolve to a callable
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

## Desktop lifecycle adapter

A QGIS plugin package can expose the adapter through its normal entry point:

```python
from qgis_sdk.adapters.desktop import create_class_factory

classFactory = create_class_factory(Tools, context_factory=build_context)
```

`build_context(iface)` returns the typed `PluginContext` for that host,
including any `DesktopAccess` service. The adapter imports neither QGIS nor Qt,
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
  package as `@archont561/qgis-sdk-bridge/host`.

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

`qgis-sdk scaffold <directory>` writes a minimal but genuinely loadable QGIS plugin
project, built from the public declaration API instead of generated boilerplate.
The command is a thin Typer layer in `src/qgis_sdk/__main__.py` over the public
`qgis_sdk.scaffold` API, so a pip or `pixi add --pypi` install gets the console
script and `python -m qgis_sdk` reaches the identical entry point. Typer is a
runtime dependency of the wheel for this command alone:

```sh
qgis-sdk scaffold /tmp/demo --title "Demo Tools"            # installed console script
python -m qgis_sdk scaffold /tmp/demo --title "Demo Tools"  # same command via -m
pixi run -e default python -m qgis_sdk scaffold /tmp/demo   # from workspace source
```

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
`PYTHONPATH=<this workspace>/packages/qgis-sdk/src pytest -q` runs load, action and
unload through the SDK runtime with no QGIS installation at all.

## Optional controlled-deployment adapter

`qgis_sdk.adapters.pydantic.PydanticContractAdapter` provides a narrow JSON-request → strict validation → typed handler → result-serialization slice for deployments that explicitly provision Pydantic. Models use standard-library dataclasses with Pydantic configuration; `qgis_sdk.adapters.pydantic_types.SafeJsonInteger` provides the agreed finite ±9007199254740991 wire bound, which both it and the schema generator take from the one `qgis_sdk.models.MAX_SAFE_INTEGER` constant while accepting integral JSON numbers such as `2.0`. Request, result-reader, and result-writer schemas remain distinct. Validation errors expose structured field paths and validator codes without copying rejected input values.

Pydantic **is not a base runtime dependency**. The explicit `controlled-deployment` extra pins `pydantic==2.14.1` (which installs native `pydantic-core`); administrators/developers provision it in their managed environment. The SDK never downloads or installs it at startup, and ordinary QGIS-free imports work without it. The adapter is a prototype, not a mandatory production backend selection. Current persistent tests exercise Linux with CPython 3.14.8 (which carries PyQGIS in the workspace), the QGIS-free suite on CPython 3.11.2 (the minimum supported version), and GitHub Actions `macos-latest` (`arm64`) and `windows-latest` (`x86_64`) on CPython 3.14 (`pip install -e "packages/qgis-sdk[dev]"`). In-process coexistence with another Pydantic-using plugin inside the real QGIS 4.2.3 Desktop application is proven on Linux by `scripts/plugin_coexistence_smoke.py`; Windows/macOS QGIS installations, display-server Desktop/WebEngine rendering, and Conda delivery remain explicit qualification gates.

## 0.1.0 experimental release and migration policy

- **Experimental `0.x` SemVer:** `0.1.0` (and prereleases such as `0.1.0-alpha.1`,
  `0.1.0-beta.1`, `0.1.0-rc.1`) is an experimental milestone target; no `1.0.0`
  stability promise is made. Breaking changes during `0.x` require a documented minor
  version bump (`0.Y.0`) with migration notes; compatible bug fixes and additive
  changes use patch releases (`0.Y.Z`).
- **Scoped manifests, independent versions:** `scripts/release.py`
  (`pixi run release-stamp --scope python|typescript|all`) updates only the manifests
  in the selected scope. `qgis-sdk` and `@archont561/qgis-sdk-bridge` both shipped
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
  `qgis_sdk.scaffold` (`qgis-sdk scaffold` CLI). All packages and the repository root
  are licensed under MIT (`LICENSE`).

## 0.2.0 migration notes

`0.2.0` is the first release where the two packages carry different numbers: the
Python SDK moves to `0.2.0` and `@archont561/qgis-sdk-bridge` stays at `0.1.1`,
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

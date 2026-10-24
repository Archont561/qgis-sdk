# qgis-sdk

**Python SDK foundations for developing QGIS plugins.**

`qgis-sdk` is the Python package in the QGIS SDK workspace. It is intended to grow into a reusable foundation for plugin authors who want maintainable, source-testable code and a consistent packaging workflow.

> **Status:** early scaffold with an experimental, QGIS-free contract layer, declarations, and a bounded plugin lifecycle runtime. The public surface is exactly `qgis_sdk.__all__` - the declaration decorators and their descriptions - and a test pins it. Native GIS services, UI rendering and handler dispatch, jobs, the full Desktop plugin template, and the bridge runtime are not implemented yet.

The [`qgis-sdk` PyPI listing](https://pypi.org/project/qgis-sdk/) is currently a `0.0.0` placeholder with no project description, not a functional SDK release. Use this repository's source package for development; see the [workspace README](../../README.md) for details and the npm bridge listing status.

## Pure contract layer (experimental)

The public `qgis_sdk.models`, `qgis_sdk.services`, and `qgis_sdk.core` modules import without QGIS or Qt. Dependencies flow **models ← services ← core**; the pure layers do not import native adapters, bridge transports, testing fakes, or CLI tools. These are contracts, not a runnable plugin or a replacement for PyQGIS.

| Module | Current contract |
| :-- | :-- |
| `models` | `QgisSdkError`, `QgisSdkScopeClosedError`, `QgisSdkUnsupportedCapabilityError`, `QgisSdkOptionalDependencyError`, `QgisSdkValidationIssue`, and safe `QgisSdkContractValidationError` metadata |
| `adapters.pydantic` | Optional controlled-deployment adapter; Pydantic is imported only when the adapter is constructed |
| `adapters.pydantic_types` | Explicit Pydantic field annotation for finite JavaScript-safe integers |
| `services` | Structural `Notifications`, `ViewControl`, `Progress`, `Cancellation`, and `DesktopAccess` protocols; implementations are supplied by the host or by tests |
| `core` | `PluginContext`, `UiContext`, `AlgorithmContext`, `JobContext`, `ResourceScope`, `PluginRuntime`, and lifecycle errors |

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

`PluginContext` is plugin-lifetime state. Create a child scope for each `UiContext`; `view.request_close()` requests closure but does not synchronously dispose the view. Give every `AlgorithmContext` and `JobContext` a fresh child scope plus execution-specific `Progress` and read-only `Cancellation` services. Jobs submitted from a view are view-owned by default; plugin-owned work requires an explicit plugin child scope. This foundation does **not** implement job scheduling, callback delivery, cancellation acknowledgement, or GUI-thread handoff.

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

## Development

From the workspace root, install the Pixi environments and run the Python tests:

```sh
pixi install -e default
pixi install -e build
pixi run -e default pytest -c packages/qgis-sdk/pyproject.toml packages/qgis-sdk/tests
```

The Python development dependencies are declared in this package's `dev` extra. Pixi pins its Python tools and installs Hypothesis, pytest-cov, and Pydantic 2.14.1 as wheels; Pydantic is needed only to test the optional adapter. The workspace package is loaded from `packages/qgis-sdk/src` on `PYTHONPATH` rather than installed as a Pixi path dependency.

The checked contract-generation examples live in `tests/contract_sample/` and are run via the workspace's `sdk:generate` package script; see the [workspace README](../../README.md#checked-contract-generation-example). Mashumaro remains a separate test-only schema-export example. The Pydantic example uses the optional adapter, emits its own request/reader/writer schemas, and is checked against the same Python/Ajv case corpus. Neither example is a general SDK generator or public operation.

## Optional controlled-deployment adapter (experimental)

`qgis_sdk.adapters.pydantic.PydanticContractAdapter` provides a narrow JSON-request → strict validation → typed handler → result-serialization slice for deployments that explicitly provision Pydantic. Models use standard-library dataclasses with Pydantic configuration; `qgis_sdk.adapters.pydantic_types.SafeJsonInteger` provides the agreed finite ±9007199254740991 wire bound, which both it and the schema generator take from the one `qgis_sdk.models.MAX_SAFE_INTEGER` constant while accepting integral JSON numbers such as `2.0`. Request, result-reader, and result-writer schemas remain distinct. Validation errors expose structured field paths and validator codes without copying rejected input values.

Pydantic **is not a base runtime dependency**. The explicit `controlled-deployment` extra pins `pydantic==2.14.1` (which installs native `pydantic-core`); administrators/developers provision it in their managed environment. The SDK never downloads or installs it at startup, and ordinary QGIS-free imports work without it. The adapter is a prototype, not a mandatory production backend selection. Current persistent tests exercise Linux with CPython 3.14.8 (which carries PyQGIS in the workspace), the QGIS-free suite on CPython 3.11.2 (the minimum supported version), and GitHub Actions `macos-latest` (`arm64`) and `windows-latest` (`x86_64`) on CPython 3.14 (`pip install -e "packages/qgis-sdk[dev]"`). In-process coexistence with another Pydantic-using plugin inside the real QGIS 4.2.3 Desktop application is proven on Linux by `scripts/plugin_coexistence_smoke.py`; Windows/macOS QGIS installations, display-server Desktop/WebEngine rendering, and Conda delivery remain explicit qualification gates.

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

The generated README teaches both modes; they differ in one thing, whether a host
`iface` exists:

| Mode | How it runs | What the SDK sees |
| :-- | :-- | :-- |
| Desktop | copy `<plugin>/` into a profile's `python/plugins/` and enable it under Plugins, Manage and Install Plugins, or launch `qgis --profiles-path <dir> --profile <name>` | `iface` is present, so `context.require_native()` succeeds and messages reach the real message bar |
| Standalone Qt | call `build_context(None)` from a plain Qt application or the starter tests, with `QT_QPA_PLATFORM=offscreen` for a display-free run | no `iface`, so `require_native()` raises `QgisSdkUnsupportedCapabilityError` (`code="unsupported_capability"`) instead of inventing a host, and informational messages are dropped |

The starter tests are the standalone mode: in the generated project,
`PYTHONPATH=<this workspace>/packages/qgis-sdk/src pytest -q` runs load, action and
unload through the SDK runtime with no QGIS installation at all.

### Load and unload evidence in real QGIS Desktop

A standalone run cannot prove QGIS accepts the package, so
`scripts/scaffold_desktop_smoke.py` scaffolds into a temporary directory, installs
the plugin package into a clean throwaway profile, and runs the **QGIS Desktop
binary** so that QGIS's own plugin machinery - `qgis.utils.findPlugins`,
`loadPlugin`, `startPlugin`, `unloadPlugin` - discovers it, parses its
`metadata.txt` with QGIS's own parser, calls `classFactory(iface)` and `initGui()`,
invokes the declared action and unloads it, with the SDK reporting `running` and
then `stopped`:

```sh
pixi run -e default python packages/qgis-sdk/scripts/scaffold_desktop_smoke.py
QGIS_SDK_SCAFFOLD_DESKTOP=1 pixi run -e default pytest -c packages/qgis-sdk/pyproject.toml packages/qgis-sdk/tests/scripts/test_qualification_scaffold.py
```

Headless Desktop needs three variables that are easy to get wrong, which is why the
harness sets them instead of leaving them to a recipe: `QT_QPA_PLATFORM=offscreen`
(no window system, nothing rendered), a placeholder `DISPLAY` (QGIS decides it is
non-interactive from `DISPLAY` alone and refuses to start), and `PYTHONHOME` at the
live prefix (QGIS carries its build-time prefix in the embedded interpreter, so a
relocated install starts and then cannot even `import sys`). This qualifies the
Desktop plugin path, not GUI behaviour: no widget is shown, so canvas, map and 3D
rendering still need a real display. Last run here: QGIS 4.2.3 and CPython 3.14.8
on Linux, `"passed": true`. The same kit backs the adapter evidence in
[Desktop lifecycle adapter](#real-desktop-startup-and-unload-evidence).

## Developer scripts

Standalone executables live in `scripts/` next to `src/`: they are runnable
tools rather than test data, so they stay out of `tests/`, and they must stay out
of `src/qgis_sdk/` because a wheel cannot ship a command that imports a display
server. Each script is covered by a module in `tests/scripts/`, and the harnesses
themselves are opt-in through the environment flags below. `scripts/` is not an
importable package: the repository root already owns that top-level name, so
tests import a harness by module name via `tests/conftest.py`.

None of it is shipped. `[tool.hatch.build.targets.wheel].packages` packs
`src/qgis_sdk` and nothing else, and `recipe.yaml` builds the Conda package by
pip-installing that same project, so neither the wheel nor the Conda artifact can
carry a harness, a generator or a test path. The one executable-shaped file inside
the package is `qgis_sdk/__main__.py`, and it belongs there because it *is* the
distributed command; `scripts/` would be the wrong home for it, since a user who
installed the wheel has no `scripts/` directory to point at.

## Headless QGIS and WebEngine qualification

`scripts/webengine_smoke.py` is a repeatable harness for the headless path QGIS uses to host a `QWebEngineView`. It starts a real QGIS application, loads a page in a real WebEngine view, tears QGIS down again and prints a machine-readable report:

```sh
pixi run -e default python packages/qgis-sdk/scripts/webengine_smoke.py
```

```json
{
  "chromium_version": "140.0.0.0",
  "error": null,
  "load_finished": true,
  "platform": "Linux-6.1.158+-x86_64-with-glibc2.36",
  "python_version": "3.14.8",
  "qgis_exited": true,
  "qgis_initialised": true,
  "qgis_version": "4.2.3-Belém do Pará",
  "qt_version": "6.11.2",
  "qualified": true,
  "webengine_available": true
}
```

The harness resolves everything it needs from the active prefix, so the same command works in any environment that provides a QGIS installation. It sets `QT_QPA_PLATFORM=offscreen`, the Chromium flags `--no-sandbox --disable-gpu --disable-dev-shm-usage --single-process`, the `PROJ_LIB` and `QGIS_PREFIX_PATH` of that prefix, and puts the QGIS Python bindings on `PYTHONPATH`.

| Requirement | Linux (`linux-64`) | macOS (`macos-latest` arm64) | Windows (`windows-latest` x86-64) |
| :-- | :-- | :-- | :-- |
| QGIS-free Python SDK + `PydanticContractAdapter` (`pydantic==2.14.1`) | Qualified (CPython 3.14.8 & 3.11.2) | Qualified in CI (`pip`, CPython 3.14) | Qualified in CI (`pip`, CPython 3.14) |
| TypeScript bridge (`packages/qgis-sdk-bridge`) | Qualified (Bun 1.4.2, 90 tests, 100% cov) | Qualified in CI (Bun 1.4.2, 90 tests) | Qualified in CI (Bun 1.4.2, 90 tests) |
| QGIS with Python bindings | Qualified (Pixi `default`, QGIS 4.2.3) | Blocker: no macOS QGIS 4 prefix in CI/sandbox (TASK-33 AC #1) | Blocker: no Windows QGIS 4 prefix in CI/sandbox (TASK-33 AC #1) |
| Qt WebEngine Python bindings (`pyqt6-webengine` 6.11.0) | Qualified headless (`offscreen`, Chromium 140.0.0.0) | Blocker: requires macOS QGIS/Qt prefix | Blocker: requires Windows QGIS/Qt prefix |
| Headless QGIS Desktop plugin manager (`qgis --noplugins --code`) | Qualified (`scaffold_desktop_smoke.py`, `desktop_adapter_smoke.py`, `plugin_coexistence_smoke.py`) | Blocker: requires macOS QGIS Desktop binary | Blocker: requires Windows QGIS Desktop binary |
| Two-plugin `pydantic` / `pydantic_core` coexistence in QGIS Desktop | Qualified on Linux (`plugin_coexistence_smoke.py`, TASK-33 AC #3) | Blocker: requires macOS QGIS Desktop binary | Blocker: requires Windows QGIS Desktop binary |
| Display-server Desktop GUI + in-Desktop `QWebEngineView` rendering | Blocker: no display server or `Xvfb` in sandbox/CI (`offscreen` renders no widgets, TASK-33 AC #2) | Blocker: no interactive display session in CI (TASK-33 AC #2) | Blocker: no interactive display session in CI (TASK-33 AC #2) |
| Chromium sandbox | Disabled by headless flags above | N/A | N/A |

Without the Chromium flags the WebEngine process fails with `eglInitialize: Failed to get system egl display`. ANGLE, EGL, dbus and PDAL messages printed during a run are noise and do not affect the result.

`tests/scripts/test_qualification_webengine.py` covers the harness helpers in the QGIS-free suite. The end-to-end run is opt-in, because it needs a real QGIS installation:

```sh
QGIS_SDK_HEADLESS_SMOKE=1 pixi run -e default pytest -c packages/qgis-sdk/pyproject.toml packages/qgis-sdk/tests/scripts/test_qualification_webengine.py
```

The headless path is **not** a visible Desktop GUI qualification and does **not** claim universal QGIS 4 support: the Linux sandbox and CI runners have no display server or `Xvfb`, and `pixi.toml` locks `linux-64` only, so no Windows or macOS QGIS 4 installation has been tested. `qgis_sdk.adapters.webengine` therefore only proves that the optional bindings can be located on a qualified host and that a missing installation is reported with an actionable error.

## Build artifacts

The package uses Hatchling for Python distributions and an explicit Conda recipe:

```sh
pixi run -e bun bun run --filter qgis-sdk build
```

The combined build produces a wheel and source distribution under `dist/pypi/`, checks them with Twine, and builds the Conda artifact under `dist/conda/`.

See the [workspace README](../../README.md) for the full development setup, coverage tasks, Pixi environments, and the TypeScript bridge for QGIS `QWebEngineView` plugin interfaces.

## Experimental Python declarations (TASK-2)

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

## Scoped plugin runtime (experimental, TASK-24)

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

## Desktop lifecycle adapter (experimental, TASK-24)

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

The headless lifecycle harness uses a real `QgsApplication` and the adapter:

```sh
pixi run -e default python packages/qgis-sdk/scripts/desktop_lifecycle_smoke.py
```

```json
{
  "action_names": ["ping"],
  "action_result": 7,
  "error": null,
  "owned_resources_released": true,
  "passed": true,
  "plugin_started": true,
  "plugin_unloaded": true,
  "qgis_exited": true,
  "qgis_initialised": true,
  "qgis_version": "4.2.3-Belém do Pará",
  "qt_version": "6.11.2"
}
```

The harness passes `iface=None`, starts no event loop and does not exercise
menus, dialogs or docks, so it is the always-runnable fallback and **not** a real
Desktop startup/unload qualification. Run the opt-in test with:

```sh
QGIS_SDK_HEADLESS_LIFECYCLE=1 pixi run -e default pytest -c packages/qgis-sdk/pyproject.toml packages/qgis-sdk/tests/scripts/test_qualification_lifecycle.py
```

### Real Desktop startup and unload evidence

`scripts/desktop_adapter_smoke.py` supplies the evidence that harness cannot: it writes
a small fixture plugin that uses `create_class_factory`, installs it into a clean
throwaway profile, and lets the **QGIS Desktop application's own plugin manager** load,
start and unload it. The fixture belongs to this harness rather than to the scaffolded
project, so the adapter contract is proven without depending on `qgis_sdk.scaffold`.

```sh
pixi run -e default python packages/qgis-sdk/scripts/desktop_adapter_smoke.py
```

```json
{
  "action_result": 7,
  "actions_detached": true,
  "error": null,
  "iface_is_host": true,
  "message_bar_received": true,
  "native_context_matches": true,
  "passed": true,
  "runtime_running": true,
  "runtime_stopped": true,
  "scope_released": true,
  "started": true,
  "unloaded": true
}
```

"No fake fallback" is what makes each field worth reading: the run fails outright if
QGIS provides no interface object, `iface_is_host` requires the adapter to hold the very
same object as `qgis.utils.iface`, `native_context_matches` requires
`ctx.require_native()` to hand that live object back through the typed escape hatch, and
`message_bar_received` requires the notifications service to add a real widget to QGIS's
own bar. `scope_released` and `actions_detached` are the runtime's side of the same
cycle: the owned scope closed and no stale callable survived `unload()`.

QGIS's module cache is deliberately not asserted. `unloadPlugin` drops only the modules
`_plugin_modules` happened to record, which is QGIS bookkeeping rather than a promise of
this SDK, so a check there would prove the wrong thing.

The headless-Desktop rules that are easy to get wrong - `QT_QPA_PLATFORM=offscreen`, the
placeholder `DISPLAY` QGIS needs to consider itself interactive, and `PYTHONHOME` at the
live prefix so the embedded interpreter can `import sys` - live in
`scripts/desktop_smoke_kit.py`, shared with the scaffold harness. Offscreen Qt shows no
window and renders nothing: GUI, canvas, 3D and WebEngine behaviour remain under
TASK-33, as does every non-Linux candidate.

```sh
QGIS_SDK_DESKTOP_ADAPTER=1 pixi run -e default pytest -c packages/qgis-sdk/pyproject.toml packages/qgis-sdk/tests/scripts/test_qualification_desktop_adapter.py
```

The Qt scheduler harness exercises the `StepScheduler` seam inside a real
`QgsApplication` on the offscreen platform: alternating GUI phases and worker
handoffs, cancellation acknowledgement, refusal of late reports after disposal,
and quiesce blocking on an unresolved handoff. It compares tick latency while a
worker is blocked against latency while phases are scheduled:

```sh
pixi run -e default python packages/qgis-sdk/scripts/qt_scheduler_smoke.py
```

```json
{
  "blocking_phase_max_ms": 61.412,
  "passed": true,
  "scheduled_phase_max_ms": 2.593,
  "scope_review_criteria": [],
  "verdict": "adopt-scheduler-seam"
}
```

The numbers are one Linux/offscreen sample, not a latency guarantee; the
reasoning and the repeated runs are recorded in
`backlog/docs/plans/doc-6 - TASK-13-Qt-scheduler-spike-evidence.md`. Run the
opt-in test with:

```sh
QGIS_SDK_QT_SCHEDULER=1 pixi run -e default pytest -c packages/qgis-sdk/pyproject.toml packages/qgis-sdk/tests/scripts/test_qualification_scheduler.py
```

### Optional native-runtime plugin coexistence (TASK-33 AC #3)

QGIS plugins share one embedded Python interpreter and `sys.modules` table inside the
Desktop process. `scripts/plugin_coexistence_smoke.py` proves that an SDK plugin using
`qgis_sdk.adapters.pydantic.PydanticContractAdapter` (`pydantic==2.14.1` and its native
`pydantic_core` extension) coexists cleanly with a pre-existing non-SDK plugin that
already imports and validates with Pydantic:

```sh
pixi run -e default python packages/qgis-sdk/scripts/plugin_coexistence_smoke.py
QGIS_SDK_PLUGIN_COEXISTENCE=1 pixi run -e default pytest -c packages/qgis-sdk/pyproject.toml packages/qgis-sdk/tests/scripts/test_qualification_coexistence.py
```

```json
{
  "action_result": 7,
  "both_loaded": true,
  "error": null,
  "neighbor_plugin": "neighbor_pydantic_probe",
  "neighbor_started": true,
  "neighbor_survives_sdk_unload": true,
  "neighbor_unloaded_cleanly": true,
  "neighbor_validates_while_coexisting": true,
  "passed": true,
  "platform": "Linux-6.1.158+-x86_64-with-glibc2.36",
  "pydantic_core_version": "2.50.1",
  "pydantic_preloaded": true,
  "pydantic_version": "2.14.1",
  "python_version": "3.14.8",
  "qgis_version": "4.2.3-Belém do Pará",
  "sdk_contract_dispatched": true,
  "sdk_plugin": "sdk_pydantic_probe",
  "sdk_started": true,
  "sdk_unloaded_cleanly": true,
  "shared_native_runtime": true
}
```

The harness installs both plugins into a clean throwaway profile, loads and starts the
neighbor plugin first so `pydantic` and `pydantic_core._pydantic_core` are already in
`sys.modules`, loads and starts the SDK plugin alongside it, confirms both share the
identical native module objects, exercises strict request validation and rejection in
`PydanticContractAdapter` while the neighbor also validates payloads, and verifies that
unloading the SDK plugin closes its `ResourceScope` while leaving the neighbor plugin
loaded and functional.

## 0.1.0 experimental release and migration policy (TASK-27)

- **Experimental `0.x` SemVer:** `0.1.0` (and prereleases such as `0.1.0-alpha.1`,
  `0.1.0-beta.1`, `0.1.0-rc.1`) is an experimental milestone target; no `1.0.0`
  stability promise is made. Breaking changes during `0.x` require a documented minor
  version bump (`0.Y.0`) with migration notes; compatible bug fixes and additive
  changes use patch releases (`0.Y.Z`).
- **Scoped manifest updates:** `scripts/release.py` (`pixi run release-stamp`) updates
  only the manifests in the selected release scope (`python` for `packages/qgis-sdk`,
  `typescript` for `packages/qgis-sdk-bridge`, or `all`). Both `qgis-sdk` (`0.1.0`)
  and `@archont561/qgis-sdk-bridge` (`0.1.0`) ship matching version 1 declaration,
  safe-integer wire-bound, and `QgisSdk*` error contracts.
- **Independent protocol versions:** `PluginDescription.schema_version = 1` in
  `qgis_sdk.declarations` and future WebEngine IPC protocol versions are versioned
  independently of the `qgis-sdk` and `qgis-sdk-bridge` package versions.
- **0.1.0 surface & migration note:** The placeholder `qgis_sdk.hello()` and bridge
  `hello()` smoke functions were removed prior to the first release (PR #23); the
  public root surface of `qgis_sdk` is `qgis_sdk.__all__` (`ActionDescription`,
  `PluginDescription`, `QgisSdkDeclarationError`, `action`, `describe_plugin`,
  `plugin`), plus the explicit submodules `qgis_sdk.models`, `qgis_sdk.services`,
  `qgis_sdk.core`, `qgis_sdk.adapters.desktop`, `qgis_sdk.adapters.webengine`,
  `qgis_sdk.adapters.pydantic`, `qgis_sdk.adapters.pydantic_types`, and
  `qgis_sdk.scaffold` (`qgis-sdk scaffold` CLI). All packages and the repository root
  are licensed under MIT (`LICENSE`).

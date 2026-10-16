# qgis-sdk

**Python SDK foundations for developing QGIS plugins.**

`qgis-sdk` is the Python package in the QGIS SDK workspace. It is intended to grow into a reusable foundation for plugin authors who want maintainable, source-testable code and a consistent packaging workflow.

> **Status:** early scaffold with an experimental, QGIS-free contract layer. `qgis_sdk.hello()` remains a smoke-test API. Plugin lifecycle, native QGIS adapters, actual GIS services, declarations, and the bridge runtime are not implemented yet.

The [`qgis-sdk` PyPI listing](https://pypi.org/project/qgis-sdk/) is currently a `0.0.0` placeholder with no project description, not a functional SDK release. Use this repository's source package for development; see the [workspace README](../../README.md) for details and the npm bridge listing status.

## Pure contract layer (experimental)

The public `qgis_sdk.models`, `qgis_sdk.services`, and `qgis_sdk.core` modules import without QGIS or Qt. Dependencies flow **models ← services ← core**; the pure layers do not import native adapters, bridge transports, testing fakes, or CLI tools. These are contracts, not a runnable plugin or a replacement for PyQGIS.

| Module | Current contract |
| :-- | :-- |
| `models` | `QgisSdkError`, `QgisSdkScopeClosedError`, `QgisSdkUnsupportedCapabilityError` |
| `services` | Structural `Notifications`, `ViewControl`, `Progress`, `Cancellation`, and `DesktopAccess` protocols; implementations are supplied by the host or by tests |
| `core` | `PluginContext`, `UiContext`, `AlgorithmContext`, `JobContext`, and `ResourceScope` |

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

`qgis_sdk.hello()` still validates package wiring:

```python
from qgis_sdk import hello
print(hello())  # hello world
```

## Development

From the workspace root, install the Pixi environments and run the Python tests:

```sh
pixi install -e default
pixi install -e build
pixi run -e default pytest -c packages/qgis-sdk/pyproject.toml packages/qgis-sdk/tests
```

The Python development dependencies are declared in this package's `dev` extra. Pixi pins its Python tools and installs Hypothesis/pytest-cov as wheels; the workspace package is loaded from `packages/qgis-sdk/src` on `PYTHONPATH` rather than installed as a Pixi path dependency.

The checked contract-generation example lives in `tests/contract_sample/` and is run via the workspace's `sdk:generate` package script; see the [workspace README](../../README.md#checked-contract-generation-example). Mashumaro exports JSON Schemas for these test DTOs, and test-only `jsonschema` checks the same examples as the bridge's Ajv tests. Both are development dependencies, **not** chosen SDK runtime validators; the ordinary dataclasses and this example generator are not a published `sdk generate` CLI.

## Build artifacts

The package uses Hatchling for Python distributions and an explicit Conda recipe:

```sh
pixi run -e bun bun run --filter qgis-sdk build
```

The combined build produces a wheel and source distribution under `dist/pypi/`, checks them with Twine, and builds the Conda artifact under `dist/conda/`.

See the [workspace README](../../README.md) for the full development setup, coverage tasks, Pixi environments, and the TypeScript bridge for QGIS `QWebEngineView` plugin interfaces.

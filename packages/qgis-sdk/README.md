# qgis-sdk

**Python SDK foundations for developing QGIS plugins.**

`qgis-sdk` is the Python package in the QGIS SDK workspace. It is intended to grow into a reusable foundation for plugin authors who want maintainable, source-testable code and a consistent packaging workflow.

> **Status:** early scaffold with an experimental, QGIS-free contract layer. `qgis_sdk.hello()` remains a smoke-test API. Plugin lifecycle, native QGIS adapters, actual GIS services, declarations, and the bridge runtime are not implemented yet.

The [`qgis-sdk` PyPI listing](https://pypi.org/project/qgis-sdk/) is currently a `0.0.0` placeholder with no project description, not a functional SDK release. Use this repository's source package for development; see the [workspace README](../../README.md) for details and the npm bridge listing status.

## Pure contract layer (experimental)

The public `qgis_sdk.models`, `qgis_sdk.services`, and `qgis_sdk.core` modules import without QGIS or Qt. Dependencies flow **models ← services ← core**; the pure layers do not import native adapters, bridge transports, testing fakes, or CLI tools. These are contracts, not a runnable plugin or a replacement for PyQGIS.

| Module | Current contract |
| :-- | :-- |
| `models` | `QgisSdkError`, `QgisSdkScopeClosedError`, `QgisSdkUnsupportedCapabilityError`, `QgisSdkOptionalDependencyError`, `QgisSdkValidationIssue`, and safe `QgisSdkContractValidationError` metadata |
| `adapters.pydantic` | Optional controlled-deployment adapter; Pydantic is imported only when the adapter is constructed |
| `adapters.pydantic_types` | Explicit Pydantic field annotation for finite JavaScript-safe integers |
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

The Python development dependencies are declared in this package's `dev` extra. Pixi pins its Python tools and installs Hypothesis, pytest-cov, and Pydantic 2.14.1 as wheels; Pydantic is needed only to test the optional adapter. The workspace package is loaded from `packages/qgis-sdk/src` on `PYTHONPATH` rather than installed as a Pixi path dependency.

The checked contract-generation examples live in `tests/contract_sample/` and are run via the workspace's `sdk:generate` package script; see the [workspace README](../../README.md#checked-contract-generation-example). Mashumaro remains a separate test-only schema-export example. The Pydantic example uses the optional adapter, emits its own request/reader/writer schemas, and is checked against the same Python/Ajv case corpus. Neither example is a general SDK generator or public operation.

## Optional controlled-deployment adapter (experimental)

`qgis_sdk.adapters.pydantic.PydanticContractAdapter` provides a narrow JSON-request → strict validation → typed handler → result-serialization slice for deployments that explicitly provision Pydantic. Models use standard-library dataclasses with Pydantic configuration; `qgis_sdk.adapters.pydantic_types.SafeJsonInteger` provides the agreed finite ±9007199254740991 wire bound while accepting integral JSON numbers such as `2.0`. Request, result-reader, and result-writer schemas remain distinct. Validation errors expose structured field paths and validator codes without copying rejected input values.

Pydantic **is not a base runtime dependency**. The explicit `controlled-deployment` extra pins `pydantic==2.14.1` (which installs native `pydantic-core`); administrators/developers provision it in their managed environment. The SDK never downloads or installs it at startup, and ordinary QGIS-free imports work without it. The adapter is a prototype, not a mandatory production backend selection. Current persistent tests exercise Linux/Python 3.14.8; Windows/QGIS coexistence, Desktop/WebEngine behavior, and Conda delivery are still qualification gates.

## Headless QGIS and WebEngine qualification

`tests/qualification/webengine_smoke.py` is a repeatable harness for the headless path QGIS uses to host a `QWebEngineView`. It starts a real QGIS application, loads a page in a real WebEngine view, tears QGIS down again and prints a machine-readable report:

```sh
pixi run -e default python packages/qgis-sdk/tests/qualification/webengine_smoke.py
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

| Requirement | Linux (qualified) | macOS | Windows |
| :-- | :-- | :-- | :-- |
| QGIS with Python bindings | Pixi `default` environment, QGIS 4.2.3 | not qualified | not qualified |
| Qt WebEngine Python bindings | `pyqt6-webengine` 6.11.0 | not qualified | not qualified |
| Display | none, `offscreen` | none, `offscreen` | none, `offscreen` |
| Chromium sandbox | disabled by the flags above | same | same |

Without the Chromium flags the WebEngine process fails with `eglInitialize: Failed to get system egl display`. ANGLE, EGL, dbus and PDAL messages printed during a run are noise and do not affect the result.

`tests/test_qualification_webengine.py` covers the harness helpers in the QGIS-free suite. The end-to-end run is opt-in, because it needs a real QGIS installation:

```sh
QGIS_SDK_HEADLESS_SMOKE=1 pixi run -e default pytest -c packages/qgis-sdk/pyproject.toml packages/qgis-sdk/tests/test_qualification_webengine.py
```

The headless path is **not** a Desktop GUI or plugin-lifecycle qualification: the development sandbox has no display and no Xvfb, and no Windows or macOS QGIS candidate has been tested. `qgis_sdk.adapters.webengine` therefore only proves that the optional bindings can be located and that a missing installation is reported with an actionable error.

## Build artifacts

The package uses Hatchling for Python distributions and an explicit Conda recipe:

```sh
pixi run -e bun bun run --filter qgis-sdk build
```

The combined build produces a wheel and source distribution under `dist/pypi/`, checks them with Twine, and builds the Conda artifact under `dist/conda/`.

See the [workspace README](../../README.md) for the full development setup, coverage tasks, Pixi environments, and the TypeScript bridge for QGIS `QWebEngineView` plugin interfaces.

---
id: doc-14
title: Workspace development, qualification harnesses and evidence
type: guide
created_date: '2026-10-24 21:20'
---
# Workspace development, qualification harnesses and evidence

How the workspace is developed and what has been proven on a real QGIS host.
This used to be spread across the root and package READMEs;
[decision-29](../../decisions/decision-29%20-%20Keep-READMEs-minimal-and-hold-reference-prose-in-backlog-guides-until-the-docs-site.md)
moved it here. The qualification tables and harness reports below are the
evidence [TASK-23](../../tasks/task-23%20-%20Qualify-candidate-QGIS-4-Windows-and-Linux-toolchains.md),
[TASK-24](../../tasks/task-24%20-%20Implement-scoped-plugin-runtime-and-native-lifecycle-adapter.md)
and [TASK-33](../../tasks/task-33%20-%20Qualify-Windows-macOS-and-Desktop-QGIS-targets.md)
cite; the numbers are the ones recorded when each harness last ran, not a
guarantee. [AGENTS.md](../../../AGENTS.md) and the skills under `.agents/skills/`
remain the authority for the session workflow.

## Quick start

Install Pixi and Bun, then install the locked environments and JavaScript dependencies:

```sh
curl -fsSL https://pixi.sh/install.sh | bash
pixi install -e default
pixi install -e build
pixi install -e bun
pixi run -e bun install-js
```

Check the package wiring from the workspace — `__all__` is the entire public surface:

```sh
pixi run -e default python -c 'import qgis_sdk; print(qgis_sdk.__all__)'
```

That prints the declarations API and nothing else; everything beyond it lives in an explicit submodule. To start a plugin project, install the package (`pip install qgis-sdk` or `pixi add --pypi qgis-sdk`) and run `qgis-sdk new <directory>`, which is the same entry point as `python -m qgis_sdk`; `qgis_sdk.scaffold` is the public API behind it. [doc-12](doc-12%20-%20qgis-sdk-Python-package-guide.md#choosing-desktop-or-standalone-qt-mode) covers Desktop versus standalone Qt mode, and [the scaffold evidence below](#load-and-unload-evidence-for-the-scaffolded-project) is the headless QGIS Desktop load/unload proof.

## Development environments

Pixi keeps the toolchains separate:

- `default`: Python, QGIS, Python development tools, and shared utilities.
- `build`: Python packaging and test tools without QGIS.
- `bun`: Bun and JavaScript workspace tooling, isolated from the Python environments.

Python development dependencies, including pytest, Rich, and Typer, are pinned in the Pixi Python feature. Hypothesis, pytest-cov, and Pydantic 2.14.1 are pinned as PyPI wheels (matching the package `dev` extra); Pydantic is present in development only to exercise the opt-in adapter and is not a required package runtime dependency. The workspace package is not an editable Pixi dependency so the sandbox publisher can pack wheels only; `PYTHONPATH` includes `packages/qgis-sdk-python/src`.

## Reproducible sandbox

The pinned Pixi Sandbox plan packages `default`, `build`, and `bun` for Linux x86-64 as the `developer` bundle. In a Git checkout with a published sandbox branch, restore it with:

```sh
bash scripts/restore.sh
```

Pushes to `main` publish the developer sandbox branch; pull requests with stale Pixi locks are relocked and revalidated. The devcontainer setup installs the pinned Pixi Sandbox CLI and then runs a locked Pixi install.

## Test, build and the Pixi tasks

```sh
pixi run -e bun bun run test       # source tests, without coverage gating
pixi run -e bun bun run coverage  # Python and TypeScript coverage checks
pixi run -e bun bun run build
pixi run -e bun typecheck
```

Root `build`, `test`, and `coverage` scripts delegate to Turbo. Tests run from source and do not depend on builds. Coverage has separate 90% checks for `qgis-sdk-python` and `qgis-sdk-typescript`, with repository-root-relative LCOV reports for Codecov.

| Task | Command | Purpose |
| :-- | :-- | :-- |
| Test | `pixi run -e bun bun run test` | Source tests, no coverage gate |
| Coverage | `pixi run -e bun bun run coverage` | Separate 90% Python/TypeScript coverage gates |
| Build | `pixi run -e bun bun run build` | Build workspace packages |
| Typecheck | `pixi run -e bun typecheck` | TypeScript bridge typecheck |
| Lint Python | `pixi run lint-python` | Ruff lint across the whole checkout |
| Format check Python | `pixi run format-python-check` | Ruff format check across the whole checkout |

Keep Python development tools in `packages/qgis-sdk-python/pyproject.toml`'s `dev` extra; Pixi installs that local extra through the Python feature. Keep direct Pixi dependency versions exactly pinned in `pixi.toml` and refresh `pixi.lock` when they change. Python build tooling and Twine stay in the Pixi Python feature; Bun remains in its separate environment.

## Repository layout

| Path | Role |
| :-- | :-- |
| `packages/qgis-sdk-python` | Python package: pure contract layer, declarations, scaffold command, lifecycle runtime |
| `packages/qgis-sdk-python/scripts` | Standalone developer executables (qualification harnesses, contract generators), covered by QGIS-free tests in `packages/qgis-sdk-python/tests/scripts` |
| `packages/qgis-sdk-python/tests` | Python tests for the package |
| `packages/qgis-sdk-typescript` | TypeScript bridge for QWebEngineView plugin interfaces |
| `packages/qgis-sdk-typescript/tests` | Bun tests for the bridge |
| `packages/qgis-sdk-alias` | Unscoped npm alias `qgis-sdk`: re-export files, manifest and Bun tests that pin it to the scoped package |
| `packages/config` | Shared TypeScript configuration and Bunup preset (private) |
| `.agents/skills` | Agent skills: session, backlog, tdd, refactor, clean-code-principles, skill-creator |
| `scripts` | Repository-root developer scripts (restore) |

## Contributing

- Keep source tests alongside each package's `tests/` directory.
- Run `pixi run -e bun bun run test` for local tests and `pixi run -e bun bun run coverage` for the coverage gates used by CI and pre-push.
- Keep direct Pixi dependency versions exactly pinned in `pixi.toml` and refresh `pixi.lock` when they change.
- Python build tooling and Twine stay in the Pixi Python feature; Bun remains in its separate environment.
- Lefthook runs staged-file Ruff/Biome checks, Convco validates commit messages, and pre-push runs the coverage task.

Commit messages use Conventional Commits form (validated by Convco). See [AGENTS.md](../../../AGENTS.md) for the session and merge workflow, and the agent skills under `.agents/skills/` for TDD, refactor, clean-code, backlog, and skill-creator guidance. Prefix every SDK-defined exception class (Python or TypeScript) with `QgisSdk` and export only prefixed exception names.

## Python package development

From the workspace root, install the Pixi environments and run the Python tests:

```sh
pixi install -e default
pixi install -e build
pixi run -e default pytest -c packages/qgis-sdk-python/pyproject.toml packages/qgis-sdk-python/tests
```

The Python development dependencies are declared in this package's `dev` extra. Pixi pins its Python tools and installs Hypothesis, pytest-cov, and Pydantic 2.14.1 as wheels; Pydantic is needed only to test the optional adapter. The workspace package is loaded from `packages/qgis-sdk-python/src` on `PYTHONPATH` rather than installed as a Pixi path dependency.

The checked contract-generation examples live in `tests/contract_sample/` and are run via the workspace's `sdk:generate` package script; see [Contract generation (checked example)](#contract-generation-checked-example). Mashumaro remains a separate test-only schema-export example. The Pydantic example uses the optional adapter, emits its own request/reader/writer schemas, and is checked against the same Python/Ajv case corpus. Neither example is a general SDK generator or public operation.

## Test layers

Every test in `packages/qgis-sdk-python/tests` belongs to exactly one layer, and each layer is a pytest marker you can select on its own (TASK-7). The markers are registered under `--strict-markers` by `tests/conftest.py` from `tests/layers.py`:

| Marker | Needs | Selected by |
| :-- | :-- | :-- |
| `pure` | Python only - no QGIS, Qt, display or network | derived: every test that declares no native layer |
| `qt` | a `QApplication` (offscreen) | `pytestmark = pytest.mark.qt` |
| `qgis` | an initialised `QgsApplication` | `pytestmark = pytest.mark.qgis` |
| `webengine` | Qt WebEngine and WebChannel under the application | `pytestmark = pytest.mark.webengine` |
| `desktop` | a real QGIS Desktop, opted in per harness flag | `@pytest.mark.desktop` |
| `native` | umbrella for `qt`, `qgis`, `webengine`, `desktop` | derived |

```sh
# the pure half, the way the macOS/Windows matrix runs it (QGIS is not installed there)
pixi run -e default pytest -c packages/qgis-sdk-python/pyproject.toml packages/qgis-sdk-python/tests -m pure
# one native layer, or all of them, offscreen
QT_QPA_PLATFORM=offscreen pixi run -e default pytest -c packages/qgis-sdk-python/pyproject.toml packages/qgis-sdk-python/tests -m webengine
QT_QPA_PLATFORM=offscreen QGIS_SDK_NATIVE_SERVICES=1 pixi run -e default pytest -c packages/qgis-sdk-python/pyproject.toml packages/qgis-sdk-python/tests -m native
```

How the layers stay honest:

- A native module imports its bindings in one guarded `try` at the top and calls `pytest.skip(..., allow_module_level=True)` with the reason, so a host without Qt reports what it lacks instead of failing. `tests/test_layers.py` runs a pure module next to the native ones in a child interpreter that refuses `qgis` and `PyQt6` imports and checks exactly that.
- The one application per process is owned by the session fixtures `qt_app` and `qgis_app` in `tests/conftest.py` (`qt_app` is already a `QgsApplication` whenever the QGIS bindings import, so the two layers never disagree about the application a process holds; `qgis_app` skips when only Qt is there) and stopped once at the end of the session; `webengine_profile` is the one `QWebEngineProfile`, because Chromium tears a profile down once per process. Native modules take `app` from these fixtures rather than building their own, so module order no longer decides which application a test sees. `tests/layers.py` prepares the headless environment (`QT_QPA_PLATFORM`, `QGIS_PREFIX_PATH`, the Chromium flags, an auth database directory) before any native module is collected, without importing Qt.
- The service backends in `tests/services/` run every contract against the in-memory fakes in the pure layer, and against real QGIS as a second `qgis`-marked parameter when `QGIS_SDK_NATIVE_SERVICES=1` is set; `tests/native_support.py` carries the loopback HTTP origin and the `pump`/`settle` loop helpers the network, WebEngine and WebChannel modules share.
- `pytest-bdd` features under `tests/features/` are ordinary pytest tests: the steps are functions in the same modules, and `tests/bridge_steps.py` - loaded as a plugin by `tests/conftest.py` - shows the shared form, where the `contract_host` fixture and the step definitions serve both `bridge_contract.feature` and `test_bridge_contract_fixtures.py`. A scenario can carry a native marker like any other test.
- The bridge contract vectors in `packages/qgis-sdk-typescript/tests/contracts/bridge/cases.json` are generated by `scripts/generate_bridge_cases.py` from the real dispatcher and consumed by the TypeScript client, the pure replay test and the feature above; `tests/test_webchannel_native.py` is the separate integration evidence that a real page over `QWebChannel` is bound to the host-minted identity and loses its subscriptions when the host disposes the view.

## Contract generation (checked example)

A **test-only**, QGIS-free example exercises the proposed web-project workflow without declaring a production validation backend or SDK CLI. From the workspace root, after installing the locked Pixi and Bun environments:

```sh
pixi run -e bun bun run sdk:generate
pixi run -e bun bun run coverage
pixi run -e bun typecheck
```

The `sdk:generate` package script keeps two schema examples separate. The test-only Mashumaro exporter uses ordinary dataclasses in `packages/qgis-sdk-python/tests/contract_sample/models.py`; the optional controlled-deployment exporter uses the adapter and fixtures in `packages/qgis-sdk-python/tests/contract_sample/pydantic_*`. Each emits request, result-reader, and result-writer Draft 2020-12 schemas. The bridge's locally installed `json2ts` (`json-schema-to-typescript==16.0.0`) generates checked-in TypeScript declarations under `packages/qgis-sdk-typescript/tests/contracts/`. No `npx`/`bunx` download is needed during generation. Python's test-only `jsonschema` oracle and bridge Ajv2020 tests check the same 40 cases against both schema sets with coercion and mutation disabled; generation drift and TypeScript required/nullable distinctions are checked in the normal suite.

`qgis_sdk.adapters.pydantic.PydanticContractAdapter` is a narrow optional prototype for controlled deployments: strict JSON request validation, typed handler dispatch, result serialization, and separate reader/writer schemas. `qgis_sdk.adapters.pydantic_types.SafeJsonInteger` implements the agreed finite JavaScript-safe integer range while accepting integral JSON numbers such as `2.0`. Its safe structured errors expose paths and validator codes, not rejected values. Pydantic is not imported by the default SDK modules or included in the base runtime; an administrator or developer must explicitly provision the `qgis-sdk[controlled-deployment]` extra. No startup installer is provided. Pydantic's native core and the `jsonschema` oracle remain outside ordinary plugin runtime dependencies.

These examples are **not** public SDK operations, a general SDK generator, or usable standalone frontend validators, and Pydantic is not selected as a mandatory production backend. The default Mashumaro decoder still coerces values and drops unknown fields, so it must not be used as the strict request boundary. Broader constraint/union support, WebEngine CSP-safe validators, and version/compatibility handshakes still need implementation. Windows/QGIS installation coexistence, Desktop/WebEngine behavior, and Conda/package delivery remain unqualified before any product-level native-runtime decision.

## Build artifacts

The package uses Hatchling for Python distributions and an explicit Conda recipe:

```sh
pixi run -e bun bun run --filter qgis-sdk-python build
```

The combined build produces a wheel and source distribution under `dist/pypi/`, checks them with Twine, and builds the Conda artifact under `dist/conda/`.

## Developer scripts

Standalone executables live in `packages/qgis-sdk-python/scripts/` next to `src/`: they are runnable
tools rather than test data, so they stay out of `tests/`, and they must stay out
of `src/qgis_sdk/` because a wheel cannot ship a command that imports a display
server. Each script is covered by a module in `tests/scripts/`, and the harnesses
themselves are opt-in through the environment flags below. `scripts/` is not an
importable package: the repository root already owns that top-level name, so
tests import a harness by module name via `tests/conftest.py`.

None of it is shipped. `[tool.hatch.build.targets.wheel].packages` packs
`src/qgis_sdk` (the runtime a plugin vendors) and `src/qgis_sdk_tools` (the
developer tools; decision-35) and nothing else, and `recipe.yaml` builds the Conda package by
pip-installing that same project, so neither the wheel nor the Conda artifact can
carry a harness, a generator or a test path. The one executable-shaped file inside
the package is `qgis_sdk_tools/__main__.py`, and it belongs there because it *is* the
distributed command; `scripts/` would be the wrong home for it, since a user who
installed the wheel has no `scripts/` directory to point at.

## Headless QGIS and WebEngine qualification

`scripts/webengine_smoke.py` is a repeatable harness for the headless path QGIS uses to host a `QWebEngineView`. It starts a real QGIS application, loads a page in a real WebEngine view, tears QGIS down again and prints a machine-readable report:

```sh
pixi run -e default python packages/qgis-sdk-python/scripts/webengine_smoke.py
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
| TypeScript bridge (`packages/qgis-sdk-typescript`) | Qualified (Bun 1.4.2, 95 tests, 100% cov) | Qualified in CI (Bun 1.4.2, 95 tests) | Qualified in CI (Bun 1.4.2, 95 tests) |
| QGIS with Python bindings | Qualified (Pixi `default`, QGIS 4.2.3) | Blocker: no macOS QGIS 4 prefix in CI/sandbox (TASK-33 AC #1) | Blocker: no Windows QGIS 4 prefix in CI/sandbox (TASK-33 AC #1) |
| Qt WebEngine Python bindings (`pyqt6-webengine` 6.11.0) | Qualified headless (`offscreen`, Chromium 140.0.0.0) | Blocker: requires macOS QGIS/Qt prefix | Blocker: requires Windows QGIS/Qt prefix |
| Headless QGIS Desktop plugin manager (`qgis --noplugins --code`) | Qualified (`scaffold_desktop_smoke.py`, `desktop_adapter_smoke.py`, `plugin_coexistence_smoke.py`) | Blocker: requires macOS QGIS Desktop binary | Blocker: requires Windows QGIS Desktop binary |
| Two-plugin `pydantic` / `pydantic_core` coexistence in QGIS Desktop | Qualified on Linux (`plugin_coexistence_smoke.py`, TASK-33 AC #3) | Blocker: requires macOS QGIS Desktop binary | Blocker: requires Windows QGIS Desktop binary |
| QGIS network transport (`NativeNetworkTransport`: proxy, auth database, certificate trust, redirects, body ceiling) | Qualified headless against loopback servers (`tests/test_network_native.py`, 25 tests; limits from `network_limits_probe.py`, doc-15) | Blocker: requires macOS QGIS/Qt prefix | Blocker: requires Windows QGIS/Qt prefix |
| Display-server Desktop GUI + in-Desktop `QWebEngineView` rendering | Blocker: no display server or `Xvfb` in sandbox/CI (`offscreen` renders no widgets, TASK-33 AC #2) | Blocker: no interactive display session in CI (TASK-33 AC #2) | Blocker: no interactive display session in CI (TASK-33 AC #2) |
| Chromium sandbox | Disabled by headless flags above | N/A | N/A |

Without the Chromium flags the WebEngine process fails with `eglInitialize: Failed to get system egl display`. ANGLE, EGL, dbus and PDAL messages printed during a run are noise and do not affect the result.

`tests/scripts/test_qualification_webengine.py` covers the harness helpers in the QGIS-free suite. The end-to-end run is opt-in, because it needs a real QGIS installation:

```sh
QGIS_SDK_HEADLESS_SMOKE=1 pixi run -e default pytest -c packages/qgis-sdk-python/pyproject.toml packages/qgis-sdk-python/tests/scripts/test_qualification_webengine.py
```

The headless path is **not** a visible Desktop GUI qualification and does **not** claim universal QGIS 4 support: the Linux sandbox and CI runners have no display server or `Xvfb`, and `pixi.toml` locks `linux-64` only, so no Windows or macOS QGIS 4 installation has been tested. `qgis_sdk.adapters.webengine` therefore only proves that the optional bindings can be located on a qualified host and that a missing installation is reported with an actionable error.

## Desktop lifecycle harnesses

The headless lifecycle harness uses a real `QgsApplication` and the adapter:

```sh
pixi run -e default python packages/qgis-sdk-python/scripts/desktop_lifecycle_smoke.py
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
QGIS_SDK_HEADLESS_LIFECYCLE=1 pixi run -e default pytest -c packages/qgis-sdk-python/pyproject.toml packages/qgis-sdk-python/tests/scripts/test_qualification_lifecycle.py
```

### Real Desktop startup and unload evidence

`scripts/desktop_adapter_smoke.py` supplies the evidence that harness cannot: it writes
a small fixture plugin that uses `create_class_factory`, installs it into a clean
throwaway profile, and lets the **QGIS Desktop application's own plugin manager** load,
start and unload it. The fixture belongs to this harness rather than to the scaffolded
project, so the adapter contract is proven without depending on `qgis_sdk.scaffold`.

```sh
pixi run -e default python packages/qgis-sdk-python/scripts/desktop_adapter_smoke.py
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
QGIS_SDK_DESKTOP_ADAPTER=1 pixi run -e default pytest -c packages/qgis-sdk-python/pyproject.toml packages/qgis-sdk-python/tests/scripts/test_qualification_desktop_adapter.py
```

The Qt scheduler harness exercises the `StepScheduler` seam inside a real
`QgsApplication` on the offscreen platform: alternating GUI phases and worker
handoffs, cancellation acknowledgement, refusal of late reports after disposal,
and quiesce blocking on an unresolved handoff. It compares tick latency while a
worker is blocked against latency while phases are scheduled:

```sh
pixi run -e default python packages/qgis-sdk-python/scripts/qt_scheduler_smoke.py
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
[doc-6](../plans/doc-6%20-%20TASK-13-Qt-scheduler-spike-evidence.md). Run the
opt-in test with:

```sh
QGIS_SDK_QT_SCHEDULER=1 pixi run -e default pytest -c packages/qgis-sdk-python/pyproject.toml packages/qgis-sdk-python/tests/scripts/test_qualification_scheduler.py
```

The network limits probe measures what
[decision-4](../../decisions/decision-4%20-%20QGIS-aware-networking-uses-an-async-first-transport.md)
left to TASK-5: how `QgsNetworkAccessManager` handles redirects on its own
(policy, hop count, which headers it forwards to another origin), what a
transport-followed hop costs, and how long the GUI thread stalls when a 1 to
128 MiB body is handed over in one piece. It prints one JSON report with a
`recommended` block:

```sh
pixi run -e default python packages/qgis-sdk-python/scripts/network_limits_probe.py
```

The shipped defaults (20 redirects, 16 MiB buffered body) and the finding that
made the transport follow redirects itself are recorded in
[doc-15](../plans/doc-15%20-%20TASK-5-network-limits-measurement-evidence.md).
`tests/scripts/test_network_limits_probe.py` pins the recommendation rule in the
QGIS-free suite; the measurement itself is opt-in:

```sh
QGIS_SDK_NETWORK_PROBE=1 pixi run -e default pytest -c packages/qgis-sdk-python/pyproject.toml packages/qgis-sdk-python/tests/scripts/test_network_limits_probe.py
```

The transport's own integration coverage is `tests/test_network_native.py`:
loopback `http.server` origins only, run offscreen by the CI step "Test native
forms and networking offscreen" and by the coverage run in the `default`
environment. It covers the coroutine and blocking forms, timeout versus
cancellation, scope close aborting replies, the body ceiling aborting a
download, cross-origin redirects dropping `Authorization`/`Cookie`/auth
configuration, `https` → `http` refusal, the QGIS proxy setting (`proxy/proxy-*`
settings entries routed to a loopback proxy), a Basic authentication
configuration applied by `QgsAuthManager` from a throwaway auth database
(`QGIS_AUTH_DB_DIR_PATH`), an untrusted self-signed certificate as
`QgisSdkTlsError`, and the same certificate accepted once stored as a QGIS
certificate authority.

### Optional native-runtime plugin coexistence (TASK-33 AC #3)

QGIS plugins share one embedded Python interpreter and `sys.modules` table inside the
Desktop process. `scripts/plugin_coexistence_smoke.py` proves that an SDK plugin using
`qgis_sdk.adapters.pydantic.PydanticContractAdapter` (`pydantic==2.14.1` and its native
`pydantic_core` extension) coexists cleanly with a pre-existing non-SDK plugin that
already imports and validates with Pydantic:

```sh
pixi run -e default python packages/qgis-sdk-python/scripts/plugin_coexistence_smoke.py
QGIS_SDK_PLUGIN_COEXISTENCE=1 pixi run -e default pytest -c packages/qgis-sdk-python/pyproject.toml packages/qgis-sdk-python/tests/scripts/test_qualification_coexistence.py
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

### Load and unload evidence for the scaffolded project

A standalone run cannot prove QGIS accepts the package, so
`scripts/scaffold_desktop_smoke.py` scaffolds into a temporary directory, installs
the plugin package into a clean throwaway profile, and runs the **QGIS Desktop
binary** so that QGIS's own plugin machinery - `qgis.utils.findPlugins`,
`loadPlugin`, `startPlugin`, `unloadPlugin` - discovers it, parses its
`metadata.txt` with QGIS's own parser, calls `classFactory(iface)` and `initGui()`,
invokes the declared action and unloads it, with the SDK reporting `running` and
then `stopped`:

```sh
pixi run -e default python packages/qgis-sdk-python/scripts/scaffold_desktop_smoke.py
QGIS_SDK_SCAFFOLD_DESKTOP=1 pixi run -e default pytest -c packages/qgis-sdk-python/pyproject.toml packages/qgis-sdk-python/tests/scripts/test_qualification_scaffold.py
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
[Real Desktop startup and unload evidence](#real-desktop-startup-and-unload-evidence).

### Generated web projects: toolchain and in-QGIS evidence

`qgis-sdk new --web vanilla|react` writes a Vite app whose dependencies are
pinned to the versions the release was qualified with (`WEB_TEMPLATE_VERSIONS`
in `qgis_sdk_tools/scaffold/web.py`, `@archont561/qgis-sdk` by exact version). The
unit tests prove the plan - file list, pins, `bridge generate --check` finding
no drift in the checked-in client, `check` passing with no native exemption,
the starter pytest passing - without a network. What they cannot prove is that
the pinned toolchain resolves and that the built page works inside Chromium,
so `tests/test_scaffold_web_native.py` is opt-in:

```sh
QGIS_SDK_SCAFFOLD_WEB=1 QT_QPA_PLATFORM=offscreen pixi run -e default pytest -c packages/qgis-sdk-python/pyproject.toml packages/qgis-sdk-python/tests/test_scaffold_web_native.py
```

For every package manager it finds (`bun`, `npm`, `pnpm` on `PATH`, or Bun in
the sibling Pixi environment) and for both frameworks it scaffolds, runs the
manager's install, `test` (Vitest against the scripted host), `typecheck`
(`tsc`) and `build`, then loads the built `<plugin>/web/index.html` in a
restricted `QWebEnginePage` under a headless `QgsApplication`, clicks Ping in
the page and waits for the plugin's answer to arrive over QWebChannel; the
React project opens as a dock, the vanilla one as a dialog. Last run here:
2026-10-25, QGIS 4.2.3 (Qt 6.11.2, Chromium 140) on Linux with Bun 1.4.2,
npm 10.9.8 (Node 22) and pnpm 10.34.8: 12 passed. A manager that is absent
is a skip, never a pass.

### `qgis-sdk test` and `qgis-sdk dev` against real QGIS (TASK-26, TASK-6)

The unit tests of `qgis_sdk_tools.devtools` assert on *plans* - the argv, working
directory, environment and notes a command would run with - through
`FakeCliRuntime`, and compile the startup scripts the commands hand to QGIS
(a `--code` script with a syntax error makes a headless QGIS hang in a modal
error dialog, silently). What only the binary can prove is opt-in:

```sh
QGIS_SDK_DEVTOOLS=1 QT_QPA_PLATFORM=offscreen pixi run -e default pytest -c packages/qgis-sdk-python/pyproject.toml packages/qgis-sdk-python/tests/test_devtools_native.py
```

It scaffolds a project, adds one `qgis`-marked and one `desktop`-marked test,
and drives the command line a user would type: `test` (pure) deselects both;
`test --target qgis` runs the first under a headless `QgsApplication`;
`test --target desktop` runs the second *inside* QGIS Desktop with the real
`iface`, loading the source plugin through `qgis.utils`; a failing desktop
test fails the command with pytest's exit code 1; a native target in which
every test skipped fails too. `dev --exercise <report>` (a hidden flag that
scripts the Reload button) proves the Desktop story end to end in one QGIS
process: the source plugin starts from `QGIS_PLUGINPATH`, reloads, a file
with a syntax error is refused while revision 2 keeps running, and after the
file is removed and the plugin's `ping` is edited to add 1000, the third
revision answers `1001`. `dev --mode standalone` reports the plugin running
with its window and a `ping` answer. With Bun available (on `PATH` or in the
sibling Pixi environment) it also scaffolds a vanilla web project, installs
its dependencies, and runs `dev` with the Vite server the command starts -
the report carries `view_shown` - then, in-process, loads the Vite-served
page in a restricted `QWebEnginePage`, clicks Ping, edits `web/src/app.ts`,
waits for the page to show the edit without a command restart and clicks
Ping again. Last run here: 2026-10-25, QGIS 4.2.3 (Qt 6.11.2, Chromium 140)
on Linux with Bun 1.4.2 and Vite 8.3.5: 9 passed in 19 s.

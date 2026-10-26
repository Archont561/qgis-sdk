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

Python development dependencies, including pytest, Rich, and Typer, are pinned in the Pixi Python feature. Hypothesis, pytest-cov, and Pydantic 2.14.1 are pinned as PyPI wheels (matching the package `dev` extra); Pydantic is present in development only to exercise the opt-in adapter and is not a required package runtime dependency. The workspace package is not an editable Pixi dependency so the sandbox publisher can pack wheels only; `PYTHONPATH` includes `packages/qgis-sdk-runtime/src` and `packages/qgis-sdk-tools/src`.

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
| `packages/qgis-sdk-runtime` | The `qgis-sdk-runtime` distribution (`src/qgis_sdk`): pure contract layer, declarations, lifecycle runtime, services, adapters |
| `packages/qgis-sdk-tools` | The `qgis-sdk-tools` distribution (`src/qgis_sdk_tools`): the `qgis-sdk` command, scaffold, check, devtools, pytest plugin, bridge generator |
| `packages/qgis-sdk-python` | The code-free `qgis-sdk` kit (pins the two above), the shared test suite, developer scripts and the three-output Conda recipe |
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

The Python development dependencies are declared in this package's `dev` extra. Pixi pins its Python tools and installs Hypothesis, pytest-cov, and Pydantic 2.14.1 as wheels; Pydantic is needed only to test the optional adapter. The workspace packages are loaded from `packages/qgis-sdk-runtime/src` and `packages/qgis-sdk-tools/src` on `PYTHONPATH` rather than installed as Pixi path dependencies; `packages/qgis-sdk-python` is the code-free `qgis-sdk` kit that owns the shared test suite, the developer scripts and the three-output Conda recipe.

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

The three Python distributions use Hatchling and share one explicit Conda recipe:

```sh
pixi run -e build release-build-python            # three wheels under dist/pypi/<runtime|tools|kit>/
pixi run -e build release-build-python --scope tools   # one distribution
pixi run -e bun bun run --filter qgis-sdk-python build # wheels + the Conda outputs (needs rattler-build)
```

`release.py build-python` writes one directory per distribution and checks every wheel with Twine; `release.yml` publishes each directory from its own step. The recipe builds `qgis-sdk-runtime`, `qgis-sdk-tools` and `qgis-sdk` under `dist/conda/`; only the outputs a tag's scope ships are uploaded.

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

The support promise itself is one machine-readable source, `qgis_sdk_tools.targets` (TASK-9 AC 2, [decision-37](../../decisions/decision-37%20-%20State-support-as-a-matrix-of-demonstrated-targets.md)): `qgis-sdk targets` prints it, [doc-12](doc-12%20-%20qgis-sdk-Python-package-guide.md#supported-targets) renders it, `tests/test_targets_native.py` fails when the host the native suite runs on is not a qualified row, and the release workflow records it in the job summary. The table below is the per-requirement evidence behind those rows.

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
a small fixture plugin whose `__init__.py` is the one line `qgis-sdk build` stages
(`classFactory = host("<pkg>.plugin:<Class>")`, decision-43) with its own
`context_factory`, installs it into a clean throwaway profile, and lets the **QGIS
Desktop application's own plugin manager** load, start and unload it. The fixture
belongs to this harness rather than to the scaffolded project, so the host contract
is proven without depending on the scaffold; `scripts/plugin_coexistence_smoke.py`
binds its SDK plugin the same way.

```sh
pixi run -e default python packages/qgis-sdk-python/scripts/desktop_adapter_smoke.py
```

```json
{
  "action_result": 7,
  "actions_detached": true,
  "error": null,
  "form_submitted": true,
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
`ctx.desktop` to hand that live object back through the typed escape hatch, and
`message_bar_received` requires the notifications service to add a real widget to QGIS's
own bar, and `form_submitted` requires the fixture's `Form.for_action` dialog, opened
through `ctx.ui`, to reach the `ping` handler when its `buttons/run` button is clicked.
`scope_released` and `actions_detached` are the runtime's side of the same
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
`metadata.txt` (rendered by `build` from `pyproject.toml`) with QGIS's own parser,
calls the staged `classFactory(iface)` - `host()` - and `initGui()`,
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
so `tests/test_scaffold_web_native.py` is opt-in. It runs the generated page on
the *workspace* bridge, not the pinned release: the session fixture
`workspace_bridge` (`conftest.py`, `layers.pack_workspace_bridge`) builds
`packages/qgis-sdk-typescript` and packs it with `bun pm pack`, and the
scaffold receives that tarball through `sdk_dependency=` - the same
`--sdk-dependency` flag the CLI exposes (decision-41). A tarball rather than
the directory because Bun would try to install the directory's own
`workspace:*` tooling, and because a tarball is exactly what a release ships.

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
hands the bootstrap to `qgis_sdk_tools.devtools.exercise`) proves the
Desktop story and the TASK-21 reload policy end to end in one QGIS process:
the source plugin starts from `QGIS_PLUGINPATH`, reloads, a file with a
syntax error is refused while revision 2 keeps running, after the file is
removed and the plugin's `ping` is edited to add 1000 the third revision
answers `1001`; a job whose worker thread blocks on an event makes the next
reload refuse after the 2 s bound with the blocker `job exercise.stuck#1 is
waiting on an unresolved worker handoff` while the plugin and the job stay
running, and the reload after the event is released succeeds; an import
error injected into `plugin.py` fails the start after teardown, the plugin
is reported disabled and not active, and the next reload recovers; three
back-to-back requests become one reload; with the watcher running, an edit
to `plugin.py` (`+ 2000`) reloads once without a button press and `ping`
answers `2001`. Eight revisions in total. The reload policy itself is unit
tested without QGIS in `tests/test_devtools_reloader.py` against a scripted
plugin host, and the runtime side (`scope.on_quiesce`,
`PluginRuntime.quiesce`) in `tests/test_quiesce.py`.
`dev --mode standalone` reports the plugin running
with its window and a `ping` answer. With Bun available (on `PATH` or in the
sibling Pixi environment) it also scaffolds a vanilla web project, installs
its dependencies, and runs `dev` with the Vite server the command starts -
the report carries `view_shown` - then, in-process, loads the Vite-served
page in a restricted `QWebEnginePage`, clicks Ping, edits `web/src/app.ts`,
waits for the page to show the edit without a command restart and clicks
Ping again. Last run here: 2026-10-25, QGIS 4.2.3 (Qt 6.11.2, Chromium 140)
on Linux with Bun 1.4.2 and Vite 8.3.5: 9 passed in 19 s.

**Built ZIP in a clean profile** (TASK-8 AC4, decision-3), opt-in:

```sh
QGIS_SDK_BUILD_INSTALL=1 QT_QPA_PLATFORM=offscreen pixi run -e default pytest -c packages/qgis-sdk-python/pyproject.toml packages/qgis-sdk-python/tests/test_bundle_native.py
```

`tests/test_bundle_native.py` builds two scaffolded plugins with
`build_plugin`, unpacks both archives into a fresh profile's
`python/plugins/` (what *Install from ZIP* does), marks each vendored
`qgis_sdk` copy so they stand in for two SDK versions, and starts QGIS
Desktop with `PYTHONPATH` stripped of the SDK and a `--code` probe that
inserts a `sys.meta_path` finder refusing every `qgis_sdk` import. Both
plugins are listed, load and start through `qgis.utils`, answer `ping`, their
runtime classes come from `<plugin>._vendor.qgis_sdk.*` and are distinct
objects, each sees its own mark, `qgis_sdk` never enters `sys.modules`, and
both unload. The archive itself - layout, exclusions, vendoring and import
rewrite, reproducibility, validation rules, the web build step - is covered
without QGIS in `tests/test_bundle.py` (which also imports the extracted
archive in-process) and `tests/test_bundle_cli.py`. Last run here:
2026-10-25, QGIS 4.2.3: 1 passed in 4 s.

### Reference plugin through the toolchain (TASK-22)

`examples/simple` (plugin id `simple`) is the decision-19 workflow as one plugin: open
the bundled `data/points.geojson`, read the selection, buffer through
Processing in an explicit projected CRS into a new layer styled with the
packaged `reference/polygon-output` QML before it is presented, and export
that layer to a bare file name inside a directory a native folder picker
chose. Its five actions sit behind both the native `BufferDialog` built from
`Form.for_action` and the vanilla page in `web/`, through `QgisSdk` on the generated
`web/src/bridge.schema.ts`. The project was written by `qgis-sdk new` and keeps that
layout, so the example doubles as the proof that the commands compose.

The workflow class (`simple/workflow.py`) is the plugin's own code:
the runtime ships the services and the reference *algorithms*, and what a
plugin chains them into stays out of `qgis_sdk` (so the example is a worked
example, not a hidden runtime feature). Deterministic, no QGIS: the export
policy (`tests/test_exports.py`) and the fake/native layer contract
(`tests/services/test_layers_contract.py`, nine export cases per backend) in
the regular suite; the plugin's seventeen pure tests in its own `qgis-sdk
test` (declared actions, fixture open, selection, styled buffer with the
source untouched, refusals for a missing CRS, a missing export directory and
a file name that is a path, and the ordering file: styled before presented,
nothing presented on cancellation, an incompatible style or a host without
Processing, the plugin's own scope). CI runs the example's `qgis-sdk test`
and `qgis-sdk test --target qgis` on Linux through the `test-reference-example`
Pixi task, and the page's Vitest suite on the workspace bridge through
`test-reference-web` (`examples/*/web` are Bun workspace members; turbo builds
`@archont561/qgis-sdk` before `simple-web`'s `test`). The full native half is
opt-in:

```sh
QGIS_SDK_REFERENCE=1 QT_QPA_PLATFORM=offscreen pixi run -e default pytest -c packages/qgis-sdk-python/pyproject.toml packages/qgis-sdk-python/tests/test_reference_example_native.py
```

`tests/test_reference_example_native.py` runs `qgis-sdk new` with the
example's options into a temporary directory (`--sdk-dependency` pointing at
the packed workspace bridge, see above), copies the example over it except
`web/package.json` - the example's says `workspace:*`, which resolves only
inside the repository's Bun workspace, and the pure
`test_reference_example.py` proves it is otherwise byte-for-byte the
scaffold's - then drives the command line: `check` (no problems), `bridge generate
--check` (no drift), `test` (17 passed on the fakes), `test --target qgis`
(4 passed: the end-to-end run with the fixture byte-identical afterwards, a
geographic working CRS refused with nothing added, the native dialog and a
direct call dispatching one handler, the workflow class refusing an unknown
layer and a silent overwrite), Bun `install`/`test`/`typecheck`/
`build`, `qgis-sdk build` (the ZIP carries the fixture, the built page, the
vendored runtime and its polygon style, no tests), and `dev --exercise`
inside QGIS Desktop with the Vite server (a project without a `ping` action
gets the smoke report: started, reloaded, view shown, unloaded). Finally, in
a headless `QgsApplication`, it opens the plugin's dock with the *built* page
in a real `QWebEngineView`, clicks Open, Buffer and Export, reads the page's
answers over QWebChannel, then renders the native `buffer` dialog for the
same source layer and dispatches it: both outputs are polygon layers in
`EPSG:3857` with the source's three features and a `SimpleFill` renderer from
the packaged style, the project holds exactly source + two outputs, the
fixture's `sha256` is unchanged and the export directory holds exactly the
one file the page named. Run it in its own process: like the scaffold-web
harness it drives a generated plugin's view on Chromium's default profile
(`tests/conftest.py` skips the other webengine modules when either is
collected).

**Evidence rows (clean profile, task-22 AC 3).** Recorded as run, not
rounded up: the Linux row is in-sandbox evidence; no Windows host exists in
this workspace and the cross-platform job (doc-8) has not run, so the Windows
row is a blocker carried by TASK-33, not a pass.

| Target | QGIS | Python | Qt | Chromium | GDAL | Bun / Vite | Harness | Outcome |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Linux x86-64 (glibc 2.36, offscreen) | 4.2.3 | 3.14.8 | 6.11.2 | 140.0.7339.225 | 3.13.3 | 1.4.2 / 8.3.5 | `QGIS_SDK_REFERENCE=1`, 2026-10-25 | 5 passed in 12 s; `services` 133 passed with `QGIS_SDK_NATIVE_SERVICES=1` (after the workflow class moved into the example; its cases run in the example's own `qgis-sdk test`) |
| Windows x86-64 | - | - | - | - | - | - | none available | **blocked**: no host, no CI runner (TASK-33) |

The bridge inside the real `QWebEngineView` is the published
`@archont561/qgis-sdk` 0.3.0 from npm (the example pins it like any generated
project); no bridge defect surfaced, so the bridge is not re-released for
0.5.0.

## 0.4.0 release gate (TASK-30, 2026-10-25)

What was run before the Python 0.4.0 stamp was requested, on Linux with
QGIS 4.2.3 (Qt 6.11.2, Chromium 140), Bun 1.4.2, from `main` `7c7a1d0`
plus the gate branch. Every line is a command that ran here; nothing is
inferred from CI.

- **Required work.** TASK-6, TASK-8, TASK-16, TASK-19, TASK-21, TASK-26
  (and TASK-29, the previous gate) are Done; their merges are PRs #65,
  #69-#71, #73 and #74, each green on `checks`, macOS and Windows.
- **Scope.** `release.py plan --scope python --bump minor` from
  `python-v0.3.0` plans `python-v0.4.0` with ten features and three fixes
  (the push default would plan a 0.3.1 patch; the minor is the explicit
  act doc-4 requires). `plan --scope typescript` skips: no release-worthy
  commit since `ts-v0.3.0`, and `git diff ts-v0.3.0..main` under
  `packages/qgis-sdk-typescript` and `packages/qgis-sdk-alias` is empty, so
  the bridge is not released (TASK-30 AC5). `verify-versions` agrees on
  0.3.0 for both scopes and on contract version 1; the planned stamp moves
  the Python manifests only.
- **Changelog fix.** The 0.4.0 Python range starts before the 2026-10-24
  directory rename, and `release.py` classified commits by the new
  `packages/qgis-sdk-python/` prefix only, so the four features of PR #65
  (`new`, derived ids, `ctx` class attribute, services on `PluginContext`)
  were missing from the generated notes. Both spellings now count, with a
  test in `tests/scripts/test_release.py`.
- **Static gate.** `lint-python`, `format-python-check` (241 files),
  `test-release-tool` (192), `lint-github-actions`, `typecheck`,
  `biome-check` (44 files), `generate_bridge_clients.py --check` (up to
  date): all clean.
- **Suites.** Bun 3/3 tasks; `bun run coverage` 96.19% (gate 90%); Python
  1369 passed, 38 skipped; `tests/scripts` 192 passed.
- **Opt-in harnesses, one process per file** (see the note below):
  lifecycle 5, desktop adapter 22, coexistence 23, scaffold desktop 10,
  scaffold web 8 (21 s), native services qualification 6 + 1 skipped and
  `tests/services` 112, devtools 9 (29 s), built ZIP in a clean profile 1,
  headless WebEngine smoke 9. All passed.
- **Artifact.** `release.py build-python` + `verify-python` (twine) pass
  on `qgis_sdk-0.3.0-py3-none-any.whl` (99 files: `qgis_sdk`,
  `qgis_sdk_tools`, `dist-info/licenses/LICENSE`, no tests, no scripts,
  console script `qgis-sdk = qgis_sdk_tools.__main__:main`, one runtime
  dependency `typer==0.27.3`). In a fresh `venv` with only that wheel and
  its dependencies, every runtime and tools module imports without `qgis`
  entering `sys.modules`; `qgis-sdk new field_tools --no-input`, `check`
  (`checked 3 files: no problems`) and `build` (70 files, runtime 0.3.0,
  web: none) run from the installed package; the unpacked ZIP imports with
  the SDK absent from the interpreter, resolving `field_tools._vendor.qgis_sdk`
  and nothing top-level. `qgis-sdk test` needs `pytest`, which the wheel
  does not require - the `dev` extra does; that is the documented shape,
  not a defect.
- **Licences.** The wheel carries the MIT `LICENSE`; the built ZIP carries
  the SDK `NOTICE` under `_vendor`. That is the whole licence validation
  `build` performs: `DEP001` refuses third-party code inside the package, so
  there is no other licence to collect yet. When the `external` allowance
  grows beyond the runtime, licence collection becomes a build rule.
- **Released afterwards, on two explicit requests.** The stamp PR (#76,
  `release.py stamp --scope python --version 0.4.0`, merged as `a6b3d8e`)
  and then the annotated tag `python-v0.4.0` on that merge commit.
  `release.yml` run 40214978629 re-stamped from the tag, verified both
  scopes and the contract, built and published: PyPI `qgis-sdk 0.4.0`
  (wheel sha256 `66de7e45…3a7eb7`, bit-identical to the wheel built here
  before the stamp - the build is reproducible), prefix.dev conda
  `qgis-sdk-0.4.0-pyh4616a5c_0.conda` (sha256 `6354bbdc…2128a`), and the
  GitHub Release with both files and `SHA256SUMS`; the npm and GitHub
  Packages jobs skipped, as a Python-scope tag must. PyPI's JSON API
  confirms 0.4.0 as the latest version; prefix.dev is not reachable from
  the sandbox, so the conda publish is attested by the job log only.

## 0.5.0 release gate (TASK-31, 2026-10-25)

What was run before the Python 0.5.0 tag, on Linux x86-64 with QGIS 4.2.3
(Qt 6.11.2, Chromium 140), CPython 3.14.8 in the locked Pixi environment and
CPython 3.11.2 for the clean install, Bun 1.4.2, from `main` `3c7aaa5` (the
TASK-9 merge) plus this gate branch. Every line is a command that ran here;
nothing is inferred from CI.

- **Required work.** TASK-57, TASK-22 and TASK-9 are Done; their merges are
  PRs #78, #80, #81 and #82, each green on `checks`, macOS and Windows. The
  pipeline rehearsal `python-v0.5.0-rc.1` (run 40220722995) built three
  wheels and three Conda outputs from the split tree. Open targets stay
  blockers, not promises: Windows and macOS QGIS rows are `unqualified` in
  the support matrix (TASK-33), the display-server Desktop GUI row is a
  blocker, decision-15's presentation-state restore and decision-19's
  transformation-choice gap are recorded and out of this release.
- **Scope.** `release.py plan --scope python --bump minor` from
  `python-v0.4.0` plans `python-v0.5.0` with six features and one fix (the
  push default would plan 0.4.1; the minor is the explicit act). After the
  TASK-9 planner fix the candidate `python-v0.5.0-rc.1` no longer moves the
  base: the changelog covers everything since 0.4.0, which is what a 0.4.0
  user upgrades across. `plan --scope typescript` skips: no release-worthy
  commit since `ts-v0.3.0`, and `git diff ts-v0.3.0..main` under
  `packages/qgis-sdk-typescript` and `packages/qgis-sdk-alias` is empty, so
  the bridge is not released (AC 5). `verify-versions` on the unstamped tree
  agrees on 0.4.0 for runtime, tools and kit, 0.3.0 for the bridge, contract
  version 1 on both sides.
- **Static gate.** `lint-python`, `format-python-check` (258 files),
  `test-release-tool` (226), `lint-github-actions`, `typecheck`,
  `biome-check` (52 files), `generate_bridge_clients.py --check` (up to
  date): all clean.
- **Suites.** `bun run test` 3/3 tasks (bridge 187, alias 10, Python 1458
  passed / 42 skipped); `bun run coverage` Python 96.11%, bridge 96.49%
  lines (gate 90%); `tests/scripts` 226 passed.
- **Opt-in harnesses, one process per file:** lifecycle 5, desktop adapter
  22, coexistence 23, scaffold desktop 10, scaffold web 8, native services
  qualification 6 + 1 skipped and `tests/services` 133, devtools 9, built
  ZIP in a clean profile 1, headless WebEngine smoke 9, reference example
  through the toolchain 5 (`new`/`check`/`bridge generate --check`/`test`/
  `build`/`dev` on `examples/simple`, page and native dialog in one QGIS).
  `qgis-sdk check examples/simple`: 8 files, no problems; `qgis-sdk test
  --project examples/simple` 17 pure, `--target qgis` 4 native. All passed.
- **The bridge pair (AC 5).** The page inside the real `QWebEngineView` of
  the reference harness runs the published `@archont561/qgis-sdk` 0.3.0
  against this tree (the 0.5.0 runtime), contract version 1 on both sides.
  No defect surfaced, so no bridge source change and no bridge version is
  published; doc-12's "Supported targets" names the pair.
- **Stamp and artifacts.** `release.py stamp --scope python --version 0.5.0`
  moved the kit, runtime and tools manifests, the kit's exact pins, the
  tools' runtime range (`>=0.5.0,<0.6`) and the recipe's three versions;
  `verify-versions --scope python --version 0.5.0` agrees on all nine
  manifest entries and the contract. `build-python --scope python` +
  `verify-python` (twine) pass on `qgis_sdk-0.5.0-py3-none-any.whl`
  (`d4d933d9…0816f`, 4 files, no code, pins `qgis-sdk-runtime==0.5.0` and
  `qgis-sdk-tools==0.5.0`), `qgis_sdk_runtime-0.5.0-py3-none-any.whl`
  (`c5f3a3ac…6a764`, 75 files, no dependency; `pydantic==2.14.1` behind the
  `controlled-deployment` extra) and `qgis_sdk_tools-0.5.0-py3-none-any.whl`
  (`7c2247ca…38de`, 32 files, console script
  `qgis-sdk = qgis_sdk_tools.__main__:main`, `qgis-sdk-runtime>=0.5.0,<0.6`
  and `typer==0.27.3`). Each wheel carries the MIT `LICENSE` under
  `dist-info/licenses`; `Requires-Python >=3.11` on all three. The Python
  suite and `tests/scripts` were rerun on the stamped tree: 1433 passed /
  42 skipped, 226 passed.
- **Clean install, on the `requires-python` floor.** A fresh CPython 3.11.2
  `venv` with only the three wheels and `typer` from PyPI: 79 of 82 modules
  import without `qgis` or `PyQt6` entering `sys.modules`; the three that do
  not are the documented optional edges (`adapters.pydantic_types` without
  pydantic, `adapters.qgis` without QGIS, `pytest_plugin` without pytest).
  `qgis-sdk new field_tools --no-input`, `check` (`checked 3 files: no
  problems`), `build` (72 files, runtime 0.5.0, web: none) and `targets`
  (the host lands on the CPython 3.11 QGIS-free row) run from the installed
  package; the unpacked ZIP imports under `python -S` with the SDK absent,
  resolving `field_tools._vendor.qgis_sdk` and no top-level `qgis_sdk`,
  with the SDK `NOTICE` under `_vendor` and no `qgis_sdk_tools` inside.
- **Licences.** As for 0.4.0: MIT `LICENSE` in each wheel, `NOTICE` in the
  built ZIP; `DEP001` still refuses third-party code inside a plugin, so
  there is no other licence to collect.
- **Not run here.** The Conda build (`release-build-conda`): rattler-build
  is not cached in the sandbox; the rc.1 rehearsal built all three outputs
  from the split recipe and `release.yml` builds them again before any
  upload, so a Conda defect fails the tag's run, not the user.
- **Approval.** Publishing 0.5.0 was authorised explicitly on 2026-10-25
  ("Gate + stamp + tag + publish", chosen from the three scopes offered),
  with a pause for "Merge" on each pull request; the tag follows on the
  merge commit of the gate-and-stamp pull request.
- **Released afterwards.** PR #83 merged as `386089b`; the annotated tag
  `python-v0.5.0` (release notes in the annotation) on that commit ran
  `release.yml` 40232586520: `build`, `conda`, `pypi` and `github-release`
  succeeded, `npm` and `github-packages` skipped as a Python-scope tag must.
  PyPI now serves `qgis-sdk 0.5.0` (`d4d933d9…0816f`), `qgis-sdk-runtime
  0.5.0` (`c5f3a3ac…6a764`) and `qgis-sdk-tools 0.5.0` (`7c2247ca…38de`) -
  the same hashes as the wheels built here before the merge, so the build is
  reproducible; `pip install qgis-sdk==0.5.0` from the index into a fresh
  CPython 3.11.2 venv resolves runtime and tools at 0.5.0 with `pip check`
  clean and `qgis-sdk targets` running from the installed package. The
  GitHub Release carries the three wheels, `qgis-sdk-0.5.0-pyhb2c62a3_0.conda`,
  `qgis-sdk-runtime-0.5.0-pyh4616a5c_0.conda`,
  `qgis-sdk-tools-0.5.0-pyh4616a5c_0.conda` and `SHA256SUMS`; the three
  prefix.dev uploads succeeded in the job log. The release-asset CDN and
  prefix.dev are not reachable from the sandbox, so the Conda checksums and
  that channel's listing are attested by the run only. The `0.0.0`
  placeholders of the runtime and the tools (and the kit's own `0.0.0`) on
  PyPI are now superseded and should be yanked by the owner.

## 0.6.0 release gate (TASK-60, 2026-10-26)

What was run on `main` `2763cad` (the TASK-67 merge, PR #98) on Linux
x86-64 with QGIS 4.2.3 (Qt 6.11.2), CPython 3.14.8 in the locked Pixi
environment and CPython 3.11.2 for the clean install, Bun 1.4.2. Every line
is a command that ran here; nothing is inferred from CI. The tree is
**unstamped**: manifests still say 0.5.0 / 0.3.0, so artifact names below
carry 0.5.0. Stamping, tagging and publishing wait for an explicit
"Release 0.6.0".

- **Required work.** TASK-58, 59, 61, 62, 63, 64, 65, 66 and 67 are Done
  (PRs #84–#98, each green on `checks`, macOS and Windows; #98's `main` run
  40374825948 green). Open targets stay blockers, not promises: Windows and
  macOS QGIS rows remain `unqualified` (TASK-33), the display-server Desktop
  GUI row is a blocker, decision-15 and decision-19 gaps are out of this
  release.
- **Scope.** `release.py plan --scope python --bump minor` from
  `python-v0.5.0` plans `python-v0.6.0`: five breaking changes (`feat(jobs)!`
  1ba9add, `feat(core)!` 43411d8, `feat(tools)` 9286234, `feat(runtime)!`
  4664769, `refactor(runtime)!` 56bae76) and fourteen features through
  `a8e4879`. `plan --scope typescript --bump minor` from `ts-v0.3.0` plans
  `ts-v0.4.0`: two breaking (ee95800, 9286234), four features (e1135a1,
  a4ca6e1, d922226, 9286234), one fix (d48c341); `git diff ts-v0.3.0..main`
  touches 13 bridge source files (+1637/−385). `verify-versions` on the
  unstamped tree agrees on 0.5.0 for runtime, tools and kit, 0.3.0 for
  `package.json`, the alias manifest, the alias dependency and the scaffold
  pin, contract version 1 on both sides. The changelog file the planner
  writes into the repository root was removed again.
- **Migration note completeness (AC 1).** An AST diff of module-level
  public names between `python-v0.5.0` and `main` under `qgis_sdk`: removed
  modules `qgis_sdk.reference(.algorithms)`; removed names
  `algorithms.{algorithm, AlgorithmResult}`, `providers.{RegisteredAlgorithm,
  parameter_kinds, LAYER_PARAMETER, METRES_PARAMETER}`,
  `declarations.{RunSignature, describe_run_method}`. All are named in
  doc-12's 0.6.0 note (the two inspectors were added by this gate; they were
  never in `__all__`). Added modules: `adapters.{surfaces, webview}`,
  `bindings`, `services.processing`, `testing.ui`,
  `ui.{actions, form_fields, surfaces}`. Tools removals (`check_entry_point`,
  `RUNTIME_DISTRIBUTIONS`, `WATCHED_FILES`, the scaffold `*_CLASS_FACTORY`,
  `TRANSPORT`, `WEBVIEW`) are internal to the command.
- **Static gate.** `lint-python`, `format-python-check` (280 files),
  `test-release-tool` (248), `lint-github-actions`, `typecheck`,
  `biome-check` (64 files), `generate_bridge_clients.py --check` (up to
  date): all clean.
- **Suites.** `bun run test` 5/5 tasks (bridge 234, alias 10, example page
  5, Python 1675 passed / 43 skipped including `tests/scripts`); `bun run
  coverage` Python 95.58%, bridge 98.55% lines (gate 90%); `tests/scripts`
  248 passed (the standalone run).
- **Opt-in harnesses, one process per file, all passed:** lifecycle 5,
  desktop adapter 22, coexistence 23, scaffold desktop 10, native services
  smoke 7, Qt scheduler 11, headless WebEngine 9, `tests/services` 134,
  scaffold web 8, devtools 9 (now including the `--ui native` dialog opened
  from its toolbar action before and after an edit, TASK-67), built ZIP in a
  clean profile 1, reference example through the toolchain 5. `qgis-sdk
  check examples/simple`: 9 files, no problems; `qgis-sdk test` on the
  example 17 pure, `--target qgis` 5 native; `test-reference-example` 5,
  `test-reference-web` 5.
- **A 0.5-style project under the 0.6 `check` (AC 3).** `qgis-sdk new
  legacy_tools --web vanilla` run from a `python-v0.5.0` worktree (so the
  project carries `metadata.txt`, `webview.py`, `classFactory`, `bridge.ts`
  and `transport.ts`), then today's `check`: `ENTRY002` on `__init__.py`,
  `META001` on `metadata.txt`, `PROJECT002` (no `[tool.qgis-sdk] plugin`)
  and `VERSION003` (no runtime requirement), `checked 4 files: 4 problems`,
  exit 1 - the API changes reported by name, no crash, each with the
  decision-43 remediation.
- **Build and clean install (unstamped).** `build-python --scope python`
  + `verify-python` (twine) pass on the three wheels (kit
  `d50b898c…fa18`, runtime `565bf3d0…f159`, tools `0d60ebd6…d7a1`, all
  named 0.5.0 until the stamp). A fresh CPython 3.11.2 `venv` with only the
  three wheels and `typer` from PyPI: `pip check` clean; 60 of 62 `qgis_sdk`
  modules import without `qgis` or `PyQt6` entering `sys.modules`, the two
  that do not are the documented optional edges (`adapters.pydantic_types`
  without pydantic, `adapters.qgis` without QGIS). From the installed
  package: `qgis-sdk new ft/field_tools --ui native`, `check` (`4 files:
  no problems`), `test` (4 passed, the `FakeUi` starter included),
  `targets` (the host lands on the CPython 3.11 QGIS-free row), `build`
  (78 files, web: none). The unpacked ZIP imports `field_tools.plugin` and
  `field_tools.ui` under `python -S` with the SDK absent, resolving
  `field_tools._vendor.qgis_sdk` and no top-level `qgis_sdk`; the generated
  `__init__.py` binds `classFactory = host(...)` and `metadata.txt`
  carries `hasProcessingProvider=no` for a project without providers.
- **The bridge pair (AC 5, evidence so far).** `HOST_FINGERPRINT`
  `sha256:f96bdf10…7d6f`, `HOST_SCHEMA_VERSION 1` and
  `BRIDGE_PROTOCOL_VERSION 1` are byte-identical at `ts-v0.3.0`,
  `python-v0.5.0` and `main`. The bridge delta since `ts-v0.3.0` is the
  root barrel, the prefixed generated errors, `bridge.schema.ts` +
  `QgisSdk.fromBridgeSchema`, nested ids and the consumer type check
  (doc-13's 0.4.0 note). Bridge 0.4.0 from this tree ran against the 0.6.0
  runtime from this tree inside a real `QWebEngineView` in the reference
  harness (`QGIS_SDK_REFERENCE=1`, 5 passed: the handshake answered by the
  real dispatcher) and in the scaffold web harness (8 passed). The stamp
  `ts-v0.4.0` will move `package.json`, the alias and the scaffold pin
  together (decision-41); not done here.
- **Licences.** As for 0.5.0: MIT `LICENSE` in each wheel
  (`dist-info/licenses`), `NOTICE` under `_vendor` in the built ZIP;
  `DEP001` still refuses third-party code inside a plugin.
- **Not run here.** The Conda build: `bun run build` succeeds for the
  bridge and the alias and fails at `qgis-sdk-python#build:conda` because
  conda-forge repodata is unreachable from the sandbox; `release.yml`
  builds the three outputs before any upload, and an `-rc.1` rehearsal can
  prove it again on request.
- **Approval.** Releasing 0.6.0 was authorised explicitly on 2026-10-26
  ("release", chosen from gate-only / gate + stamp / full after the gate
  record above was merged as #99 → `adc8fa0`), with a pause for "Merge" on
  the stamp pull request; the two tags follow on its merge commit.
- **Stamp and artifacts.** `release.py stamp --scope python --version
  0.6.0` moved the kit, runtime and tools manifests, the kit's exact pins,
  the tools' runtime range (`>=0.6.0,<0.7`), the recipe's three versions
  and the example's windows (`>=0.6,<0.7`); `stamp --scope typescript
  --version 0.4.0` moved `package.json`, the alias (and its pin on the
  scoped package) and the scaffold pin `SDK_NPM_VERSION` (decision-41).
  `verify-versions` agrees on 0.6.0 for all nine Python entries, 0.4.0 for
  the four bridge entries, contract version 1. One test literal followed
  the pin (`test_scaffold_web.py`, `0.3.0` → `0.4.0`). On the stamped tree:
  the static gate clean, `bun run test` 5/5 (bridge 234, alias 10, page 5,
  Python 1650 passed / 43 skipped), `tests/scripts` 248, reference example
  5 + 5, harnesses scaffold web 8, reference 5, bundle 1, scaffold desktop
  10. `build-python` + `verify-python` (twine) pass on
  `qgis_sdk-0.6.0-py3-none-any.whl` (`b6861c99…04f4`, pins
  `qgis-sdk-runtime==0.6.0` and `qgis-sdk-tools==0.6.0`),
  `qgis_sdk_runtime-0.6.0-py3-none-any.whl` (`8d5143c4…4cb3`, 74 modules,
  no dependency, MIT `LICENSE` in `dist-info/licenses`) and
  `qgis_sdk_tools-0.6.0-py3-none-any.whl` (`10894bf4…842f`,
  `qgis-sdk-runtime>=0.6.0,<0.7` and `typer==0.27.3`). A fresh CPython
  3.11.2 `venv` with only the three wheels: `pip check` clean; `qgis-sdk
  new --ui native --web vanilla` writes `qgis-sdk-runtime>=0.6,<0.7`,
  `qgis-sdk-tools>=0.6,<0.7` and `"@archont561/qgis-sdk": "0.4.0"`, and
  `check` is clean.
- **Released afterwards.** PR #100 merged as `0adb47a`; the annotated tags
  `python-v0.6.0` and `ts-v0.4.0` (release notes in the annotations) on
  that one commit ran `release.yml` twice: 40381881731 (`build`, `conda`,
  `pypi`, `github-release` succeeded; `npm`, `github-packages` skipped) and
  40381881508 (`build`, `npm`, `github-packages`, `github-release`
  succeeded; `conda`, `pypi` skipped). PyPI serves `qgis-sdk 0.6.0`
  (`b6861c99…04f4`), `qgis-sdk-runtime 0.6.0` (`8d5143c4…4cb3`) and
  `qgis-sdk-tools 0.6.0` (`10894bf4…842f`) - the same hashes as the wheels
  built here before the merge, so the build is reproducible; `pip install
  qgis-sdk==0.6.0` from the index into a fresh CPython 3.11.2 venv (about
  four minutes after upload, once the simple index caught up with the JSON
  API) resolves runtime and tools at 0.6.0 with `pip check` clean, and
  `qgis-sdk targets` / `new --ui native` / `check` run from the installed
  package. npm serves `@archont561/qgis-sdk@0.4.0` and the alias
  `qgis-sdk@0.4.0` as `latest`; `bun add` of both resolves the alias to the
  scoped package's objects, `QgisSdk.fromBridgeSchema` is callable and
  `@archont561/qgis-sdk/host` exports the unchanged `HOST_FINGERPRINT`. The
  GitHub Releases carry three wheels, `qgis-sdk-0.6.0-pyh38154c1_0.conda`,
  `qgis-sdk-runtime-0.6.0-pyh4616a5c_0.conda`,
  `qgis-sdk-tools-0.6.0-pyh4616a5c_0.conda` and `SHA256SUMS` (Python), the
  two tarballs and `SHA256SUMS` (TypeScript). prefix.dev uploads succeeded
  per the job log; that channel and the release-asset CDN are not reachable
  from the sandbox, so they are attested by the runs only. Still open for
  the owner: yank the `0.0.0` placeholders of the runtime and the tools on
  PyPI, deprecate the `0.0.0-stage` npm versions.

## Split release pipeline rehearsal (TASK-57 AC 3)

The pipeline for three distributions landed with PR #78 (`60c1dc2`):
`release.py classify/plan` emit `kit`/`runtime`/`tools` flags next to
`python`; `stamp`/`verify-versions` handle `python-v*` (the kit train),
`runtime-v*` and `tools-v*`; `build-python` writes `dist/pypi/<name>/`;
`release.yml` publishes each wheel from its own `pypa/gh-action-pypi-publish`
step and each Conda output from its own `publish-conda` call, in dependency
order (runtime, tools, kit). What ran here on 2026-10-25:

- `tests/scripts/test_release.py` (190) covers the scopes, the stamp shapes,
  the two refusals (a tools range that excludes the runtime at HEAD, a kit
  pin that leads the manifest it names) and the per-scope build.
- `release.py build-python --outdir /tmp/dist2` built and Twine-checked
  `runtime/qgis_sdk_runtime-0.4.0`, `tools/qgis_sdk_tools-0.4.0`,
  `kit/qgis_sdk-0.4.0`; `verify-python --dist` finds them recursively;
  `--scope runtime` built the runtime alone.
- `actionlint` passes on the workflows.

**Registry dry run (2026-10-25, after PR #78 merged as `60c1dc2`).**
rattler-build cannot run in the sandbox and the sandbox token cannot
dispatch workflows, so the Conda three-output build and the publish steps
were exercised with one prerelease tag, which the workflow treats as a dry
run (wheels and Conda outputs built and verified, every upload skipped):

```sh
git tag -a python-v0.5.0-rc.1 60c1dc2 -m "qgis-sdk 0.5.0-rc.1 ..."
git push origin python-v0.5.0-rc.1
```

`release.yml` run [40220722995](https://github.com/Archont561/qgis-sdk/actions/runs/40220722995),
all jobs green:

| Job | Outcome |
| --- | --- |
| `build` | classify (`python`, kit/runtime/tools true, prerelease true) -> stamp `0.5.0-rc.1` for scope `python` (three manifests, tools range `>=0.5.0rc1,<0.6`, recipe context) -> verify -> three wheels built and checked -> three-output Conda build -> artifacts |
| `pypi` | "Verify the wheel without uploading" passed; `Publish qgis-sdk-runtime/-tools/qgis-sdk to PyPI` skipped (prerelease) |
| `conda` | "Skip prefix.dev upload for prereleases"; the three per-output upload steps skipped |
| `github-release` | prerelease `python-v0.5.0-rc.1` with `qgis_sdk_runtime-0.5.0rc1`, `qgis_sdk_tools-0.5.0rc1`, `qgis_sdk-0.5.0rc1` wheels, `qgis-sdk-runtime-0.5.0rc1-pyh4616a5c_0`, `qgis-sdk-tools-0.5.0rc1-pyh4616a5c_0`, `qgis-sdk-0.5.0rc1-pyha27c6ed_0` Conda packages and `SHA256SUMS` |
| `npm`, `github-packages` | skipped (scope has no TypeScript) |

PyPI still lists `qgis-sdk-runtime` and `qgis-sdk-tools` at the `0.0.0`
placeholders only and `qgis-sdk` at 0.4.0, confirming nothing uploaded.
This closes AC 3 of TASK-57. The first clean `python-v0.5.0` tag will be the
first real publish of the two new names; yank the `0.0.0` placeholders after
it (owner-side).

Do not use a `workflow_dispatch` of `release.yml` with `tag=python-v0.4.0`
as a rehearsal: 0.4.0 is a clean version, so the runtime and tools steps
would publish for real.

**Run the webengine harnesses in separate processes.** The scaffold-web
harness drives a *generated* plugin's view, which uses Chromium's default
profile, while `test_webchannel_native.py` and `test_webengine_native.py`
share the session's off-the-record `webengine_profile`. One process that
runs the former and then either of the latter aborts (exit 134, after every
test passed) when Chromium tears the profiles down. Since 2026-10-25
`tests/conftest.py` skips the other webengine modules, with the reason,
whenever `test_scaffold_web_native.py` is collected in the same process
(`QGIS_SDK_SCAFFOLD_WEB=1`), so a combined invocation reports skips instead
of dying; the evidence run stays one file per process.


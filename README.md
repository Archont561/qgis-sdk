# QGIS SDK

<p align="center">
  <a href="https://github.com/Archont561/qgis-sdk/actions/workflows/ci.yml"><img src="https://github.com/Archont561/qgis-sdk/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://bun.sh"><img src="https://img.shields.io/badge/Bun-%E2%89%A51.1-black?logo=bun" alt="Bun >=1.1"></a>
  <a href="https://www.typescriptlang.org"><img src="https://img.shields.io/badge/TypeScript-strict-3178c6?logo=typescript" alt="TypeScript strict"></a>
</p>

**A Python-first foundation for developing QGIS plugins, including a bridge for plugin interfaces hosted in `QWebEngineView`.**

The goal is to help plugin authors build reusable, testable components and package them consistently across their QGIS projects. The TypeScript bridge connects the web frontend running inside QGIS's `QWebEngineView` to the plugin's Python/QGIS side. This repository is an early-stage scaffold: the Python package now includes experimental, QGIS-free context and service contracts alongside its smoke-test API; native plugin adapters and the bridge runtime are not implemented yet.

The registry entries currently point to placeholders, not usable SDK releases:

- [`qgis-sdk` on PyPI](https://pypi.org/project/qgis-sdk/) lists version `0.0.0` with placeholder metadata and no project description. It is not a released plugin-development SDK.
- [`@archont561/qgis-sdk-bridge` on npm](https://www.npmjs.com/package/@archont561/qgis-sdk-bridge) is version `0.0.0` and exists only to configure OIDC trusted publishing; its npm README states that it contains no executable code and should not be installed as a dependency.

Use this repository's source packages for development. The package listings are not installation instructions; replace this note with consumer install guidance when functional releases are published.

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

That prints the declaration decorators and their descriptions, and nothing else; there is no QGIS plugin API yet. To start a plugin project that uses them, install the package (`pip install qgis-sdk` or `pixi add --pypi qgis-sdk`) and run `qgis-sdk scaffold <directory>`, which is the same entry point as `python -m qgis_sdk`; `qgis_sdk.scaffold` is the public API behind it, and `packages/qgis-sdk/README.md` covers Desktop versus standalone Qt mode and the headless QGIS Desktop load/unload evidence.

## What it provides

| Package | Role | Current state |
| :-- | :-- | :-- |
| [`packages/qgis-sdk`](packages/qgis-sdk) | Python package intended as the core for QGIS plugin development | Experimental pure models/services/context contracts, declarations, a bounded plugin lifecycle runtime and the `qgis-sdk scaffold` project generator; no native plugin adapter yet; PyPI and Conda build pipelines are configured |
| [`packages/qgis-sdk-bridge`](packages/qgis-sdk-bridge) | TypeScript bridge for a plugin web UI hosted in QGIS `QWebEngineView` | Intended to connect the web frontend with the Python/QGIS plugin side; no bridge API yet, so the entry module is deliberately empty (a test pins that) and ships JavaScript only - no `types` mapping, because `bunup` emits no declaration for an exportless entry; built with Bunup |
| [`packages/config`](packages/config) | Shared TypeScript configuration and Bunup preset | Used by the bridge package |

The Python package is source-based and configured for a Python 3.11+ runtime. The Pixi `default` environment also provides QGIS for development and integration work.

## Test and build

```sh
pixi run -e bun bun run test       # source tests, without coverage gating
pixi run -e bun bun run coverage  # Python and TypeScript coverage checks
pixi run -e bun bun run build
pixi run -e bun typecheck
```

Root `build`, `test`, and `coverage` scripts delegate to Turbo. Tests run from source and do not depend on builds. Coverage has separate 90% checks for `qgis-sdk` and `qgis-sdk-bridge`, with repository-root-relative LCOV reports for Codecov.

## Contract generation (checked example)

A **test-only**, QGIS-free example exercises the proposed web-project workflow without declaring a production validation backend or SDK CLI. From the workspace root, after installing the locked Pixi and Bun environments:

```sh
pixi run -e bun bun run sdk:generate
pixi run -e bun bun run coverage
pixi run -e bun typecheck
```

The `sdk:generate` package script keeps two schema examples separate. The test-only Mashumaro exporter uses ordinary dataclasses in `packages/qgis-sdk/tests/contract_sample/models.py`; the optional controlled-deployment exporter uses the adapter and fixtures in `packages/qgis-sdk/tests/contract_sample/pydantic_*`. Each emits request, result-reader, and result-writer Draft 2020-12 schemas. The bridge's locally installed `json2ts` (`json-schema-to-typescript==16.0.0`) generates checked-in TypeScript declarations under `packages/qgis-sdk-bridge/tests/contracts/`. No `npx`/`bunx` download is needed during generation. Python's test-only `jsonschema` oracle and bridge Ajv2020 tests check the same 40 cases against both schema sets with coercion and mutation disabled; generation drift and TypeScript required/nullable distinctions are checked in the normal suite.

`qgis_sdk.adapters.pydantic.PydanticContractAdapter` is a narrow optional prototype for controlled deployments: strict JSON request validation, typed handler dispatch, result serialization, and separate reader/writer schemas. `qgis_sdk.adapters.pydantic_types.SafeJsonInteger` implements the agreed finite JavaScript-safe integer range while accepting integral JSON numbers such as `2.0`. Its safe structured errors expose paths and validator codes, not rejected values. Pydantic is not imported by the default SDK modules or included in the base runtime; an administrator or developer must explicitly provision the `qgis-sdk[controlled-deployment]` extra. No startup installer is provided. Pydantic's native core and the `jsonschema` oracle remain outside ordinary plugin runtime dependencies.

These examples are **not** public SDK operations, a general SDK generator, or usable standalone frontend validators, and Pydantic is not selected as a mandatory production backend. The default Mashumaro decoder still coerces values and drops unknown fields, so it must not be used as the strict request boundary. Broader constraint/union support, WebEngine CSP-safe validators, and version/compatibility handshakes still need implementation. Windows/QGIS installation coexistence, Desktop/WebEngine behavior, and Conda/package delivery remain unqualified before any product-level native-runtime decision.

## Development environments

Pixi keeps the toolchains separate:

- `default`: Python, QGIS, Python development tools, and shared utilities.
- `build`: Python packaging and test tools without QGIS.
- `bun`: Bun and JavaScript workspace tooling, isolated from the Python environments.

Python development dependencies, including pytest, Rich, and Typer, are pinned in the Pixi Python feature. Hypothesis, pytest-cov, and Pydantic 2.14.1 are pinned as PyPI wheels (matching the package `dev` extra); Pydantic is present in development only to exercise the opt-in adapter and is not a required package runtime dependency. The workspace package is not an editable Pixi dependency so the sandbox publisher can pack wheels only; `PYTHONPATH` includes `packages/qgis-sdk/src`.

## Reproducible sandbox

The pinned Pixi Sandbox plan packages `default`, `build`, and `bun` for Linux x86-64 as the `developer` bundle. In a Git checkout with a published sandbox branch, restore it with:

```sh
bash scripts/restore.sh
```

Pushes to `main` publish the developer sandbox branch; pull requests with stale Pixi locks are relocked and revalidated. The devcontainer setup installs the pinned Pixi Sandbox CLI and then runs a locked Pixi install.

## Repository layout

| Path | Role |
| :-- | :-- |
| `packages/qgis-sdk` | Python package: pure contract layer, declarations, scaffold command, lifecycle runtime |
| `packages/qgis-sdk/scripts` | Standalone developer executables (qualification harnesses, contract generators), covered by QGIS-free tests in `packages/qgis-sdk/tests/scripts` |
| `packages/qgis-sdk/tests` | Python tests for the package |
| `packages/qgis-sdk-bridge` | TypeScript bridge for QWebEngineView plugin interfaces |
| `packages/qgis-sdk-bridge/tests` | Bun tests for the bridge |
| `packages/config` | Shared TypeScript configuration and Bunup preset (private) |
| `.agents/skills` | Agent skills: session, backlog, tdd, refactor, clean-code-principles, skill-creator |
| `scripts` | Repository-root developer scripts (restore) |

## Development

| Task | Command | Purpose |
| :-- | :-- | :-- |
| Test | `pixi run -e bun bun run test` | Source tests, no coverage gate |
| Coverage | `pixi run -e bun bun run coverage` | Separate 90% Python/TypeScript coverage gates |
| Build | `pixi run -e bun bun run build` | Build workspace packages |
| Typecheck | `pixi run -e bun typecheck` | TypeScript bridge typecheck |
| Lint Python | `pixi run lint-python` | Ruff lint across the whole checkout |
| Format check Python | `pixi run format-python-check` | Ruff format check across the whole checkout |

Keep Python development tools in `packages/qgis-sdk/pyproject.toml`'s `dev` extra; Pixi installs that local extra through the Python feature. Keep direct Pixi dependency versions exactly pinned in `pixi.toml` and refresh `pixi.lock` when they change. Python build tooling and Twine stay in the Pixi Python feature; Bun remains in its separate environment.

## Contributing

- Keep source tests alongside each package's `tests/` directory.
- Run `pixi run -e bun bun run test` for local tests and `pixi run -e bun bun run coverage` for the coverage gates used by CI and pre-push.
- Keep direct Pixi dependency versions exactly pinned in `pixi.toml` and refresh `pixi.lock` when they change.
- Python build tooling and Twine stay in the Pixi Python feature; Bun remains in its separate environment.
- Lefthook runs staged-file Ruff/Biome checks, Convco validates commit messages, and pre-push runs the coverage task.

Commit messages use Conventional Commits form (validated by Convco). See [AGENTS.md](AGENTS.md) for the session and merge workflow, and the agent skills under [`.agents/skills/`](.agents/skills) for TDD, refactor, clean-code, backlog, and skill-creator guidance. Prefix every SDK-defined exception class (Python or TypeScript) with `QgisSdk` and export only prefixed exception names.

# QGIS SDK

**A Python-first foundation for developing QGIS plugins, including a bridge for plugin interfaces hosted in `QWebEngineView`.**

The goal is to help plugin authors build reusable, testable components and package them consistently across their QGIS projects. The TypeScript bridge is specifically for the web interface running inside QGIS's `QWebEngineView`, connecting that frontend to the plugin's Python/QGIS side. This repository is an early-stage scaffold: the Python package and bridge currently expose smoke-test APIs only; their plugin-facing APIs are not implemented yet.

## Package listings

The registry entries currently point to placeholders, not usable SDK releases:

- [`qgis-sdk` on PyPI](https://pypi.org/project/qgis-sdk/) lists version `0.0.0` with placeholder metadata and no project description. It is not a released plugin-development SDK.
- [`@archont561/qgis-sdk-bridge` on npm](https://www.npmjs.com/package/@archont561/qgis-sdk-bridge) is version `0.0.0` and exists only to configure OIDC trusted publishing; its npm README states that it contains no executable code and should not be installed as a dependency.

Use this repository's source packages for development. The package listings are not installation instructions; replace this note with consumer install guidance when functional releases are published.

## What is here

| Package | Role | Current state |
| :-- | :-- | :-- |
| [`packages/qgis-sdk`](packages/qgis-sdk) | Python package intended as the core for QGIS plugin development | Minimal `qgis_sdk.hello()` smoke-test API; PyPI and Conda build pipelines are configured |
| [`packages/qgis-sdk-bridge`](packages/qgis-sdk-bridge) | TypeScript bridge for a plugin web UI hosted in QGIS `QWebEngineView` | Intended to connect the web frontend with the Python/QGIS plugin side; currently only a minimal `hello()` smoke-test API; built with Bunup |
| [`packages/config`](packages/config) | Shared TypeScript configuration and Bunup preset | Used by the bridge package |

The Python package is source-based and configured for a Python 3.11+ runtime. The Pixi `default` environment also provides QGIS for development and integration work.

## Quick start

Install Pixi and Bun, then install the locked environments and JavaScript dependencies:

```sh
curl -fsSL https://pixi.sh/install.sh | bash
pixi install -e default
pixi install -e build
pixi install -e bun
pixi run -e bun install-js
```

Try the current Python package API from the workspace:

```sh
pixi run -e default python -c 'from qgis_sdk import hello; print(hello())'
```

`hello()` is currently a scaffold/smoke-test function, not a QGIS plugin API. The package README and tests describe the current surface.

## Test and build

```sh
pixi run -e bun bun run test       # source tests, without coverage gating
pixi run -e bun bun run coverage  # Python and TypeScript coverage checks
pixi run -e bun bun run build
pixi run -e bun typecheck
```

Root `build`, `test`, and `coverage` scripts delegate to Turbo. Tests run from source and do not depend on builds. Coverage has separate 90% checks for `qgis-sdk` and `qgis-sdk-bridge`, with repository-root-relative LCOV reports for Codecov.

The Python package builds a wheel and source distribution with Hatchling and a Conda package from the explicit `packages/qgis-sdk/recipe.yaml` recipe. Build outputs are under `packages/qgis-sdk/dist/`. The bridge build output is under `packages/qgis-sdk-bridge/dist/`.

## Development environments

Pixi keeps the toolchains separate:

- `default`: Python, QGIS, Python development tools, and shared utilities.
- `build`: Python packaging and test tools without QGIS.
- `bun`: Bun and JavaScript workspace tooling, isolated from the Python environments.

Python development dependencies, including pytest, Rich, and Typer, are pinned in the Pixi Python feature. Hypothesis and pytest-cov are pinned there as PyPI wheels (matching the `qgis-sdk` `dev` extra). The workspace package is not an editable Pixi dependency so the sandbox publisher can pack wheels only; `PYTHONPATH` includes `packages/qgis-sdk/src`.

## Reproducible sandbox

The pinned Pixi Sandbox plan packages `default`, `build`, and `bun` for Linux x86-64 as the `developer` bundle. In a Git checkout with a published sandbox branch, restore it with:

```sh
bash scripts/restore.sh
```

Pushes to `main` publish the developer sandbox branch; pull requests with stale Pixi locks are relocked and revalidated. The devcontainer setup installs the pinned Pixi Sandbox CLI and then runs a locked Pixi install.

## Contributing

- Keep source tests alongside each package's `tests/` directory.
- Run `pixi run -e bun bun run test` for local tests and `pixi run -e bun bun run coverage` for the coverage gates used by CI and pre-push.
- Keep direct Pixi dependency versions exactly pinned in `pixi.toml` and refresh `pixi.lock` when they change.
- Python build tooling and Twine stay in the Pixi Python feature; Bun remains in its separate environment.
- Lefthook runs staged-file Ruff/Biome checks, Convco validates commit messages, and pre-push runs the coverage task.

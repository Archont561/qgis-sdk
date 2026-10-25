---
name: qgis-sdk
description: Project-specific guidance for developing the Python QGIS SDK and its TypeScript bridge in this Pixi and Bun monorepo.
---

# QGIS SDK Development

Use this skill when changing the `qgis-sdk` Python package, the `@archont561/qgis-sdk` TypeScript package, their tests, builds, or workspace tooling.

## Repository layout

- `packages/qgis-sdk-python`: Python package built with Hatchling and the explicit Conda recipe.
- `packages/qgis-sdk-python/scripts`: standalone developer executables (qualification harnesses, contract generators), covered by the QGIS-free tests in `packages/qgis-sdk-python/tests/scripts`.
- `packages/qgis-sdk-typescript`: TypeScript bridge tested with Bun and built with Bunup.
- `packages/qgis-sdk-alias`: the unscoped npm name `qgis-sdk`, one `export *` per entry of `@archont561/qgis-sdk` at an exact pin; `scripts/release.py stamp` moves it with the bridge and its Bun tests pin it to the scoped manifest.
- `packages/config`: shared TypeScript and Bunup configuration.
- `pixi.toml`: root environments and pinned Conda dependencies; Bun remains in its separate environment.

## Development rules

- Keep Python development tools listed in the `qgis-sdk` `dev` extra. Do not add that extra as a Pixi path/editable PyPI dependency (pixi-pack only carries wheels). Pin Hypothesis and pytest-cov as wheels in the Python feature and keep `packages/qgis-sdk-python/src` on `PYTHONPATH`.
- Keep standalone executables in the package `scripts/` directory: never in `src/qgis_sdk/` or `src/qgis_sdk_tools/` (a wheel must not ship a tool that needs a display server) and never in `tests/` (a test file must not double as a command). The single exception is `src/qgis_sdk/__main__.py`, because it *is* the distributed command: the wheel's `qgis-sdk` console script and `python -m qgis_sdk` both reach it, so it has to live inside the package - `scripts/` is development automation that neither the wheel nor the Conda package ships. Keep it argument parsing over the public `qgis_sdk.scaffold` API, with no display dependency and no behaviour of its own, so the API stays testable without the CLI. Do not import that directory as a `scripts` package - the repository root already owns that top-level name; `packages/qgis-sdk-python/tests/conftest.py` puts `scripts/` and `tests/` on the path so tests import harnesses by module name, and a harness reaching a sibling or the `contract_sample` fixture does the same with its own directory. A script resolves those roots from `__file__` rather than the ambient `PYTHONPATH`, so it runs from a bare interpreter on any supported version and not only inside an activated environment.
- Run source tests locally with `pixi run -e bun bun run test`.
- Run Ruff through the whole-checkout tasks `pixi run lint-python` and `pixi run format-python-check`; keep their scope as `.` and put skips in the root `ruff.toml`. Do not re-add per-directory path lists — a new Python directory must be linted and format-checked without editing a task.
- Run coverage checks with `pixi run -e bun bun run coverage`. Keep the separate 90% checks and Codecov report paths intact.
- Build workspace packages with `pixi run -e bun bun run build`.
- Keep the bridge Bunup configuration package-local and import the shared preset from `packages/config`.
- Preserve the Python/Conda build tooling, explicit Conda recipe, and required smoke tests.

## Validation

After changes, run the relevant tests and checks. For Python dependency or packaging changes, validate the Pixi lock and build environment; for TypeScript changes, run Biome and the bridge typecheck.

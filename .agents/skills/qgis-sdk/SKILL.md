---
name: qgis-sdk
description: Project-specific guidance for developing the Python QGIS SDK and its TypeScript bridge in this Pixi and Bun monorepo.
---

# QGIS SDK Development

Use this skill when changing the `qgis-sdk` Python package, the `qgis-sdk-bridge` TypeScript package, their tests, builds, or workspace tooling.

## Repository layout

- `packages/qgis-sdk`: Python package built with Hatchling and the explicit Conda recipe.
- `packages/qgis-sdk-bridge`: TypeScript bridge tested with Bun and built with Bunup.
- `packages/config`: shared TypeScript and Bunup configuration.
- `pixi.toml`: root environments and pinned Conda dependencies; Bun remains in its separate environment.

## Development rules

- Keep Python development tools listed in the `qgis-sdk` `dev` extra. Do not add that extra as a Pixi path/editable PyPI dependency (pixi-pack only carries wheels). Pin Hypothesis and pytest-cov as wheels in the Python feature and keep `packages/qgis-sdk/src` on `PYTHONPATH`.
- Keep direct Pixi dependency versions exactly pinned.
- Run source tests locally with `pixi run -e bun bun run test`.
- Run coverage checks with `pixi run -e bun bun run coverage`. Keep the separate 90% checks and Codecov report paths intact.
- Build workspace packages with `pixi run -e bun bun run build`.
- Keep the bridge Bunup configuration package-local and import the shared preset from `packages/config`.
- Preserve the Python/Conda build tooling, explicit Conda recipe, and required smoke tests.

## Validation

After changes, run the relevant tests and checks. For Python dependency or packaging changes, validate the Pixi lock and build environment; for TypeScript changes, run Biome and the bridge typecheck.

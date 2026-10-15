# qgis-sdk

**Python SDK foundations for developing QGIS plugins.**

`qgis-sdk` is the Python package in the QGIS SDK workspace. It is intended to grow into a reusable foundation for plugin authors who want maintainable, source-testable code and a consistent packaging workflow.

> **Status:** early scaffold. The current API only contains `qgis_sdk.hello()` for smoke testing; plugin lifecycle helpers, QGIS UI abstractions, and domain-specific QGIS services have not been implemented yet.

The [`qgis-sdk` PyPI listing](https://pypi.org/project/qgis-sdk/) is currently a `0.0.0` placeholder with no project description, not a functional SDK release. Use this repository's source package for development; see the [workspace README](../../README.md) for details and the npm bridge listing status.

## Current API

```python
from qgis_sdk import hello

print(hello())  # hello world
```

The function above validates the package wiring; it is not a plugin entry point or a QGIS integration API.

## Development

From the workspace root, install the Pixi environments and run the Python tests:

```sh
pixi install -e default
pixi install -e build
pixi run -e default pytest -c packages/qgis-sdk/pyproject.toml packages/qgis-sdk/tests
```

The Python test and coverage dependencies are declared in this package's `dev` extra. The root Pixi Python feature installs that local extra for development.

## Build artifacts

The package uses Hatchling for Python distributions and an explicit Conda recipe:

```sh
pixi run -e bun bun run --filter qgis-sdk build
```

The combined build produces a wheel and source distribution under `dist/pypi/`, checks them with Twine, and builds the Conda artifact under `dist/conda/`.

See the [workspace README](../../README.md) for the full development setup, coverage tasks, Pixi environments, and the TypeScript bridge for QGIS `QWebEngineView` plugin interfaces.

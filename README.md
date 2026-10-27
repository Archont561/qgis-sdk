# QGIS SDK

<p align="center">
  <a href="https://github.com/Archont561/qgis-sdk/actions/workflows/ci.yml"><img src="https://github.com/Archont561/qgis-sdk/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://pypi.org/project/qgis-sdk/"><img src="https://img.shields.io/pypi/v/qgis-sdk?label=qgis-sdk" alt="qgis-sdk on PyPI"></a>
  <a href="https://www.npmjs.com/package/@archont561/qgis-sdk"><img src="https://img.shields.io/npm/v/%40archont561%2Fqgis-sdk?label=%40archont561%2Fqgis-sdk" alt="@archont561/qgis-sdk on npm"></a>
  <a href="https://github.com/Archont561/qgis-sdk/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT license"></a>
</p>

**A Python-first foundation for QGIS plugins, with a typed TypeScript bridge for
plugin interfaces hosted in `QWebEngineView`.**

Declare a plugin on plain Python classes; the SDK derives the plugin description,
the native forms, the Processing algorithms, the bridge allowlist and the generated
TypeScript client from those same declarations. Experimental `0.x`: every release
is documented, nothing is promised stable.

| Package | What it is | Install |
| :-- | :-- | :-- |
| [`qgis-sdk`](packages/qgis-sdk-python) | The Python developer kit: installs the runtime and the tools below at one tested version | `pip install qgis-sdk` |
| [`qgis-sdk-runtime`](packages/qgis-sdk-runtime) | Python declarations, contracts, runtime, adapters - what a plugin imports, dependency-free | `pip install qgis-sdk-runtime` |
| [`qgis-sdk-tools`](packages/qgis-sdk-tools) | `qgis-sdk new` / `check` / `test` / `dev` / `build` / `targets` | `pip install qgis-sdk-tools` |
| [`@archont561/qgis-sdk`](packages/qgis-sdk-typescript) | TypeScript transport client, host namespaces, generated clients | `bun add @archont561/qgis-sdk` |
| [`qgis-sdk` on npm](packages/qgis-sdk-alias) | Unscoped alias re-exporting `@archont561/qgis-sdk` at the same version | `bun add qgis-sdk` |
| [`@archont561/qgis-sdk-ui`](packages/qgis-sdk-ui) | Light-DOM web components mirroring the native UI catalogue, with React, Vue and Svelte wrappers | `bun add @archont561/qgis-sdk-ui` |
| [`qgis-sdk-ui` on npm](packages/qgis-sdk-ui-alias) | Unscoped alias re-exporting `@archont561/qgis-sdk-ui` at the same version | `bun add qgis-sdk-ui` |
| [`@workspace/config`](packages/config) | Shared TypeScript and Bunup configuration (private) | — |

## Try it

```sh
pip install qgis-sdk
qgis-sdk new my_tools --title "My Tools"   # pyproject.toml + the plugin class (asks about a web UI)
qgis-sdk check my_tools                    # QGIS-free project checks
cd my_tools && qgis-sdk test               # pytest, QGIS-free by default (--target qgis|desktop)
qgis-sdk dev                               # the plugin from source in a real QGIS, reload on save
qgis-sdk build                             # dist/<plugin>-<version>.zip: metadata.txt, classFactory and the runtime added for you
qgis-sdk targets                           # where the kit is qualified, and where this host stands
```

## Develop

```sh
bash scripts/restore.sh            # locked Pixi environments, offline-capable
pixi run -e bun bun run test       # Python and TypeScript tests
pixi run -e bun bun run coverage   # the 90% gates CI uses
```

## Documentation

The guides live in the backlog until the documentation site ships (TASK-43):

- [Python package guide](backlog/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md)
- [TypeScript package guide](backlog/docs/guides/doc-13%20-%20qgis-sdk-TypeScript-package-guide.md)
- [Workspace, harnesses and qualification evidence](backlog/docs/guides/doc-14%20-%20Workspace-development-qualification-harnesses-and-evidence.md)
- [Decisions](backlog/decisions) and the [roadmap](backlog/docs/plans/doc-4%20-%20SemVer-delivery-roadmap-and-task-dependencies.md)

Contributors start with [AGENTS.md](AGENTS.md).

## License

MIT

# QGIS SDK

<p align="center">
  <a href="https://github.com/Archont561/qgis-sdk/actions/workflows/ci.yml"><img src="https://github.com/Archont561/qgis-sdk/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://archont561.github.io/qgis-sdk/"><img src="https://img.shields.io/badge/docs-Starlight-6e56cf" alt="Documentation"></a>
  <a href="https://pypi.org/project/qgis-sdk/"><img src="https://img.shields.io/pypi/v/qgis-sdk?label=qgis-sdk" alt="qgis-sdk on PyPI"></a>
  <a href="https://www.npmjs.com/package/@archont561/qgis-sdk"><img src="https://img.shields.io/npm/v/%40archont561%2Fqgis-sdk?label=%40archont561%2Fqgis-sdk" alt="@archont561/qgis-sdk on npm"></a>
  <a href="https://github.com/Archont561/qgis-sdk/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT license"></a>
</p>

**The next-generation SDK for effortless QGIS plugin authoring.**

Build QGIS plugins in Python with less boilerplate: declare actions once, test
plugin logic without QGIS, and use the same actions in native and web
interfaces. Generate typed TypeScript clients, run your plugin from source,
and build an installable ZIP with its own private SDK runtime.

> Status: experimental `0.x` - Python kit `0.9.0`, TypeScript SDK `0.6.0`,
> web components `0.1.0`. The 0.9.0 minor is Python-only, so the bridge keeps
> the version it was last released at. Every `0.Y.0` carries
> migration notes; nothing is promised stable before `1.0.0`.

| Package | What it is | Install |
| :-- | :-- | :-- |
| [`qgis-sdk`](packages/qgis-sdk-python) | The Python developer kit: the runtime and the tools below at one tested version | `pip install qgis-sdk` |
| [`qgis-sdk-runtime`](packages/qgis-sdk-runtime) | What a plugin imports: declarations, UI catalogue, services, adapters - standard library only | `pip install qgis-sdk-runtime` |
| [`qgis-sdk-tools`](packages/qgis-sdk-tools) | The `qgis-sdk` command: `new`, `check`, `test`, `dev`, `build`, `bridge`, `processing`, `targets` | `pip install qgis-sdk-tools` |
| [`@archont561/qgis-sdk`](packages/qgis-sdk-typescript) | TypeScript SDK: `QgisSdk` over the generated schema, host namespaces, stores, React/Vue/Svelte bindings | `bun add @archont561/qgis-sdk` |
| [`qgis-sdk` on npm](packages/qgis-sdk-alias) | Unscoped alias of `@archont561/qgis-sdk` at the same version | `bun add qgis-sdk` |
| [`@archont561/qgis-sdk-ui`](packages/qgis-sdk-ui) | Light-DOM web components mirroring the native UI catalogue, with React, Vue and Svelte wrappers | `bun add @archont561/qgis-sdk-ui` |
| [`qgis-sdk-ui` on npm](packages/qgis-sdk-ui-alias) | Unscoped alias of `@archont561/qgis-sdk-ui` at the same version | `bun add qgis-sdk-ui` |
| [`@workspace/config`](packages/config) | Shared TypeScript and Bunup configuration (private) | - |

## Try it

```sh
pip install qgis-sdk
qgis-sdk new my_tools --title "My Tools"   # pyproject.toml, the plugin class, a declared dialog (asks about a web UI)
qgis-sdk check my_tools                    # QGIS-free project checks
cd my_tools && qgis-sdk test               # pytest, QGIS-free by default (--target qgis|desktop)
qgis-sdk dev                               # the plugin from source in a real QGIS, reload on save
qgis-sdk build                             # dist/<plugin>-<version>.zip with the runtime vendored inside
qgis-sdk targets                           # where the kit is qualified, and where this host stands
```

## Develop

```sh
bash scripts/restore.sh            # locked Pixi environments, offline-capable
pixi run -e bun bun run test       # Python and TypeScript tests
pixi run -e bun bun run coverage   # the 90% gates CI uses
```

## Documentation

**[archont561.github.io/qgis-sdk](https://archont561.github.io/qgis-sdk/)** - getting started, the three guides below as pages, and the component Storybook; rendered from the reference guides in `apps/docs` on every push to `main`.

- [Python package guide](https://archont561.github.io/qgis-sdk/python/) - declarations, the UI catalogue, services, Processing, the scaffold, the command, migration notes
- [TypeScript package guide](https://archont561.github.io/qgis-sdk/typescript/) - `QgisSdk`, host namespaces, stores, bindings, the components, testing
- [Workspace, harnesses and qualification evidence](https://archont561.github.io/qgis-sdk/contributing/workspace/) - environments, release scopes, harnesses, release gates
- [Decisions](backlog/decisions) and the [roadmap](backlog/docs/plans/doc-4%20-%20SemVer-delivery-roadmap-and-task-dependencies.md); the [reference plugin](examples/simple) is the smallest complete project

Contributors start with [AGENTS.md](AGENTS.md).

## License

MIT

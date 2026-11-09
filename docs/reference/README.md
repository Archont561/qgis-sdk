# Reference

Lookup material: commands and their flags, configuration keys, schemas and
generated surfaces. The reference pages are generated from the packages, so
they track the code instead of describing it from memory.

## Commands

| Command | What it does | Reference |
| :-- | :-- | :-- |
| `qgis-sdk new` | Scaffold a plugin or an app | [Project scaffold](https://archont561.github.io/qgis-sdk/python/project-scaffold/) |
| `qgis-sdk check` | QGIS-free project checks | [Project checks](https://archont561.github.io/qgis-sdk/python/project-checks/) |
| `qgis-sdk test` | pytest against the pure, QGIS or desktop target | [Running tests](https://archont561.github.io/qgis-sdk/python/running-tests-qgis-sdk-test/) |
| `qgis-sdk dev` | Run the plugin from source in a real QGIS | [Developing against QGIS](https://archont561.github.io/qgis-sdk/python/developing-against-qgis-qgis-sdk-dev/) |
| `qgis-sdk run` | Run a standalone app | [Running an app](https://archont561.github.io/qgis-sdk/python/running-an-app-qgis-sdk-run/) |
| `qgis-sdk build` | An installable ZIP with the runtime vendored | [Building an installable ZIP](https://archont561.github.io/qgis-sdk/python/building-an-installable-zip-qgis-sdk-build/) |
| `qgis-sdk targets` | Where the kit is qualified | [Supported targets](https://archont561.github.io/qgis-sdk/python/supported-targets/) |
| `qgis-sdk bridge`, `processing` | Contract and Processing helpers | the command's own `--help`, and the Python guide |

`qgis-sdk --help` is authoritative for flags; a flag that is missing there is
not supported, whatever a page says.

## Configuration

- `pyproject.toml` - the plugin's manifest: actions, surfaces, grants, the web
  UI choice. [Desktop host and the project manifest](https://archont561.github.io/qgis-sdk/python/desktop-host-host-and-the-project-manifest/).
- `qgis-sdk.toml` - the workspace's own test and build configuration.
- Grants, the console and the HTTP allowlist:
  [grants](https://archont561.github.io/qgis-sdk/python/grants-the-console-and-the-http-allowlist/).

## Generated surfaces

| Surface | Written by | Read it as |
| :-- | :-- | :-- |
| TypeScript contract types | `bun run sdk:generate` | `packages/qgis-sdk-typescript/dist/`, [TypeScript SDK](https://archont561.github.io/qgis-sdk/typescript/) |
| Schema JSON | `packages/qgis-sdk-python/scripts/generate_contract.py` | `packages/qgis-sdk-typescript/tests/contracts/generated/schemas/` |
| Decision records | `backlog/decisions/` | [Design decisions](https://archont561.github.io/qgis-sdk/reference/design-decisions/) |
| Markdown and llms exports | `apps/docs/scripts/postbuild.ts` | `apps/docs/out/llms.txt`, `llms-full.txt`, one `.md` per page |

## Sources

- `apps/docs/guides/doc-12 - qgis-sdk-Python-package-guide.md` (commands, configuration).
- `apps/docs/guides/doc-13 - qgis-sdk-TypeScript-package-guide.md` (the TypeScript surface).
- `backlog/decisions/` (records), `backlog/docs/plans/` (the roadmap and plans).

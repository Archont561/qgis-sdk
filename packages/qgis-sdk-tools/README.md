# qgis-sdk-tools

**The `qgis-sdk` command: `new`, `check`, `test`, `dev`, `build`, `bridge`,
`processing` and `targets`.**

Scaffolds a loadable plugin project with a declared native dialog and,
optionally, a Vite web page; reports what would stop a project from loading
in QGIS or from being tested without it; runs its tests QGIS-free or inside
QGIS; starts it from source in a real QGIS Desktop with reload on save;
generates the typed page-side schema and the Processing catalogue; and
writes an installable ZIP with the runtime vendored inside. The tools never
install anything into a QGIS.

> Status: `0.6.0`, experimental `0.x`. The tools version freely; each
> release names the `qgis-sdk-runtime` range it was tested with.

## Installation

```sh
pip install qgis-sdk            # the developer kit: runtime + tools
pip install qgis-sdk-tools      # the command alone, with the runtime it tested
```

## Example

```sh
qgis-sdk new field_tools --title "Field Tools" --web react   # pyproject.toml, the plugin, a dialog, tests/, web/
qgis-sdk check field_tools                                   # pyproject, syntax, imports, UI rules, runtime version
qgis-sdk test field_tools                                    # pytest QGIS-free; --target qgis|desktop for the native layers
qgis-sdk dev field_tools                                     # inside QGIS Desktop, reloading on save, Vite with HMR
qgis-sdk bridge generate --out web/src/bridge.schema.ts      # the typed schema QgisSdk.fromBridgeSchema reads
qgis-sdk processing generate --provider native --web-out web/src/processing.schema.ts
qgis-sdk build field_tools                                   # dist/field_tools-<version>.zip, metadata.txt and classFactory rendered
qgis-sdk targets                                             # the support matrix, and where this host stands in it
```

## Documentation

- [Python package guide](https://github.com/Archont561/qgis-sdk/blob/main/backlog/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md) -
  the scaffold, project checks and their rule ids, `test`, `dev`, `build`,
  the generators, release and migration notes.
- [Workspace, harnesses and qualification evidence](https://github.com/Archont561/qgis-sdk/blob/main/backlog/docs/guides/doc-14%20-%20Workspace-development-qualification-harnesses-and-evidence.md) -
  the support matrix and how each command is qualified.

## License

MIT

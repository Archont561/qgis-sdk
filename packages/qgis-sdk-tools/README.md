# qgis-sdk-tools

**From Python idea to QGIS plugin, without the boilerplate.**

Scaffold, check, test, run and build with the `qgis-sdk` command. Develop
against QGIS with reload on save, generate typed web and Processing contracts,
and ship a ZIP with a private SDK runtime. The tools never install anything
into QGIS.

> Status: `0.9.0`, experimental `0.x`. The tools version freely; each
> release names the `qgis-sdk-runtime` range it was tested with.

## Installation

```sh
pip install qgis-sdk            # the developer kit: runtime + tools
pip install qgis-sdk-tools      # the command alone, with the runtime it tested
```

## Example

```sh
qgis-sdk new field_tools --title "Field Tools" --web react   # create a project
cd field_tools
qgis-sdk check                                              # project, syntax, imports and UI rules
qgis-sdk test                                               # pure tests; --target qgis|desktop for native tests
qgis-sdk dev                                                # QGIS Desktop with reload and Vite HMR
qgis-sdk bridge generate --out web/src/bridge.schema.ts     # typed web client schema
qgis-sdk processing generate --provider native --web-out web/src/processing.schema.ts
qgis-sdk build                                              # dist/field_tools-<version>.zip
qgis-sdk targets                                            # support matrix
```

## Documentation

- [Python package guide](https://archont561.github.io/qgis-sdk/python/) -
  the scaffold, project checks and their rule ids, `test`, `dev`, `build`,
  the generators, release and migration notes.
- [Workspace, harnesses and qualification evidence](https://archont561.github.io/qgis-sdk/contributing/workspace/) -
  the support matrix and how each command is qualified.

## License

MIT

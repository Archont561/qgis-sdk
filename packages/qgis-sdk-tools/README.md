# qgis-sdk-tools

**The `qgis-sdk` command: new, check, test, dev and build.**

Scaffolds a loadable plugin project (optionally with a Vite web UI), reports
what would stop one from loading in QGIS, runs its tests QGIS-free or inside
QGIS, starts it from source in a real QGIS Desktop with reload on save, and
writes an installable ZIP with the runtime vendored inside.

> Experimental `0.x`. The tools version freely; each release names the
> `qgis-sdk-runtime` range it was tested with.

## Installation

```sh
pip install qgis-sdk            # the developer kit: runtime + tools
pip install qgis-sdk-tools      # the command alone, with the runtime it tested
```

## Example

```sh
qgis-sdk new field_tools --title "Field Tools"
qgis-sdk check field_tools
qgis-sdk test field_tools
qgis-sdk dev field_tools
qgis-sdk build field_tools
qgis-sdk targets    # the support matrix, and where this host stands in it
```

## Documentation

- [Python package guide](https://github.com/Archont561/qgis-sdk/blob/main/backlog/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md) -
  the scaffold, project checks, `test`, `dev`, `build`, release and migration
  notes.
- [Workspace, harnesses and qualification evidence](https://github.com/Archont561/qgis-sdk/blob/main/backlog/docs/guides/doc-14%20-%20Workspace-development-qualification-harnesses-and-evidence.md).

## License

MIT

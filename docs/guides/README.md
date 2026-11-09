# Guides

Task-oriented documentation: the shortest path from "installed nothing" to a
plugin that runs. These pages are published from `apps/docs/content/docs/` and
are the canonical copy - this file is the index, not a second copy.

## Getting started

- [Install the QGIS SDK](https://archont561.github.io/qgis-sdk/start/installation/) - the developer kit from PyPI, the TypeScript SDK from npm, and what `qgis-sdk targets` finds on the machine.
- [Your first plugin](https://archont561.github.io/qgis-sdk/start/first-plugin/) - scaffold a plugin, then follow one typed action from a pure test to native and web interfaces.
- [Concepts and vocabulary](https://archont561.github.io/qgis-sdk/start/concepts/) - the handful of words used everywhere, defined once with where each is documented.

## Working on a plugin

- [Test and run a plugin](https://archont561.github.io/qgis-sdk/guides/test-a-plugin/) - exercise the plugin without QGIS, then opt into QGIS and Desktop checks.
- [Add a web UI](https://archont561.github.io/qgis-sdk/guides/web-plugin/) - a web-backed plugin, its generated bindings, and the difference between scripted tests and a QGIS host.
- [CLI MCP server](https://archont561.github.io/qgis-sdk/guides/cli-mcp/) - the developer commands from an MCP client.
- [Experimental plugin HTTP API](https://archont561.github.io/qgis-sdk/guides/experimental-plugin-http/) - call explicitly exposed actions and streams from outside QGIS.

## Shipping a plugin

- [Build an installable ZIP](https://archont561.github.io/qgis-sdk/python/building-an-installable-zip-qgis-sdk-build/) - `qgis-sdk build`, with the private runtime vendored inside.
- [Developing against QGIS](https://archont561.github.io/qgis-sdk/python/developing-against-qgis-qgis-sdk-dev/) - reload a plugin from source in a real QGIS.
- [Project checks](https://archont561.github.io/qgis-sdk/python/project-checks/) and [running tests](https://archont561.github.io/qgis-sdk/python/running-tests-qgis-sdk-test/).

## Sources

| Page | Source |
| :-- | :-- |
| start pages | `apps/docs/content/docs/start/` |
| guides | `apps/docs/content/docs/guides/` |
| plugin workflows | `apps/docs/guides/doc-12 - qgis-sdk-Python-package-guide.md` |

The complete, current list of published pages is the site's own index:
[llms.txt](https://archont561.github.io/qgis-sdk/llms.txt).

---
title: Add a web UI
description: Scaffold a web-backed plugin, check its generated bindings and distinguish scripted tests from a QGIS host.
---

Use a web UI when a QGIS plugin needs a page hosted in `QWebEngineView`. The
Python plugin still owns its actions; the page calls them over the bridge.
Install the [developer kit](/start/installation/) and a JavaScript
package manager first.

## Scaffold a web project

```sh
qgis-sdk new field_tools --web vanilla --placement dock --package-manager bun --no-input
cd field_tools
```

The scaffold writes a Python plugin and a `web/` page with a generated bridge
schema. Install its JavaScript dependencies before running the page's scripts.
The [project scaffold](/python/project-scaffold/) reference describes
other framework, placement and package-manager options.

## Test the two sides

```sh
qgis-sdk check
qgis-sdk test
cd web
bun install
bun run test
cd ..
```

Python tests exercise the plugin on fakes. Page tests use a scripted bridge,
not a live QGIS host; see [testing against a scripted host](/typescript/testing-against-a-scripted-host/).

## Connect the page

The generated page creates a `QgisSdk` from `bridge.schema.ts` and invokes
methods declared by the plugin. After changing declarations, regenerate the
schema with `qgis-sdk bridge generate`; see
[the schema module and QgisSdk](/typescript/the-schema-module-and-qgissdk/)
and the [host-side bridge](/python/webengine-bridge-host-side/).

## Run on QGIS Desktop

```sh
qgis-sdk dev
```

A supported QGIS Desktop and display are required. The developer command runs
the plugin and its web dev server; edits reload during development. See
[developing against QGIS](/python/developing-against-qgis-qgis-sdk-dev/)
and [supported targets](/python/supported-targets/).

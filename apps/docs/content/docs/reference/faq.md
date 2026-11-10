---
title: FAQ
description: Short answers to the questions asked most before adopting the QGIS SDK, each pointing at the page that explains it.
---

## Which QGIS versions work?

QGIS 4.x and the **3.44 LTS**. One installed wheel serves both: the runtime
imports Qt through `qgis.PyQt`, which is PyQt6 on 4.x and PyQt5 on 3.44, and a
plugin declares its own floor with `qgis-minimum-version`.

[Supported targets](/python/supported-targets/) - the matrix, and the CI row behind each.

## What do I actually install?

`pip install qgis-sdk` - the developer kit, which brings `qgis-sdk-runtime`
(what a plugin imports inside QGIS) and the `qgis-sdk` command at matching
versions. Nothing installs into a QGIS; a built plugin vendors its own runtime.
Only a plugin with a web page needs the TypeScript packages.

[Install the QGIS SDK](/start/installation/) - pip, Pixi and the npm names.

## Do I need QGIS installed to work on a plugin?

No. Declarations, `check`, bridge generation and the pure tests all import
without QGIS, so a plugin is testable from source. `qgis-sdk dev` and
`--target qgis|desktop|server` are the parts that need an installation, and
`qgis-sdk targets` says which of them this machine can reach.

[Testing a plugin](/guides/test-a-plugin/) - the QGIS-free loop.

## Can one plugin run on Desktop, Server and a standalone app?

Yes, if it declares them: `hosts = ["desktop", "server", "app"]` in
`[tool.qgis-sdk]`. The class is written once; a server build gets hooks
(`@filter`, `@service`, `@access_control`) and a standalone app gets
`qgis_sdk.app.run`. A QGIS built without Server refuses the host by name.

[Declarations](/python/declarations/) - the hosts section.

## How do I ship it?

`qgis-sdk build` writes `dist/<name>-<version>.zip`: the `metadata.txt` rendered
from the declaration, the vendored runtime and the generated QGIS entry point.
Install the ZIP through QGIS's plugin manager.

[Building an installable ZIP](/python/building-an-installable-zip-qgis-sdk-build/) - what the archive holds.

## What does a failing `qgis-sdk check` mean?

It reports a code, not a prose complaint - `HOST001` for a Desktop-only
declaration, `UI003` for an action that cannot be run from a button,
`VERSION004` for a version window that excludes the release. Every code is
listed with what it refuses.

[Project checks](/python/project-checks/) - the catalogue of codes.

## Can an agent drive the toolchain?

Yes. `pip install 'qgis-sdk[mcp]'` adds a stdio MCP server that exposes the
developer commands - scaffold, generate, check, build, test, run, dev - and it
never connects to a running plugin.

[CLI MCP server](/guides/cli-mcp/) - the client configuration.

## Is there a TypeScript API for the page side?

The bridge generator emits a typed schema, and `QgisSdk.fromBridgeSchema(schema)`
turns it into a client whose methods match the actions, with the same input and
result types the Python side declares.

[The schema module and `QgisSdk`](/typescript/the-schema-module-and-qgissdk/) - the generated client.

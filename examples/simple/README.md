# simple

The smallest complete qgis-sdk plugin, and the local GIS workflow the SDK is
qualified against (decision-19): open a bundled point dataset, read the
host's selection, buffer it through Processing into a new styled layer, and
export that layer to a file the user chose. `simple/algorithms.py` declares the
two Processing algorithms the plugin owns (`simple:buffer`, `simple:centroid`),
`simple/workflow.py` is that chain over the SDK services - plugin code, not a
runtime feature - and `plugin.py` declares it as actions and lists the
provider. Native dialogs and the web page are two front ends over those
same actions; the page never names a path, and an export without a chosen
directory is refused, not guessed.

There is no `metadata.txt`, no `classFactory` and no view module in the
source (decision-43): `pyproject.toml` names the plugin class under
`[tool.qgis-sdk]` and the page's placement and grants under
`[tool.qgis-sdk.web]`; `qgis-sdk build` and `qgis-sdk dev` derive what QGIS
needs from that, through `qgis_sdk.adapters.desktop.host()`.

The project was written by `qgis-sdk new` (vanilla web page, dock placement,
bun) and keeps that layout, so every command works unchanged:

```sh
qgis-sdk check                   # pyproject, syntax, imports, runtime version
qgis-sdk test                    # the workflow over the SDK fakes, no QGIS
qgis-sdk test --target qgis      # real Processing, real OGR export, the native dialog
bun install && bun run test --filter simple-web   # from the repository root
cd web && bun run build && cd ..
qgis-sdk dev                     # inside QGIS Desktop, reloading on save
qgis-sdk build                   # dist/simple-<version>.zip
```

One line differs from a scaffolded plugin: `web/package.json` depends on
`@archont561/qgis-sdk` as `workspace:*`, so the page runs on this checkout's
`packages/qgis-sdk-typescript` (turbo builds it first), where a plugin made
outside the repository gets the exact bridge release the scaffold pins
(decision-41; `qgis-sdk new --sdk-dependency` is the switch).

`web/src/bridge.schema.ts` is generated from the plugin's declarations and
`web/src/processing.schema.ts` from the `native` Processing provider of the
project's QGIS (`bun run bindings` checks both); `web/src/main.ts` builds
the page's `QgisSdk` on the first in three statements, and `app.ts` runs
`native:centroids` through the second's typed `runAlgorithm`. The workspace harness
`packages/qgis-sdk-python/tests/test_reference_example_native.py` runs this
whole sequence and proves, inside a real `QWebEngineView`, that the page and
the native dialog produce the same result through one handler.

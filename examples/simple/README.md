# simple

The smallest complete qgis-sdk plugin, and the local GIS workflow the SDK is
qualified against (decision-19): open a bundled point dataset, read the
host's selection, buffer it through Processing into a new styled layer, and
export that layer to a file the user chose. `simple/workflow.py` is that chain over the SDK
services - plugin code, not a runtime feature - and `plugin.py` declares it
as actions. Native dialogs and the web page are two front ends over those
same actions; the page never names a path, and an export without a chosen
directory is refused, not guessed.

The project was written by `qgis-sdk new` (vanilla web page, dock placement,
bun) and keeps that layout, so every command works unchanged:

```sh
qgis-sdk check                   # metadata, syntax, manifests
qgis-sdk test                    # the workflow over the SDK fakes, no QGIS
qgis-sdk test --target qgis      # real Processing, real OGR export, the native dialog
cd web && bun install && bun run test && bun run build && cd ..
qgis-sdk dev                     # inside QGIS Desktop, reloading on save
qgis-sdk build                   # dist/simple-<version>.zip
```

`web/src/bridge.ts` is generated from the plugin's declarations (`bun run
bindings` checks it). The workspace harness
`packages/qgis-sdk-python/tests/test_reference_example_native.py` runs this
whole sequence and proves, inside a real `QWebEngineView`, that the page and
the native dialog produce the same result through one handler.

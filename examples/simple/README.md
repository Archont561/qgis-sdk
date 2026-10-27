# simple

**The smallest complete qgis-sdk plugin, and the local GIS workflow the SDK
is qualified against.**

Open a bundled point dataset, read the host's selection, buffer it through
Processing into a new styled layer and export that layer to a directory the
user chose. `plugin.py` declares the actions and lists the plugin's own
Processing provider (`algorithms.py`: `simple:buffer`, `simple:centroid`),
`workflow.py` is the chain over the SDK services, `surfaces.py` holds the
native windows - a `BufferDialog` built in pure PyQt and a declared
`ResultsDock` - and `web/` is the Vite page; both front ends drive the same
handlers. There is no `metadata.txt`, `classFactory` or view module in the
source: `pyproject.toml` names the plugin class and the page's placement
and grants, and `build` and `dev` derive what QGIS needs.

> Status: written by `qgis-sdk new` (vanilla page, dock placement, bun)
> and kept in that layout; the project's own version is `0.1.0`. One line
> differs from a scaffolded plugin: `web/package.json` depends on the
> bridge as `workspace:*`, so the page runs on this checkout.

## Try it

```sh
qgis-sdk check                      # pyproject, syntax, imports, UI rules, runtime version
qgis-sdk test                       # the workflow over the SDK fakes, no QGIS
qgis-sdk test --target qgis         # real Processing, real OGR export, the native dialog
bun run bindings                    # bridge.schema.ts and processing.schema.ts are current (from web/)
bun run test --filter simple-web    # the page's tests (from the repository root)
qgis-sdk dev                        # inside QGIS Desktop, reloading on save
qgis-sdk build                      # dist/simple-<version>.zip
```

## Example

```python
@action(id="buffer", title="Buffer in a projected CRS")
def buffer(self, layer_id: LayerInput, distance_metres: Metres, working_crs: CrsInput) -> VectorLayerInfo:
    return self.workflow.buffer(layer_id, distance_metres, working_crs)  # one handler, two front ends
```

```ts
const qgis = QgisSdk.fromBridgeSchema(schema); // web/src/main.ts
const buffered = await qgis.buffer({ layer_id, distance_metres, working_crs });
const { outputs } = await runAlgorithm(qgis, "native:centroids", { INPUT: buffered.id }); // processing.schema.ts
```

## Documentation

- [Python package guide](../../backlog/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md) -
  every API the plugin uses.
- [Workspace, harnesses and qualification evidence](../../backlog/docs/guides/doc-14%20-%20Workspace-development-qualification-harnesses-and-evidence.md) -
  "Reference plugin through the toolchain": the harness that runs this
  project end to end inside a real `QWebEngineView`.

## License

MIT

# Simple server

**The reference example on the third host: a QGIS Server plugin.**

`examples/simple` is one plugin class run by QGIS Desktop (a dock over a page)
and by a standalone PyQGIS app (`python -m simple`, `qgis-sdk run`) - one
class, two hosts, [decision-52](../../backlog/decisions/decision-52%20-%20Run-one-plugin-class-on-three-hosts-QGIS-Desktop-QGIS-Server-and-standalone-PyQGIS-apps.md).
This project is the same fixture on the host that is left: QGIS Server answers
requests, so a plugin there declares **hooks** instead of actions, has no
window, and is loaded through `serverClassFactory` rather than `classFactory`.

```python
app = QgisSdkPlugin(id="simple_server", title="Simple server")


@filter()                                   # runs before any service
def default_version(ctx, request, response):
    if request.param("VERSION") is None:
        return request.with_params(VERSION="1.0.0")
    return None


@service(name="SIMPLE_SERVER", version="1.0.0")     # owns SERVICE=SIMPLE_SERVER
def answer(ctx, request):
    measured = measure()                            # a plain function over a path
    return ServerResponse.json(
        {"features": measured.features, "bbox": list(measured.bounds)}
    )


@access_control()                            # asked once per requested layer
def no_private_layers(ctx, request, layer):
    return not layer.startswith("private_")
```

`plugin.py` holds those three hooks and one plain function, `measure()`, which
reads `data/points.geojson` - the fixture the Desktop example opens through
QGIS - and returns its bounding box and feature count. Nothing in the package
imports QGIS or Qt; `serverClassFactory` in `__init__.py` imports the adapter
lazily, inside the call, so the package imports on a machine whose QGIS was
built with `WITH_SERVER=OFF`.

> Status: written by `qgis-sdk new --host server` and kept in that layout; the
> project's own version is `0.1.0`.

## Try it

```sh
qgis-sdk check                      # pyproject, syntax, imports, hosts, runtime version
qgis-sdk test                       # the hooks through FakeServerInterface, no QGIS
qgis-sdk test --target server       # the same hooks in-process under a real QgsServer
qgis-sdk dev --host server          # a local server loop, reloading on save
qgis-sdk build                      # dist/simple-server-<version>.zip
```

The first two run anywhere. The last three need a QGIS built with
`WITH_SERVER=ON` **and** its Python bindings - the Debian/Ubuntu `qgis-server`
plus `python3-qgis` packages, the official installers, or a source build with
`-DWITH_SERVER=ON -DWITH_BINDINGS=ON`. conda-forge passes `-D WITH_SERVER=FALSE`,
so a conda QGIS has no `qgis.server` and `check` reports `HOST003` - a statement
about the environment, not the project.

## What the service answers

```sh
curl 'http://localhost/qgis/qgis_mapserv.fcgi?SERVICE=SIMPLE_SERVER&REQUEST=extent'
```

```json
{
  "service": "SIMPLE_SERVER",
  "version": "1.0.0",
  "features": 3,
  "bbox": [21.0, 52.0, 21.2, 52.2]
}
```

A request without `VERSION` gets `1.0.0` from the filter; `REQUEST` other than
`extent` is a 400 naming what the service answers; a request naming a layer that
starts with `private_` is a 403 naming the layer instead of a silently narrowed
map. `ctx.jobs` on this host is request-scoped: a job a hook submits is
abandoned when the response is sent, and work that must outlive the request says
so with `ctx.jobs.plugin`.

## Tests

```sh
qgis-sdk test      # pure: every hook through qgis_sdk.testing.FakeServerInterface
pytest -q          # the same suite, your way
```

The starter tests need no QGIS: the scripted interface serves a request through
the same dispatcher a deployed server drives, so they fail when the hooks stop
agreeing with each other, not only when QGIS is missing.

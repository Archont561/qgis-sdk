---
id: decision-52
title: Run one plugin class on three hosts - QGIS Desktop, QGIS Server and standalone PyQGIS apps
date: '2026-10-26'
status: accepted
---
## Context

The owner wants the SDK to cover QGIS Server plugins and standalone PyQGIS
applications, not only Desktop plugins. The runtime is already host-shaped:
`PluginRuntime` takes a context factory, `native_plugin_context(iface=None)`
builds every service without a Desktop (the `desktop` capability refuses by
name), the test suite runs under a headless `QgsApplication`, and decision-43
makes host entry points generated artifacts. What is missing is the server
lifecycle (`serverClassFactory(serverIface)`, filters, services, access
control), an application lifecycle that owns `QgsApplication`, and a way for
the author to say which hosts a plugin targets.

## Decision

1. **One author class, a declared host set.** `[tool.qgis-sdk] hosts =
   ["desktop", "server", "app"]` (default `["desktop"]`). The same class,
   actions, jobs, streams and providers run on every declared host; a
   capability a host lacks refuses by name (decision-39). `check` gains
   `HOST001` (a Desktop-only declaration - `@toolbar`, `@menu`, a `Dialog`/`Dock` surface,
   web view - on a plugin whose hosts exclude Desktop and that has no
   Desktop host at all is fine; on a server-only plugin it is a finding) and
   `HOST002` (a server declaration on a plugin without the server host).
2. **Server host.** Declarations: `@server.filter(priority=)` on
   `def f(ctx: ServerContext, request: ServerRequest, response: ServerResponse)`
   for the request/response hooks (`QgsServerFilter`), `@server.service(name=,
   version=)` for a custom OGC-style service (`QgsService`), and
   `@server.access_control` for `QgsAccessControlFilter` hooks (layer
   permissions, feature filters, attribute masking). `ServerContext` carries
   the curated services over the request's project plus `request`
   (parameters, headers, method, body) and `response` (status, headers,
   body, streaming) as plain models - never `QgsServerInterface`.
   `build` generates `serverClassFactory` next to `classFactory` and sets
   `server=True` in `metadata.txt`; `test --target server` and the fakes run a
   plugin against an in-process `QgsServer` (`QgsServer().handleRequest`),
   which needs no FCGI; `dev --host server` serves the project through a
   local `QgsServer` loop with reload. Jobs on the server host are
   request-scoped unless declared plugin-owned.
3. **Standalone app host.** `qgis_sdk.app.run(PluginClass, *, gui=False,
   argv=None)` owns `QgsApplication` (`initQgis`/`exitQgis`), builds the
   context without an `iface`, starts the runtime, and - with `gui=True` -
   provides a main window with a canvas so the `canvas` service of
   decision-54 and the Desktop-style bindings (`@toolbar`, `@menu`,
   `Dialog`/`Dock` surfaces) attach to the app's own window. `qgis-sdk run`
   discovers QGIS (the dev discovery) and launches the app with the right
   environment; `build --target app` produces a Python distribution with a
   console-script launcher rather than a plugin ZIP, with the same vendoring
   rules (decision-50). A web view in a standalone app uses the same bridge.
4. **Shared across hosts.** The console session (decision-48), the agent
   transport (decision-49) and UI snapshots (decision-51) work on every host
   that has what they need (no snapshot without a GUI); the loopback agent
   endpoint on the server host is developer mode only and never enabled in
   a deployed server. Host detection is explicit (`ctx.host` ∈ desktop |
   server | app), never inferred from `iface`.
5. **Not included.** QGIS Server deployment (FCGI, Docker, reverse proxy)
   and multi-process state are the operator's concern; the SDK ships the
   plugin and the local loop. Mobile (QField) is out of scope.

## Implementation note (2026-10-30)

**The server host needs a QGIS built with the server.** `qgis.server` -
`QgsServer`, `QgsServerInterface`, `QgsServerFilter`, `QgsService` - exists only
when QGIS is configured with `WITH_SERVER=ON` and Python bindings: `release-4_2`
`CMakeLists.txt` defaults `WITH_SERVER` to `FALSE` and makes `WITH_SERVER_PLUGINS`
follow `WITH_BINDINGS`. conda-forge passes `-D WITH_SERVER=FALSE` explicitly in
`recipe/build.sh` and `recipe/bld.bat`, so no conda build of QGIS has it -
including the pixi environment this workspace qualifies on, whose installed
`qgis-4.2.3` has no `libqgis_server`, no `qgis/server`, no `_server.so` and no
`qgis_mapserv.fcgi` (`from qgis.server import QgsServer` is a
`ModuleNotFoundError` there). It is available from the Debian/Ubuntu packages
(`qgis-server` plus `python3-qgis`), the official qgis.org installers, a source
build with `-DWITH_SERVER=ON -DWITH_BINDINGS=ON`, and the `qgis/qgis-server`
images.

**What that changes here.** Point 2 splits: the declarations, `ServerContext` and
the generated `serverClassFactory` are proven against a scripted fake
`QgsServerInterface` in `qgis_sdk.testing` - which `test --target server` needs in
any case - and the in-process `QgsServer` claim is its own criterion behind a
`qgis.server` skip, so any build that has the module runs it and a CI row that
installs `qgis-server`/`python3-qgis` proves it. `check` gains `HOST003`: a
project that declares the server host while the QGIS it builds against has no
`qgis.server`, reported at build time instead of as an `ImportError` in a
deployed server. The gate records that native row as run or blocked with this
evidence, never as passed. `ctx.host` and the `[tool.qgis-sdk] hosts` set are
unchanged, and nothing about the Desktop or app hosts moves.

**Jobs on the server host, decided 2026-10-30.** There is no GUI thread there
and no `QgsJobPump` to drive delivery, so point 2's "request-scoped unless
plugin-owned" becomes concrete: the server host ticks the job service at request
start, abandons a request-scoped job when its response is sent (`quiesce` with a
zero deadline, the abandoned job reported as cancelled by name), and refuses
plugin-lifetime submission unless the host was given a worker backend. Nothing
in a request may hold the response open waiting for a worker, and a plugin-owned
job that outlives requests has to be backed by something the operator started -
the SDK does not invent a background thread for it.

**Request-scoped jobs, landed 2026-10-30 (TASK-80 AC 3).** The mechanism behind
that note is three small pieces rather than a server-only scheduler. The plugin's
`JobService` stays the scheduler owner; `JobService.request_scoped(scope)` derives
a view-like service over the *request* scope with the other disposal rule - it
registers `on_close` on that scope, so the response's scope close *is* the
abandonment - and the server host builds one per request and hands it to
`ServerContext` as the `jobs` capability. Abandoning an attempt there
(`_Attempt.cancelled_by_request`) marks the handle `cancelled` immediately, asks
the worker to stop, drops the job out of `StepScheduler` through a new
`abandon(job)` (the same rule `dispose` uses for a whole scope, with a later
worker report counted as dropped), and closes the attempt's scope. The *plugin*
close path is deliberately left alone: there the scheduler's own verdict -
`QgisSdkScopeClosedError` for a job that never started, `cancelled` for one that
did - is the more informative answer, so `request_scoped` is a second rule rather
than a change to the first. `ctx.jobs.plugin` reaches the plugin-lifetime service
and survives the response. Server ticks are the host's: `ServerHost.tick()` at
request start, `QgsServerHost` calling it from `serve_filter`/`serve_service` in
both the fake and the real adapter path.

**The QGIS Server object mapping, decided 2026-10-30 with TASK-80 AC 2.** QGIS
Server does not call a dispatcher: it calls a `QgsServerFilter` before the
services, a `QgsService` for the `SERVICE` a request names, and a
`QgsAccessControlFilter` per layer while a service renders. The adapter therefore
registers one filter carrying the whole SDK chain (the SDK fixes its own order -
priority, declaration, include - so QGIS only needs one position for it: the
lowest priority any filter declares), one `QgsService` per declared service, and
one access-control object running every access hook. `ServerHost` grew the seams
that needs (`rewrite`, `denied_layer`, `permits`, `service_for`, `context`) so
both hosts run the same code rather than two dispatchers.

Three consequences are stated in the code and the guide rather than left to
inspection. A filter hook sees `request.method == ""`: `QgsServerFilter` gets no
request object and `QgsRequestHandler` exposes the URL, the headers and the merged
OGC parameters but not the verb, so the model says it does not know instead of
claiming `GET`; a hook that must distinguish `GET` from `POST` belongs in a
service, which does receive the `QgsServerRequest`. A filter that answers writes
its response over the OGC error `QgsRequestHandler.setServiceException` leaves
behind, because that flag is the only switch the C++ dispatcher checks before it
runs its own services, and returning `False` from `onRequestReady` only stops
other plugins' filters. An access refusal clears all four permissions rather than
raising, which is what `QgsAccessControl` consults, and the 403 that
`ServerHost.denied_layer` builds stays the pure host's answer. The access object
also answers `cacheKey()` with a non-empty string: `QgsAccessControl::fillCacheKey`
reads that as "this answer varies, do not reuse a capabilities document", and the
alternative - a capabilities document built for one request answering another -
is a leak rather than a slow response. The cost is one capabilities render per
request while a plugin with access hooks is loaded, and it is paid deliberately.

Nothing Qt-specific is needed to test any of that: the host lives in
`qgis_sdk.adapters._server`, imports `qgis.server` only when a host is built, and
is proven with stand-ins on every run plus a real in-process `QgsServer` on the
`QGIS 3.44 LTS` row.

## Consequences

- Service contracts gain nothing host-specific; the server adds
  `ServerRequest`/`ServerResponse` models and the access-control hook
  shapes to the runtime, the app adds `qgis_sdk.app` and a window host.
- `build` renders a second entry point and a new target; the scaffold gains
  `--host server|app`; the reference example gains a server variant.
- The bridge is untouched; `HOST_FINGERPRINT` does not move.
- Scheduled as m-8 (0.9.0) with decision-53: TASK-80 (server host),
  TASK-81 (standalone app host), gate TASK-83.

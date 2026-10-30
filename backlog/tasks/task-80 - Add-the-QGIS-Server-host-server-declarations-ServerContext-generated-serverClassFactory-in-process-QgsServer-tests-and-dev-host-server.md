---
id: TASK-80
title: >-
  Add the QGIS Server host: server declarations, ServerContext, generated
  serverClassFactory, in-process QgsServer tests and dev --host server
status: To Do
assignee: []
created_date: '2026-10-26T10:11:00Z'
updated_date: '2026-10-30 17:11'
labels: []
milestone: m-8
dependencies:
  - TASK-64
  - TASK-63
  - TASK-116
type: enhancement
ordinal: 80000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-52 points 1, 2, 4. [tool.qgis-sdk] hosts; @server.filter(priority=), @server.service(name=, version=), @server.access_control on plain functions with an injected ServerContext (curated services over the request project, request and response as plain models; never QgsServerInterface); build generates serverClassFactory and server=True in metadata.txt; check HOST001/HOST002; qgis_sdk.testing fakes for request/response and a QgsServer in-process runner for test --target server; dev --host server with a local QgsServer loop and reload; scaffold --host server; reference example server variant; jobs request-scoped unless plugin-owned; agent endpoint developer-mode only on this host.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A plugin declaring a filter, a service and an access-control hook is registered through the generated serverClassFactory against a scripted fake QgsServerInterface (pure tests, no QGIS): the filter sees and rewrites a WMS GetCapabilities request, the service answers its own request, and the access-control hook restricts a layer. ServerContext carries the request's project services plus plain ServerRequest/ServerResponse models, never QgsServerInterface.
- [ ] #2 The same plugin class, unchanged, repeats #1's three claims inside an in-process QgsServer under a headless QgsApplication (qgis native test, no FCGI), skipped when the QGIS build has no qgis.server. The test is the CI row that installs qgis-server and python3-qgis from the 4.2 channel; where that build is absent the row is recorded as blocked with the evidence, never as passed.
- [ ] #3 The same plugin class with hosts = [desktop, server] runs on both: Desktop bindings attach on Desktop and refuse by name on the server; HOST001 and HOST002 fire on misdeclared projects, and HOST003 fires when a project declares the server host while the QGIS it builds against has no qgis.server (pure tests); a request-scoped job is abandoned when its response is sent, and names itself as abandoned rather than pretending it finished (stateful tests).
- [ ] #4 qgis-sdk new --host server scaffolds, check/test --target server/build pass, dev --host server reloads a filter edit (devtools harness); doc-12 documents the server host, what it never exposes, and the QGIS build it needs (WITH_SERVER=ON plus bindings; conda-forge builds it off).
- [ ] #5 Filters and services run in the documented order (priority ascending, then declaration order, then include order) and ServerRequest/ServerResponse carry the case-insensitive OGC helpers and response constructors the host maps, proven by pure tests (decision-69 point 1).
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Ordering and request models (decision-69 point 1). Filters and services run by priority ascending, then the plugin class's own declaration order, then the declaration order of each included plugin, fixed when the runtime starts; a hook never depends on dict iteration or sort stability. ServerRequest.param(name, default=None) matches QgsServer's case-insensitive OGC lookup, params is a read-only case-insensitive view and headers is case-insensitive; ServerResponse carries status, headers and body plus text/json/xml/stream and set_header. Every @server.* decorator works bare and called. A request-scoped job is abandoned when its response is sent; plugin-owned work continues.

Server bindings availability, checked 2026-10-30 - this is why the native claim is now #2 and not part of #1. qgis.server exists only in a QGIS built with WITH_SERVER=ON plus WITH_BINDINGS: QGIS 4.2 CMakeLists defaults WITH_SERVER to FALSE and makes WITH_SERVER_PLUGINS follow WITH_BINDINGS. conda-forge turns it off deliberately (recipe/build.sh and bld.bat both pass -D WITH_SERVER=FALSE), so the pixi environment this workspace uses has no libqgis_server, no qgis/server, no _server.so and no qgis_mapserv.fcgi, and 'from qgis.server import QgsServer' is ModuleNotFoundError there. Routes that do provide it: apt qgis-server plus python3-qgis from the qgis.org or Debian repositories, the official qgis.org Windows/macOS installers (probe with python -c 'from qgis.server import QgsServer'), a source build with -DWITH_SERVER=ON -DWITH_BINDINGS=ON, and the qgis/qgis-server Docker images. Consequences: the scripted fake QgsServerInterface is what makes #1 and #3-#5 provable in this workspace, and it is what test --target server needs anyway; #2 sits behind a skip so a build with server bindings lights it up for free, and it has to be proved by the CI row rather than locally; the gate at TASK-83 records the row as run or blocked with this evidence.
Step 1 landed (2026-10-30, first slice): `[tool.qgis-sdk] hosts` is read and validated by the tools (default `["desktop"]`, an unknown name is CONFIG001), `qgis_sdk.core.Host` (`desktop`/`server`/`app`, a StrEnum with `gui`) is what the host that builds a context states, and `ctx.host` reports it on `PluginContext` and `UiContext` - a view inherits the host of the plugin context that opened it. `check` gained HOST001 (a Desktop-only declaration - `@toolbar`/`@menu`/`@shortcut`, a `Dialog`/`Dock` surface, a `[tool.qgis-sdk.web]` page - in a project whose hosts exclude `desktop`) and HOST003 (the `server` host declared while the visible QGIS has no `qgis.server`; a warning, because the environment is what is missing, and silent when no QGIS is visible at all). HOST002 waits for the server declarations themselves, since there is nothing to recognise by name until `@server.*` exists.
Step 2a landed (2026-10-30): the QGIS-free half of the server host. `qgis_sdk.server` carries `ServerRequest` (case-insensitive OGC parameters and headers, immutable, `with_params` to rewrite), `ServerResponse` (status, case-insensitive headers, `write_text`/`write_json`/`write_xml`, `text`/`xml`/`json`/`denied` constructors), `ServerContext` (host fixed to `Host.SERVER`, `request`/`response`/`scope` required, `project`/`layers`/`log` as capabilities refused by name, no `workers`/`ui`/`desktop`), the three decorators `filter(priority=)`, `service(name=, version=)` and `access_control(priority=)` - bare and called - and `ServerHooks`, which validates the signature each kind takes ((ctx, request, response), (ctx, request), (ctx, request, layer)), refuses an `async def`, an unannotated context, a non-int priority and two services claiming one name, and fixes the order once. `ServerHost` registers through a `ServerInterface` protocol (`register_filter`/`register_service`/`register_access_control`) and serves linearly: filters by priority, then declaration order, then included plugins; a filter returns None to pass, a `ServerRequest` to rewrite what the hooks after it see, or a `ServerResponse` to answer and stop; the access hooks rule on every requested layer before any service renders it; a service nobody serves is a 400 naming the SERVICE. `qgis_sdk.testing.FakeServerInterface` is the scripted interface, so 38 pure tests prove the three claims of #1 (a filter rewriting a WMS GetCapabilities request, a service answering its own request, an access hook refusing one layer) without QGIS. The refusal contract, decided here because #1 needed it: a hook says no by returning `ServerResponse.denied(reason, status=403)`, an access hook says no by returning `False` and the host builds that 403 naming the layer, and a hook that wants a different refusal writes it to `ctx.response` first. Still to do for #1: the adapter that turns these hooks into `QgsServerFilter`/`QgsService`/`QgsAccessControlFilter` over a real `QgsServerInterface`, and the codegen that emits `serverClassFactory`.
<!-- SECTION:NOTES:END -->

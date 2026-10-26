---
id: TASK-80
title: >-
  Add the QGIS Server host: server declarations, ServerContext, generated
  serverClassFactory, in-process QgsServer tests and dev --host server
status: To Do
assignee: []
created_date: '2026-10-26T10:11:00Z'
labels: []
milestone: m-8
dependencies:
  - TASK-64
  - TASK-63
type: enhancement
ordinal: 80000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-52 points 1, 2, 4. [tool.qgis-sdk] hosts; @server.filter(priority=), @server.service(name=, version=), @server.access_control on plain functions with an injected ServerContext (curated services over the request project, request and response as plain models; never QgsServerInterface); build generates serverClassFactory and server=True in metadata.txt; check HOST001/HOST002; qgis_sdk.testing fakes for request/response and a QgsServer in-process runner for test --target server; dev --host server with a local QgsServer loop and reload; scaffold --host server; reference example server variant; jobs request-scoped unless plugin-owned; agent endpoint developer-mode only on this host.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A plugin declaring a filter, a service and an access-control hook loads through the generated serverClassFactory in an in-process QgsServer, the filter sees and rewrites a WMS GetCapabilities request, the service answers its own request, and the access-control hook restricts a layer (qgis native tests under a headless QgsApplication; no FCGI).
- [ ] #2 The same plugin class with hosts = [desktop, server] runs on both: Desktop bindings attach on Desktop and refuse by name on the server; HOST001/HOST002 fire on misdeclared projects (pure tests); request-scoped jobs die with the request (stateful tests).
- [ ] #3 qgis-sdk new --host server scaffolds, check/test --target server/build pass, dev --host server reloads a filter edit (devtools harness); doc-12 documents the server host and what it never exposes.
<!-- AC:END -->

---
id: TASK-92
title: >-
  Add connections and authentication configuration: registered data-source
  connections, browsing, opening from a connection, auth configuration ids
status: Done
assignee: []
created_date: '2026-10-26T10:11:00Z'
updated_date: '2026-11-07 14:30'
labels: []
milestone: m-10
dependencies:
  - TASK-87
type: enhancement
ordinal: 92000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-54 point 4. connections.list/describe/browse over the provider connection registry, open_layer(connection, item), test(connection); auth.configurations as ids and names only (never secrets), attach to a connection; fake, native, host operations, grants with destructive and credential annotations.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A GeoPackage and a PostGIS fixture connection list, browse and open with fake and native sharing the contract tests; no secret crosses any model (native tests; PostGIS row recorded or blocked by environment).
- [x] #2 Host operations regenerated and typed; the agent consent list shows credential-touching operations distinctly.
- [x] #3 doc-22 rows complete; doc-12/doc-13 document connections.
<!-- AC:END -->

## Implementation notes

Implemented on the 0.10.0 sprint-3 branch, on top of the sprint-1 layer kinds
and the sprint-2 symbology surface.

**Models.** `qgis_sdk.models.connections` - `ConnectionInfo` (name, provider and
the *id* of the attached authentication configuration), `ConnectionItem`
(`CONNECTION_ITEM_KINDS`: schema, vector, aspatial, raster, view,
materialized_view, foreign; `geometries` in the layer vocabulary), `ConnectionTest`
(the `ExpressionCheck` shape: a verdict and, if not, why) and `AuthConfiguration`
(id and name). The no-secret rule is enforced by construction: the fields a
description carries are the whole model, the connection URI never crosses, and
the wire schemas are closed objects.

**Service.** `qgis_sdk.services.Connections` - `list_connections`, `connection`,
`browse` (one level at a time: schemas first for a schema-capable backend,
tables directly for a GeoPackage), `open_layer`, `test`, `auth_configurations`
and `attach_auth_config`. Lookup misses are named errors
(`QgisSdkConnectionNotFoundError` with both provider and name,
`QgisSdkConnectionItemNotFoundError` for a schema or table); a connection that
exists but refuses raises `QgisSdkConnectionUnavailableError` with the
provider's own refusal (password tokens redacted) while `test` answers the same
refusal as a verdict. `open_layer` refuses a schema ("browsed, not opened"), a
raster table and a provider the SDK does not open tables for.

**The registry's own names.** A GeoPackage connection answers provider `ogr` -
QGIS implements the GeoPackage connection methods in its OGR provider
(`QgsOgrProviderMetadata::connections` returns `QgsGeoPackageProviderConnection`
entries; its own data items comment "GPKG methods are implemented in OGR"), so
`ogr` is the honest registry key and both backends report it.

**Fake.** `qgis_sdk.testing.FakeConnections(layers)` - declarations of
connections, tables and auth configurations (the registry chooses the id, as
natively). Two flags model what a fake cannot pretend: `valid=False` makes
`test` answer a declared refusal, `accepts_auth=False` refuses attachment the
way a file-based connection does.

**Native.** `qgis_sdk.adapters.qgis.NativeConnections` - `dbConnections()` per
provider for the registry, `schemas()`/`tables()`/`table()`/`tableUri()` for
the browse and the open (a table opens with the provider key its registry
knows: `postgres` or `ogr`), `QgsAuthManager.availableAuthMethodConfigs` -
"base configs (not decrypted data)" - for the configuration listing, and
`saveConnection` for attach, which clears the stored password and writes the
non-expanded `authcfg=` form (`uri(expandAuthConfig=False)` keeps any stored
password otherwise, verified in the QGIS source). Opened layers land in the
sibling `NativeLayers` registry (`adopt_vector`).

**Wire.** Seven operations - `connections.list/describe/browse/open_layer/test`,
`auth.configurations`, `auth.attach` - under `connections.read`, `layers.open`
for `open_layer` ("a project grants open a layer"), `auth.read` and `auth.write`.
The surface is 82 operations, 29 grants, 14 destructive and 6 credential.
`HostOperation.credential` is a second annotation beside `destructive`, never
folded into it: the agent consent list shows "will this change my project?" and
"will this touch my credentials?" distinctly (`network.fetch` carries
`credential` too - its request may name an `auth_config`). Both sets are pinned
in `tests/test_bridge_host_project.py`.

**Fixtures.** `tests/connection_fixtures.py` writes the GeoPackage fixture
pure-python (SQLite with the GPKG geometry dialect, the three tables the fake
declares) rather than committing a blob; a dead-port `warehouse` connection
registered **with a password in its settings** proves three claims without a
server - `test` answers a verdict, a description carries no secret, and attach
replaces the stored password. The PostGIS row runs against a server
`QGIS_SDK_TEST_POSTGIS` names (holding `public.points`) or is recorded as
**blocked by environment**, which AC 1 allows.

**AC 2's "credential-touching operations distinctly"** is the second annotation
in the manifest (`to_description()` emits `destructive` and `credential` as
separate fields), pinned by hand-written sets so neither axis can grow by
accident.

**Docs.** doc-22's planned row is complete with the seven host-operation rows,
the destructive list at fourteen and a new credential paragraph; doc-12 gains
"Connections and authentication configurations"; doc-13 gains "Connections from
a page".

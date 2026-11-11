"""Steps for the connections feature: one fake registry, no secrets to leak.

The fake answers from the declarations it was handed, so what these scenarios
prove is that the *models* carry a description whole and that the refusals are
named ones. The QGIS registry is not here on purpose: the contract suite is
where a registered connection - including one whose settings hold a password -
is proven against a real QGIS.

The declarations are the shared fixture vocabulary, so a scenario and the
contract suite arrange the same ``survey`` and ``lagoon`` and read the same
numbers back.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import connection_fixtures as connection_files
from pytest_bdd import given, parsers, then, when
from qgis_sdk.core import ResourceScope
from qgis_sdk.models import (
    AuthConfiguration,
    ConnectionInfo,
    ConnectionItem,
    ConnectionTest,
    QgisSdkError,
    VectorLayerInfo,
)
from qgis_sdk.testing import (
    ConnectionDeclaration,
    FakeConnections,
    FakeLayers,
    TableDeclaration,
)


def _runtime_phase3(connections, layers, scope):
    connections.declare_connection(
        ConnectionDeclaration(
            connection_files.POSTGIS_CONNECTION,
            provider="postgres",
            schemas=(connection_files.POSTGIS_SCHEMA,),
        )
    )
    connections.declare_table(
        TableDeclaration(
            connection_files.POSTGIS_CONNECTION,
            connection_files.POSTGIS_POINTS,
            provider="postgres",
            schema=connection_files.POSTGIS_SCHEMA,
            kind=connection_files.POSTGIS_POINTS_KIND,
            geometries=connection_files.POSTGIS_POINTS_GEOMETRIES,
            fields=connection_files.POSTGIS_POINTS_FIELDS,
            crs=connection_files.FIXTURE_CRS,
        )
    )
    return _runtime_phase2(connections, layers, scope)


def _runtime_phase2(connections, layers, scope):
    connections.declare_connection(
        ConnectionDeclaration(
            connection_files.BROKEN_CONNECTION,
            provider="postgres",
            valid=False,
            message="connection refused",
        )
    )
    connections.declare_auth_configuration(connection_files.AUTH_CONFIG_NAME)
    world = ConnectionsWorld(scope=scope, layers=layers, connections=connections)
    return _runtime_phase1(world)


def _runtime_phase1(world):
    world.providers = {
        connection_files.GPKG_CONNECTION: "ogr",
        connection_files.POSTGIS_CONNECTION: "postgres",
        connection_files.BROKEN_CONNECTION: "postgres",
    }
    return world


@dataclass
class ConnectionsWorld:
    """The fake registry the connections scenarios arrange and observe."""

    scope: ResourceScope
    layers: FakeLayers
    connections: FakeConnections
    providers: dict[str, str] = field(default_factory=dict)
    described: ConnectionInfo | None = None
    listed: tuple[ConnectionInfo, ...] = ()
    items: tuple[ConnectionItem, ...] = ()
    opened: VectorLayerInfo | None = None
    verdict: ConnectionTest | None = None
    configs: tuple[AuthConfiguration, ...] = ()
    attached: str | None = None
    refused: Exception | None = None


def _runtime() -> ConnectionsWorld:
    scope = ResourceScope()
    layers = FakeLayers(scope)
    connections = FakeConnections(layers)
    connections.declare_connection(
        ConnectionDeclaration(
            connection_files.GPKG_CONNECTION, schemas=(), accepts_auth=False
        )
    )
    connections.declare_table(
        TableDeclaration(
            connection_files.GPKG_CONNECTION,
            connection_files.GPKG_ROADS,
            kind=connection_files.GPKG_ROADS_KIND,
            geometries=connection_files.GPKG_ROADS_GEOMETRIES,
            fields=connection_files.GPKG_ROADS_FIELDS,
            crs=connection_files.FIXTURE_CRS,
        )
    )
    connections.declare_table(
        TableDeclaration(
            connection_files.GPKG_CONNECTION,
            connection_files.GPKG_NOTES,
            kind=connection_files.GPKG_NOTES_KIND,
            geometries=connection_files.GPKG_NOTES_GEOMETRIES,
            fields=connection_files.GPKG_NOTES_FIELDS,
        )
    )
    return _runtime_phase3(connections, layers, scope)


@given("a runtime with connections and auth configurations", target_fixture="world")
def a_runtime() -> ConnectionsWorld:
    return _runtime()


@when("the plugin lists the connections", target_fixture="world")
def lists(world: ConnectionsWorld) -> ConnectionsWorld:
    world.listed = world.connections.list_connections()
    return world


@when(
    parsers.parse('the plugin describes connection "{name}" of provider "{provider}"'),
    target_fixture="world",
)
def describes(world: ConnectionsWorld, name: str, provider: str) -> ConnectionsWorld:
    try:
        world.described = world.connections.connection(provider, name)
    except QgisSdkError as error:
        world.refused = error
    return world


@when(
    parsers.parse('the plugin browses connection "{name}" of provider "{provider}"'),
    target_fixture="world",
)
def browses(world: ConnectionsWorld, name: str, provider: str) -> ConnectionsWorld:
    world.items = world.connections.browse(provider, name)
    return world


@when(
    parsers.parse('the plugin browses schema "{schema}" of connection "{name}"'),
    target_fixture="world",
)
def browses_schema(world: ConnectionsWorld, schema: str, name: str) -> ConnectionsWorld:
    world.items = world.connections.browse(world.providers[name], name, schema)
    return world


@when(
    parsers.parse('the plugin opens table "{table}" of connection "{name}"'),
    target_fixture="world",
)
def opens_table(world: ConnectionsWorld, table: str, name: str) -> ConnectionsWorld:
    world.opened = world.connections.open_layer(world.providers[name], name, "", table)
    return world


@when(
    parsers.parse(
        'the plugin opens schema "{schema}" as a table of connection "{name}"'
    ),
    target_fixture="world",
)
def opens_schema(world: ConnectionsWorld, schema: str, name: str) -> ConnectionsWorld:
    try:
        world.opened = world.connections.open_layer(
            world.providers[name], name, "", schema
        )
    except QgisSdkError as error:
        world.refused = error
    return world


@when(
    parsers.parse('the plugin tests connection "{name}" of provider "{provider}"'),
    target_fixture="world",
)
def tests(world: ConnectionsWorld, name: str, provider: str) -> ConnectionsWorld:
    world.verdict = world.connections.test(provider, name)
    return world


@when("the plugin lists the auth configurations", target_fixture="world")
def lists_configs(world: ConnectionsWorld) -> ConnectionsWorld:
    world.configs = world.connections.auth_configurations()
    return world


@when(
    parsers.parse(
        'the plugin attaches configuration "{name}" to connection "{connection}"'
    ),
    target_fixture="world",
)
def attaches(world: ConnectionsWorld, name: str, connection: str) -> ConnectionsWorld:
    # Read the registry rather than the last listing: this scenario may run
    # without the listing step having run first.
    world.configs = world.connections.auth_configurations()
    auth_config = next(each.id for each in world.configs if each.name == name)
    try:
        world.connections.attach_auth_config(
            world.providers[connection], connection, auth_config
        )
        world.attached = auth_config
    except QgisSdkError as error:
        world.refused = error
    return world


@then(parsers.parse('the registry lists connection "{name}" of provider "{provider}"'))
def listed(world: ConnectionsWorld, name: str, provider: str) -> None:
    assert (provider, name) in {(info.provider, info.name) for info in world.listed}


@then(parsers.parse('the description names "{name}" of provider "{provider}"'))
def described(world: ConnectionsWorld, name: str, provider: str) -> None:
    assert world.described is not None
    assert (world.described.name, world.described.provider) == (name, provider)


@then("its wire shape carries no credential")
def wire_without_secret(world: ConnectionsWorld) -> None:
    assert world.described is not None
    assert set(world.described.to_wire()) == {"name", "provider", "auth_config"}


@then(parsers.parse('the browse lists table "{name}" of kind "{kind}"'))
def browse_table(world: ConnectionsWorld, name: str, kind: str) -> None:
    assert (name, kind) in {(item.name, item.kind) for item in world.items}


@then(parsers.parse('the browse lists schema "{name}"'))
def browse_schema(world: ConnectionsWorld, name: str) -> None:
    assert (name, "schema") in {(item.name, item.kind) for item in world.items}


@then(parsers.parse('the opened layer is named "{name}"'))
def opened_named(world: ConnectionsWorld, name: str) -> None:
    assert world.opened is not None
    assert world.opened.name == name


@then(parsers.parse('its geometry type is "{geometry}"'))
def opened_geometry(world: ConnectionsWorld, geometry: str) -> None:
    assert world.opened is not None
    assert world.opened.geometry_type == geometry


@then("the layer list holds it")
def opened_registered(world: ConnectionsWorld) -> None:
    assert world.opened is not None
    assert world.opened.id in [info.id for info in world.layers.list_layers()]


@then("the SDK refuses it as browsed, not opened")
def refused_browsed(world: ConnectionsWorld) -> None:
    assert world.refused is not None
    assert "browsed, not opened" in str(world.refused)


@then("the verdict is invalid and says why")
def verdict_invalid(world: ConnectionsWorld) -> None:
    assert world.verdict is not None
    assert world.verdict.valid is False
    assert world.verdict.message


@then(parsers.parse('the configuration named "{name}" is listed'))
def config_listed(world: ConnectionsWorld, name: str) -> None:
    assert name in {each.name for each in world.configs}


@then("its wire shape carries an id and a name only")
def config_wire(world: ConnectionsWorld) -> None:
    assert world.configs
    for each in world.configs:
        assert set(each.to_wire()) == {"id", "name"}


@then(
    parsers.parse(
        'connection "{name}" of provider "{provider}" spends that configuration'
    )
)
def spends(world: ConnectionsWorld, name: str, provider: str) -> None:
    described = world.connections.connection(provider, name)
    assert described.auth_config == world.attached


@then("the SDK refuses it as having none to attach")
def refused_attach(world: ConnectionsWorld) -> None:
    assert world.refused is not None
    assert "there is none to attach" in str(world.refused)


@then("the SDK refuses it as no such connection")
def refused_missing(world: ConnectionsWorld) -> None:
    assert world.refused is not None
    assert "No connection" in str(world.refused)

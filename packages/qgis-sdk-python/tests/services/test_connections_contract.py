"""Both backends hold one connections contract (TASK-92's acceptance criterion).

The GeoPackage fixture connection runs everywhere: the fake declares it and the
native backend opens the file ``connection_fixtures.write_geopackage`` builds
and registers it in QGIS's own settings. The PostGIS connection is declared by
the fake always and registered natively only when ``QGIS_SDK_TEST_POSTGIS``
names a server holding ``public.points``; its tests record **blocked by
environment** rather than pretending a row passed.

What the contract asserts is what every backend must answer alike: the
descriptions (and their silence about secrets), the two-level browse, an opened
table landing in the layer registry with the fixture's shape, the test verdict,
and the authentication registry as ids and names only.
"""

from __future__ import annotations

import json

import connection_fixtures as connection_files
import pytest
from qgis_sdk.models import (
    QgisSdkAuthConfigNotFoundError,
    QgisSdkConnectionItemNotFoundError,
    QgisSdkUnsupportedCapabilityError,
)

POSTGIS_BLOCKED = (
    "blocked by environment: no PostGIS server answers, so the row is "
    "recorded rather than pretended (set QGIS_SDK_TEST_POSTGIS to a database "
    "holding public.points)"
)


@pytest.fixture()
def postgis(services):
    name = services.postgis_connection
    if name is None:
        pytest.skip(POSTGIS_BLOCKED)
    return name


def test_the_registry_holds_the_fixture_connections(services):
    listed = {
        (info.provider, info.name) for info in services.connections.list_connections()
    }

    assert ("ogr", connection_files.GPKG_CONNECTION) in listed
    assert ("postgres", connection_files.BROKEN_CONNECTION) in listed


def test_every_description_is_the_same_one_the_listing_answers(services):
    for info in services.connections.list_connections():
        assert services.connections.connection(info.provider, info.name) == info, (
            info.name
        )


def test_a_description_carries_no_secret_by_construction(services):
    for info in services.connections.list_connections():
        wire = info.to_wire()
        assert set(wire) == {"name", "provider", "auth_config"}, info.name
        encoded = json.dumps(wire)
        assert "password" not in encoded.lower(), info.name
        assert connection_files.BROKEN_PASSWORD not in encoded, info.name


def test_the_geopackage_connection_browses_its_tables_directly(services):
    items = services.connections.browse("ogr", connection_files.GPKG_CONNECTION)

    assert {(item.name, item.kind, item.schema) for item in items} == {
        (connection_files.GPKG_ROADS, connection_files.GPKG_ROADS_KIND, ""),
        (connection_files.GPKG_PLACES, connection_files.GPKG_PLACES_KIND, ""),
        (connection_files.GPKG_NOTES, connection_files.GPKG_NOTES_KIND, ""),
    }
    by_name = {item.name: item for item in items}
    assert by_name[connection_files.GPKG_ROADS].geometries == (
        connection_files.GPKG_ROADS_GEOMETRIES
    )
    assert by_name[connection_files.GPKG_PLACES].geometries == (
        connection_files.GPKG_PLACES_GEOMETRIES
    )
    assert by_name[connection_files.GPKG_NOTES].geometries == ()


def test_browsing_the_postgis_connection_answers_its_schemas_first(services, postgis):
    items = services.connections.browse("postgres", postgis)

    assert [item.name for item in items] == [connection_files.POSTGIS_SCHEMA]
    assert all(item.kind == "schema" for item in items)


def test_browsing_one_postgis_schema_answers_its_tables(services, postgis):
    items = services.connections.browse(
        "postgres", postgis, connection_files.POSTGIS_SCHEMA
    )

    points = [item for item in items if item.name == connection_files.POSTGIS_POINTS]
    assert points, [item.name for item in items]
    assert points[0].kind == connection_files.POSTGIS_POINTS_KIND
    assert points[0].geometries == connection_files.POSTGIS_POINTS_GEOMETRIES


def test_a_schema_the_connection_does_not_hold_is_refused_by_name(services):
    with pytest.raises(QgisSdkConnectionItemNotFoundError) as refused:
        services.connections.browse("ogr", connection_files.GPKG_CONNECTION, "topology")

    assert "topology" in str(refused.value)


def test_an_item_the_connection_does_not_hold_is_refused_by_name(services):
    with pytest.raises(QgisSdkConnectionItemNotFoundError):
        services.connections.open_layer(
            "ogr", connection_files.GPKG_CONNECTION, "", "bridges"
        )


def test_opening_a_geopackage_table_answers_the_shape_the_fixture_holds(services):
    info = services.connections.open_layer(
        "ogr", connection_files.GPKG_CONNECTION, "", connection_files.GPKG_ROADS
    )

    assert info.name == connection_files.GPKG_ROADS
    assert info.kind == "vector"
    assert info.geometry_type == "line"
    assert info.field_names == connection_files.GPKG_ROADS_FIELDS
    assert info.crs == connection_files.FIXTURE_CRS
    # The layer lands in the runtime's registry like any other opened layer.
    assert info.id in [opened.id for opened in services.layers.list_layers()]


def test_opening_the_aspatial_table_answers_no_geometry(services):
    info = services.connections.open_layer(
        "ogr", connection_files.GPKG_CONNECTION, "", connection_files.GPKG_NOTES
    )

    assert info.geometry_type == "none"
    assert info.field_names == connection_files.GPKG_NOTES_FIELDS


def test_opening_the_postgis_table_answers_a_vector_layer(services, postgis):
    info = services.connections.open_layer(
        "postgres",
        postgis,
        connection_files.POSTGIS_SCHEMA,
        connection_files.POSTGIS_POINTS,
    )

    assert info.name == connection_files.POSTGIS_POINTS
    assert info.geometry_type == "point"
    assert info.id in [opened.id for opened in services.layers.list_layers()]


def test_a_schema_is_browsed_not_opened(services, postgis):
    with pytest.raises(QgisSdkUnsupportedCapabilityError) as refused:
        services.connections.open_layer(
            "postgres", postgis, "", connection_files.POSTGIS_SCHEMA
        )

    assert "browsed, not opened" in str(refused.value)


def test_the_unreachable_connection_answers_a_verdict_not_an_exception(services):
    verdict = services.connections.test("postgres", connection_files.BROKEN_CONNECTION)

    assert verdict.valid is False
    assert verdict.message
    assert connection_files.BROKEN_PASSWORD not in verdict.message


def test_the_reachable_connection_tests_valid(services):
    verdict = services.connections.test("ogr", connection_files.GPKG_CONNECTION)

    assert verdict.valid is True
    assert verdict.message is None


def test_the_auth_registry_answers_ids_and_names_only(services):
    auth_config = services.declare_auth_configuration(connection_files.AUTH_CONFIG_NAME)

    listed = {each.id: each for each in services.connections.auth_configurations()}

    assert auth_config in listed
    assert listed[auth_config].name == connection_files.AUTH_CONFIG_NAME
    assert set(listed[auth_config].to_wire()) == {"id", "name"}


def test_attaching_swaps_the_id_the_description_answers(services):
    auth_config = services.declare_auth_configuration(connection_files.AUTH_CONFIG_NAME)

    services.connections.attach_auth_config(
        "postgres", connection_files.BROKEN_CONNECTION, auth_config
    )

    described = services.connections.connection(
        "postgres", connection_files.BROKEN_CONNECTION
    )
    assert described.auth_config == auth_config


def test_attaching_an_id_the_registry_does_not_hold_is_refused(services):
    with pytest.raises(QgisSdkAuthConfigNotFoundError):
        services.connections.attach_auth_config(
            "postgres", connection_files.BROKEN_CONNECTION, "zzz9999"
        )


def test_attaching_to_a_connection_without_one_is_refused_by_name(services):
    auth_config = services.declare_auth_configuration(connection_files.AUTH_CONFIG_NAME)

    with pytest.raises(QgisSdkUnsupportedCapabilityError) as refused:
        services.connections.attach_auth_config(
            "ogr", connection_files.GPKG_CONNECTION, auth_config
        )

    assert "there is none to attach" in str(refused.value)
    assert connection_files.GPKG_CONNECTION in str(refused.value)
    assert "ogr" in str(refused.value)

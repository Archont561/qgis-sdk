"""The connection models and their fake, stated as rules a reader can check.

This file is the pure lane: what the models validate, what the wire carries and
what the fake refuses. The two backends answer the same contract in
``tests/services/test_connections_contract.py``; what only real QGIS can prove -
a registered connection whose settings hold a password, and an attach that
replaces it - lives in ``tests/services/test_native_connections.py``.
"""

from __future__ import annotations

import json

import pytest
from qgis_sdk.core import ResourceScope
from qgis_sdk.models import (
    AUTH_CONFIGURATION,
    CONNECTION_INFO,
    CONNECTION_ITEM,
    CONNECTION_TEST,
    ITEM_GEOMETRIES,
    AuthConfiguration,
    ConnectionInfo,
    ConnectionItem,
    ConnectionTest,
    QgisSdkAuthConfigNotFoundError,
    QgisSdkConnectionItemNotFoundError,
    QgisSdkConnectionNotFoundError,
    QgisSdkUnsupportedCapabilityError,
    auth_configuration_from_wire,
    connection_info_from_wire,
    connection_item_from_wire,
    connection_test_from_wire,
)
from qgis_sdk.testing import (
    ConnectionDeclaration,
    FakeConnections,
    FakeLayers,
    TableDeclaration,
)

# -- the models --------------------------------------------------------------


def test_a_connection_description_carries_a_name_a_provider_and_nothing_secret():
    info = ConnectionInfo(name="survey", provider="ogr")

    assert info.to_wire() == {
        "name": "survey",
        "provider": "ogr",
        "auth_config": None,
    }


def test_a_connection_description_names_the_auth_config_it_spends():
    info = ConnectionInfo(name="lagoon", provider="postgres", auth_config="a1b2c3d")

    assert info.auth_config == "a1b2c3d"
    assert set(info.to_wire()) == {"name", "provider", "auth_config"}


def test_a_blank_name_or_provider_is_refused_where_it_is_declared():
    for arguments in ({"name": " ", "provider": "ogr"}, {"name": "x", "provider": ""}):
        with pytest.raises(ValueError):
            ConnectionInfo(**arguments)


@pytest.mark.parametrize("blank", ["", "   "])
def test_an_auth_config_id_is_never_blank(blank: str):
    with pytest.raises(ValueError):
        ConnectionInfo(name="lagoon", provider="postgres", auth_config=blank)


def test_a_browse_item_names_its_kind_from_the_declared_vocabulary():
    item = ConnectionItem(
        name="roads", schema="", kind="vector", geometries=("line", "point")
    )

    assert item.to_wire() == {
        "name": "roads",
        "schema": "",
        "kind": "vector",
        "geometries": ["line", "point"],
    }


def test_a_browse_item_kind_outside_the_vocabulary_is_refused():
    with pytest.raises(ValueError):
        ConnectionItem(name="roads", schema="", kind="materialized view")


def test_a_geometry_outside_the_layer_vocabulary_is_refused():
    with pytest.raises(ValueError):
        ConnectionItem(name="roads", schema="", kind="vector", geometries=("curve",))


def test_a_schema_entry_has_no_schema_of_its_own_and_no_geometry():
    ConnectionItem(name="public", schema="", kind="schema")

    with pytest.raises(ValueError):
        ConnectionItem(name="public", schema="other", kind="schema")
    with pytest.raises(ValueError):
        ConnectionItem(name="public", schema="", kind="schema", geometries=("point",))


def test_a_connection_test_is_a_verdict_and_if_not_why():
    assert ConnectionTest(valid=True).to_wire() == {"valid": True, "message": None}

    failed = ConnectionTest(valid=False, message="connection refused")
    assert failed.to_wire() == {"valid": False, "message": "connection refused"}

    with pytest.raises(ValueError):
        ConnectionTest(valid=True, message="odd")
    with pytest.raises(ValueError):
        ConnectionTest(valid=False)


def test_an_auth_configuration_is_an_id_and_a_name_only():
    configuration = AuthConfiguration(id="a1b2c3d", name="field crew")

    assert configuration.to_wire() == {"id": "a1b2c3d", "name": "field crew"}


@pytest.mark.parametrize(
    ("model", "reader"),
    [
        (ConnectionInfo("survey", "ogr"), connection_info_from_wire),
        (
            ConnectionItem("roads", "", "vector", ("line",)),
            connection_item_from_wire,
        ),
        (ConnectionTest(valid=True), connection_test_from_wire),
        (AuthConfiguration("a1b2c3d", "field crew"), auth_configuration_from_wire),
    ],
)
def test_every_model_round_trips_through_its_wire_shape(model, reader):
    assert reader(model.to_wire()) == model
    # A model that is already a model is answered as itself, so a handler that
    # passes one through does not rebuild it field by field.
    assert reader(model) is model


def test_a_wire_shape_that_is_not_an_object_is_refused_by_type():
    for reader in (
        connection_info_from_wire,
        connection_item_from_wire,
        connection_test_from_wire,
        auth_configuration_from_wire,
    ):
        with pytest.raises(TypeError):
            reader(["not", "an", "object"])


def test_the_wire_schemas_are_closed_and_name_the_discriminators():
    for schema in (
        CONNECTION_INFO,
        CONNECTION_ITEM,
        CONNECTION_TEST,
        AUTH_CONFIGURATION,
    ):
        assert schema["additionalProperties"] is False, schema["title"]
    assert set(CONNECTION_ITEM["properties"]["kind"]["enum"]) > {"schema", "vector"}
    assert set(CONNECTION_ITEM["properties"]["geometries"]["items"]["enum"]) == set(
        ITEM_GEOMETRIES
    )


# -- the fake ----------------------------------------------------------------


@pytest.fixture()
def registry():
    scope = ResourceScope()
    layers = FakeLayers(scope)
    connections = FakeConnections(layers)
    yield connections, layers, scope
    scope.close()


def _declared(connections: FakeConnections) -> None:
    connections.declare_connection(
        ConnectionDeclaration("survey", schemas=(), accepts_auth=False)
    )
    connections.declare_table(
        TableDeclaration(
            "survey",
            "roads",
            kind="vector",
            geometries=("line",),
            fields=("name",),
            crs="EPSG:4326",
        )
    )
    connections.declare_connection(
        ConnectionDeclaration("lagoon", provider="postgres", schemas=("public",))
    )
    connections.declare_table(
        TableDeclaration(
            "lagoon",
            "points",
            provider="postgres",
            schema="public",
            kind="vector",
            geometries=("point",),
            fields=("kind",),
        )
    )


def test_a_fresh_registry_lists_the_connections_declared_in_order(registry):
    connections, _, _ = registry
    _declared(connections)

    assert [info.name for info in connections.list_connections()] == [
        "survey",
        "lagoon",
    ]
    assert [info.provider for info in connections.list_connections()] == [
        "ogr",
        "postgres",
    ]


def test_an_unknown_provider_or_connection_is_refused_with_both_names(registry):
    connections, _, _ = registry
    _declared(connections)

    with pytest.raises(QgisSdkConnectionNotFoundError) as unknown:
        connections.connection("postgres", "survey")
    assert unknown.value.provider == "postgres"
    assert unknown.value.name == "survey"
    assert "survey" in str(unknown.value) and "postgres" in str(unknown.value)

    with pytest.raises(QgisSdkConnectionNotFoundError) as missing:
        connections.connection("oracle", "lagoon")
    assert "oracle" in str(missing.value)


def test_a_connection_is_described_by_the_same_description_the_list_answers(registry):
    connections, _, _ = registry
    _declared(connections)
    connections.declare_auth_configuration("field crew")
    connections.attach_auth_config("postgres", "lagoon", "cfg0001")

    listed = {info.name: info for info in connections.list_connections()}

    assert connections.connection("postgres", "lagoon") == listed["lagoon"]
    assert listed["lagoon"].auth_config == "cfg0001"
    assert listed["survey"].auth_config is None


def test_browsing_a_schema_capable_connection_answers_its_schemas_first(registry):
    connections, _, _ = registry
    _declared(connections)

    items = connections.browse("postgres", "lagoon")

    assert [(item.name, item.kind) for item in items] == [("public", "schema")]


def test_browsing_one_schema_answers_that_schemas_tables(registry):
    connections, _, _ = registry
    _declared(connections)

    items = connections.browse("postgres", "lagoon", "public")

    assert [(item.name, item.kind, item.geometries) for item in items] == [
        ("points", "vector", ("point",))
    ]
    assert items[0].schema == "public"


def test_browsing_a_schema_less_connection_answers_its_tables_directly(registry):
    connections, _, _ = registry
    _declared(connections)

    items = connections.browse("ogr", "survey")

    assert [(item.name, item.kind) for item in items] == [("roads", "vector")]


def test_a_schema_the_connection_does_not_hold_is_refused_by_name(registry):
    connections, _, _ = registry
    _declared(connections)

    with pytest.raises(QgisSdkConnectionItemNotFoundError) as unknown:
        connections.browse("postgres", "lagoon", "topology")

    assert unknown.value.schema == "topology"
    assert "topology" in str(unknown.value)


def test_opening_a_table_answers_a_vector_layer_with_the_declared_detail(registry):
    connections, layers, _ = registry
    _declared(connections)

    info = connections.open_layer("ogr", "survey", "", "roads")

    assert info.name == "roads"
    assert info.geometry_type == "line"
    assert info.field_names == ("name",)
    assert info.crs == "EPSG:4326"
    # The opened layer lands in the layers registry like any other.
    assert [opened.id for opened in layers.list_layers()] == [info.id]


def test_opening_a_schema_is_refused_as_what_it_is(registry):
    connections, _, _ = registry
    _declared(connections)

    with pytest.raises(QgisSdkUnsupportedCapabilityError) as refused:
        connections.open_layer("postgres", "lagoon", "", "public")

    assert "browsed, not opened" in str(refused.value)


def test_opening_a_raster_table_is_refused_by_name(registry):
    connections, _, _ = registry
    connections.declare_connection(
        ConnectionDeclaration("warehouse", provider="postgres", schemas=())
    )
    connections.declare_table(
        TableDeclaration("warehouse", "dem", provider="postgres", kind="raster")
    )

    with pytest.raises(QgisSdkUnsupportedCapabilityError) as refused:
        connections.open_layer("postgres", "warehouse", "", "dem")

    assert "raster" in str(refused.value)


def test_opening_an_item_the_connection_does_not_hold_is_refused(registry):
    connections, _, _ = registry
    _declared(connections)

    with pytest.raises(QgisSdkConnectionItemNotFoundError):
        connections.open_layer("ogr", "survey", "", "bridges")
    with pytest.raises(QgisSdkConnectionItemNotFoundError):
        connections.open_layer("ogr", "survey", "other", "roads")


def test_test_answers_a_verdict_not_an_exception(registry):
    connections, _, _ = registry
    _declared(connections)
    connections.declare_connection(
        ConnectionDeclaration(
            "warehouse", provider="postgres", valid=False, message="connection refused"
        )
    )

    assert connections.test("ogr", "survey").valid is True
    failed = connections.test("postgres", "warehouse")
    assert failed.valid is False
    assert failed.message == "connection refused"


def test_the_auth_registry_lists_ids_and_names_only(registry):
    connections, _, _ = registry
    auth_config = connections.declare_auth_configuration("field crew")

    listed = connections.auth_configurations()

    assert [each.to_wire() for each in listed] == [
        {"id": auth_config, "name": "field crew"}
    ]
    assert json.dumps([each.to_wire() for each in listed]).count("field crew") == 1


def test_attaching_swaps_the_id_the_description_answers(registry):
    connections, _, _ = registry
    _declared(connections)
    auth_config = connections.declare_auth_configuration("field crew")

    connections.attach_auth_config("postgres", "lagoon", auth_config)

    assert connections.connection("postgres", "lagoon").auth_config == auth_config


def test_attaching_an_id_the_registry_does_not_hold_is_refused(registry):
    connections, _, _ = registry
    _declared(connections)

    with pytest.raises(QgisSdkAuthConfigNotFoundError):
        connections.attach_auth_config("postgres", "lagoon", "zzz9999")


def test_attaching_to_a_connection_that_authenticates_without_one_is_refused(registry):
    connections, _, _ = registry
    _declared(connections)
    auth_config = connections.declare_auth_configuration("field crew")

    with pytest.raises(QgisSdkUnsupportedCapabilityError) as refused:
        connections.attach_auth_config("ogr", "survey", auth_config)

    assert "there is none to attach" in str(refused.value)
    assert "survey" in str(refused.value) and "ogr" in str(refused.value)


def test_a_table_is_declared_under_its_connection_not_before_it(registry):
    from qgis_sdk.declarations import QgisSdkDeclarationError

    connections, _, _ = registry

    with pytest.raises(QgisSdkDeclarationError):
        connections.declare_table(TableDeclaration("survey", "roads"))

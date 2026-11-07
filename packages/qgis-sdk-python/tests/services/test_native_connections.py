"""What only a real QGIS can prove about connections (TASK-92's native tests).

Three claims need the provider registry, its settings and a live provider, and
no fake can make them honestly:

* a connection registered **with a password in its settings** still describes
  itself without one - the no-secret claim against a secret that exists;
* attaching an authentication configuration **replaces the stored password**
  and writes the non-expanded ``authcfg=`` form back;
* the fixture GeoPackage the pure writer built is a file the OGR provider
  actually reads, listed under the ``ogr`` registry key - the answer to "why is
  a GeoPackage connection not provider ``geopackage``".

This file asks for ``native_services`` rather than ``services``, because a
claim about real QGIS must never be answered by the fake.
"""

from __future__ import annotations

import json

import connection_fixtures as connection_files
import pytest
from qgis_sdk.models import QgisSdkUnsupportedCapabilityError

pytestmark = pytest.mark.qgis


def _stored_uri(provider: str, name: str) -> str:
    """The connection's registered URI, straight out of QGIS's settings."""
    from qgis.core import QgsProviderRegistry

    found = (
        QgsProviderRegistry.instance().providerMetadata(provider).dbConnections(False)
    )
    return found[name].uri()


def test_a_registered_password_reaches_no_description(native_services):
    described = native_services.connections.connection(
        "postgres", connection_files.BROKEN_CONNECTION
    )

    encoded = json.dumps(described.to_wire())
    assert connection_files.BROKEN_PASSWORD not in encoded
    assert described.auth_config is None
    # The secret does exist: it is in the settings this fixture registered.
    assert connection_files.BROKEN_PASSWORD in _stored_uri(
        "postgres", connection_files.BROKEN_CONNECTION
    )


def test_the_fixture_geopackage_is_listed_under_the_ogr_registry_key(native_services):
    listed = {
        (info.provider, info.name): info
        for info in native_services.connections.list_connections()
    }

    described = listed[("ogr", connection_files.GPKG_CONNECTION)]
    assert described.auth_config is None


def test_the_pure_writer_built_a_geopackage_the_provider_reads(native_services):
    items = {
        item.name: item
        for item in native_services.connections.browse(
            "ogr", connection_files.GPKG_CONNECTION
        )
    }

    assert set(items) == {
        connection_files.GPKG_ROADS,
        connection_files.GPKG_PLACES,
        connection_files.GPKG_NOTES,
    }
    assert items[connection_files.GPKG_ROADS].kind == "vector"
    assert items[connection_files.GPKG_ROADS].geometries == ("line",)
    assert items[connection_files.GPKG_NOTES].kind == "aspatial"
    assert items[connection_files.GPKG_NOTES].geometries == ()


def test_attaching_replaces_the_stored_password_with_the_configuration(native_services):
    auth_config = native_services.declare_auth_configuration(
        connection_files.AUTH_CONFIG_NAME
    )

    native_services.connections.attach_auth_config(
        "postgres", connection_files.BROKEN_CONNECTION, auth_config
    )

    stored = _stored_uri("postgres", connection_files.BROKEN_CONNECTION)
    assert connection_files.BROKEN_PASSWORD not in stored
    assert f"authcfg={auth_config}" in stored
    # And the description now names the configuration it spends.
    described = native_services.connections.connection(
        "postgres", connection_files.BROKEN_CONNECTION
    )
    assert described.auth_config == auth_config


def test_the_auth_registry_answers_base_configs_only(native_services):
    auth_config = native_services.declare_auth_configuration(
        connection_files.AUTH_CONFIG_NAME
    )

    listed = {
        each.id: each for each in native_services.connections.auth_configurations()
    }

    assert listed[auth_config].name == connection_files.AUTH_CONFIG_NAME
    for each in listed.values():
        assert set(each.to_wire()) == {"id", "name"}, each.id


def test_a_geopackage_connection_cannot_carry_an_authentication_configuration(
    native_services,
):
    auth_config = native_services.declare_auth_configuration(
        connection_files.AUTH_CONFIG_NAME
    )

    with pytest.raises(QgisSdkUnsupportedCapabilityError) as refused:
        native_services.connections.attach_auth_config(
            "ogr", connection_files.GPKG_CONNECTION, auth_config
        )

    assert "there is none to attach" in str(refused.value)


def test_the_unreachable_connection_reports_the_servers_own_refusal(native_services):
    verdict = native_services.connections.test(
        "postgres", connection_files.BROKEN_CONNECTION
    )

    assert verdict.valid is False
    assert verdict.message
    assert connection_files.BROKEN_PASSWORD not in verdict.message

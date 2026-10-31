"""Simple server's hooks, through the scripted server: no QGIS, no display.

``FakeServerInterface`` is the interface ``qgis.server`` provides - it records
what a host registers - and ``serve`` drives the same dispatcher a deployed
server drives, so these tests fail when the hooks stop agreeing with each other,
not only when QGIS is missing. ``qgis-sdk test --target server`` runs the same
suite against the real ``QgsServer`` where the build has server bindings.
"""

from __future__ import annotations

import json
from collections.abc import Iterator

import pytest
from qgis_sdk.core import ResourceScope
from qgis_sdk.server import (
    ServerContext,
    ServerHost,
    ServerRequest,
    ServerResponse,
)
from qgis_sdk.testing import FakeServerInterface
from simple_server import HOOKS
from simple_server.plugin import FIXTURE, SERVICE, measure

BOUNDS = (21.0, 52.0, 21.2, 52.2)


def request(**params: str) -> ServerRequest:
    return ServerRequest(
        method="GET",
        url="http://localhost/qgis/qgis_mapserv.fcgi",
        params=params,
    )


@pytest.fixture
def scope() -> Iterator[ResourceScope]:
    """One request scope, closed at the end, the way a host closes it."""
    opened = ResourceScope()
    try:
        yield opened
    finally:
        opened.close()


@pytest.fixture
def interface() -> FakeServerInterface:
    """A host that records what the plugin registers and serves through it."""
    recorded = FakeServerInterface()
    ServerHost(HOOKS, recorded).register()
    return recorded


def test_the_service_answers_the_extent_of_the_bundled_fixture() -> None:
    answered = FakeServerInterface().serve(
        HOOKS, request(SERVICE=SERVICE, REQUEST="extent")
    )

    assert answered.status == 200
    assert json.loads(answered.body) == {
        "service": SERVICE,
        # The filter filled the missing VERSION in before the service ran.
        "version": "1.0.0",
        "features": 3,
        "bbox": list(BOUNDS),
    }


def test_the_measurement_is_the_fixture_and_not_a_constant() -> None:
    measured = measure(FIXTURE)

    assert measured.bounds == BOUNDS
    assert measured.features == 3


def test_a_request_that_names_no_version_is_rewritten_by_the_filter(
    scope: ResourceScope,
) -> None:
    served = request(SERVICE=SERVICE)

    changed = HOOKS.filters[0](
        ServerContext(scope, served, ServerResponse()), served, ServerResponse()
    )

    assert changed.param("VERSION") == "1.0.0"


def test_a_request_that_names_a_version_is_passed_on_untouched(
    scope: ResourceScope,
) -> None:
    served = request(SERVICE=SERVICE, VERSION="1.0.0")

    assert (
        HOOKS.filters[0](
            ServerContext(scope, served, ServerResponse()), served, ServerResponse()
        )
        is None
    )


def test_another_request_of_this_service_is_refused_with_its_own_status() -> None:
    answered = FakeServerInterface().serve(
        HOOKS, request(SERVICE=SERVICE, REQUEST="GetCapabilities")
    )

    assert answered.status == 400
    assert "REQUEST=extent" in answered.body.decode()


def test_the_access_hook_allows_a_public_layer(scope: ResourceScope) -> None:
    served = request(SERVICE=SERVICE, REQUEST="extent", LAYERS="parcels")

    host = ServerHost(HOOKS, FakeServerInterface())
    context = ServerContext(scope, served, ServerResponse())

    assert host.permits(context, served, "parcels") is True
    assert host.denied_layer(context, served) is None


def test_a_private_layer_is_a_403_that_names_it(scope: ResourceScope) -> None:
    served = request(
        SERVICE=SERVICE, REQUEST="extent", LAYERS="parcels,private_parcels"
    )

    refused = ServerHost(HOOKS, FakeServerInterface()).denied_layer(
        ServerContext(scope, served, ServerResponse()), served
    )

    assert refused is not None
    assert refused.status == 403
    assert "private_parcels" in refused.body.decode()


def test_the_hooks_are_registered_with_the_interface_a_server_drives(
    interface: FakeServerInterface,
) -> None:
    assert interface.registrations == {"filters": 1, "services": 1, "access_control": 1}
    assert interface.services[0][:2] == (SERVICE, "1.0.0")

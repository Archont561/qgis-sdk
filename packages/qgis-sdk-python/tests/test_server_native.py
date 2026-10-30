"""The one QGIS the SDK cannot assume: a build with QGIS Server in it.

``qgis.server`` - ``QgsServer``, ``QgsServerInterface``, ``QgsServerFilter`` -
exists only when QGIS was configured with ``WITH_SERVER=ON`` and its Python
bindings. conda-forge passes ``-D WITH_SERVER=FALSE`` on every platform, so the
Pixi environment every other job uses has no such module and the whole server
host is proven there against ``qgis_sdk.testing.FakeServerInterface`` instead
(decision-52 implementation note).

This file is the other half: it runs only where the module exists, and it is
what the ``Server host`` CI row in ``.github/workflows/ci.yml`` selects with
``-m server``. Everywhere else ``pytest.importorskip`` skips it, so a build
without server bindings costs a skip and never a failure. It carries the seed of
TASK-80 AC 2 - the same plugin class served in-process under a headless
``QgsApplication`` - and grows there rather than starting a second file.
"""

from __future__ import annotations

import pytest

# One layer per module: `server` already means the QGIS bindings are there,
# and the application comes from the shared `qgis_app` fixture.
pytestmark = pytest.mark.server

server = pytest.importorskip(
    "qgis.server", reason="this QGIS was built without WITH_SERVER (no qgis.server)"
)


def test_the_bindings_the_host_needs_are_importable() -> None:
    from qgis.server import (
        QgsServer,
        QgsServerFilter,
        QgsServerInterface,
        QgsService,
    )

    assert all(
        item is not None
        for item in (QgsServer, QgsServerFilter, QgsServerInterface, QgsService)
    )


def test_a_server_can_be_created_in_process(qgis_app) -> None:
    from qgis.server import QgsServer

    created = QgsServer()

    assert created is not None
    # The in-process route TASK-80 AC 2 takes instead of FCGI: build a request,
    # hand it to this server, read the response. Only the classes are asserted
    # here, so the test keeps working on a build that renames either one.
    assert hasattr(created, "handleRequest")


def test_the_sdk_serves_a_request_inside_a_qgis_process(qgis_app) -> None:
    from qgis_sdk.server import (
        ServerHooks,
        ServerRequest,
        ServerResponse,
        filter,
        service,
    )
    from qgis_sdk.testing import FakeServerInterface

    @filter(priority=10)
    def default_version(ctx, request, response):
        if request.param("VERSION") is None:
            return request.with_params(VERSION="1.3.0")
        return None

    @service(name="WMS")
    def capabilities(ctx, request) -> ServerResponse:
        return ServerResponse.xml(f"<v>{request.param('VERSION')}</v>")

    answer = FakeServerInterface().serve(
        ServerHooks((default_version, capabilities)),
        ServerRequest(
            method="GET",
            url="http://localhost/qgis/qgis_mapserv.fcgi",
            params={"SERVICE": "WMS", "REQUEST": "GetCapabilities"},
        ),
    )

    # The pure layer answers the same way with QGIS loaded as it does without:
    # nothing in the dispatcher reaches a Qt object behind the author's back.
    assert answer.status == 200
    assert answer.body == b"<v>1.3.0</v>"

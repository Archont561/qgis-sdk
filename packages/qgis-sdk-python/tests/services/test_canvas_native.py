"""Real PyQGIS canvas: encoded drawings, real pans, and the server refusal.

Opt-in under ``QGIS_SDK_NATIVE_SERVICES=1``. The shared contract suite proves the
fake and the adapter answer the same boxes and callbacks; these tests prove the
parts only QGIS can answer - that a drawn polygon comes back as real WKT with a
part and vertex count, that a pan on a real ``QgsMapCanvas`` reaches an extent
subscription, that a map theme inserted in the project is one the canvas can be
drawn with, and that a server host refuses by name instead of inventing a canvas.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import conftest
import pytest
from qgis_sdk.core import Host, ResourceScope
from qgis_sdk.models import (
    QgisSdkScopeClosedError,
    QgisSdkUnsupportedCapabilityError,
)
from qgis_sdk.models.canvas import ZoomTarget

pytestmark = pytest.mark.qgis

if TYPE_CHECKING:
    from .conftest import Services


def _canvas(services: Services):
    assert services.canvas is not None
    return services.canvas


def test_a_drawn_polygon_is_real_wkt_with_its_ring(native_services: Services) -> None:
    drawn: list[object] = []
    cancel = _canvas(native_services).capture("polygon", drawn.append)
    try:
        assert native_services.draw is not None
        native_services.draw("polygon")
    finally:
        cancel()

    assert len(drawn) == 1, drawn
    geometry = drawn[0]
    assert geometry.geometry_type == "polygon"
    assert geometry.encoding == "wkt"
    assert geometry.value.upper().startswith("POLYGON")
    assert geometry.part_count == 1
    assert geometry.vertex_count == 4  # three corners plus the closing vertex
    assert geometry.crs == conftest.FIXTURE_CRS
    assert geometry.is_empty is False


def test_a_drawn_line_is_two_vertices_and_a_point_is_one(
    native_services: Services,
) -> None:
    drawn: list[object] = []
    canvas = _canvas(native_services)
    for shape, vertices in (("line", 2), ("point", 1)):
        assert native_services.draw is not None
        cancel = canvas.capture(shape, drawn.append)
        try:
            native_services.draw(shape)
        finally:
            cancel()
        assert drawn[-1].geometry_type == shape
        assert drawn[-1].vertex_count == vertices


def test_a_pan_on_a_real_canvas_reaches_the_extent_subscription(
    native_services: Services,
) -> None:
    """The stream follows the canvas's signal, not a value the host remembered."""
    canvas = _canvas(native_services)
    seen: list[object] = []

    cancel = canvas.watch_extent(seen.append)
    try:
        landed = canvas.zoom_to(ZoomTarget.layer(_fixture_layer(native_services)))
    finally:
        cancel()

    assert seen and seen[-1] == landed
    # The native box is the canvas's own, so it must cover the reference points.
    assert landed.x_min <= conftest.FIXTURE_EXTENT.x_min
    assert landed.y_min <= conftest.FIXTURE_EXTENT.y_min
    assert landed.x_max >= conftest.FIXTURE_EXTENT.x_max
    assert landed.y_max >= conftest.FIXTURE_EXTENT.y_max


def test_a_theme_in_the_project_is_one_the_canvas_draws_with(
    native_services: Services,
) -> None:
    assert native_services.declare_theme is not None
    assert native_services.fixture_layer is not None
    native_services.fixture_layer()
    native_services.declare_theme(conftest.DECLARED_THEME)

    canvas = _canvas(native_services)
    applied = canvas.apply_theme(conftest.DECLARED_THEME)

    assert conftest.DECLARED_THEME in applied.names
    assert applied.active == conftest.DECLARED_THEME
    assert canvas.themes().active == conftest.DECLARED_THEME


@pytest.mark.usefixtures("native_services")
def test_a_server_host_refuses_the_canvas_by_name() -> None:
    """A server request has map settings, not a view a user pans."""
    server = _server_canvas()

    for call in (
        server.extent,
        server.scale,
        server.crs,
        server.center,
        server.themes,
        server.refresh,
    ):
        with pytest.raises(QgisSdkUnsupportedCapabilityError) as failure:
            call()
        assert "QGIS Server" in str(failure.value), call.__name__

    with pytest.raises(QgisSdkUnsupportedCapabilityError):
        server.zoom_to(ZoomTarget.to_extent(conftest.FIXTURE_EXTENT))
    with pytest.raises(QgisSdkUnsupportedCapabilityError):
        server.apply_theme(conftest.DECLARED_THEME)
    with pytest.raises(QgisSdkUnsupportedCapabilityError):
        server.capture("point", lambda geometry: None)
    with pytest.raises(QgisSdkUnsupportedCapabilityError):
        server.watch_extent(lambda extent: None)


def test_a_runtime_with_no_canvas_refuses_by_name_without_one(
    native_services: Services,
) -> None:
    """A standalone application that never opened a map hears exactly that."""
    from qgis_sdk.adapters.qgis import NativeCanvas

    canvas = NativeCanvas(ResourceScope(), layers=None)
    with pytest.raises(QgisSdkUnsupportedCapabilityError) as failure:
        canvas.extent()

    assert "no map canvas" in str(failure.value)


def test_a_closed_scope_refuses_through_the_canvas(native_services: Services) -> None:
    """A disposed context cannot read the canvas it had a moment ago."""
    from qgis_sdk.adapters.qgis import NativeCanvas

    scope = ResourceScope()
    scope.close()
    canvas = NativeCanvas(scope, canvas=_offscreen_canvas())

    with pytest.raises(QgisSdkScopeClosedError):
        canvas.extent()


def _server_canvas():
    from qgis_sdk.adapters.qgis import NativeCanvas

    return NativeCanvas(ResourceScope(), host=Host.SERVER)


def _offscreen_canvas():
    from qgis.gui import QgsMapCanvas

    return QgsMapCanvas()


def _fixture_layer(services: Services) -> str:
    assert services.fixture_layer is not None
    return services.fixture_layer()

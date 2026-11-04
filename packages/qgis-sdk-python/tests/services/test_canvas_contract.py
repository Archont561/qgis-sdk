"""Contract: the map canvas through the injected service.

Every backend in ``conftest.BACKENDS`` runs these tests unchanged, so "the fake
and the real canvas answer the same contract" is a property of the run. Two
things about the assertions are deliberate.

*A zoom is asserted by what it covers, not by a byte-identical box.* A real
``QgsMapCanvas`` grows the extent it was handed to the aspect ratio of the
window it draws into, so the value it reports is at least the box requested.
The contract says what must hold on both: the landed extent covers the target,
is in the canvas's CRS, and is tight enough to be a zoom rather than a world map.

*Nothing here drives a drawing by itself.* A capture is finished by the backend's
``draw`` driver - real map clicks on the native canvas, ``FakeCanvas.draw`` on
the fake - because the surface reads a drawing and never makes one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import conftest
import pytest
from qgis_sdk.models import (
    QgisSdkLayerNotFoundError,
    QgisSdkThemeNotFoundError,
    QgisSdkUnsupportedCapabilityError,
)
from qgis_sdk.models.canvas import CanvasExtent, ZoomTarget

if TYPE_CHECKING:
    Services = conftest.Services
    Canvas = object


def _canvas(services: Services):
    assert services.canvas is not None, "this backend has no canvas service"
    return services.canvas


def _layer(services: Services) -> str:
    """The reference-points layer, opened if the backend opens it on demand."""
    assert services.fixture_layer is not None
    return services.fixture_layer()


def _draw(services: Services, shape: str) -> None:
    assert services.draw is not None, "this backend cannot draw on its canvas"
    services.draw(shape)


def _is_drawing(services: Services) -> bool:
    assert services.is_drawing is not None
    return services.is_drawing()


def _box(x_min: float, y_min: float, x_max: float, y_max: float) -> CanvasExtent:
    return CanvasExtent(
        x_min=x_min, y_min=y_min, x_max=x_max, y_max=y_max, crs=conftest.FIXTURE_CRS
    )


def _covers(landed: CanvasExtent, target: CanvasExtent) -> bool:
    # ``slack`` absorbs the last bit of a float round trip: a real canvas hands
    # the corner back as 52.14999999999999 when it was given 52.15.
    slack = 1e-9
    return (
        landed.x_min <= target.x_min + slack
        and landed.y_min <= target.y_min + slack
        and landed.x_max >= target.x_max - slack
        and landed.y_max >= target.y_max - slack
    )


def _twice(extent: CanvasExtent) -> bool:
    """Whether ``extent`` is at most twice the target in either direction."""
    return extent.width <= 2 * conftest.FIXTURE_EXTENT.width + 1e-9 and (
        extent.height <= 2 * conftest.FIXTURE_EXTENT.height + 1e-9
    )


# -- reading -----------------------------------------------------------------


def test_an_extent_is_four_ordered_numbers_and_a_crs(services: Services) -> None:
    extent = _canvas(services).extent()

    assert isinstance(extent, CanvasExtent)
    assert extent.x_min < extent.x_max and extent.y_min < extent.y_max
    assert extent.crs == conftest.FIXTURE_CRS
    assert extent.width > 0 and extent.height > 0


def test_the_centre_is_the_middle_of_the_extent(services: Services) -> None:
    canvas = _canvas(services)
    extent = canvas.extent()
    centre = canvas.center()

    assert canvas.crs() == conftest.FIXTURE_CRS
    assert centre.crs == conftest.FIXTURE_CRS
    assert centre.x == pytest.approx((extent.x_min + extent.x_max) / 2)
    assert centre.y == pytest.approx((extent.y_min + extent.y_max) / 2)
    assert extent.x_min <= centre.x <= extent.x_max


def test_the_scale_is_a_positive_denominator_that_follows_the_extent(
    services: Services,
) -> None:
    canvas = _canvas(services)
    before = canvas.scale()
    assert before > 0

    canvas.zoom_to(ZoomTarget.to_extent(_box(20.0, 51.0, 23.0, 53.0)))
    assert canvas.scale() > before


# -- zooming -----------------------------------------------------------------


def test_zooming_to_a_layer_lands_on_a_box_that_covers_it(services: Services) -> None:
    landed = _canvas(services).zoom_to(ZoomTarget.layer(_layer(services)))

    assert landed.crs == conftest.FIXTURE_CRS
    assert _covers(landed, conftest.FIXTURE_EXTENT)
    assert _twice(landed), landed
    # The reported extent is where the canvas actually is, not a copy of the
    # target: a page that draws after a zoom uses this answer.
    assert _canvas(services).extent() == landed


def test_zooming_to_an_extent_lands_on_a_box_that_covers_it(services: Services) -> None:
    target = _box(21.05, 52.05, 21.15, 52.15)
    landed = _canvas(services).zoom_to(ZoomTarget.to_extent(target))

    assert _covers(landed, target)
    assert landed.width < conftest.FIXTURE_EXTENT.width


def test_a_margin_widens_the_landed_extent_by_the_same_arithmetic(
    services: Services,
) -> None:
    """``margin`` is a fraction of the target's own span, on every side."""
    canvas = _canvas(services)
    target = _box(21.05, 52.05, 21.15, 52.15)

    plain = canvas.zoom_to(ZoomTarget.to_extent(target, margin=0.0))
    canvas.zoom_to(ZoomTarget.to_extent(target, margin=0.0))
    with_margin = canvas.zoom_to(ZoomTarget.to_extent(target, margin=0.25))

    assert with_margin.width == pytest.approx(plain.width * 1.5, rel=0.2)
    assert with_margin.height == pytest.approx(plain.height * 1.5, rel=0.2)


def test_zooming_to_a_layer_the_canvas_does_not_know_refuses_by_name(
    services: Services,
) -> None:
    with pytest.raises(QgisSdkLayerNotFoundError) as failure:
        _canvas(services).zoom_to(ZoomTarget.layer("no-such-layer-anywhere"))

    assert "no-such-layer-anywhere" in str(failure.value)


def test_zooming_to_nothing_selected_refuses_by_name(services: Services) -> None:
    with pytest.raises(QgisSdkUnsupportedCapabilityError) as failure:
        _canvas(services).zoom_to(ZoomTarget.selection(_layer(services)))

    assert "nothing is selected" in str(failure.value)


def test_a_refused_zoom_leaves_the_canvas_where_it_was(services: Services) -> None:
    canvas = _canvas(services)
    before = canvas.extent()

    with pytest.raises(QgisSdkLayerNotFoundError):
        canvas.zoom_to(ZoomTarget.layer("no-such-layer-anywhere"))

    assert canvas.extent() == before


# -- refreshing and themes ---------------------------------------------------


def test_a_refresh_keeps_the_extent(services: Services) -> None:
    canvas = _canvas(services)
    before = canvas.extent()

    canvas.refresh()

    assert canvas.extent() == before


def test_themes_list_what_the_project_holds_and_name_an_active_one(
    services: Services,
) -> None:
    assert services.declare_theme is not None
    services.declare_theme(conftest.DECLARED_THEME)
    themes = _canvas(services).themes()

    assert conftest.DECLARED_THEME in themes.names
    assert themes.active is None or themes.active in themes.names


def test_applying_a_theme_draws_the_canvas_with_it(services: Services) -> None:
    assert services.declare_theme is not None
    services.declare_theme(conftest.DECLARED_THEME)

    applied = _canvas(services).apply_theme(conftest.DECLARED_THEME)

    assert applied.active == conftest.DECLARED_THEME
    assert _canvas(services).themes().active == conftest.DECLARED_THEME
    # Theming redraws; it does not move the map.
    assert _canvas(services).extent().crs == conftest.FIXTURE_CRS


def test_an_unknown_theme_refuses_by_name_and_keeps_the_current_one(
    services: Services,
) -> None:
    assert services.declare_theme is not None
    services.declare_theme(conftest.DECLARED_THEME)
    canvas = _canvas(services)
    canvas.apply_theme(conftest.DECLARED_THEME)

    with pytest.raises(QgisSdkThemeNotFoundError) as failure:
        canvas.apply_theme("no-such-theme")

    assert "no-such-theme" in str(failure.value)
    assert canvas.themes().active == conftest.DECLARED_THEME


# -- capture -----------------------------------------------------------------


@pytest.mark.parametrize("shape", ["point", "line", "polygon"])
def test_a_capture_answers_with_the_geometry_the_user_drew(
    services: Services, shape: str
) -> None:
    drawn: list[object] = []
    canvas = _canvas(services)

    cancel = canvas.capture(shape, drawn.append)
    try:
        assert _is_drawing(services) is True
        _draw(services, shape)
    finally:
        cancel()

    assert len(drawn) == 1, drawn
    geometry = drawn[0]
    assert geometry.geometry_type == shape
    assert geometry.value
    assert geometry.crs == conftest.FIXTURE_CRS
    assert _is_drawing(services) is False


def test_a_cancelled_capture_never_answers(services: Services) -> None:
    drawn: list[object] = []
    canvas = _canvas(services)

    cancel = canvas.capture("point", drawn.append)
    cancel()
    cancel()  # idempotent: a closing view races the user all the time

    assert _is_drawing(services) is False
    assert drawn == []


def test_a_second_capture_replaces_the_first(services: Services) -> None:
    first: list[object] = []
    second: list[object] = []
    canvas = _canvas(services)

    canvas.capture("polygon", first.append)
    cancel = canvas.capture("point", second.append)
    try:
        _draw(services, "point")
    finally:
        cancel()

    assert [geometry.geometry_type for geometry in second] == ["point"]
    assert first == []


def test_an_unknown_capture_shape_refuses_by_name(services: Services) -> None:
    with pytest.raises(QgisSdkUnsupportedCapabilityError) as failure:
        _canvas(services).capture("hexagon", lambda geometry: None)

    assert "hexagon" in str(failure.value)


# -- the extent stream -------------------------------------------------------


def test_the_extent_stream_delivers_every_move_in_order(services: Services) -> None:
    canvas = _canvas(services)
    seen: list[CanvasExtent] = []

    cancel = canvas.watch_extent(seen.append)
    try:
        first = canvas.zoom_to(ZoomTarget.to_extent(_box(21.0, 52.0, 21.1, 52.1)))
        second = canvas.zoom_to(ZoomTarget.to_extent(_box(21.1, 52.1, 21.3, 52.3)))
    finally:
        cancel()

    # A real canvas may report one move more than once - the adapter forwards
    # what the host emits rather than filtering it - so the contract is the
    # order and where it ended, not the exact number of frames.
    assert len(seen) >= 2
    assert seen[0] == first
    assert seen[-1] == second
    assert first != second


def test_a_subscription_outlives_only_its_own_canceller(services: Services) -> None:
    canvas = _canvas(services)
    kept: list[CanvasExtent] = []
    dropped: list[CanvasExtent] = []

    keep = canvas.watch_extent(kept.append)
    cancel = canvas.watch_extent(dropped.append)
    try:
        cancel()
        cancel()  # idempotent
        canvas.zoom_to(ZoomTarget.to_extent(_box(21.0, 52.0, 21.1, 52.1)))
    finally:
        keep()

    assert kept and kept[-1].crs == conftest.FIXTURE_CRS
    assert dropped == []


def test_a_refresh_is_not_a_move_and_the_stream_ignores_it(services: Services) -> None:
    canvas = _canvas(services)
    seen: list[CanvasExtent] = []

    cancel = canvas.watch_extent(seen.append)
    try:
        canvas.refresh()
    finally:
        cancel()

    assert seen == []

"""The fakes record what they were given, so a pure test can assert on it.

These are fake-specific guarantees, not contract requirements: the native
adapters hold no in-memory record to inspect, and asserting one would be the
parity suite testing the fake rather than the contract.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from qgis_sdk.core import ResourceScope
from qgis_sdk.models import QgisSdkLayerNotFoundError, QgisSdkStyleIncompatibleError
from qgis_sdk.testing import (
    FakeLayers,
    FakeSettings,
    FakeStyles,
    RecordingNotifications,
)


def _opened_layer(layers: FakeLayers) -> str:
    source = Path("fixtures/reference/points.geojson")
    layers.register(
        source,
        name="points",
        geometry_type="point",
        field_names=("id", "value"),
    )
    return layers.open_vector(source).id


def test_recorded_notifications_are_readable_in_order() -> None:
    notifications = RecordingNotifications(ResourceScope())

    notifications.info("first")
    notifications.info("second")

    assert notifications.messages == ["first", "second"]


def test_applied_styles_are_readable_per_layer() -> None:
    layers = FakeLayers(ResourceScope())
    styles = FakeStyles(layers, ResourceScope())
    layer_id = _opened_layer(layers)

    styles.apply_style(layer_id, "reference/point-output")

    assert styles.applied(layer_id) == ("reference/point-output",)


def test_a_refused_style_leaves_nothing_applied() -> None:
    """No partial application: the refusal happens before anything is recorded."""
    layers = FakeLayers(ResourceScope())
    styles = FakeStyles(layers, ResourceScope())
    layer_id = _opened_layer(layers)

    with pytest.raises(QgisSdkStyleIncompatibleError):
        styles.apply_style(layer_id, "reference/line-output")

    assert styles.applied(layer_id) == ()


def test_style_application_to_an_unknown_layer_is_refused() -> None:
    styles = FakeStyles(FakeLayers(ResourceScope()), ResourceScope())

    with pytest.raises(QgisSdkLayerNotFoundError):
        styles.apply_style("no-such-layer", "reference/point-output")


def test_settings_accept_initial_values() -> None:
    settings = FakeSettings(ResourceScope(), {"reference/distance-unit": "metres"})

    assert settings.get("reference/distance-unit") == "metres"

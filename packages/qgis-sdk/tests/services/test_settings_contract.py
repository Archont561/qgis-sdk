"""Contract: settings are read and written through the injected service."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .conftest import Services


def test_stored_setting_round_trips(services: Services) -> None:
    services.settings.set("reference/distance-unit", "metres")

    assert services.settings.get("reference/distance-unit") == "metres"


def test_storing_a_setting_twice_keeps_the_latest_value(services: Services) -> None:
    services.settings.set("reference/distance-unit", "metres")
    services.settings.set("reference/distance-unit", "feet")

    assert services.settings.get("reference/distance-unit") == "feet"


def test_absent_setting_returns_the_declared_default(services: Services) -> None:
    assert services.settings.get("reference/absent", "fallback") == "fallback"


def test_absent_setting_without_a_default_is_unspecified(services: Services) -> None:
    assert services.settings.get("reference/absent") is None

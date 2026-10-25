"""Contract: the existing notification capability is implemented by a backend."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .conftest import Services


def test_informational_message_is_accepted(services: Services) -> None:
    services.notifications.info("Opened the reference dataset")

"""Module app."""

from __future__ import annotations

from ._init_state import (
    ALGORITHMS_PUMP_LOOP,
    JOB_PUMP_LOOP,
    LAYOUT_PUMP_LOOP,
    AppNotifications,
    AppWindowInterface,
    _package_directory,  # noqa: F401 - the app tests read it by name
    app_context,
)
from ._surface import (
    QtAppBackend,
    QtAppSurface,
)

__all__ = [
    "ALGORITHMS_PUMP_LOOP",
    "JOB_PUMP_LOOP",
    "LAYOUT_PUMP_LOOP",
    "AppNotifications",
    "AppWindowInterface",
    "QtAppBackend",
    "QtAppSurface",
    "app_context",
]

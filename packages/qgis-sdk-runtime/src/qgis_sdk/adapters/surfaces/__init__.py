"""Module surfaces."""

from __future__ import annotations

from ._bindings import (
    DesktopBindings,
)
from ._entries import (
    DOCK_VISIBLE_SETTING,
    MENU_HOOKS,
    OpenDialog,
    OpenDock,
    dock_visible_setting,
)
from ._host import (
    SurfaceHost,
)

__all__ = [
    "DOCK_VISIBLE_SETTING",
    "MENU_HOOKS",
    "DesktopBindings",
    "OpenDialog",
    "OpenDock",
    "SurfaceHost",
    "dock_visible_setting",
]

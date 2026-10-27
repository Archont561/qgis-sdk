"""The handshake's ``theme`` is the running palette (TASK-70, decision-16).

The shape a page receives is pinned without Qt: :func:`theme_from_colours`
keeps the known roles, drops what the palette lacks and decides ``dark`` from
the window colour. Reading a real ``QPalette`` is the ``qt`` layer's part,
``test_palette_native.py``.
"""

from __future__ import annotations

from qgis_sdk.adapters.palette import PALETTE_ROLES, theme_from_colours


def test_the_roles_are_the_ones_the_ui_package_maps_to_tokens() -> None:
    assert tuple(PALETTE_ROLES) == (
        "window",
        "windowText",
        "base",
        "text",
        "button",
        "buttonText",
        "highlight",
        "highlightedText",
        "mid",
        "placeholderText",
        "link",
    )


def test_the_theme_keeps_known_roles_and_decides_dark_from_the_window() -> None:
    light = theme_from_colours(
        {"window": "#efefef", "text": "#000000", "shadow": "#000000", "mid": ""},
        window_lightness=0.94,
    )
    assert light == {"palette": {"window": "#efefef", "text": "#000000"}, "dark": False}

    dark = theme_from_colours({"window": "#323232"}, window_lightness=0.2)
    assert dark == {"palette": {"window": "#323232"}, "dark": True}

"""The running palette, as the handshake's ``theme`` (decision-16).

A page inside QGIS should look like QGIS. The WebEngine adapter reads
``QApplication.palette()`` through :func:`palette_theme` and hands the result to
the dispatcher, which puts it in every handshake reply; ``qgis-sdk-ui`` turns
the roles into its ``--qgis-sdk-*`` custom properties. Outside QGIS the reply
carries no ``theme`` and the page keeps the documented defaults.

Qt is imported inside the function, so the module loads without QGIS and the
pure tests import it freely.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

__all__ = ["PALETTE_ROLES", "palette_theme", "theme_from_colours"]

#: The ``QPalette.ColorRole`` names the theme carries, by the key a page reads.
PALETTE_ROLES: Final[Mapping[str, str]] = {
    "window": "Window",
    "windowText": "WindowText",
    "base": "Base",
    "text": "Text",
    "button": "Button",
    "buttonText": "ButtonText",
    "highlight": "Highlight",
    "highlightedText": "HighlightedText",
    "mid": "Mid",
    "placeholderText": "PlaceholderText",
    "link": "Link",
}

_DARK_LIGHTNESS: Final = 0.5


def theme_from_colours(
    colours: Mapping[str, str], *, window_lightness: float
) -> dict[str, Any]:
    """The theme payload for colours already read: ``palette`` plus ``dark``.

    ``colours`` maps the keys of :data:`PALETTE_ROLES` to ``#rrggbb`` or
    ``#rrggbbaa`` strings; ``window_lightness`` is the HSL lightness of the
    window colour, which decides ``dark``. Kept apart from Qt so the shape the
    page receives is pinned without an application.
    """
    palette = {
        key: colours[key]
        for key in PALETTE_ROLES
        if isinstance(colours.get(key), str) and colours[key]
    }
    return {"palette": palette, "dark": window_lightness < _DARK_LIGHTNESS}


def palette_theme(palette: Any | None = None) -> dict[str, Any] | None:
    """Read ``palette`` (the application's by default) into a theme payload.

    Returns ``None`` when no application is running, so a dispatcher built
    outside a GUI process advertises no theme rather than a made-up one.
    """
    from qgis.PyQt.QtGui import QColor, QPalette
    from qgis.PyQt.QtWidgets import QApplication

    if palette is None:
        if QApplication.instance() is None:
            return None
        palette = QApplication.palette()
    colours: dict[str, str] = {}
    for key, role in PALETTE_ROLES.items():
        colour: QColor = palette.color(getattr(QPalette.ColorRole, role))
        if not colour.isValid():
            continue
        name_format = (
            QColor.NameFormat.HexRgb
            if colour.alpha() == 255
            else QColor.NameFormat.HexArgb
        )
        name = colour.name(name_format)
        if name_format == QColor.NameFormat.HexArgb:
            # Qt writes #aarrggbb; CSS reads #rrggbbaa.
            name = f"#{name[3:]}{name[1:3]}"
        colours[key] = name
    window = palette.color(QPalette.ColorRole.Window)
    return theme_from_colours(colours, window_lightness=window.lightnessF())

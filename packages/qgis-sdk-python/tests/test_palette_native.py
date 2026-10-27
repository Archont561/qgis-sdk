"""``palette_theme`` reads a real ``QPalette`` (TASK-70, decision-16).

The colours arrive as CSS hex - ``#rrggbb``, or ``#rrggbbaa`` when a role is
translucent - and ``dark`` follows the window colour. The imports are guarded
like ``test_jobs_native.py`` so a host without Qt reports what it lacks instead
of failing collection.
"""

from __future__ import annotations

import pytest

# The qt layer: a palette needs the GUI bindings, no QGIS. The headless
# environment and the bindings path are prepared by tests/conftest.py. The
# module is named to collect after ``test_desktop_host.py``, which pins what a
# host does in a process that has no application yet.
pytestmark = pytest.mark.qt

try:
    from PyQt6.QtGui import QColor, QPalette
    from qgis_sdk.adapters.palette import PALETTE_ROLES, palette_theme
except ImportError as error:  # pragma: no cover - depends on the host
    pytest.skip(f"a palette needs Qt: {error}", allow_module_level=True)


def _palette(window: str, placeholder_alpha: int = 255) -> QPalette:
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(window))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#dddddd"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#3daee9"))
    placeholder = QColor("#808080")
    placeholder.setAlpha(placeholder_alpha)
    palette.setColor(QPalette.ColorRole.PlaceholderText, placeholder)
    return palette


def test_a_dark_palette_reads_as_css_hex_with_the_dark_flag(qt_app) -> None:
    theme = palette_theme(_palette("#323232", placeholder_alpha=128))

    assert theme is not None
    assert theme["dark"] is True
    assert theme["palette"]["window"] == "#323232"
    assert theme["palette"]["windowText"] == "#dddddd"
    assert theme["palette"]["highlight"] == "#3daee9"
    assert theme["palette"]["placeholderText"] == "#80808080"
    assert set(theme["palette"]) == set(PALETTE_ROLES)


def test_a_light_palette_is_not_dark(qt_app) -> None:
    theme = palette_theme(_palette("#efefef"))

    assert theme is not None
    assert theme["dark"] is False
    assert theme["palette"]["placeholderText"] == "#808080"


def test_the_application_palette_is_the_default(qt_app) -> None:
    theme = palette_theme()

    assert theme is not None
    assert set(theme["palette"]) == set(PALETTE_ROLES)
    assert theme["palette"]["window"] == qt_app.palette().color(
        QPalette.ColorRole.Window
    ).name(QColor.NameFormat.HexRgb)

"""The one native picker this plugin asks the Desktop for.

Qt is imported inside the function, so `qgis-sdk check` and the pure tests
import this package without QGIS; the action calls it with the Desktop's
``iface``. This is where file authority comes from (decision-20): a picker
the user answered on the host, never a path typed into the page.
"""

from __future__ import annotations

from typing import Any


def ask_for_directory(iface: Any, title: str) -> str:
    """Ask the user for a directory with the native dialog; empty when cancelled."""
    from qgis.PyQt.QtWidgets import QFileDialog

    return QFileDialog.getExistingDirectory(iface.mainWindow(), title)

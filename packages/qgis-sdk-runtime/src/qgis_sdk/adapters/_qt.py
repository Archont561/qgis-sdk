"""Qt, between the two bindings a supported QGIS may ship.

A QGIS build is either Qt5 with PyQt5 (QGIS 3.44 LTS, which is what Debian and
Ubuntu install today) or Qt6 with PyQt6 (QGIS 4.x). ``qgis.PyQt`` always names
the right binding for the running QGIS, so the adapters import through it rather
than naming ``PyQt6`` - but the *APIs* still differ in two places that matter
here, and this module absorbs both once:

``qt_enum``
    Qt 6 groups its enums (``Qt.DockWidgetArea.LeftDockWidgetArea``); Qt 5 exposes
    the same values flat on ``Qt`` (``Qt.LeftDockWidgetArea``).
``action_class``
    ``QAction`` lives in ``QtWidgets`` on Qt 5 and in ``QtGui`` on Qt 6 (QGIS'
    ``qgis.PyQt`` shim re-exports it from ``QtWidgets`` on 4.x, but not every
    build does).

Nothing here imports Qt at module level: importing this module is free, and each
helper is handed the classes the caller already has.
"""

from __future__ import annotations

from typing import Any

__all__ = ["action_class", "qt_enum"]


def qt_enum(owner: Any, group: str, name: str) -> Any:
    """Resolve one Qt enum value on either binding.

    ``qt_enum(Qt, "DockWidgetArea", "LeftDockWidgetArea")`` is
    ``Qt.DockWidgetArea.LeftDockWidgetArea`` on Qt 6 and ``Qt.LeftDockWidgetArea``
    on Qt 5. A value neither binding carries raises ``AttributeError`` naming
    both spellings, because a typo that silently returned ``None`` would move a
    dock to the wrong place instead of failing.
    """
    scoped = getattr(owner, group, None)
    if scoped is not None and hasattr(scoped, name):
        return getattr(scoped, name)
    if hasattr(owner, name):
        return getattr(owner, name)
    raise AttributeError(owner, f"{group}.{name} is on neither Qt 5 nor Qt 6")


def action_class() -> Any:
    """The ``QAction`` class of the running binding.

    Qt 6 moved ``QAction`` from ``QtWidgets`` to ``QtGui``; Qt 5 only has the
    ``QtWidgets`` one. Both are tried in that order, so a surface that places a
    toolbar button works on either QGIS.
    """
    from qgis.PyQt import QtGui, QtWidgets

    for module in (QtWidgets, QtGui):
        action = getattr(module, "QAction", None)
        if action is not None:
            return action
    raise ImportError("this Qt binding has no QAction")

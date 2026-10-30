"""One adapter surface, two Qt bindings: the compat helpers, without Qt.

QGIS 3.44 LTS ships Qt 5 and PyQt5, QGIS 4.x ships Qt 6 and PyQt6, and
``qgis.PyQt`` names whichever one the running QGIS has. Two APIs still differ -
grouped enums and where ``QAction`` lives - so the adapters ask these helpers
instead of spelling either binding. Each helper is handed the classes, which is
what makes it testable here: no Qt is imported.
"""

from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace

import pytest
from qgis_sdk.adapters._qt import action_class, qt_enum


class Qt6(SimpleNamespace):
    """Qt 6: ``Qt.DockWidgetArea.LeftDockWidgetArea``."""

    DockWidgetArea = SimpleNamespace(
        LeftDockWidgetArea="left6",
        RightDockWidgetArea="right6",
        TopDockWidgetArea="top6",
        BottomDockWidgetArea="bottom6",
    )
    ItemFlag = SimpleNamespace(ItemIsEditable=16, ItemIsSelectable=1)
    ConnectionType = SimpleNamespace(QueuedConnection=1)


class Qt5(SimpleNamespace):
    """Qt 5: the same values, flat on ``Qt``."""

    LeftDockWidgetArea = "left5"
    RightDockWidgetArea = "right5"
    TopDockWidgetArea = "top5"
    BottomDockWidgetArea = "bottom5"
    ItemIsEditable = 16
    ItemIsSelectable = 1
    QueuedConnection = 1


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("LeftDockWidgetArea", "left6"),
        ("RightDockWidgetArea", "right6"),
        ("TopDockWidgetArea", "top6"),
        ("BottomDockWidgetArea", "bottom6"),
    ],
)
def test_a_qt6_group_is_read_through_its_group(name: str, expected: str) -> None:
    assert qt_enum(Qt6, "DockWidgetArea", name) == expected


def test_a_qt5_flat_value_is_read_off_the_owner() -> None:
    assert qt_enum(Qt5, "DockWidgetArea", "LeftDockWidgetArea") == "left5"
    assert qt_enum(Qt5, "ItemFlag", "ItemIsEditable") == 16
    assert qt_enum(Qt5, "ConnectionType", "QueuedConnection") == 1


def test_a_value_neither_binding_carries_names_both_spellings() -> None:
    with pytest.raises(AttributeError, match=r"DockWidgetArea.NoSuchArea"):
        qt_enum(Qt5, "DockWidgetArea", "NoSuchArea")


def _fake_binding(monkeypatch: pytest.MonkeyPatch, **modules: ModuleType) -> None:
    """Install fake ``qgis.PyQt.*`` modules for ``action_class`` to find."""
    qgis = ModuleType("qgis")
    pyqt = ModuleType("qgis.PyQt")
    pyqt.__path__ = []  # a package, so `from qgis.PyQt import QtGui` resolves
    for name, module in modules.items():
        setattr(pyqt, name, module)
        monkeypatch.setitem(sys.modules, f"qgis.PyQt.{name}", module)
    monkeypatch.setitem(sys.modules, "qgis", qgis)
    monkeypatch.setitem(sys.modules, "qgis.PyQt", pyqt)


def test_a_qt6_action_comes_from_qtgui(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_binding(
        monkeypatch,
        QtGui=SimpleNamespace(QAction="Qt6QAction"),
        QtWidgets=SimpleNamespace(),
    )

    assert action_class() == "Qt6QAction"


def test_a_qt5_action_comes_from_qtwidgets(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_binding(
        monkeypatch,
        QtGui=SimpleNamespace(),
        QtWidgets=SimpleNamespace(QAction="Qt5QAction"),
    )

    assert action_class() == "Qt5QAction"


def test_a_binding_without_an_action_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_binding(monkeypatch, QtGui=SimpleNamespace(), QtWidgets=SimpleNamespace())

    with pytest.raises(ImportError, match="no QAction"):
        action_class()

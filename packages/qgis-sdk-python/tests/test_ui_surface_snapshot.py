"""The surface snapshot of decision-51, read through Qt-shaped stand-ins."""

from __future__ import annotations

import json

import pytest
from qgis_sdk.models import QgisSdkUiError
from qgis_sdk.ui import canonical_json, surface_snapshot


class _Point:
    def __init__(self, x: int, y: int) -> None:
        self._x = x
        self._y = y

    def x(self) -> int:
        return self._x

    def y(self) -> int:
        return self._y


class _Widget:
    """The slice of the QWidget protocol a snapshot reads."""

    def __init__(self, name: str = "", *, x=0, y=0, width=10, height=10) -> None:
        self._name = name
        self._x, self._y = x, y
        self._width, self._height = width, height
        self._children: list[_Widget] = []
        self._parent: _Widget | None = None
        self._enabled = True
        self._visible = True
        self._focus = False

    def objectName(self) -> str:
        return self._name

    def children(self) -> list[_Widget]:
        return list(self._children)

    def isWidgetType(self) -> bool:
        return True

    def parentWidget(self):
        return self._parent

    def pos(self) -> _Point:
        return _Point(self._x, self._y)

    def width(self) -> int:
        return self._width

    def height(self) -> int:
        return self._height

    def isEnabled(self) -> bool:
        return self._enabled

    def isVisible(self) -> bool:
        return self._visible

    def hasFocus(self) -> bool:
        return self._focus

    def add(self, child):
        child._parent = self
        self._children.append(child)
        return child


class QWidget(_Widget):
    pass


class QDialogButtonBox(_Widget):
    pass


class QFrame(_Widget):
    pass


class QLabel(_Widget):
    def __init__(self, name: str = "", text: str = "", buddy=None, **geometry) -> None:
        super().__init__(name, **geometry)
        self._text = text
        self._buddy = buddy

    def text(self) -> str:
        return self._text

    def buddy(self):
        return self._buddy


class QPushButton(_Widget):
    def __init__(self, name: str = "", text: str = "OK", **geometry) -> None:
        super().__init__(name, **geometry)
        self._text = text

    def text(self) -> str:
        return self._text


class QLineEdit(_Widget):
    def __init__(self, name: str = "", text: str = "", **geometry) -> None:
        super().__init__(name, **geometry)
        self._text = text

    def text(self) -> str:
        return self._text


class QgsDoubleSpinBox(_Widget):
    def __init__(self, name: str = "", value: float = 0.0, **geometry) -> None:
        super().__init__(name, **geometry)
        self._value = value

    def value(self) -> float:
        return self._value


def _form_surface() -> QWidget:
    surface = QWidget("surface", width=320, height=200)
    group = surface.add(QFrame("", x=10, y=20))
    spin = group.add(QgsDoubleSpinBox("form/distance", value=12.5, x=5, y=7))
    surface.add(QLabel("", "Distance", buddy=spin))
    surface.add(QPushButton("buttons/ok", "Run"))
    return surface


def test_a_form_surface_lists_roles_values_labels_and_state():
    surface = _form_surface()
    snapshot = surface_snapshot(
        surface,
        surface_id="buffer",
        kind="dialog",
        title="Buffer",
        declared=("distance",),
        screenshot="sha256:abcd",
        scale=2.0,
    )

    assert snapshot["surface"] == "buffer"
    assert snapshot["kind"] == "dialog"
    assert snapshot["title"] == "Buffer"
    assert snapshot["size"] == {"width": 320, "height": 200}
    assert snapshot["scale"] == 2.0
    assert snapshot["screenshot"] == "sha256:abcd"
    assert snapshot["findings"] == []

    group, label, button = snapshot["nodes"]
    assert group["role"] == "container"
    assert group["id"].startswith("#"), "an unnamed container gets a positional id"

    (spin,) = group["children"]
    assert spin["id"] == "form/distance"
    assert spin["role"] == "spinbox"
    assert spin["value"] == 12.5
    assert spin["label"] == "Distance"
    assert spin["declared"] == {"field": "distance"}
    assert spin["state"] == {"enabled": True, "visible": True, "focus": False}
    assert spin["geometry"] == {"x": 15, "y": 27, "width": 10, "height": 10}

    assert label["role"] == "label"
    assert label["value"] == "Distance"
    assert button["id"] == "buttons/ok"
    assert button["role"] == "button"
    assert button["declared"] == {"button": "ok"}


def test_an_unnamed_actionable_widget_is_a_ui001_finding():
    surface = QWidget("surface")
    surface.add(QFrame("container"))
    surface.add(QPushButton(""))
    snapshot = surface_snapshot(surface, surface_id="custom", kind="dock")

    findings = snapshot["findings"]
    assert [finding["rule"] for finding in findings] == ["UI001"]
    assert findings[0]["node"] == "#1"
    assert "objectName" in findings[0]["message"]
    assert snapshot["nodes"][0]["id"] == "container", "a named container keeps its id"


def test_a_named_state_is_reported_per_node():
    surface = QWidget("surface")
    field = surface.add(QLineEdit("form/name", "Ada"))
    field._enabled = False
    field._visible = False
    field._focus = True
    snapshot = surface_snapshot(surface, surface_id="s", kind="dialog")
    assert snapshot["nodes"][0]["state"] == {
        "enabled": False,
        "visible": False,
        "focus": True,
    }
    assert snapshot["nodes"][0]["value"] == "Ada"


def test_two_captures_are_byte_identical():
    first = canonical_json(
        surface_snapshot(_form_surface(), surface_id="b", kind="dialog")
    )
    second = canonical_json(
        surface_snapshot(_form_surface(), surface_id="b", kind="dialog")
    )
    assert first == second
    assert first.endswith("\n") and not first.endswith("\n\n")


def test_canonical_json_sorts_keys_and_separates_nothing():
    rendered = canonical_json({"b": 1, "a": {"d": 2, "c": 3}})
    assert rendered == '{"a":{"c":3,"d":2},"b":1}\n'
    assert json.loads(rendered) == {"a": {"c": 3, "d": 2}, "b": 1}


def test_surface_snapshot_refuses_what_is_not_a_surface():
    with pytest.raises(QgisSdkUiError, match="opened Qt surface"):
        surface_snapshot(object(), surface_id="x", kind="dialog")

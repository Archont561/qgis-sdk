"""Qt Designer ``.ui`` files: the names they declare, and a tree without Qt.

A surface may point at a Designer file (``ui = "buffer.ui"``) instead of
writing ``build()``. The host loads it with ``uic``; this module reads the
same file as XML so that ``check`` can tell an ``@on`` name is missing
(UI002) and :func:`qgis_sdk.testing.build_surface` can hand a pure test a
:class:`FakeUiTree` - the declared widgets by ``objectName`` with the
signals their classes have, each a :class:`FakeSignal` a test ``emit``s.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from qgis_sdk.models import QgisSdkUiError

__all__ = [
    "FakeSignal",
    "FakeUiTree",
    "FakeWidget",
    "UiNode",
    "fake_ui_tree",
    "read_ui",
    "resolve_ui_path",
    "ui_names",
]


@dataclass(frozen=True, slots=True)
class UiNode:
    """One ``<widget>`` of a ``.ui`` file: its class, its name, its children."""

    cls: str
    name: str
    children: tuple[UiNode, ...] = ()

    def walk(self) -> Iterator[UiNode]:
        yield self
        for child in self.children:
            yield from child.walk()


def read_ui(path: Path) -> UiNode:
    """Parse ``path`` into its widget tree; a file without a root widget is refused."""
    try:
        tree = ElementTree.parse(path)
    except (OSError, ElementTree.ParseError) as error:
        raise QgisSdkUiError(f"cannot read {path}: {error}") from error
    root = tree.getroot()
    widget = root.find("widget")
    if widget is None:
        raise QgisSdkUiError(f"{path} declares no root widget")
    return _node(widget)


def _node(element: ElementTree.Element) -> UiNode:
    return UiNode(
        element.get("class", ""),
        element.get("name", ""),
        tuple(_node(child) for child in _direct_widgets(element)),
    )


def _direct_widgets(element: ElementTree.Element) -> list[ElementTree.Element]:
    """The widgets directly below ``element``, looking through layouts and items."""
    found: list[ElementTree.Element] = []
    for child in element:
        if child.tag == "widget":
            found.append(child)
        elif child.tag in ("layout", "item"):
            found.extend(_direct_widgets(child))
    return found


def ui_names(path: Path) -> tuple[str, ...]:
    """Every ``objectName`` the file declares, document order, root included."""
    return tuple(node.name for node in read_ui(path).walk() if node.name)


def resolve_ui_path(cls: type, ui: str) -> Path:
    """``ui`` relative to the module that defines ``cls``; absolute paths stay."""
    candidate = Path(ui)
    if candidate.is_absolute():
        return candidate
    module = inspect.getmodule(cls)
    module_file = getattr(module, "__file__", None)
    if module_file is None:
        raise QgisSdkUiError(
            f"{cls.__name__}.ui = {ui!r}: cannot resolve a relative path, "
            "the class's module has no file"
        )
    return Path(module_file).parent / candidate


# -- the fake tree ----------------------------------------------------------------------

#: The signals the fake widgets of these classes carry; a class not listed
#: answers to any signal name, so a test can still drive it.
WIDGET_SIGNALS: dict[str, tuple[str, ...]] = {
    "QWidget": (),
    "QDialog": ("accepted", "rejected", "finished"),
    "QLineEdit": ("textChanged", "textEdited", "editingFinished", "returnPressed"),
    "QPlainTextEdit": ("textChanged",),
    "QTextEdit": ("textChanged",),
    "QSpinBox": ("valueChanged", "editingFinished"),
    "QDoubleSpinBox": ("valueChanged", "editingFinished"),
    "QgsSpinBox": ("valueChanged", "editingFinished"),
    "QgsDoubleSpinBox": ("valueChanged", "editingFinished"),
    "QCheckBox": ("toggled", "clicked", "stateChanged"),
    "QRadioButton": ("toggled", "clicked"),
    "QPushButton": ("clicked", "pressed", "released", "toggled"),
    "QToolButton": ("clicked", "pressed", "released", "toggled"),
    "QComboBox": ("currentIndexChanged", "currentTextChanged", "activated"),
    "QSlider": ("valueChanged", "sliderReleased"),
    "QDialogButtonBox": ("accepted", "rejected", "clicked"),
    "QTabWidget": ("currentChanged",),
    "QListWidget": ("itemSelectionChanged", "currentRowChanged", "itemClicked"),
    "QTableWidget": ("itemSelectionChanged", "cellClicked", "currentCellChanged"),
    "QDateEdit": ("dateChanged",),
    "QDateTimeEdit": ("dateTimeChanged",),
    "QgsMapLayerComboBox": ("layerChanged",),
    "QgsFieldComboBox": ("fieldChanged",),
    "QgsFileWidget": ("fileChanged",),
    "QgsProjectionSelectionWidget": ("crsChanged",),
    "QgsColorButton": ("colorChanged",),
    "QgsCollapsibleGroupBox": ("collapsedStateChanged",),
    "QGroupBox": ("toggled", "clicked"),
}


class FakeSignal:
    """A signal of a fake widget: ``connect``, ``disconnect``, ``emit``."""

    __slots__ = ("_slots", "name")

    def __init__(self, name: str) -> None:
        self.name = name
        self._slots: list[Callable[..., Any]] = []

    @property
    def receivers(self) -> int:
        return len(self._slots)

    def connect(self, slot: Callable[..., Any]) -> None:
        self._slots.append(slot)

    def disconnect(self, slot: Callable[..., Any] | None = None) -> None:
        if slot is None:
            self._slots.clear()
            return
        if slot not in self._slots:
            raise TypeError(f"{self.name}: slot is not connected")
        self._slots.remove(slot)

    def emit(self, *arguments: Any) -> None:
        for slot in tuple(self._slots):
            slot(*arguments)


class FakeWidget:
    """One declared widget: ``objectName()``, ``children()``, its signals."""

    def __init__(self, node: UiNode, parent: FakeWidget | None = None) -> None:
        self._node = node
        self._parent = parent
        self._signals: dict[str, FakeSignal] = {}
        self._children = tuple(FakeWidget(child, self) for child in node.children)

    @property
    def widget_class(self) -> str:
        return self._node.cls

    def objectName(self) -> str:
        return self._node.name

    def children(self) -> tuple[FakeWidget, ...]:
        return self._children

    def parent(self) -> FakeWidget | None:
        return self._parent

    def isWidgetType(self) -> bool:
        return True

    def findChild(self, _type: Any, name: str) -> FakeWidget | None:
        for child in self._children:
            if child.objectName() == name:
                return child
            found = child.findChild(_type, name)
            if found is not None:
                return found
        return None

    def signals(self) -> tuple[str, ...]:
        """The signal names this widget's class is known to have."""
        return WIDGET_SIGNALS.get(self._node.cls, ())

    def __getattr__(self, name: str) -> FakeSignal:
        if name.startswith("_"):
            raise AttributeError(name)
        known = WIDGET_SIGNALS.get(self._node.cls)
        if known is not None and name not in known:
            raise AttributeError(
                f"{self._node.cls} {self._node.name!r} has no signal {name!r}"
            )
        signal = self._signals.get(name)
        if signal is None:
            signal = self._signals[name] = FakeSignal(name)
        return signal

    def __repr__(self) -> str:
        return f"FakeWidget({self._node.cls} {self._node.name!r})"


@dataclass(slots=True)
class FakeUiTree:
    """What ``build_surface`` returns for a ``ui =`` surface under the fake."""

    path: Path
    root: FakeWidget
    _index: dict[str, FakeWidget] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for widget in self.walk():
            self._index.setdefault(widget.objectName(), widget)

    def walk(self) -> Iterator[FakeWidget]:
        pending = [self.root]
        while pending:
            widget = pending.pop(0)
            yield widget
            pending.extend(widget.children())

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(
            widget.objectName() for widget in self.walk() if widget.objectName()
        )

    def find(self, name: str) -> FakeWidget:
        """The widget called ``name``, or a refusal naming the ones there are."""
        widget = self._index.get(name)
        if widget is None:
            raise QgisSdkUiError(
                f"{self.path.name} declares no widget {name!r}; it has: "
                + ", ".join(self.names)
            )
        return widget

    def objectName(self) -> str:
        return self.root.objectName()

    def children(self) -> tuple[FakeWidget, ...]:
        return self.root.children()

    def findChild(self, _type: Any, name: str) -> FakeWidget | None:
        return self.root.findChild(_type, name)


def fake_ui_tree(path: Path) -> FakeUiTree:
    """Read ``path`` into a :class:`FakeUiTree`."""
    return FakeUiTree(path, FakeWidget(read_ui(path)))

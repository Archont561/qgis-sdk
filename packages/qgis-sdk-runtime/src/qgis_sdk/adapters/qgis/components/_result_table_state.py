"""The Qt half of the catalogue: one widget per :mod:`qgis_sdk.ui.components` class.

``mount(component, parent, on_change)`` builds the QGIS widget that renders
a component's state - ``QgsMapLayerComboBox`` for a ``LayerPicker``,
``QgsFileWidget`` for a ``FileInput``, ``QgsColorButton`` for a ``Colour``
- and returns a rendering the component drives: ``apply`` writes a value the
component already validated, the widget's own signal reports the user's
edits back through ``on_change`` as a model value (an id, a path, a number),
and ``dispose`` disconnects. The component owns validation, listeners and
the fake; nothing here is reachable from a pure test, and nothing here is
imported until a component is mounted.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from qgis.core import (
    QgsMapLayerProxyModel,
    QgsProject,
)
from qgis.gui import (
    QgsColorButton,
    QgsMapLayerComboBox,
)
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from qgis_sdk.adapters._qt import qt_enum
from qgis_sdk.models import QgisSdkFormError, QgisSdkUiError
from qgis_sdk.ui.components import (
    Choice,
    Colour,
    Component,
    Distance,
    LayerPicker,
    Number,
    Option,
    Text,
    Toggle,
)

from ._widgets import BUILDERS


class CcState1:
    """A mutable record shared by the phases of one long function."""

    def __init__(_cc_self, **values):
        _cc_self.__dict__.update(values)


class CcReturn1:
    """An early return travelling out of a phase."""

    def __init__(_cc_self, value):
        _cc_self.value = value


def cc_result_table_p1(_s1):
    _s1.table = QTableWidget(0, len(_s1.component.columns), _s1.parent)
    _s1.table.setHorizontalHeaderLabels(list(_s1.component.headings))
    _s1.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    _s1.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    _s1.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    _s1.table.verticalHeader().setVisible(False)


def cc_result_table_p2(_s1):

    def apply(value: object) -> None:
        rows, selected = value  # type: ignore[misc]
        _s1.table.blockSignals(True)
        try:
            _s1.table.setRowCount(len(rows))
            for row_index, cells in enumerate(rows):
                _s1.row_index = row_index
                _s1.cells = cells
                for column_index, text in enumerate(cells):
                    _s1.column_index = column_index
                    _s1.text = text
                    item = QTableWidgetItem(text)
                    item.setFlags(
                        item.flags() & ~qt_enum(Qt, "ItemFlag", "ItemIsEditable")
                    )
                    _s1.table.setItem(row_index, column_index, item)
            _s1.table.clearSelection()
            if selected is not None:
                _s1.table.selectRow(selected)
        finally:
            _s1.table.blockSignals(False)

    _s1.apply = apply


def cc_result_table_p3(_s1):

    def read() -> None:
        rows = {index.row() for index in _s1.table.selectionModel().selectedRows()}
        _s1.on_change(min(rows) if rows else None)

    _s1.read = read

    _s1.rendering = Rendering(_s1.table, _s1.apply)
    connect(_s1.rendering, _s1.table.itemSelectionChanged, _s1.read)
    return CcReturn1(_s1.rendering)


def CcPhases1():
    return (
        _cc_job_progress_p1,
        _cc_job_progress_p2,
        _cc_job_progress_p3,
        _cc_job_progress_p4,
    )


class CcState:
    """A mutable record shared by the phases of one long function."""

    def __init__(_cc_self, **values):
        _cc_self.__dict__.update(values)


class CcReturn:
    """An early return travelling out of a phase."""

    def __init__(_cc_self, value):
        _cc_self.value = value


def _cc_job_progress_p1(_s):
    _s.widget = QWidget(_s.parent)
    _s.layout = QHBoxLayout(_s.widget)
    _s.layout.setContentsMargins(0, 0, 0, 0)
    _s.bar = QProgressBar(_s.widget)
    _s.bar.setObjectName(f"{_s.component.object_name}/bar")
    _s.bar.setRange(0, 100)
    _s.bar.setTextVisible(True)
    _s.message = QLabel(_s.widget)
    _s.message.setObjectName(f"{_s.component.object_name}/message")
    _s.layout.addWidget(_s.bar, 1)
    _s.layout.addWidget(_s.message)
    _s.cancel: QPushButton | None = None


def _cc_job_progress_p2(_s):
    if _s.component.cancellable:
        _s.cancel = QPushButton("Cancel", _s.widget)
        _s.cancel.setObjectName(f"{_s.component.object_name}/cancel")
        _s.layout.addWidget(_s.cancel)


def _cc_job_progress_p3(_s):

    def apply(value: object) -> None:
        status, fraction, text = value  # type: ignore[misc]
        if fraction is None:
            if status in ("queued", "running"):
                _s.bar.setRange(0, 0)  # busy
            else:
                _s.bar.setRange(0, 100)
                _s.bar.setValue(0)
        else:
            _s.bar.setRange(0, 100)
            _s.bar.setValue(round(float(fraction) * 100))
        if text:
            _s.message.setText(text)
        elif status == "idle":
            _s.message.setText("")
        else:
            _s.message.setText(str(status))
        if _s.cancel is not None:
            _s.cancel.setEnabled(status in ("queued", "running"))

    _s.apply = apply


def _cc_job_progress_p4(_s):

    _s.rendering = Rendering(_s.widget, _s.apply)
    if _s.cancel is not None:
        connect(
            _s.rendering,
            _s.cancel.clicked,
            lambda _checked=False: _s.on_change("cancel"),
        )
    return CcReturn(_s.rendering)


_INT_MIN, _INT_MAX = -(2**31), 2**31 - 1
_REAL_MAX = 1e15
_LAYER_FILTERS = {
    "vector": QgsMapLayerProxyModel.Filter.VectorLayer,
    "raster": QgsMapLayerProxyModel.Filter.RasterLayer,
    "mesh": QgsMapLayerProxyModel.Filter.MeshLayer,
    "point_cloud": QgsMapLayerProxyModel.Filter.PointCloudLayer,
    "vector_tile": QgsMapLayerProxyModel.Filter.VectorTileLayer,
    "annotation": QgsMapLayerProxyModel.Filter.AnnotationLayer,
    "tiled_scene": QgsMapLayerProxyModel.Filter.TiledSceneLayer,
    "any": QgsMapLayerProxyModel.Filter.All,
}
OnChange = Callable[[object], None]


@dataclass
class Rendering:
    """A mounted component: the widget plus how to write to and read from it."""

    widget: QWidget
    _apply: Callable[[object], None]
    _options: Callable[[], tuple[Option, ...] | None] = lambda: None
    _connections: list[tuple[Any, Callable[..., None]]] = field(default_factory=list)

    def apply(self, value: object) -> None:
        self._apply(value)

    def options(self) -> tuple[Option, ...] | None:
        return self._options()

    def dispose(self) -> None:
        for signal, slot in self._connections:
            try:
                signal.disconnect(slot)
            except (TypeError, RuntimeError):  # already gone with the widget
                pass
        self._connections.clear()


def mount(
    component: Component, parent: QWidget | None, *, on_change: OnChange
) -> Rendering:
    """Build the widget for ``component`` and connect it both ways."""
    for cls, builder in BUILDERS:
        if isinstance(component, cls):
            return builder(component, parent, on_change)
    raise QgisSdkUiError(f"no native widget for {type(component).__name__}")


def load_ui(path: Path, parent: QWidget | None = None) -> QWidget:
    """Load a Designer file into a fresh widget (``uic.loadUi``)."""
    from qgis.PyQt import uic

    widget = uic.loadUi(str(path))
    if parent is not None:
        widget.setParent(parent)
    return widget


def connect(rendering: Rendering, signal: Any, slot: Callable[..., None]) -> None:
    signal.connect(slot)
    rendering._connections.append((signal, slot))


def text(component: Text, parent: QWidget | None, on_change: OnChange) -> Rendering:
    widget = QLineEdit(parent)
    rendering = Rendering(widget, lambda value: widget.setText(str(value)))
    connect(rendering, widget.textChanged, on_change)
    return rendering


def toggle(component: Toggle, parent: QWidget | None, on_change: OnChange) -> Rendering:
    widget = QCheckBox(parent)
    rendering = Rendering(widget, lambda value: widget.setChecked(bool(value)))
    connect(rendering, widget.toggled, on_change)
    return rendering


def number(component: Number, parent: QWidget | None, on_change: OnChange) -> Rendering:
    if component.integer:
        box: QSpinBox | QDoubleSpinBox = QSpinBox(parent)
        low, high = component.range or (_INT_MIN, _INT_MAX)
        box.setRange(int(low), int(high))
    else:
        box = QDoubleSpinBox(parent)
        box.setDecimals(6)
        low, high = component.range or (-_REAL_MAX, _REAL_MAX)
        box.setRange(float(low), float(high))
    if component.step is not None:
        box.setSingleStep(component.step)
    rendering = Rendering(box, box.setValue)
    connect(rendering, box.valueChanged, on_change)
    return rendering


def distance(
    component: Distance, parent: QWidget | None, on_change: OnChange
) -> Rendering:
    box = QDoubleSpinBox(parent)
    box.setDecimals(3)
    box.setSuffix(" m")
    box.setRange(0.0, _REAL_MAX)
    rendering = Rendering(box, box.setValue)
    connect(rendering, box.valueChanged, on_change)
    return rendering


def choice(component: Choice, parent: QWidget | None, on_change: OnChange) -> Rendering:
    combo = QComboBox(parent)
    for option in component.options:
        combo.addItem(str(option), option)
    rendering = Rendering(
        combo, lambda value: combo.setCurrentIndex(component.options.index(value))
    )
    connect(
        rendering,
        combo.currentIndexChanged,
        lambda index: on_change(combo.itemData(index)),
    )
    return rendering


def colour(component: Colour, parent: QWidget | None, on_change: OnChange) -> Rendering:
    button = QgsColorButton(parent)
    button.setAllowOpacity(component.alpha)

    def apply(value: object) -> None:
        text = str(value)
        rgb, alpha = text[:7], text[7:9]
        colour = QColor(rgb)
        if alpha:
            colour.setAlpha(int(alpha, 16))
        button.setColor(colour)

    def read(colour: QColor) -> None:
        on_change(_hex(colour, alpha=component.alpha))

    rendering = Rendering(button, apply)
    connect(rendering, button.colorChanged, read)
    return rendering


def _hex(colour: QColor, *, alpha: bool) -> str:
    """Spell a QColor the way the colour kind stores it: ``#rrggbb[aa]``."""
    rgb = colour.name(QColor.NameFormat.HexRgb).lower()
    return f"{rgb}{colour.alpha():02x}" if alpha else rgb


def layer(
    component: LayerPicker, parent: QWidget | None, on_change: OnChange
) -> Rendering:
    combo = QgsMapLayerComboBox(parent)
    combo.setFilters(_LAYER_FILTERS[component.layer_kind])
    combo.setAllowEmptyLayer(True)

    def apply(value: object) -> None:
        layer = None if value is None else QgsProject.instance().mapLayer(str(value))
        if value is not None and layer is None:
            raise QgisSdkFormError(
                f"LayerPicker {component.name!r}: layer {value!r} is not in the project"
            )
        combo.setLayer(layer)

    def options() -> tuple[Option, ...]:
        listed = []
        for index in range(combo.count()):
            layer = combo.layer(index)
            if layer is not None:
                listed.append(Option(id=layer.id(), label=layer.name()))
        return tuple(listed)

    rendering = Rendering(combo, apply, options)
    connect(
        rendering,
        combo.layerChanged,
        lambda layer: on_change(None if layer is None else layer.id()),
    )
    return rendering

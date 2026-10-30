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
    QgsCoordinateReferenceSystem,
    QgsMapLayerProxyModel,
    QgsProject,
)
from qgis.gui import (
    QgsCollapsibleGroupBox,
    QgsColorButton,
    QgsFieldComboBox,
    QgsFileWidget,
    QgsMapLayerComboBox,
    QgsProjectionSelectionWidget,
)
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from qgis_sdk.adapters._qt import qt_enum
from qgis_sdk.models import QgisSdkFormError, QgisSdkUiError
from qgis_sdk.ui.buttons import AcceptCancel, RunButton
from qgis_sdk.ui.components import (
    Button,
    Choice,
    Colour,
    Column,
    Component,
    CrsPicker,
    DirectoryInput,
    Distance,
    FieldPicker,
    FileInput,
    LayerPicker,
    Number,
    Option,
    Text,
    Toggle,
)
from qgis_sdk.ui.containers import Group, Panel, Row, Tabs
from qgis_sdk.ui.custom import Custom
from qgis_sdk.ui.feedback import JobProgress, LogView, ResultTable
from qgis_sdk.ui.form import Form

from .processing import _qt_filter

__all__ = ["Rendering", "load_ui", "mount"]

#: Spin-box bounds: wide enough never to clip a
#: value the wire accepts, finite so the widget does not overflow.
_INT_MIN, _INT_MAX = -(2**31), 2**31 - 1
_REAL_MAX = 1e15

_LAYER_FILTERS = {
    "vector": QgsMapLayerProxyModel.Filter.VectorLayer,
    "raster": QgsMapLayerProxyModel.Filter.RasterLayer,
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
    for cls, builder in _BUILDERS:
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


def _connect(rendering: Rendering, signal: Any, slot: Callable[..., None]) -> None:
    signal.connect(slot)
    rendering._connections.append((signal, slot))


# -- plain values ------------------------------------------------------------------------


def _text(component: Text, parent: QWidget | None, on_change: OnChange) -> Rendering:
    widget = QLineEdit(parent)
    rendering = Rendering(widget, lambda value: widget.setText(str(value)))
    _connect(rendering, widget.textChanged, on_change)
    return rendering


def _toggle(
    component: Toggle, parent: QWidget | None, on_change: OnChange
) -> Rendering:
    widget = QCheckBox(parent)
    rendering = Rendering(widget, lambda value: widget.setChecked(bool(value)))
    _connect(rendering, widget.toggled, on_change)
    return rendering


def _number(
    component: Number, parent: QWidget | None, on_change: OnChange
) -> Rendering:
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
    _connect(rendering, box.valueChanged, on_change)
    return rendering


def _distance(
    component: Distance, parent: QWidget | None, on_change: OnChange
) -> Rendering:
    box = QDoubleSpinBox(parent)
    box.setDecimals(3)
    box.setSuffix(" m")
    box.setRange(0.0, _REAL_MAX)
    rendering = Rendering(box, box.setValue)
    _connect(rendering, box.valueChanged, on_change)
    return rendering


def _choice(
    component: Choice, parent: QWidget | None, on_change: OnChange
) -> Rendering:
    combo = QComboBox(parent)
    for option in component.options:
        combo.addItem(str(option), option)
    rendering = Rendering(
        combo, lambda value: combo.setCurrentIndex(component.options.index(value))
    )
    _connect(
        rendering,
        combo.currentIndexChanged,
        lambda index: on_change(combo.itemData(index)),
    )
    return rendering


def _colour(
    component: Colour, parent: QWidget | None, on_change: OnChange
) -> Rendering:
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
    _connect(rendering, button.colorChanged, read)
    return rendering


def _hex(colour: QColor, *, alpha: bool) -> str:
    """Spell a QColor the way the colour kind stores it: ``#rrggbb[aa]``."""
    rgb = colour.name(QColor.NameFormat.HexRgb).lower()
    return f"{rgb}{colour.alpha():02x}" if alpha else rgb


# -- pickers -----------------------------------------------------------------------------


def _layer(
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
    _connect(
        rendering,
        combo.layerChanged,
        lambda layer: on_change(None if layer is None else layer.id()),
    )
    return rendering


def _field(
    component: FieldPicker, parent: QWidget | None, on_change: OnChange
) -> Rendering:
    combo = QgsFieldComboBox(parent)
    combo.setAllowEmptyFieldName(True)

    def apply(value: object) -> None:
        layer_id = component.of.value()
        layer = None if layer_id is None else QgsProject.instance().mapLayer(layer_id)
        if combo.layer() is not layer:
            combo.setLayer(layer)
        combo.setField("" if value is None else str(value))

    def options() -> tuple[Option, ...]:
        layer = combo.layer()
        if layer is None:
            return ()
        return tuple(Option(id=name, label=name) for name in layer.fields().names())

    rendering = Rendering(combo, apply, options)
    _connect(rendering, combo.fieldChanged, lambda name: on_change(name or None))
    return rendering


def _crs(
    component: CrsPicker, parent: QWidget | None, on_change: OnChange
) -> Rendering:
    picker = QgsProjectionSelectionWidget(parent)
    picker.setOptionVisible(QgsProjectionSelectionWidget.CrsOption.CrsNotSet, True)

    def apply(value: object) -> None:
        if value is None:
            picker.setCrs(QgsCoordinateReferenceSystem())
            return
        crs = QgsCoordinateReferenceSystem(str(value))
        if not crs.isValid():
            raise QgisSdkFormError(
                f"CrsPicker {component.name!r}: {value!r} is not a known CRS"
            )
        picker.setCrs(crs)

    def read(crs: QgsCoordinateReferenceSystem) -> None:
        on_change((crs.authid() or None) if crs.isValid() else None)

    rendering = Rendering(picker, apply)
    _connect(rendering, picker.crsChanged, read)
    return rendering


# -- files ---------------------------------------------------------------------------------


def _file(
    component: FileInput | DirectoryInput, parent: QWidget | None, on_change: OnChange
) -> Rendering:
    widget = QgsFileWidget(parent)
    if isinstance(component, DirectoryInput):
        widget.setStorageMode(QgsFileWidget.StorageMode.GetDirectory)
    else:
        widget.setStorageMode(QgsFileWidget.StorageMode.GetFile)
        if component.filters:
            widget.setFilter(";;".join(_qt_filter(glob) for glob in component.filters))

    def apply(value: object) -> None:
        # The widget shows the path behind the ref; the ref is the value.
        path = component.path(value)
        widget.setFilePath("" if path is None else str(path))

    rendering = Rendering(widget, apply)
    _connect(rendering, widget.fileChanged, on_change)
    return rendering


# -- buttons and containers ------------------------------------------------------------------


def _button(
    component: Button, parent: QWidget | None, on_change: OnChange
) -> Rendering:
    button = QPushButton(component.text, parent)
    rendering = Rendering(button, lambda value: None)
    _connect(rendering, button.clicked, lambda _checked=False: on_change(None))
    return rendering


def _column(
    component: Column, parent: QWidget | None, on_change: OnChange
) -> Rendering:
    widget = QWidget(parent)
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    for child in component.children():
        layout.addWidget(child.mount(widget))
    return Rendering(widget, lambda value: None)


def _row(component: Row, parent: QWidget | None, on_change: OnChange) -> Rendering:
    widget = QWidget(parent)
    layout = QHBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    for child in component.children():
        layout.addWidget(child.mount(widget))
    return Rendering(widget, lambda value: None)


def _panel(component: Panel, parent: QWidget | None, on_change: OnChange) -> Rendering:
    inner = QWidget(parent)
    layout = QVBoxLayout(inner)
    for child in component.children():
        layout.addWidget(child.mount(inner))
    layout.addStretch(1)
    if not component.scrollable:
        return Rendering(inner, lambda value: None)
    area = QScrollArea(parent)
    area.setWidgetResizable(True)
    area.setFrameShape(QScrollArea.Shape.NoFrame)
    inner.setParent(area)
    area.setWidget(inner)
    return Rendering(area, lambda value: None)


def _group(component: Group, parent: QWidget | None, on_change: OnChange) -> Rendering:
    box: QGroupBox = (
        QgsCollapsibleGroupBox(component.label, parent)
        if component.collapsible
        else QGroupBox(component.label, parent)
    )
    layout = QVBoxLayout(box)
    for child in component.children():
        layout.addWidget(child.mount(box))
    return Rendering(box, lambda value: None)


def _tabs(component: Tabs, parent: QWidget | None, on_change: OnChange) -> Rendering:
    tabs = QTabWidget(parent)
    for child in component.children():
        tabs.addTab(child.mount(tabs), child.label)
    rendering = Rendering(tabs, lambda value: tabs.setCurrentIndex(int(value)))  # type: ignore[arg-type]
    _connect(rendering, tabs.currentChanged, on_change)
    return rendering


def _form(component: Form, parent: QWidget | None, on_change: OnChange) -> Rendering:
    widget = QWidget(parent)
    layout = QFormLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    for entry in component.fields:
        label = f"{entry.label} *" if entry.required else entry.label
        layout.addRow(label, entry.mount(widget))
    return Rendering(widget, lambda value: None)


def _accept_cancel(
    component: AcceptCancel, parent: QWidget | None, on_change: OnChange
) -> Rendering:
    box = QDialogButtonBox(parent)
    accept = box.addButton(
        component.accept_text, QDialogButtonBox.ButtonRole.AcceptRole
    )
    cancel = box.addButton(
        component.cancel_text, QDialogButtonBox.ButtonRole.RejectRole
    )
    accept.setObjectName(f"{component.object_name}/accept")
    cancel.setObjectName(f"{component.object_name}/cancel")
    rendering = Rendering(box, lambda value: None)
    _connect(rendering, box.accepted, lambda: on_change("accept"))
    _connect(rendering, box.rejected, lambda: on_change("cancel"))
    return rendering


def _custom(
    component: Custom, parent: QWidget | None, on_change: OnChange
) -> Rendering:
    widget = component.resolve(parent)
    if not isinstance(widget, QWidget):
        raise QgisSdkUiError(
            f"Custom {component.name!r}: expected a QWidget, got {type(widget).__name__}"
        )
    if parent is not None and widget.parent() is not parent:
        widget.setParent(parent)
    return Rendering(widget, lambda value: None)


# -- feedback ---------------------------------------------------------------------------


def _job_progress(
    component: JobProgress, parent: QWidget | None, on_change: OnChange
) -> Rendering:
    widget = QWidget(parent)
    layout = QHBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    bar = QProgressBar(widget)
    bar.setObjectName(f"{component.object_name}/bar")
    bar.setRange(0, 100)
    bar.setTextVisible(True)
    message = QLabel(widget)
    message.setObjectName(f"{component.object_name}/message")
    layout.addWidget(bar, 1)
    layout.addWidget(message)
    cancel: QPushButton | None = None
    if component.cancellable:
        cancel = QPushButton("Cancel", widget)
        cancel.setObjectName(f"{component.object_name}/cancel")
        layout.addWidget(cancel)

    def apply(value: object) -> None:
        status, fraction, text = value  # type: ignore[misc]
        if fraction is None:
            if status in ("queued", "running"):
                bar.setRange(0, 0)  # busy
            else:
                bar.setRange(0, 100)
                bar.setValue(0)
        else:
            bar.setRange(0, 100)
            bar.setValue(round(float(fraction) * 100))
        message.setText(text if text else ("" if status == "idle" else str(status)))
        if cancel is not None:
            cancel.setEnabled(status in ("queued", "running"))

    rendering = Rendering(widget, apply)
    if cancel is not None:
        _connect(rendering, cancel.clicked, lambda _checked=False: on_change("cancel"))
    return rendering


def _log_view(
    component: LogView, parent: QWidget | None, on_change: OnChange
) -> Rendering:
    view = QPlainTextEdit(parent)
    view.setReadOnly(True)
    view.setMaximumBlockCount(component.limit)

    def apply(value: object) -> None:
        view.setPlainText("\n".join(value))  # type: ignore[arg-type]
        bar = view.verticalScrollBar()
        bar.setValue(bar.maximum())

    return Rendering(view, apply)


def _result_table(
    component: ResultTable, parent: QWidget | None, on_change: OnChange
) -> Rendering:
    table = QTableWidget(0, len(component.columns), parent)
    table.setHorizontalHeaderLabels(list(component.headings))
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.verticalHeader().setVisible(False)

    def apply(value: object) -> None:
        rows, selected = value  # type: ignore[misc]
        table.blockSignals(True)
        try:
            table.setRowCount(len(rows))
            for row_index, cells in enumerate(rows):
                for column_index, text in enumerate(cells):
                    item = QTableWidgetItem(text)
                    item.setFlags(
                        item.flags() & ~qt_enum(Qt, "ItemFlag", "ItemIsEditable")
                    )
                    table.setItem(row_index, column_index, item)
            table.clearSelection()
            if selected is not None:
                table.selectRow(selected)
        finally:
            table.blockSignals(False)

    def read() -> None:
        rows = {index.row() for index in table.selectionModel().selectedRows()}
        on_change(min(rows) if rows else None)

    rendering = Rendering(table, apply)
    _connect(rendering, table.itemSelectionChanged, read)
    return rendering


_BUILDERS: tuple[tuple[type[Component], Callable[..., Rendering]], ...] = (
    (RunButton, _button),
    (Button, _button),
    (AcceptCancel, _accept_cancel),
    (Column, _column),
    (Row, _row),
    (Panel, _panel),
    (Group, _group),
    (Tabs, _tabs),
    (Custom, _custom),
    (Form, _form),
    (JobProgress, _job_progress),
    (LogView, _log_view),
    (ResultTable, _result_table),
    (Text, _text),
    (Toggle, _toggle),
    (Number, _number),
    (Distance, _distance),
    (Choice, _choice),
    (Colour, _colour),
    (LayerPicker, _layer),
    (FieldPicker, _field),
    (CrsPicker, _crs),
    (FileInput, _file),
    (DirectoryInput, _file),
)

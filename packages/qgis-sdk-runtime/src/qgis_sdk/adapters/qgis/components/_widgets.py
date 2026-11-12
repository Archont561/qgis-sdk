from __future__ import annotations

from collections.abc import Callable

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsProject,
)
from qgis.gui import (
    QgsCollapsibleGroupBox,
    QgsFieldComboBox,
    QgsFileWidget,
    QgsProjectionSelectionWidget,
)
from qgis.PyQt.QtWidgets import (
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

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

from ..processing._parameters import _qt_filter
from ._result_table_state import (
    CcPhases1,
    CcReturn,
    CcReturn1,
    CcState,
    CcState1,
    OnChange,
    Rendering,
    cc_result_table_p1,
    cc_result_table_p2,
    cc_result_table_p3,
    choice,
    colour,
    connect,
    distance,
    layer,
    number,
    text,
    toggle,
)


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
    connect(rendering, combo.fieldChanged, lambda name: on_change(name or None))
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
    connect(rendering, picker.crsChanged, read)
    return rendering


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
    connect(rendering, widget.fileChanged, on_change)
    return rendering


def _button(
    component: Button, parent: QWidget | None, on_change: OnChange
) -> Rendering:
    button = QPushButton(component.text, parent)
    rendering = Rendering(button, lambda value: None)
    connect(rendering, button.clicked, lambda _checked=False: on_change(None))
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
    connect(rendering, tabs.currentChanged, on_change)
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
    connect(rendering, box.accepted, lambda: on_change("accept"))
    connect(rendering, box.rejected, lambda: on_change("cancel"))
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


def _job_progress(
    component: JobProgress, parent: QWidget | None, on_change: OnChange
) -> Rendering:
    _s = CcState(**locals())
    for _p in CcPhases1():
        _r = _p(_s)
        if isinstance(_r, CcReturn):
            return _r.value
    return None


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
    _s1 = CcState1(component=component, parent=parent, on_change=on_change)
    for _p1 in (cc_result_table_p1, cc_result_table_p2, cc_result_table_p3):
        _r1 = _p1(_s1)
        if isinstance(_r1, CcReturn1):
            return _r1.value
    return None


BUILDERS: tuple[tuple[type[Component], Callable[..., Rendering]], ...] = (
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
    (Text, text),
    (Toggle, toggle),
    (Number, number),
    (Distance, distance),
    (Choice, choice),
    (Colour, colour),
    (LayerPicker, layer),
    (FieldPicker, _field),
    (CrsPicker, _crs),
    (FileInput, _file),
    (DirectoryInput, _file),
)

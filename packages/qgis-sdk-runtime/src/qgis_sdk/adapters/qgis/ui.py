"""Render a declared action as a native Qt dialog and dispatch it.

Widget choice is not decided here. :func:`qgis_sdk.ui.form_fields` maps the wire
schema plus the author's ``Annotated`` markers to a widget *family*, and this
module only turns that family into a concrete Qt class and reads a value back out
of it. A field with no family never reaches a dialog, so there is no "pick
something reasonable" branch to drift.

The escape hatch is not a second API. ``PluginRuntime.actions`` is keyed by
action id and holds ordinary bound methods, so conventional PyQt code can build
its own dialog - a canvas tool, a wizard, a form with live preview - and call the
same handler through :meth:`NativeForms.dispatch`. This class automates the
common case and refuses what it cannot represent instead of guessing.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any, get_args, get_origin, get_type_hints

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLineEdit,
    QSpinBox,
    QWidget,
)
from qgis.core import QgsMapLayerProxyModel
from qgis.gui import (
    QgsColorButton,
    QgsFieldComboBox,
    QgsMapLayerComboBox,
    QgsProjectionSelectionWidget,
)

from qgis_sdk.core import PluginRuntime
from qgis_sdk.declarations import ActionDescription
from qgis_sdk.models import QgisSdkFormError, parameter_kinds
from qgis_sdk.ui import FieldSpec, coerce_values, form_fields

__all__ = ["DeclaredFormDialog", "NativeForms"]

#: Spin-box bounds. The wire contract already refuses integers outside the JSON
#: safe range (``models.limits``); these only stop a Qt widget from overflowing
#: before the value ever reaches that check.
_INT_MIN, _INT_MAX = -(2**31), 2**31 - 1
_REAL_MAX = 1e15


class NativeForms:
    """Render declared actions and dispatch their validated values."""

    def __init__(
        self, runtime: PluginRuntime, *, parent: QWidget | None = None
    ) -> None:
        self._runtime = runtime
        self._parent = parent

    def fields(self, action_id: str) -> tuple[FieldSpec, ...]:
        """Describe the inputs of one declared action."""
        return form_fields(self._action(action_id), markers=self._markers(action_id))

    def render(self, action_id: str) -> DeclaredFormDialog:
        """Build the dialog for one declared action without showing it."""
        action = self._action(action_id)
        return DeclaredFormDialog(
            action,
            self.fields(action_id),
            self._markers(action_id),
            self._parent,
        )

    def dispatch(self, action_id: str, values: Mapping[str, object]) -> object:
        """Coerce submitted values and call the declared handler.

        This is the escape hatch: any code holding the runtime can validate and
        call a handler without going through a dialog.
        """
        action = self._action(action_id)
        coerced = coerce_values(action, values, markers=self._markers(action_id))
        handler = self._runtime.actions.get(action_id)
        if handler is None:
            raise QgisSdkFormError(
                f"action {action_id!r} is declared but not bound; start the runtime first"
            )
        return handler(**coerced)

    def run(self, action_id: str) -> object | None:
        """Show the dialog, then dispatch, or return ``None`` when cancelled."""
        dialog = self.render(action_id)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return self.dispatch(action_id, dialog.values())

    def _action(self, action_id: str) -> ActionDescription:
        for action in self._runtime.description.actions:
            if action.id == action_id:
                return action
        raise QgisSdkFormError(
            f"plugin {self._runtime.description.id!r} declares no action {action_id!r}"
        )

    def _markers(self, action_id: str) -> dict[str, str]:
        """Read the author's widget markers from the handler's signature.

        The wire description drops ``Annotated`` extras on purpose - they are
        host hints, not serialized shape - so the only place they still exist is
        the declared method, which lives on the running instance's class.
        """
        instance = self._runtime.instance
        if instance is None:
            raise QgisSdkFormError(
                "native forms need a running plugin: the widget markers live on "
                "the handler's signature"
            )
        action = self._action(action_id)
        method = getattr(type(instance), action.handler, None)
        if not callable(method):
            raise QgisSdkFormError(
                f"action {action_id!r} handler {action.handler!r} is not callable"
            )
        markers: dict[str, str] = {}
        for name, hint in get_type_hints(method, include_extras=True).items():
            if name == "return":
                continue
            marker = _marker_of(hint)
            if marker is not None:
                markers[name] = marker
        return markers


class DeclaredFormDialog(QDialog):
    """A dialog built from a declared action's schema."""

    def __init__(
        self,
        action: ActionDescription,
        specs: tuple[FieldSpec, ...],
        markers: Mapping[str, str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._action = action
        self._specs = specs
        self._markers = dict(markers)
        self._widgets: dict[str, QWidget] = {}
        self.setWindowTitle(action.title)
        layout = QFormLayout(self)
        for spec in specs:
            widget = _widget_for(spec, self)
            self._widgets[spec.name] = widget
            label = f"{spec.label} *" if spec.required else spec.label
            layout.addRow(label, widget)
        for spec in specs:
            if spec.widget == "field":
                _follow_layer(
                    self._widgets[spec.name], self._widgets[spec.details["of"]]
                )
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def widget(self, name: str) -> QWidget:
        """Return the widget built for one field, for tests and for tweaking."""
        try:
            return self._widgets[name]
        except KeyError:
            raise QgisSdkFormError(
                f"action {self._action.id!r} has no field {name!r}"
            ) from None

    def values(self) -> dict[str, object]:
        """Collect the dialog's current values, coerced and validated."""
        raw = {spec.name: _read(spec, self._widgets[spec.name]) for spec in self._specs}
        return coerce_values(self._action, raw, markers=self._markers)


def _marker_of(hint: Any) -> str | None:
    """Return the kind name of the SDK marker carried by an ``Annotated`` hint."""
    if get_origin(hint) is not Annotated:
        return None
    markers = {
        kind.marker: name for name, kind in parameter_kinds().items() if kind.marker
    }
    for extra in get_args(hint)[1:]:
        name = markers.get(type(extra))
        if name is not None:
            return name
    return None


def _follow_layer(picker: QgsFieldComboBox, source: QgsMapLayerComboBox) -> None:
    """Keep a field picker on the layer its ``of`` picker currently shows."""
    picker.setLayer(source.currentLayer())
    source.layerChanged.connect(picker.setLayer)


def _widget_for(spec: FieldSpec, parent: QWidget) -> QWidget:
    """Instantiate the Qt widget for one field family."""
    if spec.widget == "text":
        return QLineEdit(parent)
    if spec.widget == "integer":
        box = QSpinBox(parent)
        box.setRange(_INT_MIN, _INT_MAX)
        return box
    if spec.widget == "number":
        box = QDoubleSpinBox(parent)
        box.setDecimals(6)
        box.setRange(-_REAL_MAX, _REAL_MAX)
        return box
    if spec.widget == "metres":
        box = QDoubleSpinBox(parent)
        box.setDecimals(3)
        box.setSuffix(" m")
        box.setRange(0.0, _REAL_MAX)
        return box
    if spec.widget == "boolean":
        return QCheckBox(parent)
    if spec.widget == "layer":
        combo = QgsMapLayerComboBox(parent)
        combo.setFilters(QgsMapLayerProxyModel.Filter.VectorLayer)
        return combo
    if spec.widget == "crs":
        return QgsProjectionSelectionWidget(parent)
    if spec.widget == "choice":
        combo = QComboBox(parent)
        for choice in spec.choices:
            combo.addItem(str(choice), choice)
        return combo
    if spec.widget == "field":
        return QgsFieldComboBox(parent)
    if spec.widget == "range":
        low, high = spec.details["minimum"], spec.details["maximum"]
        if isinstance(low, int) and isinstance(high, int):
            box = QSpinBox(parent)
            box.setRange(low, high)
        else:
            box = QDoubleSpinBox(parent)
            box.setDecimals(6)
            box.setRange(float(low), float(high))
        step = spec.details.get("step")
        if step is not None:
            box.setSingleStep(step)
        return box
    if spec.widget == "colour":
        button = QgsColorButton(parent)
        button.setAllowOpacity(spec.details.get("alpha", True))
        return button
    if spec.widget in ("file", "directory"):
        raise QgisSdkFormError(
            f"field {spec.name!r}: a {spec.widget} input is rendered by the "
            "FileInput component of the Form helper, which mints the FileRef; "
            "the declared-form dialog cannot grant file authority"
        )
    raise QgisSdkFormError(
        f"action {spec.name!r}: no widget for family {spec.widget!r}"
    )


def _read(spec: FieldSpec, widget: QWidget) -> object:
    """Read one submitted value out of its widget, before coercion."""
    if spec.widget == "text":
        return widget.text()
    if spec.widget in ("integer", "number", "metres"):
        return widget.value()
    if spec.widget == "boolean":
        return widget.isChecked()
    if spec.widget == "layer":
        layer = widget.currentLayer()
        return layer.id() if layer is not None else ""
    if spec.widget == "crs":
        return widget.crs().authid()
    if spec.widget == "choice":
        return widget.currentData()
    if spec.widget == "field":
        return widget.currentField()
    if spec.widget == "range":
        return widget.value()
    if spec.widget == "colour":
        colour: QColor = widget.color()
        spelling = (
            QColor.NameFormat.HexArgb
            if widget.allowOpacity()
            else QColor.NameFormat.HexRgb
        )
        named = colour.name(spelling)
        # Qt spells alpha first (#AARRGGBB); the wire spells it last.
        return (
            f"#{named[3:]}{named[1:3]}"
            if spelling is QColor.NameFormat.HexArgb
            else named
        )
    raise QgisSdkFormError(
        f"action {spec.name!r}: no reader for widget family {spec.widget!r}"
    )

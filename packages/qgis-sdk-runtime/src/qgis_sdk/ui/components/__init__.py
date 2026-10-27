"""The catalogue's input components (decision-55 point 3).

A component is *state first, widget second*. ``LayerPicker("layer")`` holds
a layer id, ``FileInput("source")`` a :class:`~qgis_sdk.models.FileRef`,
``Number("count", range=(0, 10))`` an ``int`` - models, never Qt types -
and ``value()``/``set_value()``/``changed()`` work before any widget exists.
That state is the fake rendering a pure test asserts on and the semantic
node a UI snapshot shows (decision-51). ``mount()`` builds the QGIS widget
that mirrors the state (``QgsMapLayerComboBox``, ``QgsFileWidget``,
``QgsColorButton``...) through :mod:`qgis_sdk.adapters.qgis.components`,
the one module here that imports Qt, and only when asked: importing
``qgis_sdk.ui`` loads no Qt.

Two rules hold under both renderings, and the contract tests run the same
assertions against each:

* ``set_value`` refuses what a declared form would refuse, with the same
  words (:func:`qgis_sdk.ui.form_fields.coerce_value`), and a refused value
  changes nothing.
* ``attach(ctx)`` binds the component to a surface's :class:`UiContext`:
  pickers list through ``ctx.layers``/``ctx.project``, ``FileInput`` mints
  refs through ``ctx.files``, and every listener is dropped when the
  context's scope closes.
"""

from __future__ import annotations

from qgis_sdk.ui.components._base import (
    NATIVE_CATALOGUE,
    Component,
    Input,
    Option,
    split_name_and_children,
)
from qgis_sdk.ui.components._files import DirectoryInput, FileInput
from qgis_sdk.ui.components._layout import Button, Column, Container
from qgis_sdk.ui.components._pickers import CrsPicker, FieldPicker, LayerPicker
from qgis_sdk.ui.components._scalars import (
    Choice,
    Colour,
    Distance,
    Number,
    Text,
    Toggle,
)

__all__ = [
    "NATIVE_CATALOGUE",
    "Button",
    "Choice",
    "Colour",
    "Column",
    "Component",
    "Container",
    "CrsPicker",
    "DirectoryInput",
    "Distance",
    "FieldPicker",
    "FileInput",
    "Input",
    "LayerPicker",
    "Number",
    "Option",
    "Text",
    "Toggle",
    "split_name_and_children",
]

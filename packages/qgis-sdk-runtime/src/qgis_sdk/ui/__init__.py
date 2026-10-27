"""What an author's surfaces are made of, without importing Qt here.

``Dialog`` and ``Dock`` are the surface base classes (decision-55); the
form-field rules that back the 0.5 declared forms stay in
:mod:`qgis_sdk.ui.form_fields` and are re-exported for the adapters that
still use them. The catalogue - the input components, the buttons, the
containers, the feedback components, ``Custom`` and ``Form`` - lives in the
sibling modules and imports Qt only when mounted; ``ui_snapshot`` reads a
tree built either way.
"""

from .actions import ActionCall, ViewActions
from .buttons import AcceptCancel, RunButton
from .components import (
    Button,
    Choice,
    Colour,
    Column,
    Component,
    Container,
    CrsPicker,
    DirectoryInput,
    Distance,
    FieldPicker,
    FileInput,
    Input,
    LayerPicker,
    Number,
    Option,
    Text,
    Toggle,
)
from .containers import Group, Panel, Row, Tabs
from .custom import Custom
from .feedback import JobProgress, LogView, ResultTable
from .form import Form, input_for
from .form_fields import (
    FieldSpec,
    coerce_value,
    coerce_values,
    form_fields,
    schema_fields,
)
from .snapshot import snapshot_names, ui_snapshot
from .surfaces import (
    DOCK_AREAS,
    Dialog,
    Dock,
    Surface,
    SurfaceDescription,
    describe_surface,
    is_dock,
    is_surface_class,
    is_widget_surface,
)

__all__ = [
    "DOCK_AREAS",
    "AcceptCancel",
    "ActionCall",
    "Button",
    "Choice",
    "Colour",
    "Column",
    "Component",
    "Container",
    "CrsPicker",
    "Custom",
    "Dialog",
    "DirectoryInput",
    "Distance",
    "Dock",
    "FieldPicker",
    "FieldSpec",
    "FileInput",
    "Form",
    "Group",
    "Input",
    "JobProgress",
    "LayerPicker",
    "LogView",
    "Number",
    "Option",
    "Panel",
    "ResultTable",
    "Row",
    "RunButton",
    "Surface",
    "SurfaceDescription",
    "Tabs",
    "Text",
    "Toggle",
    "ViewActions",
    "coerce_value",
    "coerce_values",
    "describe_surface",
    "form_fields",
    "input_for",
    "is_dock",
    "is_surface_class",
    "is_widget_surface",
    "schema_fields",
    "snapshot_names",
    "ui_snapshot",
]

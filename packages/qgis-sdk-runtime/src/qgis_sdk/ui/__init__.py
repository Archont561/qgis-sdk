"""What an author's surfaces are made of, without importing Qt here.

``Dialog`` and ``Dock`` are the surface base classes (decision-55); the
form-field rules that back the 0.5 declared forms stay in
:mod:`qgis_sdk.ui.form_fields` and are re-exported for the adapters that
still use them. The catalogue - the input components, ``Button``, ``Column``
and ``Form`` - lives in :mod:`qgis_sdk.ui.components` and :mod:`qgis_sdk.ui.form`;
it imports Qt only when mounted.
"""

from .actions import ActionCall, ViewActions
from .components import (
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
    Input,
    LayerPicker,
    Number,
    Option,
    Text,
    Toggle,
)
from .form import Form, input_for
from .form_fields import (
    FieldSpec,
    coerce_value,
    coerce_values,
    form_fields,
    schema_fields,
)
from .surfaces import (
    DOCK_AREAS,
    Dialog,
    Dock,
    Surface,
    SurfaceDescription,
    describe_surface,
    is_surface_class,
)

__all__ = [
    "DOCK_AREAS",
    "ActionCall",
    "Button",
    "Choice",
    "Colour",
    "Column",
    "Component",
    "CrsPicker",
    "Dialog",
    "DirectoryInput",
    "Distance",
    "Dock",
    "FieldPicker",
    "FieldSpec",
    "FileInput",
    "Form",
    "Input",
    "LayerPicker",
    "Number",
    "Option",
    "Surface",
    "SurfaceDescription",
    "Text",
    "Toggle",
    "ViewActions",
    "coerce_value",
    "coerce_values",
    "describe_surface",
    "form_fields",
    "input_for",
    "is_surface_class",
    "schema_fields",
]

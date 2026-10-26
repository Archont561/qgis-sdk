"""What an author's surfaces are made of, without importing Qt here.

``Dialog`` and ``Dock`` are the surface base classes (decision-55); the
form-field rules that back the 0.5 declared forms stay in
:mod:`qgis_sdk.ui.form_fields` and are re-exported for the adapters that
still use them. The input components of the catalogue live in
:mod:`qgis_sdk.ui.components`; they import Qt only when mounted.
"""

from .components import (
    Choice,
    Colour,
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
from .form_fields import FieldSpec, coerce_value, coerce_values, form_fields
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
    "Choice",
    "Colour",
    "Component",
    "CrsPicker",
    "Dialog",
    "DirectoryInput",
    "Distance",
    "Dock",
    "FieldPicker",
    "FieldSpec",
    "FileInput",
    "LayerPicker",
    "Number",
    "Option",
    "Surface",
    "SurfaceDescription",
    "Text",
    "Toggle",
    "coerce_value",
    "coerce_values",
    "describe_surface",
    "form_fields",
    "is_surface_class",
]

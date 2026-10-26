"""What an author's surfaces are made of, without importing Qt here.

``Dialog`` and ``Dock`` are the surface base classes (decision-55); the
form-field rules that back the 0.5 declared forms stay in
:mod:`qgis_sdk.ui.form_fields` and are re-exported for the adapters that
still use them. The curated widget catalogue lands in a later task.
"""

from .form_fields import FieldSpec, coerce_values, form_fields
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
    "Dialog",
    "Dock",
    "FieldSpec",
    "Surface",
    "SurfaceDescription",
    "coerce_values",
    "describe_surface",
    "form_fields",
    "is_surface_class",
]

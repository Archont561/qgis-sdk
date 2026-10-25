"""Markers that say what a request field *means* to a host, not what it stores.

A dataclass field already carries a type, and the type is enough to render a text
box or a spin box. It is not enough to render the right *widget*: a ``str`` may be
free text or a vector layer the user picks from the canvas, and a ``float`` may be
an arbitrary number or a distance whose unit the host should show. These markers
ride along in ``Annotated`` metadata so the wire schema keeps describing the
stored value while the host learns the intent (TASK-39).

They are plain frozen values: equality is by type, so a test can assert which
marker a field carries without importing QGIS.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["CrsInput", "LayerInput", "Metres"]


@dataclass(frozen=True, slots=True)
class LayerInput:
    """The field receives a vector layer chosen by the user."""


@dataclass(frozen=True, slots=True)
class CrsInput:
    """The field receives a coordinate reference system chosen by the user."""


@dataclass(frozen=True, slots=True)
class Metres:
    """The field is a distance in metres, so the host may label and bound it."""

    minimum: float = 0.0
    maximum: float | None = None

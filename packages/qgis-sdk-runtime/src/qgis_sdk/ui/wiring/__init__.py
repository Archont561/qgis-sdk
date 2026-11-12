"""``@on`` and ``@subscribe``: connect a surface's methods after ``build()``.

decision-55 keeps decorators to marking: ``@on("distance").changed`` and
``@subscribe("progress")`` attach a record and ``describe()`` to the method,
without wrapping it, so a test calls it directly with a fake
context. Once the host (or :func:`qgis_sdk.testing.build_surface`) has the
built tree, :func:`wire_surface` reads the records, finds each named node
- a catalogue component by ``name`` or a Qt widget by ``objectName`` in a
hand-built or ``.ui``-loaded tree - connects the method, and registers the
disconnects with the view's scope, so a closed window hears nothing more.

``@on(name)`` offers the signals the catalogue speaks - ``changed``,
``clicked``, ``toggled``, ``edited``, ``accepted``, ``cancelled``,
``finished``, ``selected`` - and ``@on(name, "textEdited")`` names a Qt
signal of a widget directly.
"""

from __future__ import annotations

import inspect as _inspect

from qgis_sdk.declarations import (
    WIRES_ATTRIBUTE,
)
from qgis_sdk.declarations import (
    register_predicate_describer as _register_predicate_describer,
)

from ._connect import wire_surface, wires_of
from ._markers import OnMarker, on, subscribe
from ._types import ON_SIGNALS, Wire, WiringDescription

__all__ = [
    "ON_SIGNALS",
    "WIRES_ATTRIBUTE",
    "OnMarker",
    "Wire",
    "WiringDescription",
    "on",
    "subscribe",
    "wire_surface",
    "wires_of",
]


def _describe_wiring(method) -> WiringDescription:
    return WiringDescription(method.__name__, tuple(getattr(method, WIRES_ATTRIBUTE)))


_register_predicate_describer(
    lambda value: _inspect.isfunction(value) and WIRES_ATTRIBUTE in vars(value),
    _describe_wiring,
)

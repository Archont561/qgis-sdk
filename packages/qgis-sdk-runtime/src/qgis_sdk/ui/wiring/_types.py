"""The wiring vocabulary: wires, descriptions, and the signal tables."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, TypeVar

from qgis_sdk.ui.components import Component

__all__ = ["ON_SIGNALS", "Wire", "WiringDescription", "shown"]

T = TypeVar("T", bound=Callable[..., Any])

#: The catalogue signals ``@on(name).<signal>`` accepts, each mapped to the
#: component's subscription method.
ON_SIGNALS: Mapping[str, str] = MappingProxyType(
    {
        "changed": "changed",
        "clicked": "clicked",
        "toggled": "changed",
        "edited": "changed",
        "accepted": "accepted",
        "cancelled": "cancelled",
        "finished": "finished",
        "selected": "changed",
    }
)

#: What ``changed`` means on a plain Qt widget: the first of these it has.
QT_CHANGED = (
    "valueChanged",
    "textChanged",
    "toggled",
    "currentIndexChanged",
    "currentTextChanged",
    "dateTimeChanged",
    "dateChanged",
    "colorChanged",
    "layerChanged",
    "fieldChanged",
    "crsChanged",
    "fileChanged",
    "currentChanged",
)

#: A catalogue signal on a plain Qt widget, where it is not ``changed``.
QT_SIGNALS = {
    "clicked": ("clicked",),
    "toggled": ("toggled",),
    "edited": ("textEdited", "textChanged", "valueChanged"),
    "accepted": ("accepted",),
    "cancelled": ("rejected",),
    "finished": ("finished",),
    "selected": ("itemSelectionChanged", "currentRowChanged", "currentIndexChanged"),
}


@dataclass(frozen=True, slots=True)
class Wire:
    """One connection a method asked for.

    ``target`` is a node name, a stream id, or - for ``@on(component)`` -
    the component prototype declared on the surface class.
    """

    kind: str  # "on" | "subscribe"
    target: str | Component
    signal: str | None = None
    request: Mapping[str, object] = field(default_factory=dict)

    @property
    def shown(self) -> str:
        """How the target reads in a message: the name, or the attribute."""
        return shown(self.target)


@dataclass(frozen=True, slots=True)
class WiringDescription:
    """The UI and stream connections declared on a surface handler."""

    handler: str
    wires: tuple[Wire, ...]


def shown(target: str | Component) -> str:
    if isinstance(target, str):
        return repr(target)
    return target._name or f"<unnamed {type(target).__name__}>"

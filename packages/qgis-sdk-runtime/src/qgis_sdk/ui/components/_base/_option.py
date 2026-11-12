"""The option a picker lists, and what the adapter hands back for a mount."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

__all__ = ["NATIVE_CATALOGUE", "Listener", "NativeRendering", "Option"]

#: The module that builds the widgets. Looked up by name at mount time so
#: that this package stays importable without Qt; ``tests/test_pure_imports``
#: pins this as the one edge from ``ui`` to the adapters.
NATIVE_CATALOGUE = "qgis_sdk.adapters.qgis.components"

Listener = Callable[[Any], None]


@dataclass(frozen=True, slots=True)
class Option:
    """One entry a picker lists: the model value and the label shown for it."""

    id: str
    label: str


class NativeRendering(Protocol):
    """What the adapter hands back for a mounted component.

    ``widget`` is the Qt widget; ``apply`` writes a validated value into it
    (and may refuse one the host cannot represent); ``options`` lists what
    the widget shows, when it owns that list; ``dispose`` disconnects.
    """

    widget: Any

    def apply(self, value: object) -> None: ...

    def options(self) -> tuple[Option, ...] | None: ...

    def dispose(self) -> None: ...

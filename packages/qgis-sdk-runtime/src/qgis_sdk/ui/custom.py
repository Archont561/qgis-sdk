"""``Custom``: any QWidget inside a catalogue tree (decision-55 point 3).

The catalogue is curated, not closed. ``Custom("map", factory)`` places a
widget the author builds themselves - a ``QgsMapCanvas``, a third-party
widget, a legacy panel - among the catalogue's components. ``factory`` is a
callable taking the Qt parent (or none) and returning the widget; it runs
only when the tree is mounted, so a surface using ``Custom`` still builds
under the fake, where the node is recorded and no widget exists. An already
constructed widget is accepted too, for the author who builds it in
``build()`` and accepts that ``build()`` then needs Qt.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

from qgis_sdk.models import QgisSdkUiError

from .components import Component

__all__ = ["Custom"]


class Custom(Component):
    """A node whose widget the author supplies.

    ``widget`` is a callable (``factory(parent)`` or ``factory()``) or a
    widget instance. ``objectName`` is ``custom/<name>``.
    """

    prefix = "custom"

    def __init__(
        self,
        name: str | Callable[..., Any] | Any = None,
        widget: Callable[..., Any] | Any = None,
        *,
        label: str | None = None,
    ) -> None:
        if name is not None and not isinstance(name, str):
            # ``Custom(factory)``: the name comes from the class attribute.
            if widget is not None:
                raise QgisSdkUiError(
                    f"Custom takes a name or a widget first, not both: {name!r}"
                )
            name, widget = None, name
        super().__init__(name, label=label)
        if widget is None:
            raise QgisSdkUiError(f"{self._describe()} needs a widget or a factory")
        self._source = widget
        self._built: Any | None = None

    @property
    def factory(self) -> bool:
        """Whether the widget is built on demand (``True``) or was given built."""
        return callable(self._source) and not _looks_like_widget(self._source)

    def resolve(self, parent: Any = None) -> Any:
        """Produce the widget: call the factory once, or return the instance."""
        if self._built is not None:
            return self._built
        source = self._source
        if self.factory:
            try:
                takes_parent = len(inspect.signature(source).parameters) >= 1
            except (TypeError, ValueError):  # a builtin or a Qt class
                takes_parent = True
            widget = source(parent) if takes_parent else source()
        else:
            widget = source
        if widget is None or not _looks_like_widget(widget):
            raise QgisSdkUiError(
                f"{self._describe()}: the factory must return a QWidget, "
                f"got {type(widget).__name__}"
            )
        self._built = widget
        return widget

    def dispose(self) -> None:
        super().dispose()
        self._built = None

    def snapshot(self) -> dict[str, Any]:
        node = super().snapshot()
        source = self._built if self._built is not None else self._source
        node["widget"] = (
            getattr(source, "__name__", type(source).__name__)
            if self.factory and self._built is None
            else type(source).__name__
        )
        node["built"] = self._built is not None
        return node


def _looks_like_widget(value: object) -> bool:
    return (
        not isinstance(value, type)
        and callable(getattr(value, "setObjectName", None))
        and callable(getattr(value, "setParent", None))
    )

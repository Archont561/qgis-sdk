"""Button, Container and Column."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from qgis_sdk.models import (
    QgisSdkUiError,
)
from qgis_sdk.ui.components._base import Component, split_name_and_children

# -- buttons and containers -------------------------------------------------------------


class Button(Component):
    """A push button; ``clicked(listener)`` subscribes, ``click()`` presses it.

    ``text`` is the caption (the label by default). The widget's
    ``objectName`` is ``buttons/<name>``.
    """

    prefix = "buttons"

    def __init__(
        self,
        name: str | None = None,
        text: str | None = None,
        *,
        label: str | None = None,
    ) -> None:
        super().__init__(name, label=label if label is not None else text)
        self._text = text
        self._listeners: list[Callable[[], None]] = []

    @property
    def text(self) -> str:
        """The caption on the button: ``text``, else the label."""
        return self._text if self._text is not None else self.label

    @text.setter
    def text(self, value: str | None) -> None:
        self._text = value

    def clicked(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Call ``listener()`` on each press; returns the unsubscribe."""
        self._listeners.append(listener)

        def unsubscribe() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return unsubscribe

    def click(self) -> None:
        """Press the button: the fake's way to drive what the user would."""
        for listener in tuple(self._listeners):
            listener()

    def dispose(self) -> None:
        super().dispose()
        self._listeners.clear()

    def snapshot(self) -> dict[str, Any]:
        node = super().snapshot()
        node["text"] = self.text
        return node

    def _from_widget(self, value: object) -> None:
        self.click()


class Container(Component):
    """A component made of others; the base of every layout in the catalogue.

    Children are attached, mounted into the container's layout and disposed
    with it; two children sharing an ``objectName`` are refused at
    construction so a snapshot and a ``find`` are unambiguous.
    """

    def __init__(
        self,
        name: str | Sequence[Component] | None = None,
        children: Sequence[Component] | None = None,
        *,
        label: str | None = None,
    ) -> None:
        name, children = split_name_and_children(type(self).__name__, name, children)
        super().__init__(name, label=label)
        self._children = tuple(children)
        for child in self._children:
            if not isinstance(child, Component):
                raise QgisSdkUiError(
                    f"{self._describe()}: children must be components, "
                    f"got {type(child).__name__}"
                )
        # Children declared on a class get their names after the class body
        # ran, so the clash check runs now for the named ones and again when
        # the tree is attached.
        self._check_children()

    def _check_children(self) -> None:
        seen: set[str] = set()
        for child in self._children:
            if not child.named:
                continue
            if child.object_name in seen:
                raise QgisSdkUiError(
                    f"{self._describe()}: two children named {child.object_name!r}"
                )
            seen.add(child.object_name)

    def _attached(self) -> None:
        self._check_children()

    def children(self) -> tuple[Component, ...]:
        return self._children

    def find(self, name: str) -> Component:
        """The child (at any depth) whose ``name`` matches, or a refusal by name."""
        for child in self._children:
            if child.name == name:
                return child
            if isinstance(child, Container):
                try:
                    return child.find(name)
                except QgisSdkUiError:
                    continue
        raise QgisSdkUiError(f"{self._describe()} has no child named {name!r}")

    def snapshot(self) -> dict[str, Any]:
        node = super().snapshot()
        node["children"] = [child.snapshot() for child in self._children]
        return node


class Column(Container):
    """Components stacked top to bottom; the plain container of the catalogue."""

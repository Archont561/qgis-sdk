"""The catalogue's layouts beside ``Column`` (decision-55 point 3; TASK-96).

Every container here is a :class:`~qgis_sdk.ui.components.Container`: it
holds other components, attaches and disposes them with itself and names
its node by its bare ``name``. ``Row`` lays children out left to right,
``Panel`` is a padded (optionally scrolling) column, ``Group`` a titled box
and ``Tabs`` one page per child with the child's ``label`` as the tab title.
Only ``Tabs`` carries state - which page is current - and like an input it
works before any widget exists.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from qgis_sdk.models import QgisSdkUiError

from .components import Component, Container

__all__ = ["Group", "Panel", "Row", "Tabs"]


class Row(Container):
    """Components laid out left to right."""


class Panel(Container):
    """A padded column; ``scrollable=True`` scrolls when the window is short."""

    def __init__(
        self,
        name: str,
        children: Sequence[Component],
        *,
        label: str | None = None,
        scrollable: bool = False,
    ) -> None:
        super().__init__(name, children, label=label)
        self.scrollable = scrollable

    def snapshot(self) -> dict[str, Any]:
        node = super().snapshot()
        node["scrollable"] = self.scrollable
        return node


class Group(Container):
    """A titled box around its children; the title is the ``label``.

    ``collapsible=True`` renders the QGIS collapsible group box so a long
    dialog can fold a section away; it is a presentation choice, not state.
    """

    def __init__(
        self,
        name: str,
        children: Sequence[Component],
        *,
        label: str | None = None,
        collapsible: bool = False,
    ) -> None:
        super().__init__(name, children, label=label)
        self.collapsible = collapsible

    def snapshot(self) -> dict[str, Any]:
        node = super().snapshot()
        node["collapsible"] = self.collapsible
        return node


class Tabs(Container):
    """One page per child, titled by the child's ``label``.

    ``current()`` is the name of the page shown, ``set_current(name)``
    switches it (an unknown name is refused, nothing changes) and
    ``changed(listener)`` hears every switch, the user's included.
    """

    def __init__(
        self,
        name: str,
        children: Sequence[Component],
        *,
        label: str | None = None,
        current: str | None = None,
    ) -> None:
        super().__init__(name, children, label=label)
        if not self._children:
            raise QgisSdkUiError(f"{self._describe()} needs at least one page")
        self._current = self._children[0].name
        self._listeners: list[Callable[[str], None]] = []
        if current is not None:
            self.set_current(current)

    @property
    def pages(self) -> tuple[str, ...]:
        """The page names in tab order."""
        return tuple(child.name for child in self._children)

    def current(self) -> str:
        """The name of the page currently shown."""
        return self._current

    def set_current(self, name: str) -> None:
        """Show the page called ``name``; an unknown name is refused."""
        if name not in self.pages:
            raise QgisSdkUiError(
                f"{self._describe()} has no page {name!r}; it has: "
                + ", ".join(self.pages)
            )
        self._commit(name)

    def changed(self, listener: Callable[[str], None]) -> Callable[[], None]:
        """Call ``listener(name)`` on each switch; returns the unsubscribe."""
        self._listeners.append(listener)

        def unsubscribe() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return unsubscribe

    def dispose(self) -> None:
        super().dispose()
        self._listeners.clear()

    def snapshot(self) -> dict[str, Any]:
        node = super().snapshot()
        node["current"] = self._current
        return node

    def _state(self) -> object:
        return self.pages.index(self._current)

    def _from_widget(self, value: object) -> None:
        if self._syncing:
            return
        if isinstance(value, int) and 0 <= value < len(self._children):
            self._store(self.pages[value])

    def _commit(self, name: str) -> None:
        if self._native is not None and not self._syncing:
            self._syncing = True
            try:
                self._native.apply(self.pages.index(name))
            finally:
                self._syncing = False
        self._store(name)

    def _store(self, name: str) -> None:
        if name == self._current:
            return
        self._current = name
        for listener in tuple(self._listeners):
            listener(name)

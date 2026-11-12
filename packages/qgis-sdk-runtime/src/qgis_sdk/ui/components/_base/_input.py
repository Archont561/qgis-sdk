"""Input: a component that holds one value, validated against a field spec."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar

from qgis_sdk.models import FileRef
from qgis_sdk.ui.form_fields import FieldSpec, coerce_value, label_for

from ._component import Component
from ._option import Listener

__all__ = ["Input"]


class _InputMixin1:
    @property
    def spec(self) -> FieldSpec:
        """The field specification ``set_value`` validates against."""
        return self._spec()

    # -- value ----------------------------------------------------------------------

    def value(self) -> Any:
        """The current value as a model: a layer id, a ``FileRef``, a number..."""
        return self._value

    def set_value(self, value: object) -> None:
        """Validate ``value``, write it to the widget and tell the listeners.

        A value the component's rule refuses raises
        :class:`~qgis_sdk.models.QgisSdkFormError` and changes nothing.
        """
        coerced = coerce_value(self._spec(), value, owner=self._describe())
        coerced = self._accept(coerced)
        self._commit(coerced)

    def changed(self, listener: Listener) -> Callable[[], None]:
        """Call ``listener(value)`` after each change; returns the unsubscribe."""
        self._listeners.append(listener)

        def unsubscribe() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return unsubscribe

    def refresh(self) -> None:
        """Re-read what the component lists; a value no longer listed becomes ``None``."""
        self._refreshed()

    # -- for subclasses -------------------------------------------------------------

    def _default(self) -> object:
        return None

    def _spec(self) -> FieldSpec:
        return FieldSpec(
            name=self._name or "",
            label=self._label or (label_for(self._name) if self._name else ""),
            widget=self.kind,
            required=False,
            nullable=self._default() is None,
            details=self._details(),
        )

    def _details(self) -> dict[str, Any]:
        return {}

    def _accept(self, value: object) -> object:
        """A subclass's rule beyond the field spec's; returns the value to commit."""
        return value

    def _refreshed(self) -> None:
        """Hook: re-list and reconcile the value."""

    def _state(self) -> object:
        return self._value

    def _commit(self, value: object) -> None:
        """Write ``value`` to the widget, store it and notify when it changed."""
        if self._native is not None and not self._syncing:
            self._syncing = True
            try:
                self._native.apply(value)
            finally:
                self._syncing = False
        self._store(value)

    def _store(self, value: object) -> None:
        if value == self._value and type(value) is type(self._value):
            return
        self._value = value
        for listener in tuple(self._listeners):
            listener(value)


class _InputMixin2:
    def _from_widget(self, value: object) -> None:
        """The widget changed under the user: adopt the value the adapter read."""
        if self._syncing:
            return
        self._store(value)


class Input(_InputMixin1, _InputMixin2, Component):
    """A component that holds one value: the catalogue's eleven inputs.

    Subclasses set ``kind`` (a name from ``parameter_kinds()``) and build the
    :class:`FieldSpec` that validates ``set_value``. ``name`` is the
    handler's parameter name; ``required`` marks a field a form refuses to
    submit empty.
    """

    prefix = "form"
    kind: ClassVar[str]

    def __init__(
        self,
        name: str | None = None,
        *,
        label: str | None = None,
        value: object = None,
        required: bool = False,
    ) -> None:
        super().__init__(name, label=label)
        self.required = required
        self._listeners: list[Listener] = []
        self._value: object = self._default()
        if value is not None:
            self.set_value(value)

    def dispose(self) -> None:
        super().dispose()
        self._listeners.clear()

    def snapshot(self) -> dict[str, Any]:
        value = self._value
        node = super().snapshot()
        node["kind"] = self.kind
        node["value"] = value.to_wire() if isinstance(value, FileRef) else value
        if self.required:
            node["required"] = True
        node.update(self._details())
        return node

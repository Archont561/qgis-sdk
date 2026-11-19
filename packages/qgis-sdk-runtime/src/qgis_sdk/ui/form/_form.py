"""The ``Form`` component and the catalogue input each widget maps to."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING, Any

from qgis_sdk.models import QgisSdkUiError
from qgis_sdk.ui.components import Component, Input

if TYPE_CHECKING:
    from qgis_sdk.core.contexts import UiContext
    from qgis_sdk.declarations import ActionDescription

__all__ = ["Form"]

FormListener = Callable[[str, Any], None]


class Form(Component):
    """Inputs for one action, submitted through ``ctx.actions``.

    ``fields`` are :class:`Input` components in display order; ``action_id``
    is what :meth:`submit` calls (set by :meth:`for_action`, or by hand for
    a form built from fields). The widget's ``objectName`` is the form's
    ``name`` (``form`` by default), its fields' ``form/<field>``.

    The fields may be unnamed when the form is built - inputs declared on a
    surface class get their names after the class body ran - so the form
    keys them by name the first time anything asks (``fields``, ``values()``,
    ``attach``), and refuses two of one name then.

    Args:
        fields: One input per handler parameter.
        name: The form's name in the surface.
        action_id: The action a submit runs.
        label: The text shown above it, or ``None`` for none.
    """

    def __init__(
        self,
        fields: Sequence[Input],
        *,
        name: str = "form",
        action_id: str | None = None,
        label: str | None = None,
    ) -> None:
        super().__init__(name, label=label)
        self.action_id = action_id
        self._inputs: tuple[Input, ...] = tuple(fields)
        for field in self._inputs:
            if not isinstance(field, Input):
                shown = f" {field._name!r}" if isinstance(field, Component) else ""
                raise QgisSdkUiError(
                    f"{self._describe()}: {type(field).__name__}{shown} is "
                    "not an input; a form holds the catalogue's inputs only"
                )
        self._listeners: list[FormListener] = []
        self._unsubscribes = [
            field.changed(_FieldRelay(self, field)) for field in self._inputs
        ]
        self._by_name: dict[str, Input] | None = None
        if all(field.named for field in self._inputs):
            _ = self._fields  # named already: refuse a duplicate now

    @classmethod
    def from_schema(
        cls,
        schema: Mapping[str, Any] | ActionDescription,
        *,
        name: str = "form",
        action_id: str | None = None,
        initial: Mapping[str, object] | None = None,
    ) -> Form:
        """Build the inputs a request schema (or an action's description) declares.

        The kind of each field comes from the ``x-qgis-sdk`` annotation the
        describer put on it; a ``FieldInput`` follows the layer field its
        ``of`` names, which must be in the same schema.

        Args:
            schema: The request schema or action description to build from.
            name: The form's name in the surface.
            action_id: The action a submit runs.
            initial: The values the fields start with.
        """
        from ._construction import from_schema

        return from_schema(cls, schema, name=name, action_id=action_id, initial=initial)

    @classmethod
    def for_action(
        cls,
        ctx: UiContext,
        action_id: str,
        *,
        initial: Mapping[str, object] | None = None,
        name: str = "form",
    ) -> Form:
        """The form for one of the plugin's actions, attached to ``ctx``.

        ``initial`` sets field values first (a name the action lacks is
        refused), typically the surface's ``self.initial``.

        Args:
            ctx: The context the form is attached to.
            action_id: The action to build the form for.
            initial: The values the fields start with.
            name: The form's name in the surface.
        """
        from ._construction import for_action

        return for_action(cls, ctx, action_id, initial=initial, name=name)

    # -- fields ---------------------------------------------------------------------

    @property
    def _fields(self) -> dict[str, Input]:
        """The inputs by name, resolved once every input has its name."""
        if self._by_name is None:
            by_name: dict[str, Input] = {}
            for field in self._inputs:
                if field.name in by_name:
                    raise QgisSdkUiError(
                        f"{self._describe()}: two fields named {field.name!r}"
                    )
                by_name[field.name] = field
            self._by_name = by_name
        return self._by_name

    @property
    def fields(self) -> tuple[Input, ...]:
        return tuple(self._fields.values())

    def field(self, name: str) -> Input:
        """The input called ``name``, or a refusal naming the form's fields.

        Args:
            name: The parameter whose input is read.
        """
        try:
            return self._fields[name]
        except KeyError:
            known = ", ".join(self._fields) or "none"
            raise QgisSdkUiError(
                f"{self._describe()} has no field {name!r}; it has: {known}"
            ) from None

    def children(self) -> tuple[Component, ...]:
        return self.fields

    # -- values ---------------------------------------------------------------------

    def values(self) -> dict[str, Any]:
        """Every field's current value, by name, in display order."""
        from ._values import values_of

        return values_of(self)

    def set_values(self, values: Mapping[str, object]) -> None:
        """Set several fields at once; an unknown name is refused before any change.

        Args:
            values: The values to write, by parameter name.
        """
        from ._values import set_values

        set_values(self, values)

    def changed(self, listener: FormListener) -> Callable[[], None]:
        """Call ``listener(name, value)`` after any field changes; returns the unsubscribe.

        Args:
            listener: What each change is handed to.
        """
        from ._values import changed

        return changed(self, listener)

    def submit(self) -> Any:
        """Dispatch ``action_id`` with the current values through ``ctx.actions``.

        An empty required field is refused here by name; the action's own
        coercion refuses the rest. Optional fields left empty are not sent,
        so the handler's defaults apply.
        """
        from ._values import submit

        return submit(self)

    # -- lifecycle ------------------------------------------------------------------

    def dispose(self) -> None:
        super().dispose()
        self._listeners.clear()

    def snapshot(self) -> dict[str, Any]:
        node = super().snapshot()
        if self.action_id is not None:
            node["action"] = self.action_id
        node["fields"] = [field.snapshot() for field in self._fields.values()]
        return node

    def _notify(self, name: str, value: Any) -> None:
        for listener in tuple(self._listeners):
            listener(name, value)


class _FieldRelay:
    """A field's change, reported to its form as ``(name, value)``.

    An object rather than a closure so that ``deepcopy`` of a declared form
    (one copy per window) copies the link too: the copied field then reports
    to the copied form, not the prototype. The name is read when the change
    happens, by which time a declared input has it.
    """

    def __init__(self, form: Form, field: Input) -> None:
        self.form = form
        self.field = field

    def __call__(self, value: Any) -> None:
        self.form._notify(self.field.name, value)

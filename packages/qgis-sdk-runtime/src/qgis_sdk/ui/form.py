"""``Form``: an action's inputs as catalogue components (decision-55 point 4).

A form is a helper, not a popup. ``Form.for_action(ctx, "buffer",
initial={...})`` builds one input per field of the declared action, from the
same ``form_fields`` rule a page's schema and the 0.5 declared dialogs used;
``Form.from_schema(schema)`` does the same from a request schema and
``Form(fields=[...])`` from components an author placed by hand. All three
produce the same tree: ``values()`` reads every field as a model,
``changed(listener)`` reports ``(name, value)``, ``submit()`` dispatches
through ``ctx.actions`` with the view's authority. Mounted, a form is a
``QWidget`` with a ``QFormLayout`` of labelled rows and no buttons - place
a :class:`~qgis_sdk.ui.components.Button` next to it.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING, Any

from qgis_sdk.models import QgisSdkFormError, QgisSdkUiError

from .components import (
    Choice,
    Colour,
    Component,
    CrsPicker,
    DirectoryInput,
    Distance,
    FieldPicker,
    FileInput,
    Input,
    LayerPicker,
    Number,
    Text,
    Toggle,
)
from .form_fields import FieldSpec, schema_fields

if TYPE_CHECKING:
    from qgis_sdk.core.contexts import UiContext
    from qgis_sdk.declarations import ActionDescription

__all__ = ["Form", "input_for"]

FormListener = Callable[[str, Any], None]


class Form(Component):
    """Inputs for one action, submitted through ``ctx.actions``.

    ``fields`` are :class:`Input` components in display order; ``action_id``
    is what :meth:`submit` calls (set by :meth:`for_action`, or by hand for
    a form built from fields). The widget's ``objectName`` is the form's
    ``name`` (``form`` by default), its fields' ``form/<field>``.
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
        self._fields: dict[str, Input] = {}
        for field in fields:
            if not isinstance(field, Input):
                raise QgisSdkUiError(
                    f"{self._describe()}: {type(field).__name__} {field.name!r} is "
                    "not an input; a form holds the catalogue's inputs only"
                )
            if field.name in self._fields:
                raise QgisSdkUiError(
                    f"{self._describe()}: two fields named {field.name!r}"
                )
            self._fields[field.name] = field
        self._listeners: list[FormListener] = []
        self._unsubscribes = [
            field.changed(_relay(self, field.name)) for field in self._fields.values()
        ]

    # -- construction ---------------------------------------------------------------

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
        """
        request = schema if isinstance(schema, Mapping) else schema.request
        if action_id is None and not isinstance(schema, Mapping):
            action_id = schema.id
        owner = f"action {action_id!r}" if action_id else "form"
        specs = schema_fields(request, owner=owner)
        form = cls(_inputs(specs, owner=owner), name=name, action_id=action_id)
        if initial:
            form.set_values(initial)
        return form

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
        """
        action = ctx.actions.describe(action_id)
        form = cls.from_schema(action, name=name, action_id=action.id)
        form.attach(ctx)
        if initial:
            form.set_values(initial)
        return form

    # -- fields ---------------------------------------------------------------------

    @property
    def fields(self) -> tuple[Input, ...]:
        return tuple(self._fields.values())

    def field(self, name: str) -> Input:
        """The input called ``name``, or a refusal naming the form's fields."""
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
        return {name: field.value() for name, field in self._fields.items()}

    def set_values(self, values: Mapping[str, object]) -> None:
        """Set several fields at once; an unknown name is refused before any change."""
        unknown = sorted(set(values) - set(self._fields))
        if unknown:
            raise QgisSdkUiError(
                f"{self._describe()} has no field(s) {', '.join(map(repr, unknown))}"
            )
        for name, value in values.items():
            self._fields[name].set_value(value)

    def changed(self, listener: FormListener) -> Callable[[], None]:
        """Call ``listener(name, value)`` after any field changes; returns the unsubscribe."""
        self._listeners.append(listener)

        def unsubscribe() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return unsubscribe

    def submit(self) -> Any:
        """Dispatch ``action_id`` with the current values through ``ctx.actions``.

        An empty required field is refused here by name; the action's own
        coercion refuses the rest. Optional fields left empty are not sent,
        so the handler's defaults apply.
        """
        if self.action_id is None:
            raise QgisSdkUiError(
                f"{self._describe()} has no action to submit to; build it with "
                "Form.for_action or pass action_id="
            )
        actions = self._require_ctx("actions")
        values = self.values()
        missing = [
            name
            for name, field in self._fields.items()
            if field.required and values[name] in (None, "")
        ]
        if missing:
            raise QgisSdkFormError(
                f"{self._describe()}: {', '.join(missing)} "
                f"{'is' if len(missing) == 1 else 'are'} required"
            )
        return actions.call(
            self.action_id, **{k: v for k, v in values.items() if v is not None}
        )

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


def _relay(form: Form, name: str) -> Callable[[Any], None]:
    return lambda value: form._notify(name, value)


def input_for(spec: FieldSpec, *, of: LayerPicker | None = None) -> Input:
    """The catalogue input that renders ``spec``; a ``field`` spec needs its ``of``."""
    name, label, required = spec.name, spec.label, spec.required
    details = spec.details
    widget = spec.widget
    if widget == "text":
        return Text(name, label=label, required=required)
    if widget == "boolean":
        return Toggle(name, label=label, required=required)
    if widget == "integer":
        return Number(name, integer=True, label=label, required=required)
    if widget == "number":
        return Number(name, label=label, required=required)
    if widget == "range":
        return Number(
            name,
            range=(details["minimum"], details["maximum"]),
            step=details.get("step"),
            label=label,
            required=required,
        )
    if widget == "metres":
        return Distance(name, label=label, required=required)
    if widget == "choice":
        return Choice(name, options=spec.choices, label=label, required=required)
    if widget == "colour":
        return Colour(
            name, alpha=details.get("alpha", True), label=label, required=required
        )
    if widget == "layer":
        return LayerPicker(name, label=label, required=required)
    if widget == "crs":
        return CrsPicker(name, label=label, required=required)
    if widget == "file":
        return FileInput(
            name,
            filters=tuple(details.get("filters", ())),
            label=label,
            required=required,
        )
    if widget == "directory":
        return DirectoryInput(name, label=label, required=required)
    if widget == "field":
        if of is None:
            raise QgisSdkFormError(
                f"field {name}: a field picker needs the layer picker its "
                f"'of' names ({details.get('of')!r})"
            )
        return FieldPicker(name, of=of, label=label, required=required)
    raise QgisSdkFormError(f"field {name}: no catalogue input for widget {widget!r}")


def _inputs(specs: Sequence[FieldSpec], *, owner: str) -> list[Input]:
    """Build the inputs for ``specs``, wiring each field picker to its layer."""
    layers: dict[str, LayerPicker] = {}
    inputs: list[Input] = []
    pending: list[tuple[int, FieldSpec]] = []
    for spec in specs:
        if spec.widget == "field":
            pending.append((len(inputs), spec))
            inputs.append(None)  # type: ignore[arg-type] - filled below
            continue
        component = input_for(spec)
        if isinstance(component, LayerPicker):
            layers[spec.name] = component
        inputs.append(component)
    for index, spec in pending:
        of = layers.get(str(spec.details.get("of")))
        if of is None:
            raise QgisSdkFormError(
                f"{owner}: field {spec.name} follows {spec.details.get('of')!r}, "
                "which is not a layer input of this form"
            )
        inputs[index] = input_for(spec, of=of)
    return inputs

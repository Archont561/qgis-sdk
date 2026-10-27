"""Component and Input: state, listeners, snapshots and the mount by catalogue name."""

from __future__ import annotations

import importlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Protocol

from qgis_sdk.models import (
    FileRef,
    QgisSdkUiError,
)
from qgis_sdk.ui.form_fields import FieldSpec, coerce_value, label_for

if TYPE_CHECKING:
    from qgis_sdk.core.contexts import UiContext


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


def split_name_and_children(
    kind: str, name: object, children: Sequence[Component] | None
) -> tuple[str | None, Sequence[Component]]:
    """Read ``Row("x", [a, b])``, ``Row([a, b])`` and ``Row(children=[a, b])`` alike.

    The first positional of a container is its name when it is a string and
    its children when it is a sequence, so the declarative form
    (``tools = Row([run, clear])``) needs no keyword.
    """
    if name is None or isinstance(name, str):
        return name, tuple(children or ())
    if children is not None:
        raise QgisSdkUiError(
            f"{kind} takes a name or children first, not both: {name!r} and {children!r}"
        )
    if isinstance(name, Sequence):
        return None, tuple(name)
    raise QgisSdkUiError(
        f"{kind} needs a name (letters, digits, underscores) or children, got {name!r}"
    )


class Component:
    """One node of a surface: a named thing with a widget on demand.

    ``name`` is what the node is called in ``objectName`` (``form/<name>``
    for an :class:`Input`, ``buttons/<name>`` for a :class:`Button`, the
    bare name for a container), which is how a test or an agent selects the
    widget. A component assigned to a class attribute of a surface may leave
    the name out and takes the attribute's (``go = Button(text="Go")`` is
    ``buttons/go``); until it has one, anything that needs the name refuses.
    ``attach(ctx)`` binds it to a surface's :class:`UiContext`, ``mount()``
    builds the widget, ``snapshot()`` is its node in a UI snapshot
    (decision-51).
    """

    #: ``objectName`` prefix; a container uses its bare name.
    prefix: ClassVar[str] = ""

    def __init__(self, name: str | None = None, *, label: str | None = None) -> None:
        self._name: str | None = None
        if name is not None:
            self._name = self._valid_name(name)
        self._attribute: str | None = None
        self._label = label
        self._ctx: UiContext | None = None
        self._native: NativeRendering | None = None
        self._syncing = False

    def __set_name__(self, owner: type, attribute: str) -> None:
        """A component declared on a class is called after its attribute.

        The attribute is remembered either way, so a snapshot can say which
        class attribute a node came from when its name was given explicitly.
        """
        self._attribute = attribute
        if self._name is None:
            self._name = self._valid_name(attribute)

    # -- identity -------------------------------------------------------------------

    @property
    def name(self) -> str:
        """The node's name; refused while the component has none yet."""
        if self._name is None:
            raise QgisSdkUiError(
                f"{self._describe()} has no name yet: pass one, or declare the "
                "component as a class attribute of a surface so it takes the "
                "attribute's name"
            )
        return self._name

    @property
    def named(self) -> bool:
        """Whether the component has its name already."""
        return self._name is not None

    @property
    def attribute(self) -> str | None:
        """The surface class attribute this component was declared on, if any."""
        return self._attribute

    @property
    def label(self) -> str:
        """The caption shown for the node; derived from the name unless given."""
        return self._label if self._label is not None else label_for(self.name)

    @label.setter
    def label(self, value: str | None) -> None:
        self._label = value

    @property
    def object_name(self) -> str:
        """The ``objectName`` of the widget: ``<prefix>/<name>`` or the name."""
        return f"{self.prefix}/{self.name}" if self.prefix else self.name

    def _valid_name(self, name: object) -> str:
        if not isinstance(name, str) or not name or not name.replace("_", "").isalnum():
            raise QgisSdkUiError(
                f"{type(self).__name__} needs a name "
                f"(letters, digits, underscores), got {name!r}"
            )
        return name

    @property
    def ctx(self) -> UiContext | None:
        return self._ctx

    @property
    def attached(self) -> bool:
        return self._ctx is not None

    @property
    def mounted(self) -> bool:
        return self._native is not None

    @property
    def widget(self) -> Any:
        """The Qt widget, once :meth:`mount` built it."""
        if self._native is None:
            raise QgisSdkUiError(f"{self._describe()} is not mounted")
        return self._native.widget

    def children(self) -> tuple[Component, ...]:
        """The components this one contains, in layout order."""
        return ()

    # -- lifecycle ------------------------------------------------------------------

    def attach(self, ctx: UiContext) -> Component:
        """Bind the component (and its children) to a surface's context.

        Pickers list through the context's services from here on and a
        ``FileInput`` can mint refs. The context's scope closing detaches
        the component and drops every listener. Returns ``self``.
        """
        if self._ctx is not None:
            if self._ctx is ctx:
                return self
            raise QgisSdkUiError(f"{self._describe()} is already attached")
        _ = self.name  # a node without a name cannot be found or snapshotted
        self._ctx = ctx
        ctx.scope.on_close(self.dispose)
        for child in self.children():
            child.attach(ctx)
        self._attached()
        return self

    def mount(self, parent: Any = None) -> Any:
        """Build the widget mirroring the state and return it; idempotent.

        The adapter module imports Qt; without QGIS this refuses by name
        instead of raising an ``ImportError`` from deep inside Qt.
        """
        if self._native is not None:
            return self._native.widget
        try:
            catalogue = importlib.import_module(NATIVE_CATALOGUE)
        except ImportError as error:
            raise QgisSdkUiError(
                f"mounting {self._describe()} needs QGIS: {error}"
            ) from error
        rendering = catalogue.mount(self, parent, on_change=self._from_widget)
        rendering.widget.setObjectName(self.object_name)
        self._syncing = True
        try:
            rendering.apply(self._state())
        finally:
            self._syncing = False
        self._native = rendering
        return rendering.widget

    def dispose(self) -> None:
        """Forget the context, the widget and every listener."""
        if self._native is not None:
            self._native.dispose()
            self._native = None
        for child in self.children():
            child.dispose()
        self._ctx = None
        self._detached()

    def snapshot(self) -> dict[str, Any]:
        """The semantic node of this component in a UI snapshot (decision-51)."""
        node = {
            "type": type(self).__name__,
            "name": self.name,
            "label": self.label,
            "objectName": self.object_name,
        }
        if self._attribute is not None:
            node["attribute"] = self._attribute
        return node

    # -- for subclasses -------------------------------------------------------------

    def _state(self) -> object:
        """What ``mount`` writes into the fresh widget."""
        return None

    def _from_widget(self, value: object) -> None:
        """Hook: the widget reported ``value`` under the user."""

    def _attached(self) -> None:
        """Hook: the context is bound."""

    def _detached(self) -> None:
        """Hook: the context is gone."""

    def _describe(self) -> str:
        if self._name is None:
            return f"unnamed {type(self).__name__}"
        return f"{type(self).__name__} {self._name!r}"

    def _require_ctx(self, capability: str) -> Any:
        if self._ctx is None:
            raise QgisSdkUiError(
                f"{self._describe()} must be attached to a surface context "
                f"before it can use {capability}"
            )
        if not self._ctx.has(capability):
            raise QgisSdkUiError(
                f"{self._describe()} needs ctx.{capability}, which this host "
                "does not provide"
            )
        return getattr(self._ctx, capability)


class Input(Component):
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

    def _from_widget(self, value: object) -> None:
        """The widget changed under the user: adopt the value the adapter read."""
        if self._syncing:
            return
        self._store(value)

"""Component: state, listeners, snapshots and the mount by catalogue name."""

from __future__ import annotations

import importlib
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, ClassVar

from qgis_sdk.models import QgisSdkUiError
from qgis_sdk.ui.form_fields import label_for

from ._option import NATIVE_CATALOGUE, NativeRendering

if TYPE_CHECKING:
    from qgis_sdk.core.contexts import UiContext

__all__ = ["Component", "split_name_and_children"]


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


class _ComponentMixin1:
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


class _ComponentMixin2:
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


class Component(_ComponentMixin1, _ComponentMixin2):
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

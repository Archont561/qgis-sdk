"""The catalogue's input components (decision-55 point 3).

A component is *state first, widget second*. ``LayerPicker("layer")`` holds
a layer id, ``FileInput("source")`` a :class:`~qgis_sdk.models.FileRef`,
``Number("count", range=(0, 10))`` an ``int`` - models, never Qt types -
and ``value()``/``set_value()``/``changed()`` work before any widget exists.
That state is the fake rendering a pure test asserts on and the semantic
node a UI snapshot shows (decision-51). ``mount()`` builds the QGIS widget
that mirrors the state (``QgsMapLayerComboBox``, ``QgsFileWidget``,
``QgsColorButton``...) through :mod:`qgis_sdk.adapters.qgis.components`,
the one module here that imports Qt, and only when asked: importing
``qgis_sdk.ui`` loads no Qt.

Two rules hold under both renderings, and the contract tests run the same
assertions against each:

* ``set_value`` refuses what a declared form would refuse, with the same
  words (:func:`qgis_sdk.ui.form_fields.coerce_value`), and a refused value
  changes nothing.
* ``attach(ctx)`` binds the component to a surface's :class:`UiContext`:
  pickers list through ``ctx.layers``/``ctx.project``, ``FileInput`` mints
  refs through ``ctx.files``, and every listener is dropped when the
  context's scope closes.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from os import PathLike
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Literal, Protocol

from qgis_sdk.models import (
    FileRef,
    QgisSdkBridgeRefusalError,
    QgisSdkFormError,
    QgisSdkLayerNotFoundError,
    QgisSdkUiError,
)

from .form_fields import FieldSpec, coerce_value, label_for

if TYPE_CHECKING:
    from qgis_sdk.core.contexts import UiContext

__all__ = [
    "Button",
    "Choice",
    "Colour",
    "Column",
    "Component",
    "Container",
    "CrsPicker",
    "DirectoryInput",
    "Distance",
    "FieldPicker",
    "FileInput",
    "Input",
    "LayerPicker",
    "Number",
    "Option",
    "Text",
    "Toggle",
    "split_name_and_children",
]

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


# -- plain values --------------------------------------------------------------------


class Text(Input):
    """A line of text; the value is a ``str`` (``""`` when empty)."""

    kind = "text"

    def _default(self) -> object:
        return ""


class Toggle(Input):
    """A check box; the value is a ``bool``."""

    kind = "boolean"

    def _default(self) -> object:
        return False


class Number(Input):
    """A number, bounded when ``range=(low, high)`` is given.

    An integral range (or ``integer=True``) stores an ``int`` and renders a
    spin box; otherwise the value is a ``float``. ``step`` is the spin box
    increment.
    """

    def __init__(
        self,
        name: str | None = None,
        *,
        range: tuple[float, float] | None = None,
        step: float | None = None,
        integer: bool | None = None,
        label: str | None = None,
        value: object = None,
        required: bool = False,
    ) -> None:
        if range is not None:
            low, high = range
            if low > high:
                raise QgisSdkUiError(
                    f"Number {name!r}: range low {low!r} is above high {high!r}"
                )
            integral = isinstance(low, int) and isinstance(high, int)
            if integer is None:
                integer = integral
            elif integer and not integral:
                raise QgisSdkUiError(
                    f"Number {name!r}: an integer range needs integer bounds"
                )
        self.range = range
        self.step = step
        self.integer = bool(integer)
        super().__init__(name, label=label, value=value, required=required)

    @property
    def kind(self) -> str:  # type: ignore[override]
        if self.range is not None:
            return "range"
        return "integer" if self.integer else "number"

    def _default(self) -> object:
        low = self.range[0] if self.range is not None else 0
        return int(low) if self.integer else float(low)

    def _details(self) -> dict[str, Any]:
        details: dict[str, Any] = {}
        if self.range is not None:
            details["minimum"], details["maximum"] = self.range
        if self.step is not None:
            details["step"] = self.step
        return details


class Distance(Input):
    """A distance in metres, 0 or more; the value is a ``float``."""

    kind = "metres"

    def _default(self) -> object:
        return 0.0


class Choice(Input):
    """One of ``options``; the value is the chosen string, the first by default."""

    kind = "choice"

    def __init__(
        self,
        name: str | None = None,
        *,
        options: Sequence[str],
        label: str | None = None,
        value: object = None,
        required: bool = False,
    ) -> None:
        self.options = tuple(options)
        if not self.options:
            raise QgisSdkUiError(f"Choice {name!r} needs at least one option")
        super().__init__(name, label=label, value=value, required=required)

    def _default(self) -> object:
        return self.options[0]

    def _spec(self) -> FieldSpec:
        return FieldSpec(
            name=self._name or "",
            label=self._label or (label_for(self._name) if self._name else ""),
            widget="choice",
            required=True,
            choices=self.options,
        )

    def _details(self) -> dict[str, Any]:
        return {"options": list(self.options)}


class Colour(Input):
    """A colour as ``#rrggbb`` or, with ``alpha`` (the default), ``#rrggbbaa``."""

    kind = "colour"

    def __init__(
        self,
        name: str | None = None,
        *,
        alpha: bool = True,
        label: str | None = None,
        value: object = None,
        required: bool = False,
    ) -> None:
        self.alpha = alpha
        super().__init__(name, label=label, value=value, required=required)

    def _default(self) -> object:
        return "#000000ff" if self.alpha else "#000000"

    def _accept(self, value: object) -> object:
        text = str(value)
        if not self.alpha and len(text) == 9:
            raise QgisSdkFormError(
                f"{self._describe()}: field {self.name} expects an opaque "
                "#RRGGBB colour"
            )
        return text

    def _details(self) -> dict[str, Any]:
        return {"alpha": self.alpha}


# -- pickers --------------------------------------------------------------------------


class _Picker(Input):
    """A component that chooses among listed options; the value is an id or ``None``."""

    def options(self) -> tuple[Option, ...]:
        """What the picker currently lists, in display order."""
        if self._native is not None:
            listed = self._native.options()
            if listed is not None:
                return listed
        return self._list()

    def _list(self) -> tuple[Option, ...]:
        return ()

    def _refreshed(self) -> None:
        if self._value is not None and self._value not in {
            option.id for option in self.options()
        }:
            self._commit(None)

    def _snapshot_options(self) -> list[dict[str, str]]:
        return [{"id": option.id, "label": option.label} for option in self.options()]


class LayerPicker(_Picker):
    """A layer of the open project; the value is its layer id or ``None``.

    ``kind`` filters what is listed: ``"vector"`` (the default), ``"raster"``
    or ``"any"``. Natively this is ``QgsMapLayerComboBox``, which follows the
    project on its own; under the fake the list comes from ``ctx.project``
    and ``ctx.layers`` (vector layers, until the all-layer-types service
    lands) and :meth:`refresh` re-reads it.
    """

    kind = "layer"

    def __init__(
        self,
        name: str | None = None,
        *,
        kind: Literal["vector", "raster", "any"] = "vector",
        label: str | None = None,
        value: object = None,
        required: bool = False,
    ) -> None:
        if kind not in ("vector", "raster", "any"):
            raise QgisSdkUiError(
                f"LayerPicker {name!r}: kind must be vector, raster or any, got {kind!r}"
            )
        self.layer_kind = kind
        super().__init__(name, label=label, value=value, required=required)

    def _list(self) -> tuple[Option, ...]:
        ctx = self._ctx
        if ctx is None or not ctx.has("layers") or self.layer_kind == "raster":
            return ()
        ids: Iterable[str]
        if ctx.has("project"):
            ids = ctx.project.layer_ids()
        else:
            ids = (info.id for info in ctx.layers.list_layers())
        listed: list[Option] = []
        for layer_id in ids:
            try:
                info = ctx.layers.layer(layer_id)
            except QgisSdkLayerNotFoundError:
                continue
            listed.append(Option(id=info.id, label=info.name))
        return tuple(listed)

    def _accept(self, value: object) -> object:
        if value is None:
            return None
        if value not in {option.id for option in self.options()}:
            raise QgisSdkFormError(
                f"{self._describe()}: layer {value!r} is not in the project"
            )
        return value

    def _details(self) -> dict[str, Any]:
        return {"layers": self.layer_kind}

    def snapshot(self) -> dict[str, Any]:
        node = super().snapshot()
        node["options"] = self._snapshot_options()
        return node


class FieldPicker(_Picker):
    """A field of the layer another picker chose; the value is the field name or ``None``.

    ``of`` is the :class:`LayerPicker` to follow: when its layer changes the
    field list is re-read and a field the new layer lacks is dropped.
    """

    kind = "field"

    def __init__(
        self,
        name: str | None = None,
        *,
        of: LayerPicker,
        label: str | None = None,
        value: object = None,
        required: bool = False,
    ) -> None:
        if not isinstance(of, LayerPicker):
            raise QgisSdkUiError(f"FieldPicker {name!r}: of= must be a LayerPicker")
        self.of = of
        self._unfollow = of.changed(lambda _layer: self.refresh())
        super().__init__(name, label=label, value=value, required=required)

    def _list(self) -> tuple[Option, ...]:
        ctx = self._ctx
        layer_id = self.of.value()
        if ctx is None or layer_id is None or not ctx.has("layers"):
            return ()
        try:
            info = ctx.layers.layer(layer_id)
        except QgisSdkLayerNotFoundError:
            return ()
        return tuple(Option(id=name, label=name) for name in info.field_names)

    def _refreshed(self) -> None:
        if self._native is not None:
            self._syncing = True
            try:
                self._native.apply(self._value)
            finally:
                self._syncing = False
        super()._refreshed()

    def _accept(self, value: object) -> object:
        if value is None:
            return None
        if value not in {option.id for option in self.options()}:
            raise QgisSdkFormError(
                f"{self._describe()}: {value!r} is not a field of the chosen layer"
            )
        return value

    def _detached(self) -> None:
        self._unfollow()

    def _details(self) -> dict[str, Any]:
        return {"of": self.of.name}

    def snapshot(self) -> dict[str, Any]:
        node = super().snapshot()
        node["options"] = self._snapshot_options()
        return node


class CrsPicker(Input):
    """A coordinate reference system; the value is its authority id (``EPSG:4326``) or ``None``."""

    kind = "crs"

    def _accept(self, value: object) -> object:
        if value is None:
            return None
        authority, separator, code = str(value).partition(":")
        if not separator or not authority.strip() or not code.strip():
            raise QgisSdkFormError(
                f"{self._describe()}: field {self.name} expects an authority id "
                f"such as 'EPSG:4326', got {value!r}"
            )
        return f"{authority.strip().upper()}:{code.strip()}"


# -- files ----------------------------------------------------------------------------


class _RefInput(Input):
    """A path chosen by the user, held as the ``FileRef`` ``ctx.files`` minted."""

    def set_path(self, path: str | PathLike[str]) -> None:
        """Mint a ref for ``path`` through ``ctx.files`` and make it the value."""
        files = self._require_ctx("files")
        try:
            ref = self._grant(files, Path(path))
        except (QgisSdkBridgeRefusalError, OSError) as error:
            raise QgisSdkFormError(f"{self._describe()}: {error}") from error
        self._commit(ref)

    def path(self, ref: FileRef | None = None) -> Path | None:
        """The path behind ``ref`` (the current value by default), via ``ctx.files``."""
        ref = self._value if ref is None else ref
        if ref is None:
            return None
        return self._require_ctx("files").resolve(ref)

    def _accept(self, value: object) -> object:
        if value is None:
            return None
        files = self._require_ctx("files")
        try:
            files.resolve(value)
        except QgisSdkBridgeRefusalError as error:
            raise QgisSdkFormError(
                f"{self._describe()}: ref {value.id!r} is unknown to ctx.files ({error})"
            ) from error
        return value

    def _grant(self, files: Any, path: Path) -> FileRef:
        raise NotImplementedError

    def _from_widget(self, value: object) -> None:
        """The file widget hands back a path; it becomes a ref or nothing."""
        if self._syncing:
            return
        if value in (None, ""):
            self._store(None)
            return
        try:
            self.set_path(str(value))
        except (QgisSdkFormError, QgisSdkUiError) as error:
            ctx = self._ctx
            if ctx is not None:
                ctx.notifications.warning(f"{self._describe()}: {error}")


class FileInput(_RefInput):
    """One file; the value is a file ``FileRef`` the plugin's ``ctx.files`` resolves.

    ``filters`` are author globs (``("*.csv", "*.gpkg")``) the dialog offers.
    """

    kind = "file"

    def __init__(
        self,
        name: str | None = None,
        *,
        filters: Sequence[str] = (),
        label: str | None = None,
        value: object = None,
        required: bool = False,
    ) -> None:
        self.filters = tuple(filters)
        super().__init__(name, label=label, value=value, required=required)

    def _grant(self, files: Any, path: Path) -> FileRef:
        return files.grant_file(path)

    def _details(self) -> dict[str, Any]:
        return {"filters": list(self.filters)}


class DirectoryInput(_RefInput):
    """One directory; the value is a directory ``FileRef``."""

    kind = "directory"

    def _grant(self, files: Any, path: Path) -> FileRef:
        return files.grant_directory(path)


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

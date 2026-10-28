"""The surface classes an author subclasses to show a Dialog or a Dock.

decision-55 settles how a plugin gets a window: not from an action's
signature, and not from a decorator that invents a widget, but from a plain
class the author writes and lists on the plugin::

    class BufferDialog(Dialog):
        title = "Buffer a layer"

        def build(self):
            from qgis.PyQt.QtWidgets import QLabel
            return QLabel("...")   # any QWidget - the catalogue comes later

    class LayerPanel(Dock, area="right"):
        def build(self): ...

    @plugin(id="field_tools", title="Field tools")
    class FieldTools:
        surfaces = [BufferDialog, LayerPanel]

Nothing here imports Qt. The base classes carry metadata (``title``, the dock
``area``) and the two hooks the host calls: ``build()`` once the instance has
its ``ctx`` (a ``UiContext`` for that one window) and its ``initial`` values,
and ``on_close()`` when the window goes away. A ``Dialog`` is a fresh instance
per opening; a ``Dock`` is one instance per runtime, toggled, with its
visibility remembered in the plugin's settings. How the window is placed is
the host's business (:mod:`qgis_sdk.adapters.surfaces`); how it is reached is
a binding (:mod:`qgis_sdk.bindings`) or ``ctx.ui.open(Surface)``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar, Final, Literal

from qgis_sdk.declarations import (
    QgisSdkDeclarationError,
    attach_describe,
    bindings_of,
    derive_id,
    derive_title,
    register_predicate_describer,
    validate_given,
)
from qgis_sdk.models import QgisSdkUiError

if TYPE_CHECKING:
    from qgis_sdk.core.contexts import UiContext

__all__ = [
    "DOCK_AREAS",
    "Dialog",
    "Dock",
    "Surface",
    "SurfaceDescription",
    "describe_surface",
    "is_dock",
    "is_surface_class",
    "is_widget_surface",
    "load_ui",
]

#: Where a ``Dock`` may sit; the names QGIS uses, not Qt's enum.
DOCK_AREAS: Final = ("left", "right", "top", "bottom")

SurfaceKind = Literal["dialog", "dock"]


class Surface:
    """What ``Dialog`` and ``Dock`` share; authors subclass one of those two.

    The host assigns ``ctx`` and ``initial`` on the instance before calling
    ``build()``, so a surface reads ``self.ctx.actions``, ``self.ctx.view``
    and ``self.ctx.notifications`` from the first line of ``build()`` on.
    """

    kind: ClassVar[SurfaceKind]
    #: The window title; derived from the class name when left ``None``.
    title: ClassVar[str | None] = None
    #: An explicit surface id; derived from the class name when left ``None``.
    id: ClassVar[str | None] = None
    #: A Qt Designer file, relative to the class's module, that the default
    #: ``build()`` loads; ``@on`` names then refer to its ``objectName``s.
    ui: ClassVar[str | None] = None

    ctx: UiContext
    initial: Mapping[str, Any]

    def build(self) -> Any:
        """Return the widget the host shows; the one Qt-touching author hook.

        The default loads ``ui`` when the class names a Designer file, else
        returns the components declared on the class (the declarative form:
        the roots, stacked in a ``Column`` when there are several, with the
        declared inputs seeded from ``initial`` by name), and refuses when
        there is neither.
        """
        if self.ui is not None:
            return load_ui(type(self))
        from .declarative import apply_initial, declared_root

        root = declared_root(self)
        if root is not None:
            apply_initial(self)
            return root
        raise NotImplementedError(
            f"{type(self).__name__}.build() must return the widget to show, "
            "or the class must name a Designer file in `ui` or declare "
            "components as class attributes"
        )

    def on_accept(self) -> Any:
        """Called by the Accept button (``HasAcceptCancel``); ``False`` keeps the window."""

    def on_close(self) -> None:
        """Called once the window closes, before the surface's scope disposes."""

    def _attach_behaviours(self, root: Any, ctx: UiContext) -> None:
        """Hook the behaviour mixins chain through after ``build()``."""


attach_describe(Surface)


class Dialog(Surface):
    """A window opened fresh every time: by a binding or by ``ctx.ui.open``."""

    kind: ClassVar[SurfaceKind] = "dialog"
    #: Block the rest of QGIS while open; off by default (decision-55).
    modal: ClassVar[bool] = False


class Dock(Surface):
    """One panel per runtime, toggled by its binding, remembered across sessions.

    ``class LayerPanel(Dock, area="left")`` picks the side; ``right`` is the
    default and an unknown name is refused when the class is created.
    """

    kind: ClassVar[SurfaceKind] = "dock"
    area: ClassVar[str] = "right"

    def __init_subclass__(cls, *, area: str | None = None, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if area is None:
            return
        if area not in DOCK_AREAS:
            raise QgisSdkDeclarationError(
                f"{cls.__name__}: dock area must be one of "
                f"{', '.join(DOCK_AREAS)}, got {area!r}"
            )
        cls.area = area


@dataclass(frozen=True, slots=True)
class SurfaceDescription:
    """What a host needs to place one surface; never part of ``describe_plugin``."""

    id: str
    title: str
    kind: SurfaceKind
    area: str | None
    modal: bool
    bindings: tuple[Any, ...] = field(default=(), repr=False, compare=False)


def load_ui(cls: type, parent: Any = None) -> Any:
    """Load the Designer file ``cls.ui`` names into a widget; needs QGIS."""
    import importlib

    from .components import NATIVE_CATALOGUE
    from .uifile import resolve_ui_path

    ui = getattr(cls, "ui", None)
    if not isinstance(ui, str) or not ui:
        raise QgisSdkUiError(f"{cls.__name__} names no Designer file in `ui`")
    path = resolve_ui_path(cls, ui)
    if not path.is_file():
        raise QgisSdkUiError(f"{cls.__name__}.ui = {ui!r}: {path} does not exist")
    try:
        catalogue = importlib.import_module(NATIVE_CATALOGUE)
    except ImportError as error:
        raise QgisSdkUiError(f"loading {path.name} needs QGIS: {error}") from error
    return catalogue.load_ui(path, parent)


def is_surface_class(value: object) -> bool:
    """Whether ``value`` is a surface class: a ``Dialog``/``Dock`` subclass or a widget surface.

    The widget form (decision-55) is a plain class - typically a ``QWidget``
    subclass the author already has - that declares ``kind = "dialog"`` or
    ``kind = "dock"`` and takes the ``UiContext`` as its one constructor
    argument; it is accepted without inheriting from the SDK.
    """
    if not isinstance(value, type):
        return False
    if issubclass(value, Surface):
        return value not in (Surface, Dialog, Dock)
    return is_widget_surface(value)


def is_widget_surface(value: object) -> bool:
    """Whether ``value`` is a surface in the widget form (``kind`` declared, no base)."""
    return (
        isinstance(value, type)
        and not issubclass(value, Surface)
        and getattr(value, "kind", None) in ("dialog", "dock")
    )


def is_dock(cls: type) -> bool:
    """Whether a surface class is a dock, whichever form it takes."""
    return describe_surface(cls).kind == "dock"


def describe_surface(cls: type) -> SurfaceDescription:
    """Read a surface class's metadata without constructing it."""
    if not is_surface_class(cls):
        name = getattr(cls, "__name__", repr(cls))
        raise QgisSdkDeclarationError(
            f"{name} is not a surface: subclass qgis_sdk.ui.Dialog or qgis_sdk.ui.Dock, "
            'or declare kind = "dialog"/"dock" on a widget class'
        )
    given_id = cls.__dict__.get("id", None) or _inherited(cls, "id")
    given_title = cls.__dict__.get("title", None) or _inherited(cls, "title")
    if not isinstance(given_id, str | None):
        given_id = None
    if not isinstance(given_title, str | None):
        given_title = None
    validate_given(given_id, given_title)
    surface_id = given_id if given_id is not None else derive_id(cls.__name__)
    title = given_title if given_title is not None else derive_title(cls.__name__)
    kind: SurfaceKind = cls.kind
    if kind == "dock":
        area = str(getattr(cls, "area", "right"))
        if area not in DOCK_AREAS:
            raise QgisSdkDeclarationError(
                f"{cls.__name__}: dock area must be one of "
                f"{', '.join(DOCK_AREAS)}, got {area!r}"
            )
        modal = False
    else:
        area = None
        modal = bool(getattr(cls, "modal", False))
    return SurfaceDescription(surface_id, title, kind, area, modal, bindings_of(cls))


def _inherited(cls: type, attribute: str) -> str | None:
    """A value set on an author's intermediate base, never on the SDK bases."""
    for base in cls.__mro__[1:]:
        if base in (Surface, Dialog, Dock, object):
            return None
        value = base.__dict__.get(attribute)
        if value is not None:
            return value
    return None


register_predicate_describer(is_surface_class, describe_surface)

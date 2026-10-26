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
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Final, Literal

from qgis_sdk.declarations import (
    QgisSdkDeclarationError,
    derive_id,
    derive_title,
    validate_given,
)

if TYPE_CHECKING:
    from qgis_sdk.core.contexts import UiContext

__all__ = [
    "DOCK_AREAS",
    "Dialog",
    "Dock",
    "Surface",
    "SurfaceDescription",
    "describe_surface",
    "is_surface_class",
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

    ctx: UiContext
    initial: Mapping[str, Any]

    def build(self) -> Any:
        """Return the widget the host shows; the one Qt-touching author hook."""
        raise NotImplementedError(
            f"{type(self).__name__}.build() must return the widget to show"
        )

    def on_close(self) -> None:
        """Called once the window closes, before the surface's scope disposes."""


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


def is_surface_class(value: object) -> bool:
    """Whether ``value`` is a ``Dialog``/``Dock`` subclass (not the bases)."""
    return (
        isinstance(value, type)
        and issubclass(value, Surface)
        and value not in (Surface, Dialog, Dock)
    )


def describe_surface(cls: type) -> SurfaceDescription:
    """Read a surface class's metadata without constructing it."""
    if not is_surface_class(cls):
        name = getattr(cls, "__name__", repr(cls))
        raise QgisSdkDeclarationError(
            f"{name} is not a surface: subclass qgis_sdk.ui.Dialog or qgis_sdk.ui.Dock"
        )
    given_id = cls.__dict__.get("id", None) or _inherited(cls, "id")
    given_title = cls.__dict__.get("title", None) or _inherited(cls, "title")
    validate_given(given_id, given_title)
    surface_id = given_id if given_id is not None else derive_id(cls.__name__)
    title = given_title if given_title is not None else derive_title(cls.__name__)
    area = cls.area if issubclass(cls, Dock) else None
    modal = bool(getattr(cls, "modal", False)) if issubclass(cls, Dialog) else False
    return SurfaceDescription(surface_id, title, cls.kind, area, modal)


def _inherited(cls: type, attribute: str) -> str | None:
    """A value set on an author's intermediate base, never on the SDK bases."""
    for base in cls.__mro__[1:]:
        if base in (Surface, Dialog, Dock, object):
            return None
        value = base.__dict__.get(attribute)
        if value is not None:
            return value
    return None

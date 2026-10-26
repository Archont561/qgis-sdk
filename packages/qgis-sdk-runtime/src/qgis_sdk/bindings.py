"""Bind actions and surfaces to the Desktop: ``@toolbar``, ``@menu``, ``@shortcut``.

decision-45 and decision-55: a binding says *where QGIS shows a way to
trigger something*, and nothing else. The decorators stack in any order on an
``@action`` method or on a ``Dialog``/``Dock`` subclass::

    @toolbar(icon="buffer.svg")
    @menu("Vector/Field tools")
    @shortcut("Ctrl+Alt+B")
    @action
    def buffer_selection(self) -> None: ...

    @menu("Plugins/Field tools")
    class BufferDialog(Dialog): ...

They mark, never wrap (decision-10): the method stays the plain function it
was and the class gains one attribute. Bindings are host metadata: they are
not part of :func:`qgis_sdk.describe_plugin`, the bridge schema or the host
fingerprint, so adding a toolbar button does not move the wire. Tests and
``qgis-sdk check`` read them through :func:`describe_bindings`.

What is refused, and how: a ``@job`` ("bind an ``@action`` that submits the
job"), a ``@stream``, and - when the ``@plugin`` class is created - a plain
method that never became an ``@action``. The trigger rule the Desktop host
applies is decision-55's: an action without inputs runs on the GUI thread; one
that returns a job handle reports through the message bar; a *typed* action
bound without a surface of its own is a ``UI003`` finding, and the host
refuses it by name rather than inventing a dialog for it.
"""

from __future__ import annotations

import inspect
import itertools
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Final, Literal, TypeVar

from qgis_sdk.declarations import (
    BINDING_ORDER_ATTRIBUTE,
    BINDINGS_ATTRIBUTE,
    ActionDescription,
    QgisSdkDeclarationError,
    bindings_of,
    describe_plugin,
)
from qgis_sdk.ui.surfaces import (
    SurfaceDescription,
    describe_surface,
    is_surface_class,
)

__all__ = [
    "BINDINGS_ATTRIBUTE",
    "SURFACES_ATTRIBUTE",
    "Binding",
    "BindingsDescription",
    "BoundAction",
    "BoundSurface",
    "MenuBinding",
    "ShortcutBinding",
    "ToolbarBinding",
    "bindings_of",
    "describe_bindings",
    "menu",
    "shortcut",
    "toolbar",
]

T = TypeVar("T")

#: The plugin class attribute listing its surfaces (decision-55).
SURFACES_ATTRIBUTE: Final = "surfaces"

_sequence = itertools.count(1)


@dataclass(frozen=True, slots=True)
class ToolbarBinding:
    """One toolbar button; ``text`` replaces the target's title when given."""

    icon: str | None = None
    text: str | None = None
    kind: Literal["toolbar"] = field(default="toolbar", init=False)


@dataclass(frozen=True, slots=True)
class MenuBinding:
    """One entry under ``path`` (``"Vector/Field tools"``), slash-separated."""

    path: str
    kind: Literal["menu"] = field(default="menu", init=False)


@dataclass(frozen=True, slots=True)
class ShortcutBinding:
    """One key sequence in Qt's portable spelling (``"Ctrl+Alt+B"``)."""

    keys: str
    kind: Literal["shortcut"] = field(default="shortcut", init=False)


Binding = ToolbarBinding | MenuBinding | ShortcutBinding


@dataclass(frozen=True, slots=True)
class BoundAction:
    """An ``@action`` with at least one binding, as the host sees it."""

    action: ActionDescription
    bindings: tuple[Binding, ...]
    #: Whether the handler takes inputs; bound and typed without a surface = UI003.
    takes_inputs: bool
    order: int = field(compare=False, default=0)

    @property
    def id(self) -> str:
        return self.action.id

    @property
    def title(self) -> str:
        return self.action.title


@dataclass(frozen=True, slots=True)
class BoundSurface:
    """A surface listed in ``surfaces = [...]``; ``bindings`` may be empty."""

    surface: SurfaceDescription
    cls: type = field(compare=False, repr=False)
    bindings: tuple[Binding, ...] = ()
    order: int = field(compare=False, default=0)

    @property
    def id(self) -> str:
        return self.surface.id

    @property
    def title(self) -> str:
        return self.surface.title


@dataclass(frozen=True, slots=True)
class BindingsDescription:
    """Everything the Desktop host places for one plugin class."""

    plugin_id: str
    actions: tuple[BoundAction, ...]
    surfaces: tuple[BoundSurface, ...]

    @property
    def entries(self) -> tuple[BoundAction | BoundSurface, ...]:
        """Bound actions and bound surfaces in declaration order across both."""
        bound: list[BoundAction | BoundSurface] = [
            *self.actions,
            *(surface for surface in self.surfaces if surface.bindings),
        ]
        return tuple(sorted(bound, key=lambda entry: entry.order))

    @property
    def typed_without_surface(self) -> tuple[BoundAction, ...]:
        """The ``UI003`` findings: bound actions whose inputs nothing collects."""
        return tuple(action for action in self.actions if action.takes_inputs)

    def surface(self, cls: type) -> BoundSurface:
        """The registered entry for ``cls``, or a refusal naming the class."""
        for surface in self.surfaces:
            if surface.cls is cls:
                return surface
        name = getattr(cls, "__name__", repr(cls))
        raise QgisSdkDeclarationError(
            f"{name} is not registered: list it in {self.plugin_id}'s surfaces = [...]"
        )


def toolbar(
    target: T | None = None, /, *, icon: str | None = None, text: str | None = None
) -> Any:
    """Put a button on the QGIS toolbar; ``@toolbar`` bare or with arguments.

    ``icon`` names a file under the package's ``icons/`` directory, resolved
    through :mod:`qgis_sdk.resources`; a missing file is a ``check`` finding.
    """
    if icon is not None and (not isinstance(icon, str) or not icon.strip()):
        raise QgisSdkDeclarationError("@toolbar: icon must be a file name")
    if text is not None and (not isinstance(text, str) or not text.strip()):
        raise QgisSdkDeclarationError("@toolbar: text must be a nonempty string")

    def decorate(value: T) -> T:
        return _bind(value, ToolbarBinding(icon=icon, text=text), "@toolbar")

    if target is None:
        return decorate
    return decorate(target)


def menu(path: str) -> Callable[[T], T]:
    """Add an entry under a QGIS menu path such as ``"Vector/Field tools"``.

    The first segment names the QGIS top-level menu (``Plugins``, ``Vector``,
    ``Raster``, ``Database``, ``Web``); the rest is the submenu. Repeat the
    decorator for a second place.
    """
    if not isinstance(path, str) or not path.strip().strip("/").strip():
        raise QgisSdkDeclarationError("@menu: path must be a nonempty menu path")

    def decorate(value: T) -> T:
        return _bind(value, MenuBinding(path.strip().strip("/")), "@menu")

    return decorate


def shortcut(keys: str) -> Callable[[T], T]:
    """Register a key sequence (``"Ctrl+Alt+B"``) that triggers the target."""
    if not isinstance(keys, str) or not keys.strip():
        raise QgisSdkDeclarationError("@shortcut: keys must be a nonempty key sequence")

    def decorate(value: T) -> T:
        return _bind(value, ShortcutBinding(keys.strip()), "@shortcut")

    return decorate


def _bind(target: Any, binding: Binding, decorator: str) -> Any:
    if inspect.isclass(target):
        if not is_surface_class(target):
            raise QgisSdkDeclarationError(
                f"{decorator} binds an @action method or a Dialog/Dock subclass; "
                f"{target.__name__} is neither"
            )
    elif inspect.isfunction(target):
        if hasattr(target, "__qgis_sdk_job__"):
            raise QgisSdkDeclarationError(
                f"{decorator} cannot bind a @job ({target.__name__}); "
                "bind an @action that submits the job"
            )
        if hasattr(target, "__qgis_sdk_stream__"):
            raise QgisSdkDeclarationError(
                f"{decorator} cannot bind a @stream ({target.__name__}); "
                "bind an @action that opens a surface over it"
            )
    else:
        raise QgisSdkDeclarationError(
            f"{decorator} binds an @action method or a Dialog/Dock subclass"
        )
    existing = bindings_of(target)
    if not existing:
        setattr(target, BINDING_ORDER_ATTRIBUTE, next(_sequence))
    setattr(target, BINDINGS_ATTRIBUTE, (*existing, binding))
    return target


def _order_of(target: object) -> int:
    return int(vars(target).get(BINDING_ORDER_ATTRIBUTE, 0))


def describe_bindings(cls: type) -> BindingsDescription:
    """Read the bound actions and the registered surfaces of a plugin class.

    Separate from ``describe_plugin`` on purpose: bindings never reach the
    wire. Actions are reported only when bound; every surface in
    ``surfaces = [...]`` is reported, bound or not, because ``ctx.ui.open``
    reaches the unbound ones. Refusals name the member.
    """
    description = describe_plugin(cls)
    members: dict[str, Any] = {}
    for base in reversed(cls.__mro__):
        members.update(vars(base))
    actions: list[BoundAction] = []
    for action in description.actions:
        member = members.get(action.handler)
        function = member.__func__ if isinstance(member, staticmethod) else member
        bound = bindings_of(function)
        if not bound:
            continue
        actions.append(
            BoundAction(
                action,
                bound,
                takes_inputs=bool(action.request.get("properties")),
                order=_order_of(function),
            )
        )
    surfaces: list[BoundSurface] = []
    seen: dict[str, str] = {}
    for entry in _listed_surfaces(cls):
        surface = describe_surface(entry)
        if surface.id in seen:
            raise QgisSdkDeclarationError(
                f"{cls.__name__}.surfaces: {entry.__name__} and {seen[surface.id]} "
                f"share the id {surface.id!r}"
            )
        seen[surface.id] = entry.__name__
        surfaces.append(
            BoundSurface(surface, entry, bindings_of(entry), order=_order_of(entry))
        )
    actions.sort(key=lambda bound: bound.order)
    return BindingsDescription(description.id, tuple(actions), tuple(surfaces))


def _listed_surfaces(cls: type) -> Sequence[type]:
    listed = getattr(cls, SURFACES_ATTRIBUTE, ())
    if isinstance(listed, (str, bytes)) or not isinstance(listed, Sequence):
        raise QgisSdkDeclarationError(
            f"{cls.__name__}.surfaces must be a list of Dialog/Dock subclasses"
        )
    for entry in listed:
        if not is_surface_class(entry):
            name = getattr(entry, "__name__", repr(entry))
            raise QgisSdkDeclarationError(
                f"{cls.__name__}.surfaces: {name} is not a Dialog/Dock subclass"
            )
    return tuple(listed)

"""The binding decorators and the description of what they placed."""

from __future__ import annotations

import inspect
import itertools
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, Final, Literal, TypeVar

from qgis_sdk.declarations import (
    BINDING_ORDER_ATTRIBUTE,
    BINDINGS_ATTRIBUTE,
    PLUGIN_ATTRIBUTE,
    ActionDescription,
    QgisSdkDeclarationError,
    attach_describe,
    bindings_of,
    register_describer_enricher,
)
from qgis_sdk.declarations._describe import describe_plugin
from qgis_sdk.ui.surfaces import (
    SurfaceDescription,
    describe_surface,
    is_surface_class,
)


def _describe_lowered_bindings_tail1(**values):
    actions = values["actions"]
    cls = values["cls"]
    description = values["description"]
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


def _bind_facts1(binding, target):
    attach_describe(target)
    existing = bindings_of(target)
    if not existing:
        setattr(target, BINDING_ORDER_ATTRIBUTE, next(_sequence))
    setattr(target, BINDINGS_ATTRIBUTE, (*existing, binding))
    return target


if TYPE_CHECKING:
    from qgis_sdk.core._application import QgisSdkPlugin

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

__stability__ = "stable"
T = TypeVar("T")

#: The plugin class attribute listing its surfaces (decision-55).
SURFACES_ATTRIBUTE: Final = "surfaces"

_sequence = itertools.count(1)


@dataclass(frozen=True, slots=True)
class ToolbarBinding:
    """One toolbar button; ``text`` replaces the target's title when given.

    Attributes:
        icon: The file name under the package's ``icons/`` directory.
        text: The label, or ``None`` for the target's own title.
    """

    icon: str | None = None
    text: str | None = None
    kind: Literal["toolbar"] = field(default="toolbar", init=False)


@dataclass(frozen=True, slots=True)
class MenuBinding:
    """One entry under ``path`` (``"Vector/Field tools"``), slash-separated.

    Attributes:
        path: The menu path: a top-level menu, then the submenu.
    """

    path: str
    kind: Literal["menu"] = field(default="menu", init=False)


@dataclass(frozen=True, slots=True)
class ShortcutBinding:
    """One key sequence in Qt's portable spelling (``"Ctrl+Alt+B"``).

    Attributes:
        keys: The sequence, as Qt spells it.
    """

    keys: str
    kind: Literal["shortcut"] = field(default="shortcut", init=False)


Binding = ToolbarBinding | MenuBinding | ShortcutBinding


@dataclass(frozen=True, slots=True)
class BoundAction:
    """An ``@action`` with at least one binding, as the host sees it.

    Attributes:
        action: The action's own description.
        bindings: Every place the host shows a way to trigger it.
        takes_inputs: Whether the handler takes inputs, which is what makes a
            bound action without a surface a ``UI003`` finding.
        order: Where it falls in the plugin's declaration order.
    """

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
    """A surface listed in ``surfaces = [...]``; ``bindings`` may be empty.

    Attributes:
        surface: The surface's own description.
        cls: The class it describes, which is how the host finds it.
        bindings: Where it is placed; empty when it is only opened by code.
        order: Where it falls in the plugin's declaration order.
    """

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
    """Everything the Desktop host places for one plugin class.

    Attributes:
        plugin_id: The plugin the entries belong to.
        actions: The bound actions, in declaration order.
        surfaces: Every registered surface, bound or not.
    """

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
        """The registered entry for ``cls``, or a refusal naming the class.

        Args:
            cls: The surface class to look up.
        """
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

    Args:
        target: The action when used bare, and ``None`` when called.
        icon: The icon's file name, or ``None`` for a button with no icon.
        text: The label, or ``None`` to use the action's own title.
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

    The first segment names the top-level menu (``Vector``, ``Plugins``); the
    rest is the submenu. Repeat the decorator for a second place.

    Args:
        path: The menu path.
    """
    if not isinstance(path, str) or not path.strip().strip("/").strip():
        raise QgisSdkDeclarationError("@menu: path must be a nonempty menu path")

    def decorate(value: T) -> T:
        return _bind(value, MenuBinding(path.strip().strip("/")), "@menu")

    return decorate


def shortcut(keys: str) -> Callable[[T], T]:
    """Register a key sequence (``"Ctrl+Alt+B"``) that triggers the target.

    Args:
        keys: The sequence, in Qt's spelling.
    """
    if not isinstance(keys, str) or not keys.strip():
        raise QgisSdkDeclarationError("@shortcut: keys must be a nonempty key sequence")

    def decorate(value: T) -> T:
        return _bind(value, ShortcutBinding(keys.strip()), "@shortcut")

    return decorate


def _bind(target: Any, binding: Binding, decorator: str) -> Any:
    if inspect.isclass(target):
        if not is_surface_class(target):
            raise QgisSdkDeclarationError(
                f"{decorator} binds an application action or a Dialog/Dock subclass; "
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
        if hasattr(target, "__qgis_sdk_tool__"):
            raise QgisSdkDeclarationError(
                f"{decorator} cannot bind a @tool ({target.__name__}); "
                "bind an @action that calls start() on it"
            )
    else:
        raise QgisSdkDeclarationError(
            f"{decorator} binds an application action or a Dialog/Dock subclass"
        )
    return _bind_facts1(binding, target)


def _order_of(target: object) -> int:
    return int(vars(target).get(BINDING_ORDER_ATTRIBUTE, 0))


def describe_bindings(app: QgisSdkPlugin) -> BindingsDescription:
    """Read the bound actions and registered surfaces of an application.

    Bindings never reach the wire. Only bound actions are reported, but every
    registered surface is included: ``ctx.ui.open`` can reach them all.

    Args:
        app: The started application, whose class carries the bindings.
    """
    from qgis_sdk.core._application import QgisSdkPlugin

    if not isinstance(app, QgisSdkPlugin):
        raise QgisSdkDeclarationError("describe_bindings requires a QgisSdkPlugin")
    return _describe_lowered_bindings(app._plugin_class())


def _describe_lowered_bindings(cls: type) -> BindingsDescription:
    """Read bindings from an internally lowered application class."""
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
    return _describe_lowered_bindings_tail1(**{**globals(), **locals()})


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


def _enrich_plugin_description(cls: type, description: Any) -> Any:
    return replace(description, bindings=_describe_lowered_bindings(cls))


register_describer_enricher(PLUGIN_ATTRIBUTE, _enrich_plugin_description)

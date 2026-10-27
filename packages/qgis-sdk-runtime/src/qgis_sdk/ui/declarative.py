"""Surfaces declared as class attributes (decision-55, the declarative form).

A surface may list its components on the class instead of building them in
``build()``::

    class ResultsDock(Dock, area="right"):
        fixture = RunButton(action_id="open_fixture", text="Fixture")
        clear = Button(text="Clear")
        tools = Row([fixture, clear])
        results = ResultTable(columns=["id", "name"])

        @on(clear).clicked
        def cleared(self): ...

The class attributes are *prototypes*: a component holds state (a value,
listeners, a widget once mounted) that two open windows must never share, so
:func:`materialise` gives every surface instance its own deep copy of the
whole set at once - one ``deepcopy`` over the dict, so a ``Row`` on the
instance holds the instance's buttons and a ``RunButton`` its instance's
``JobProgress``. The host does this right after constructing the surface,
before ``build()``; :func:`declared_root` is what the default ``build()``
returns: the components no other declared component contains, as one
``Column`` when there are several. :func:`apply_initial` is the other half
of the default ``build()``: the ``initial`` values the opener passed go to
the declared inputs of those names (at any depth - a ``Form`` or a ``Group``
declared on the class counts), and a name no declared input carries is
refused rather than dropped.
"""

from __future__ import annotations

import copy
from typing import Any

from qgis_sdk.declarations import derive_id
from qgis_sdk.models import QgisSdkUiError

from .components import Column, Component, Input

__all__ = [
    "MATERIALISED_ATTRIBUTE",
    "apply_initial",
    "declared_components",
    "declared_inputs",
    "declared_root",
    "materialise",
    "resolve_declared",
]

#: Where an instance keeps its copies (attribute name -> component).
MATERIALISED_ATTRIBUTE = "__qgis_sdk_components__"


def declared_components(cls: type) -> dict[str, Component]:
    """Every component a class declares, as ``attribute -> prototype``.

    Base classes first, in definition order; a subclass that reassigns an
    attribute replaces the base's component at the base's position.
    """
    found: dict[str, Component] = {}
    for base in reversed(cls.__mro__):
        for attribute, value in vars(base).items():
            if isinstance(value, Component):
                found[attribute] = value
    return found


def materialise(surface: Any) -> dict[str, Component]:
    """Give ``surface`` its own copies of the declared components; idempotent.

    Returns ``attribute -> copy``; the copies are set on the instance so
    ``self.clear`` in a method is the instance's button, not the prototype.
    """
    existing = surface.__dict__.get(MATERIALISED_ATTRIBUTE)
    if existing is not None:
        return existing
    prototypes = declared_components(type(surface))
    try:
        copies: dict[str, Component] = copy.deepcopy(prototypes)
    except Exception as error:  # a Qt widget instance in a Custom, typically
        culprit = _culprit(prototypes)
        raise QgisSdkUiError(
            f"{type(surface).__name__}.{culprit} cannot be copied for each "
            f"window ({error}); declare components the catalogue can copy, "
            "pass Custom a factory, or create the widget in build()"
        ) from error
    for attribute, component in copies.items():
        setattr(surface, attribute, component)
    surface.__dict__[MATERIALISED_ATTRIBUTE] = copies
    return copies


def declared_root(surface: Any) -> Component | None:
    """The tree the default ``build()`` shows, or ``None`` when nothing is declared.

    The roots are the declared components no other declared component
    contains; a single root is returned as is, several are stacked in a
    ``Column`` named after the surface class.
    """
    components = materialise(surface)
    if not components:
        return None
    contained: set[int] = set()
    for component in components.values():
        _collect(component, contained)
    roots = [c for c in components.values() if id(c) not in contained]
    if len(roots) == 1:
        return roots[0]
    return Column(derive_id(type(surface).__name__), roots)


def declared_inputs(surface: Any) -> dict[str, Input]:
    """Every :class:`Input` in the declared trees of ``surface``, by name.

    The instance's copies, at any depth, in declaration order; an input
    reached twice (declared and placed in a declared container) counts once.
    """
    found: dict[str, Input] = {}
    seen: set[int] = set()

    def visit(component: Component) -> None:
        if id(component) in seen:
            return
        seen.add(id(component))
        if isinstance(component, Input):
            found.setdefault(component.name, component)
        for child in component.children():
            visit(child)

    for component in materialise(surface).values():
        visit(component)
    return found


def apply_initial(surface: Any) -> None:
    """Seed the declared inputs from ``surface.initial``; an unknown name is refused."""
    initial = getattr(surface, "initial", None) or {}
    if not initial:
        return
    inputs = declared_inputs(surface)
    unknown = sorted(set(initial) - set(inputs))
    if unknown:
        known = ", ".join(sorted(inputs)) or "none"
        raise QgisSdkUiError(
            f"{type(surface).__name__} has no input "
            f"{', '.join(map(repr, unknown))}; it has: {known}"
        )
    for name, value in initial.items():
        inputs[name].set_value(value)


def resolve_declared(surface: Any, prototype: Component) -> Component | None:
    """The instance's copy of ``prototype``, or ``None`` if the class lacks it."""
    for attribute, declared in declared_components(type(surface)).items():
        if declared is prototype:
            return materialise(surface)[attribute]
    return None


def _collect(component: Component, into: set[int]) -> None:
    for child in component.children():
        into.add(id(child))
        _collect(child, into)


def _culprit(prototypes: dict[str, Component]) -> str:
    for attribute, component in prototypes.items():
        try:
            copy.deepcopy(component)
        except Exception:  # noqa: BLE001 - the same failure, located
            return attribute
    return "<components>"  # pragma: no cover - the whole failed, no part did

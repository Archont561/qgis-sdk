from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from ._symbols import (
    COLOUR,
    GRADUATED_MODES,
    RENDERER_KIND_NAMES,
    SYMBOLS_FOR_GEOMETRY,
    Category,
    SingleSymbolRenderer,
    Symbol,
    non_empty,
    symbol_from_wire,
)


@dataclass(frozen=True, slots=True)
class CategorizedRenderer:
    """One symbol per distinct value of ``field``.

    Attributes:
        field: The attribute field whose values are matched.
        categories: One symbol per distinct value, in the order they are tried.
        kind: The discriminator a page reads: always ``categorized``.
    """

    field: str
    categories: tuple[Category, ...]
    kind: Literal["categorized"] = field(default="categorized", init=False)

    def __post_init__(self) -> None:
        non_empty(self.field, "a categorized renderer's field")
        if not self.categories:
            raise ValueError("a categorized renderer draws at least one category")
        seen = [category.value for category in self.categories]
        if len(set(seen)) != len(seen):
            raise ValueError(
                f"a categorized renderer names each value once; {seen} repeats one"
            )

    def to_wire(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "field": self.field,
            "categories": [category.to_wire() for category in self.categories],
        }

    @classmethod
    def from_wire(cls, value: Any) -> CategorizedRenderer:
        """Rebuild this value from its wire shape.

        Args:
            value: The mapping a page sent, whose keys are checked.
        """
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise TypeError("a categorized renderer is an object")
        return cls(
            field=str(value["field"]),
            categories=tuple(Category.from_wire(item) for item in value["categories"]),
        )


@dataclass(frozen=True, slots=True)
class GraduatedClass:
    """One band of a graduated renderer: ``lower`` to ``upper``, and its symbol.

    Attributes:
        lower: The band's lower bound, inclusive.
        upper: The band's upper bound.
        label: The legend text for the band.
        symbol: How features in the band are drawn.
    """

    lower: float
    upper: float
    label: str
    symbol: Symbol

    def __post_init__(self) -> None:
        if self.lower > self.upper:
            raise ValueError(
                f"a graduated class runs from its lower to its upper bound; "
                f"{self.lower} is above {self.upper}"
            )

    def to_wire(self) -> dict[str, Any]:
        return {
            "lower": self.lower,
            "upper": self.upper,
            "label": self.label,
            "symbol": self.symbol.to_wire(),
        }

    @classmethod
    def from_wire(cls, value: Any) -> GraduatedClass:
        """Rebuild this value from its wire shape.

        Args:
            value: The mapping a page sent, whose keys are checked.
        """
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise TypeError("a graduated class is an object")
        return cls(
            lower=float(value["lower"]),
            upper=float(value["upper"]),
            label=str(value["label"]),
            symbol=symbol_from_wire(value["symbol"]),
        )


@dataclass(frozen=True, slots=True)
class GraduatedRenderer:
    """A field banded into classes, each drawn with its own symbol.

    Attributes:
        field: The attribute field the values are banded from.
        classes: The bands, in ascending order.
        mode: How a value is placed in a band: ``equal_interval``, ``quantile`` and so on.
        kind: The discriminator a page reads: always ``graduated``.
    """

    field: str
    classes: tuple[GraduatedClass, ...]
    mode: str = "equal_interval"
    kind: Literal["graduated"] = field(default="graduated", init=False)

    def __post_init__(self) -> None:
        non_empty(self.field, "a graduated renderer's field")
        if not self.classes:
            raise ValueError("a graduated renderer draws at least one class")
        if self.mode not in GRADUATED_MODES:
            raise ValueError(
                f"a graduated mode is one of {', '.join(GRADUATED_MODES)}, "
                f"not {self.mode!r}"
            )
        # Adjacent classes may share an edge - 0-1, 1-2 - but a class that starts
        # below the one before it is a caller's ordering bug, not a classification.
        previous = self.classes[0].lower
        for band in self.classes:
            if band.lower < previous:
                raise ValueError(
                    f"graduated classes run upwards; {band.lower} follows {previous}"
                )
            previous = band.lower

    def to_wire(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "field": self.field,
            "mode": self.mode,
            "classes": [band.to_wire() for band in self.classes],
        }

    @classmethod
    def from_wire(cls, value: Any) -> GraduatedRenderer:
        """Rebuild this value from its wire shape.

        Args:
            value: The mapping a page sent, whose keys are checked.
        """
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise TypeError("a graduated renderer is an object")
        return cls(
            field=str(value["field"]),
            mode=str(value.get("mode", "equal_interval")),
            classes=tuple(GraduatedClass.from_wire(item) for item in value["classes"]),
        )


@dataclass(frozen=True, slots=True)
class Rule:
    """One rule: an expression, and the symbol drawn where it is true.

    Attributes:
        filter: The expression that has to hold for the rule to draw.
        label: The legend text for the rule.
        symbol: How features matching it are drawn.
        enabled: Whether the rule takes part at all.
    """

    filter: str
    label: str
    symbol: Symbol
    enabled: bool = True

    def __post_init__(self) -> None:
        non_empty(self.filter, "a rule's filter expression")

    def to_wire(self) -> dict[str, Any]:
        return {
            "filter": self.filter,
            "label": self.label,
            "enabled": self.enabled,
            "symbol": self.symbol.to_wire(),
        }

    @classmethod
    def from_wire(cls, value: Any) -> Rule:
        """Rebuild this value from its wire shape.

        Args:
            value: The mapping a page sent, whose keys are checked.
        """
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise TypeError("a rule is an object")
        return cls(
            filter=str(value["filter"]),
            label=str(value["label"]),
            enabled=bool(value.get("enabled", True)),
            symbol=symbol_from_wire(value["symbol"]),
        )


@dataclass(frozen=True, slots=True)
class RuleBasedRenderer:
    """Rules evaluated in order; the first one whose expression holds draws.

    Attributes:
        rules: The rules, in the order they are evaluated.
        kind: The discriminator a page reads: always ``rule_based``.
    """

    rules: tuple[Rule, ...]
    kind: Literal["rule_based"] = field(default="rule_based", init=False)

    def __post_init__(self) -> None:
        if not self.rules:
            raise ValueError("a rule-based renderer holds at least one rule")

    def to_wire(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "rules": [rule.to_wire() for rule in self.rules],
        }

    @classmethod
    def from_wire(cls, value: Any) -> RuleBasedRenderer:
        """Rebuild this value from its wire shape.

        Args:
            value: The mapping a page sent, whose keys are checked.
        """
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise TypeError("a rule-based renderer is an object")
        return cls(rules=tuple(Rule.from_wire(item) for item in value["rules"]))


Renderer = (
    SingleSymbolRenderer | CategorizedRenderer | GraduatedRenderer | RuleBasedRenderer
)
RENDERERS: dict[str, Any] = {
    "single_symbol": SingleSymbolRenderer,
    "categorized": CategorizedRenderer,
    "graduated": GraduatedRenderer,
    "rule_based": RuleBasedRenderer,
}


def renderer_from_wire(value: Any) -> Renderer:
    """Return the renderer ``value`` describes, dispatching on its ``kind``.

    Args:
        value: The mapping a page sent, whose ``kind`` picks the class.
    """
    for model in (
        SingleSymbolRenderer,
        CategorizedRenderer,
        GraduatedRenderer,
        RuleBasedRenderer,
    ):
        if isinstance(value, model):
            return value
    if not isinstance(value, Mapping):
        raise TypeError("a renderer is an object")
    kind = value.get("kind")
    model = RENDERERS.get(str(kind))
    if model is None:
        raise ValueError(
            f"a renderer's kind is one of {', '.join(RENDERER_KIND_NAMES)}, "
            f"not {kind!r}"
        )
    return model.from_wire(value)


NULLABLE_STRING: dict[str, Any] = {"anyOf": [{"type": "string"}, {"type": "null"}]}
NUMBER = {"type": "number"}
COLOUR_SCHEMA = {"type": "string", "pattern": COLOUR.pattern}


def symbol_kind(renderer: Renderer) -> str:
    """Return the kind of symbol ``renderer`` draws with throughout.

    Every renderer in the curated set draws one kind of symbol - a categorized
    renderer's categories are all markers, or all fills - because a renderer that
    mixed kinds would draw the wrong thing on half a layer. The first symbol
    answers for the whole description, and both backends refuse a mismatch
    against the layer's geometry through :func:`symbol_fits_geometry`.

    Args:
        renderer: The renderer to read.
    """
    if isinstance(renderer, SingleSymbolRenderer):
        return renderer.symbol.kind
    if isinstance(renderer, CategorizedRenderer):
        return renderer.categories[0].symbol.kind
    if isinstance(renderer, GraduatedRenderer):
        return renderer.classes[0].symbol.kind
    return renderer.rules[0].symbol.kind


def symbol_fits_geometry(renderer: Renderer, geometry_type: str) -> str | None:
    """Return why ``renderer`` cannot draw ``geometry_type`` layers, or ``None``.

    QGIS will happily accept a marker symbol on a polygon layer and then draw
    nothing, which is the silent failure this SDK exists to refuse: a page that
    asked for markers and got blank space cannot tell a bug from an empty map.
    A geometry kind the table does not name (a mesh, a raster) is not this
    function's business - there is no renderer to set on it at all.

    Args:
        renderer: The renderer to check.
        geometry_type: The geometry the target layer carries.
    """
    expected = SYMBOLS_FOR_GEOMETRY.get(geometry_type)
    drawn = symbol_kind(renderer)
    if expected is None or drawn == expected:
        return None
    return (
        f"a {renderer.kind} renderer draws {drawn} symbols; the layer is "
        f"{geometry_type} geometry, drawn by {expected}"
    )

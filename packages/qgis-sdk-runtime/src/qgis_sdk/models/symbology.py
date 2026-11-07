"""A layer's appearance, as a page and a plugin handler see it.

decision-54 point 4 asks for symbology, labelling and the style manager behind
the curated surface, and decision-16 already drew the line this module walks:
*"do not mirror the entire renderer API prematurely"*. So what crosses the
boundary is a **curated** description, not a projection of ``QgsFeatureRenderer``:

* **Four renderers, not sixteen.** Single symbol, categorized, graduated and
  rule-based are the ones a plugin actually asks for. A heatmap, a point
  displacement or a merged renderer is refused by name
  (``QgisSdkUnsupportedCapabilityError``) rather than half described, because a
  page that renders a field the host silently dropped draws a lie.
* **Three symbols, not a symbol layer tree.** A marker, a line and a fill carry
  a colour, a size or width, and an outline. That is what a page can paint and
  what a reviewer can read; a symbol built from five nested layers is QGIS's to
  hold, and this SDK describes it as the one symbol it is.
* **A renderer says which kind it is.** ``kind`` is the discriminator on the
  wire, exactly as the layer kinds do it: one field tells a page which of the
  four descriptions it holds, and the union narrows without guessing.
* **An expression stays a string.** A rule's filter is a QGIS expression, not
  something this module parses. Whether it is valid is QGIS's answer, and a
  parser here would be a second, wrong one.
* **Style text is text.** QML and SLD cross the wire as strings; which dialect a
  string is, the caller says explicitly rather than the host sniffing the first
  character.

Everything here is frozen and validated at construction, so a renderer with a
negative symbol size or a graduated class whose bounds run backwards is a bug in
the caller, reported where it was declared, not a layer that renders oddly later.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

__all__ = [
    "CATEGORIZED_RENDERER",
    "CATEGORY",
    "FILL_SYMBOL",
    "GRADUATED_CLASS",
    "GRADUATED_MODES",
    "GRADUATED_RENDERER",
    "LABELLING",
    "LINE_SYMBOL",
    "MARKER_SHAPES",
    "MARKER_SYMBOL",
    "RENDERERS",
    "RENDERER_KIND_NAMES",
    "RENDERER_SCHEMAS",
    "RULE",
    "RULE_BASED_RENDERER",
    "SINGLE_SYMBOL_RENDERER",
    "STYLE_ENTRY",
    "STYLE_FORMATS",
    "STYLE_MANAGER_KINDS",
    "STYLE_TEXT",
    "SYMBOLS_FOR_GEOMETRY",
    "SYMBOL_KINDS",
    "SYMBOL_SCHEMAS",
    "CategorizedRenderer",
    "Category",
    "FillSymbol",
    "GraduatedClass",
    "GraduatedRenderer",
    "Labelling",
    "LineSymbol",
    "MarkerSymbol",
    "Renderer",
    "Rule",
    "RuleBasedRenderer",
    "SingleSymbolRenderer",
    "StyleEntry",
    "StyleText",
    "Symbol",
    "labelling_from_wire",
    "renderer_from_wire",
    "style_entry_from_wire",
    "symbol_fits_geometry",
    "symbol_from_wire",
    "symbol_kind",
]

#: The symbol kinds, in wire order. A marker draws a point, a line a polyline and
#: a fill a polygon - the three geometries QGIS draws, in the order a page
#: narrows them.
SYMBOL_KINDS: tuple[str, ...] = ("marker", "line", "fill")

#: The renderer kinds, in wire order. This tuple is the vocabulary the model, the
#: host catalogue, the coverage map and the fake all read, so a kind cannot be
#: one thing in one place and a typo in another.
RENDERER_KIND_NAMES: tuple[str, ...] = (
    "single_symbol",
    "categorized",
    "graduated",
    "rule_based",
)

#: The graduated classification modes this SDK names, in the order a page offers
#: them. Each is a QGIS *classification method*, not the deprecated renderer
#: ``mode`` enum, and the table lives here so the fake and the native adapter
#: refuse the same name.
#:
#: ``custom`` is last because it is an answer, not a request: QGIS reports it for
#: a renderer whose ranges were edited by hand, which is a perfectly ordinary
#: layer to read. Refusing it would make ``symbology()`` fail on any layer the
#: user banded themselves, so it is named - and a caller that asks for it is
#: saying "these ranges are mine", which is exactly what the classes already say.
GRADUATED_MODES: tuple[str, ...] = (
    "equal_interval",
    "quantile",
    "jenks",
    "std_dev",
    "pretty",
    "custom",
)

#: The well-known marker shapes a page can ask for. QGIS accepts more (a
#: half-filled circle, a picture marker); those are symbol-layer details a
#: curated description does not carry, and a shape outside this list is refused
#: where it is declared rather than silently drawn as a circle.
MARKER_SHAPES: tuple[str, ...] = (
    "circle",
    "square",
    "diamond",
    "triangle",
    "star",
)

#: Style dialects this SDK imports and exports. Two names, deliberately: a caller
#: says which one it holds instead of the host sniffing the text.
STYLE_FORMATS: tuple[str, ...] = ("qml", "sld")

#: The kinds of thing the style manager holds, in wire order. A QGIS style
#: database stores symbols, colour ramps and label settings; those three are what
#: a page can offer, and a fourth (a "style" of its own) is not something the
#: API answers.
STYLE_MANAGER_KINDS: tuple[str, ...] = ("symbol", "color_ramp", "label_settings")

_COLOUR = re.compile(r"#[0-9a-f]{6}")


def _colour(value: str, what: str) -> str:
    """Return ``value`` as a lower-case ``#rrggbb`` colour, or refuse it by name.

    Normalising here is what makes a get/set round trip comparable: QGIS answers
    ``QColor.name()`` in lower case, so a caller that wrote ``#FF0000`` gets
    ``#ff0000`` back and one assertion holds on both backends.
    """
    if not isinstance(value, str):
        raise TypeError(f"a {what} is a '#rrggbb' string")
    normalised = value.lower()
    if not _COLOUR.fullmatch(normalised):
        raise ValueError(f"a {what} is '#rrggbb', not {value!r}")
    return normalised


def _positive(value: float, what: str) -> float:
    """Return ``value`` as a float greater than zero, or refuse it by name."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{what} is a number")
    number = float(value)
    if number <= 0:
        raise ValueError(f"{what} is greater than zero, not {value!r}")
    return number


def _non_negative(value: float, what: str) -> float:
    """Return ``value`` as a float of zero or more, or refuse it by name.

    Zero is meaningful for an outline: a marker drawn without one is a shape of
    one colour, and QGIS stores that as a width of 0 rather than as a missing
    field.
    """
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{what} is a number")
    number = float(value)
    if number < 0:
        raise ValueError(f"{what} is zero or more, not {value!r}")
    return number


def _non_empty(value: str, what: str) -> str:
    """Return ``value`` stripped, refusing an empty or blank string."""
    if not isinstance(value, str):
        raise TypeError(f"{what} is a string")
    if not value.strip():
        raise ValueError(f"{what} is not blank")
    return value


# -- symbols ------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MarkerSymbol:
    """How a point is drawn: a shape of one colour with an outline.

    ``size`` and ``outline_width`` are millimetres - QGIS's own unit for a symbol
    dimension, and the one a legend is printed in.
    """

    color: str
    size: float = 2.0
    shape: str = "circle"
    outline_color: str = "#000000"
    outline_width: float = 0.2
    kind: Literal["marker"] = field(default="marker", init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "color", _colour(self.color, "marker colour"))
        object.__setattr__(
            self, "outline_color", _colour(self.outline_color, "marker outline colour")
        )
        object.__setattr__(self, "size", _positive(self.size, "a marker's size"))
        object.__setattr__(
            self,
            "outline_width",
            _non_negative(self.outline_width, "a marker's outline"),
        )
        if self.shape not in MARKER_SHAPES:
            raise ValueError(
                f"a marker shape is one of {', '.join(MARKER_SHAPES)}, "
                f"not {self.shape!r}"
            )

    def to_wire(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "color": self.color,
            "size": self.size,
            "shape": self.shape,
            "outline_color": self.outline_color,
            "outline_width": self.outline_width,
        }

    @classmethod
    def from_wire(cls, value: Any) -> MarkerSymbol:
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise TypeError("a marker symbol is an object")
        return cls(
            color=str(value["color"]),
            size=float(value["size"]),
            shape=str(value["shape"]),
            outline_color=str(value["outline_color"]),
            outline_width=float(value["outline_width"]),
        )


@dataclass(frozen=True, slots=True)
class LineSymbol:
    """How a polyline is drawn: one colour and a width in millimetres."""

    color: str
    width: float = 0.26
    kind: Literal["line"] = field(default="line", init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "color", _colour(self.color, "line colour"))
        object.__setattr__(self, "width", _positive(self.width, "a line's width"))

    def to_wire(self) -> dict[str, Any]:
        return {"kind": self.kind, "color": self.color, "width": self.width}

    @classmethod
    def from_wire(cls, value: Any) -> LineSymbol:
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise TypeError("a line symbol is an object")
        return cls(color=str(value["color"]), width=float(value["width"]))


@dataclass(frozen=True, slots=True)
class FillSymbol:
    """How a polygon is drawn: a fill colour and an outline."""

    color: str
    outline_color: str = "#000000"
    outline_width: float = 0.26
    kind: Literal["fill"] = field(default="fill", init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "color", _colour(self.color, "fill colour"))
        object.__setattr__(
            self, "outline_color", _colour(self.outline_color, "fill outline colour")
        )
        object.__setattr__(
            self,
            "outline_width",
            _non_negative(self.outline_width, "a fill's outline"),
        )

    def to_wire(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "color": self.color,
            "outline_color": self.outline_color,
            "outline_width": self.outline_width,
        }

    @classmethod
    def from_wire(cls, value: Any) -> FillSymbol:
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise TypeError("a fill symbol is an object")
        return cls(
            color=str(value["color"]),
            outline_color=str(value["outline_color"]),
            outline_width=float(value["outline_width"]),
        )


#: Any symbol a renderer can hold.
Symbol = MarkerSymbol | LineSymbol | FillSymbol

#: The model each symbol kind reads back from the wire, keyed by its ``kind``.
SYMBOL_MODELS: dict[str, type[MarkerSymbol | LineSymbol | FillSymbol]] = {
    "marker": MarkerSymbol,
    "line": LineSymbol,
    "fill": FillSymbol,
}

#: The symbol kind that draws each geometry type, which is what a fresh layer's
#: renderer is asked for and what a mismatched one is refused against.
SYMBOLS_FOR_GEOMETRY: dict[str, str] = {
    "point": "marker",
    "line": "line",
    "polygon": "fill",
}


def symbol_kind(renderer: Renderer) -> str:
    """Return the kind of symbol ``renderer`` draws with throughout.

    Every renderer in the curated set draws one kind of symbol - a categorized
    renderer's categories are all markers, or all fills - because a renderer that
    mixed kinds would draw the wrong thing on half a layer. The first symbol
    answers for the whole description, and both backends refuse a mismatch
    against the layer's geometry through :func:`symbol_fits_geometry`.
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
    """
    expected = SYMBOLS_FOR_GEOMETRY.get(geometry_type)
    drawn = symbol_kind(renderer)
    if expected is None or drawn == expected:
        return None
    return (
        f"a {renderer.kind} renderer draws {drawn} symbols; the layer is "
        f"{geometry_type} geometry, drawn by {expected}"
    )


def symbol_from_wire(value: Any) -> Symbol:
    """Return the symbol ``value`` describes, dispatching on its ``kind``."""
    for model in (MarkerSymbol, LineSymbol, FillSymbol):
        if isinstance(value, model):
            return value
    if not isinstance(value, Mapping):
        raise TypeError("a symbol is an object")
    kind = value.get("kind")
    model = SYMBOL_MODELS.get(str(kind))
    if model is None:
        raise ValueError(
            f"a symbol's kind is one of {', '.join(SYMBOL_KINDS)}, not {kind!r}"
        )
    return model.from_wire(value)


# -- renderers ----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SingleSymbolRenderer:
    """Every feature drawn the same way."""

    symbol: Symbol
    kind: Literal["single_symbol"] = field(default="single_symbol", init=False)

    def to_wire(self) -> dict[str, Any]:
        return {"kind": self.kind, "symbol": self.symbol.to_wire()}

    @classmethod
    def from_wire(cls, value: Any) -> SingleSymbolRenderer:
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise TypeError("a single symbol renderer is an object")
        return cls(symbol=symbol_from_wire(value["symbol"]))


@dataclass(frozen=True, slots=True)
class Category:
    """One value of the renderer's field, and the symbol drawn for it."""

    value: str
    label: str
    symbol: Symbol

    def to_wire(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "label": self.label,
            "symbol": self.symbol.to_wire(),
        }

    @classmethod
    def from_wire(cls, value: Any) -> Category:
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise TypeError("a category is an object")
        return cls(
            value=str(value["value"]),
            label=str(value["label"]),
            symbol=symbol_from_wire(value["symbol"]),
        )


@dataclass(frozen=True, slots=True)
class CategorizedRenderer:
    """One symbol per distinct value of ``field``."""

    field: str
    categories: tuple[Category, ...]
    kind: Literal["categorized"] = field(default="categorized", init=False)

    def __post_init__(self) -> None:
        _non_empty(self.field, "a categorized renderer's field")
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
    """One band of a graduated renderer: ``lower`` to ``upper``, and its symbol."""

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
    """A field banded into classes, each drawn with its own symbol."""

    field: str
    classes: tuple[GraduatedClass, ...]
    mode: str = "equal_interval"
    kind: Literal["graduated"] = field(default="graduated", init=False)

    def __post_init__(self) -> None:
        _non_empty(self.field, "a graduated renderer's field")
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
    """One rule: an expression, and the symbol drawn where it is true."""

    filter: str
    label: str
    symbol: Symbol
    enabled: bool = True

    def __post_init__(self) -> None:
        _non_empty(self.filter, "a rule's filter expression")

    def to_wire(self) -> dict[str, Any]:
        return {
            "filter": self.filter,
            "label": self.label,
            "enabled": self.enabled,
            "symbol": self.symbol.to_wire(),
        }

    @classmethod
    def from_wire(cls, value: Any) -> Rule:
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
    """Rules evaluated in order; the first one whose expression holds draws."""

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
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise TypeError("a rule-based renderer is an object")
        return cls(rules=tuple(Rule.from_wire(item) for item in value["rules"]))


#: Any renderer a layer can be drawn with.
Renderer = (
    SingleSymbolRenderer | CategorizedRenderer | GraduatedRenderer | RuleBasedRenderer
)

#: The model each renderer kind reads back from the wire, keyed by its ``kind``.
RENDERERS: dict[str, Any] = {
    "single_symbol": SingleSymbolRenderer,
    "categorized": CategorizedRenderer,
    "graduated": GraduatedRenderer,
    "rule_based": RuleBasedRenderer,
}


def renderer_from_wire(value: Any) -> Renderer:
    """Return the renderer ``value`` describes, dispatching on its ``kind``."""
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


# -- labelling ----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Labelling:
    """How a layer's features are labelled, or that they are not.

    ``enabled`` without ``field`` is refused here rather than by QGIS: a layer
    asked to label with no field labels nothing, and a page that switched labels
    on and saw no text would have to guess whether it had asked correctly.
    """

    enabled: bool = False
    field: str | None = None
    size: float = 10.0
    color: str = "#000000"

    def __post_init__(self) -> None:
        if self.enabled and not (self.field or "").strip():
            raise ValueError(
                "labelling a layer needs the field to label; set field= with enabled=True"
            )
        object.__setattr__(self, "size", _positive(self.size, "a label's size"))
        object.__setattr__(self, "color", _colour(self.color, "label colour"))

    def to_wire(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "field": self.field,
            "size": self.size,
            "color": self.color,
        }

    @classmethod
    def from_wire(cls, value: Any) -> Labelling:
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise TypeError("a labelling is an object")
        field_value = value.get("field")
        return cls(
            enabled=bool(value.get("enabled", False)),
            field=None if field_value is None else str(field_value),
            size=float(value.get("size", 10.0)),
            color=str(value.get("color", "#000000")),
        )


def labelling_from_wire(value: Any) -> Labelling:
    """Return the labelling ``value`` describes."""
    return Labelling.from_wire(value)


# -- the style manager, and style text ----------------------------------------


@dataclass(frozen=True, slots=True)
class StyleEntry:
    """One named thing a QGIS style database holds."""

    name: str
    kind: str

    def __post_init__(self) -> None:
        _non_empty(self.name, "a style entry's name")
        if self.kind not in STYLE_MANAGER_KINDS:
            raise ValueError(
                f"a style entry is one of {', '.join(STYLE_MANAGER_KINDS)}, "
                f"not {self.kind!r}"
            )

    def to_wire(self) -> dict[str, Any]:
        return {"name": self.name, "kind": self.kind}

    @classmethod
    def from_wire(cls, value: Any) -> StyleEntry:
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise TypeError("a style entry is an object")
        return cls(name=str(value["name"]), kind=str(value["kind"]))


def style_entry_from_wire(value: Any) -> StyleEntry:
    """Return the style entry ``value`` describes."""
    return StyleEntry.from_wire(value)


@dataclass(frozen=True, slots=True)
class StyleText:
    """A layer's style as text, with the dialect it is written in."""

    format: str
    text: str

    def __post_init__(self) -> None:
        if self.format not in STYLE_FORMATS:
            raise ValueError(
                f"a style format is one of {', '.join(STYLE_FORMATS)}, "
                f"not {self.format!r}"
            )
        if not isinstance(self.text, str) or not self.text:
            raise ValueError("a style's text is not empty")

    def to_wire(self) -> dict[str, Any]:
        return {"format": self.format, "text": self.text}


# -- the wire shapes ----------------------------------------------------------

_NULLABLE_STRING: dict[str, Any] = {"anyOf": [{"type": "string"}, {"type": "null"}]}
_NUMBER = {"type": "number"}
_COLOUR_SCHEMA = {"type": "string", "pattern": _COLOUR.pattern}


def _schema(title: str, kind: str, properties: Mapping[str, Any]) -> dict[str, Any]:
    """One wire object: its discriminator first, then its own fields."""
    return {
        "type": "object",
        "title": title,
        "properties": {"kind": {"enum": [kind]}, **properties},
        "required": ["kind", *properties],
        "additionalProperties": False,
    }


MARKER_SYMBOL = _schema(
    "MarkerSymbol",
    "marker",
    {
        "color": _COLOUR_SCHEMA,
        "size": _NUMBER,
        "shape": {"enum": list(MARKER_SHAPES)},
        "outline_color": _COLOUR_SCHEMA,
        "outline_width": _NUMBER,
    },
)

LINE_SYMBOL = _schema(
    "LineSymbol",
    "line",
    {"color": _COLOUR_SCHEMA, "width": _NUMBER},
)

FILL_SYMBOL = _schema(
    "FillSymbol",
    "fill",
    {
        "color": _COLOUR_SCHEMA,
        "outline_color": _COLOUR_SCHEMA,
        "outline_width": _NUMBER,
    },
)

#: Every symbol schema, by kind, in wire order - the table the host catalogue and
#: the generator read so a new symbol kind cannot be described in one place and
#: forgotten in another.
SYMBOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "marker": MARKER_SYMBOL,
    "line": LINE_SYMBOL,
    "fill": FILL_SYMBOL,
}

#: Any symbol: the union a renderer's symbol and a category's symbol carry.
SYMBOL: dict[str, Any] = {
    "anyOf": [SYMBOL_SCHEMAS[kind] for kind in SYMBOL_SCHEMAS],
}

CATEGORY: dict[str, Any] = {
    "type": "object",
    "title": "Category",
    "properties": {
        "value": {"type": "string"},
        "label": {"type": "string"},
        "symbol": SYMBOL,
    },
    "required": ["value", "label", "symbol"],
    "additionalProperties": False,
}

GRADUATED_CLASS: dict[str, Any] = {
    "type": "object",
    "title": "GraduatedClass",
    "properties": {
        "lower": _NUMBER,
        "upper": _NUMBER,
        "label": {"type": "string"},
        "symbol": SYMBOL,
    },
    "required": ["lower", "upper", "label", "symbol"],
    "additionalProperties": False,
}

RULE: dict[str, Any] = {
    "type": "object",
    "title": "Rule",
    "properties": {
        "filter": {"type": "string"},
        "label": {"type": "string"},
        "enabled": {"type": "boolean"},
        "symbol": SYMBOL,
    },
    "required": ["filter", "label", "enabled", "symbol"],
    "additionalProperties": False,
}

SINGLE_SYMBOL_RENDERER = _schema(
    "SingleSymbolRenderer", "single_symbol", {"symbol": SYMBOL}
)

CATEGORIZED_RENDERER = _schema(
    "CategorizedRenderer",
    "categorized",
    {"field": {"type": "string"}, "categories": {"type": "array", "items": CATEGORY}},
)

GRADUATED_RENDERER = _schema(
    "GraduatedRenderer",
    "graduated",
    {
        "field": {"type": "string"},
        "mode": {"enum": list(GRADUATED_MODES)},
        "classes": {"type": "array", "items": GRADUATED_CLASS},
    },
)

RULE_BASED_RENDERER = _schema(
    "RuleBasedRenderer", "rule_based", {"rules": {"type": "array", "items": RULE}}
)

#: Every renderer schema, by kind, in wire order.
RENDERER_SCHEMAS: dict[str, dict[str, Any]] = {
    "single_symbol": SINGLE_SYMBOL_RENDERER,
    "categorized": CATEGORIZED_RENDERER,
    "graduated": GRADUATED_RENDERER,
    "rule_based": RULE_BASED_RENDERER,
}

#: Any renderer: the union ``symbology.get`` answers and ``symbology.set`` takes.
RENDERER: dict[str, Any] = {
    "anyOf": [RENDERER_SCHEMAS[kind] for kind in RENDERER_SCHEMAS]
}

LABELLING: dict[str, Any] = {
    "type": "object",
    "title": "Labelling",
    "properties": {
        "enabled": {"type": "boolean"},
        "field": _NULLABLE_STRING,
        "size": _NUMBER,
        "color": _COLOUR_SCHEMA,
    },
    "required": ["enabled", "field", "size", "color"],
    "additionalProperties": False,
}

STYLE_ENTRY: dict[str, Any] = {
    "type": "object",
    "title": "StyleEntry",
    "properties": {
        "name": {"type": "string"},
        "kind": {"enum": list(STYLE_MANAGER_KINDS)},
    },
    "required": ["name", "kind"],
    "additionalProperties": False,
}

STYLE_TEXT: dict[str, Any] = {
    "type": "object",
    "title": "StyleText",
    "properties": {
        "format": {"enum": list(STYLE_FORMATS)},
        "text": {"type": "string"},
    },
    "required": ["format", "text"],
    "additionalProperties": False,
}

#: The TypeScript name each renderer is declared under, so the generated union
#: and the model module cannot disagree about what a kind is called.
RENDERER_NAMES: dict[str, str] = {
    kind: str(schema["title"]) for kind, schema in RENDERER_SCHEMAS.items()
}

#: The TypeScript name each symbol is declared under.
SYMBOL_NAMES: dict[str, str] = {
    kind: str(schema["title"]) for kind, schema in SYMBOL_SCHEMAS.items()
}

#: Every renderer model, by kind, as a tuple a test can walk: the order is the
#: wire order, so a test that iterates it checks the same sequence a page sees.
RENDERER_MODELS: tuple[Any, ...] = tuple(
    RENDERERS[kind] for kind in RENDERER_KIND_NAMES
)

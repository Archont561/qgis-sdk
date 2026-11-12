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

SYMBOL_KINDS: tuple[str, ...] = ("marker", "line", "fill")
RENDERER_KIND_NAMES: tuple[str, ...] = (
    "single_symbol",
    "categorized",
    "graduated",
    "rule_based",
)
GRADUATED_MODES: tuple[str, ...] = (
    "equal_interval",
    "quantile",
    "jenks",
    "std_dev",
    "pretty",
    "custom",
)
MARKER_SHAPES: tuple[str, ...] = (
    "circle",
    "square",
    "diamond",
    "triangle",
    "star",
)
STYLE_FORMATS: tuple[str, ...] = ("qml", "sld")
STYLE_MANAGER_KINDS: tuple[str, ...] = ("symbol", "color_ramp", "label_settings")
COLOUR = re.compile(r"#[0-9a-f]{6}")


def colour(value: str, what: str) -> str:
    """Return ``value`` as a lower-case ``#rrggbb`` colour, or refuse it by name.

    Normalising here is what makes a get/set round trip comparable: QGIS answers
    ``QColor.name()`` in lower case, so a caller that wrote ``#FF0000`` gets
    ``#ff0000`` back and one assertion holds on both backends.
    """
    if not isinstance(value, str):
        raise TypeError(f"a {what} is a '#rrggbb' string")
    normalised = value.lower()
    if not COLOUR.fullmatch(normalised):
        raise ValueError(f"a {what} is '#rrggbb', not {value!r}")
    return normalised


def positive(value: float, what: str) -> float:
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


def non_empty(value: str, what: str) -> str:
    """Return ``value`` stripped, refusing an empty or blank string."""
    if not isinstance(value, str):
        raise TypeError(f"{what} is a string")
    if not value.strip():
        raise ValueError(f"{what} is not blank")
    return value


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
        object.__setattr__(self, "color", colour(self.color, "marker colour"))
        object.__setattr__(
            self, "outline_color", colour(self.outline_color, "marker outline colour")
        )
        object.__setattr__(self, "size", positive(self.size, "a marker's size"))
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
        object.__setattr__(self, "color", colour(self.color, "line colour"))
        object.__setattr__(self, "width", positive(self.width, "a line's width"))

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
        object.__setattr__(self, "color", colour(self.color, "fill colour"))
        object.__setattr__(
            self, "outline_color", colour(self.outline_color, "fill outline colour")
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


Symbol = MarkerSymbol | LineSymbol | FillSymbol
SYMBOL_MODELS: dict[str, type[MarkerSymbol | LineSymbol | FillSymbol]] = {
    "marker": MarkerSymbol,
    "line": LineSymbol,
    "fill": FillSymbol,
}
SYMBOLS_FOR_GEOMETRY: dict[str, str] = {
    "point": "marker",
    "line": "line",
    "polygon": "fill",
}


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

"""Labelling, the style-manager entry list, and markup text, as values."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ._symbols import (
    COLOUR,
    STYLE_FORMATS,
    STYLE_MANAGER_KINDS,
    colour,
    non_empty,
    positive,
)

__all__ = [
    "Labelling",
    "StyleEntry",
    "StyleText",
    "labelling_from_wire",
    "style_entry_from_wire",
]


@dataclass(frozen=True, slots=True)
class Labelling:
    """How a layer's features are labelled, or that they are not.

    ``enabled`` without ``field`` is refused here rather than by QGIS: a layer
    asked to label with no field labels nothing, and a page that switched labels
    on and saw no text would have to guess whether it had asked correctly.

    Attributes:
        enabled: Whether the layer's features are labelled at all.
        field: The attribute field the label text comes from, if labelling is on.
        size: The label's text size in millimetres.
        color: The label's text colour, as ``#RRGGBB``.
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
        object.__setattr__(self, "size", positive(self.size, "a label's size"))
        object.__setattr__(self, "color", colour(self.color, "label colour"))

    def to_wire(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "field": self.field,
            "size": self.size,
            "color": self.color,
        }

    @classmethod
    def from_wire(cls, value: Any) -> Labelling:
        """Rebuild this value from its wire shape.

        Args:
            value: The mapping a page sent, whose keys are checked.
        """
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
    """Return the labelling ``value`` describes.

    Args:
        value: The mapping a page sent.
    """
    return Labelling.from_wire(value)


@dataclass(frozen=True, slots=True)
class StyleEntry:
    """One named thing a QGIS style database holds.

    Attributes:
        name: The style's name in the project's style manager.
        kind: What it can be applied to: ``symbol``, ``colorramp`` and so on.
    """

    name: str
    kind: str

    def __post_init__(self) -> None:
        non_empty(self.name, "a style entry's name")
        if self.kind not in STYLE_MANAGER_KINDS:
            raise ValueError(
                f"a style entry is one of {', '.join(STYLE_MANAGER_KINDS)}, "
                f"not {self.kind!r}"
            )

    def to_wire(self) -> dict[str, Any]:
        return {"name": self.name, "kind": self.kind}

    @classmethod
    def from_wire(cls, value: Any) -> StyleEntry:
        """Rebuild this value from its wire shape.

        Args:
            value: The mapping a page sent, whose keys are checked.
        """
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise TypeError("a style entry is an object")
        return cls(name=str(value["name"]), kind=str(value["kind"]))


def style_entry_from_wire(value: Any) -> StyleEntry:
    """Return the style entry ``value`` describes.

    Args:
        value: The mapping a page sent.
    """
    return StyleEntry.from_wire(value)


@dataclass(frozen=True, slots=True)
class StyleText:
    """A layer's style as text, with the dialect it is written in.

    Attributes:
        format: The dialect the text is in: ``qml`` or ``sld``.
        text: The style document itself.
    """

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


NULLABLE_STRING: dict[str, Any] = {"anyOf": [{"type": "string"}, {"type": "null"}]}
NUMBER = {"type": "number"}
COLOUR_SCHEMA = {"type": "string", "pattern": COLOUR.pattern}

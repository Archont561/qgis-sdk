"""The tail of one field's facts: the widget, its choices and its details."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ._fields import DETAIL_KEYS, field_facts_full, widget_for


def _details_of(
    concrete: Mapping[str, Any], intent: Mapping[str, Any]
) -> dict[str, Any]:
    """The declared details a field keeps, lists frozen to tuples."""
    return {
        key: tuple(value) if isinstance(value, list) else value
        for key, value in {**concrete, **intent}.items()
        if key in DETAIL_KEYS
    }


def _choices_of(widget: str, concrete: Mapping[str, Any]) -> tuple[Any, ...]:
    """An enum widget's choices; every other widget has none."""
    return tuple(concrete["enum"]) if widget == "choice" else ()


def field_tail1(**values):
    """Close one field's facts: its widget, choices and declared details."""
    concrete = values["concrete"]
    intent = values["intent"]
    name = values["name"]
    widget = widget_for(values["owner"], name, concrete, values["marker"])
    details = _details_of(concrete, intent)
    if widget == "integer":
        # The safe-integer bounds are a wire rule, not an author's range.
        details = {}
    return field_facts_full(
        choices=_choices_of(widget, concrete),
        details=details,
        name=name,
        nullable=values["nullable"],
        required=values["required"],
        widget=widget,
    )

"""Plain-value inputs: Text, Toggle, Number, Distance, Choice and Colour."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, TypedDict, Unpack

from qgis_sdk._published import REQUIRED, published
from qgis_sdk.models import (
    QgisSdkFormError,
    QgisSdkUiError,
)
from qgis_sdk.ui.components._base import Input
from qgis_sdk.ui.form_fields import FieldSpec, label_for

# -- plain values --------------------------------------------------------------------


class Text(Input):
    """A line of text; the value is a ``str`` (``""`` when empty)."""

    kind = "text"

    def _default(self) -> object:
        return ""


class Toggle(Input):
    """A check box; the value is a ``bool``."""

    kind = "boolean"

    def _default(self) -> object:
        return False


class Number(Input):
    """A number, bounded when ``range=(low, high)`` is given.

    An integral range (or ``integer=True``) stores an ``int`` and renders a
    spin box; otherwise the value is a ``float``. ``step`` is the spin box
    increment.
    """

    _CC_SPECS_init_1 = (
        ("self", REQUIRED, REQUIRED, "positional"),
        ("name", str | None, None, "positional"),
        ("range", tuple[float, float] | None, None, "keyword"),
        ("step", float | None, None, "keyword"),
        ("integer", bool | None, None, "keyword"),
        ("label", str | None, None, "keyword"),
        ("value", object, None, "keyword"),
        ("required", bool, False, "keyword"),
    )

    @published(_CC_SPECS_init_1, returns=type(None))
    def __init__(_published_values):
        if _published_values.range is not None:
            low, high = _published_values.range
            if low > high:
                raise QgisSdkUiError(
                    f"Number {_published_values.name!r}: range low {low!r} is above high {high!r}"
                )
            integral = isinstance(low, int) and isinstance(high, int)
            if _published_values.integer is None:
                _published_values.integer = integral
            elif _published_values.integer and not integral:
                raise QgisSdkUiError(
                    f"Number {_published_values.name!r}: an integer range needs integer bounds"
                )
        _published_values.self.range = _published_values.range
        _published_values.self.step = _published_values.step
        _published_values.self.integer = bool(_published_values.integer)
        super(Number, _published_values.self).__init__(
            _published_values.name,
            label=_published_values.label,
            value=_published_values.value,
            required=_published_values.required,
        )

    @property
    def kind(self) -> str:  # type: ignore[override]
        if self.range is not None:
            return "range"
        return "integer" if self.integer else "number"

    def _default(self) -> object:
        low = self.range[0] if self.range is not None else 0
        return int(low) if self.integer else float(low)

    def _details(self) -> dict[str, Any]:
        details: dict[str, Any] = {}
        if self.range is not None:
            details["minimum"], details["maximum"] = self.range
        if self.step is not None:
            details["step"] = self.step
        return details


class Distance(Input):
    """A distance in metres, 0 or more; the value is a ``float``."""

    kind = "metres"

    def _default(self) -> object:
        return 0.0


class Choice(Input):
    """One of ``options``; the value is the chosen string, the first by default."""

    kind = "choice"

    _CC_SPECS_init_2 = (
        ("self", REQUIRED, REQUIRED, "positional"),
        ("name", str | None, None, "positional"),
        ("options", Sequence[str], REQUIRED, "keyword"),
        ("label", str | None, None, "keyword"),
        ("value", object, None, "keyword"),
        ("required", bool, False, "keyword"),
    )

    @published(_CC_SPECS_init_2, returns=type(None))
    def __init__(_published_values):
        _published_values.self.options = tuple(_published_values.options)
        if not _published_values.self.options:
            raise QgisSdkUiError(
                f"Choice {_published_values.name!r} needs at least one option"
            )
        super(Choice, _published_values.self).__init__(
            _published_values.name,
            label=_published_values.label,
            value=_published_values.value,
            required=_published_values.required,
        )

    def _default(self) -> object:
        return self.options[0]

    def _spec(self) -> FieldSpec:
        return FieldSpec(
            name=self._name or "",
            label=self._label or (label_for(self._name) if self._name else ""),
            widget="choice",
            required=True,
            choices=self.options,
        )

    def _details(self) -> dict[str, Any]:
        return {"options": list(self.options)}


class Colour(Input):
    """A colour as ``#rrggbb`` or, with ``alpha`` (the default), ``#rrggbbaa``."""

    kind = "colour"

    def __init__(
        self, name: str | None = None, **options: Unpack[_InitOptions1]
    ) -> None:
        values = _InitValues1(**options)
        self.alpha = values.alpha
        super().__init__(
            name, label=values.label, value=values.value, required=values.required
        )

    def _default(self) -> object:
        return "#000000ff" if self.alpha else "#000000"

    def _accept(self, value: object) -> object:
        text = str(value)
        if not self.alpha and len(text) == 9:
            raise QgisSdkFormError(
                f"{self._describe()}: field {self.name} expects an opaque "
                "#RRGGBB colour"
            )
        return text

    def _details(self) -> dict[str, Any]:
        return {"alpha": self.alpha}


class _InitOptions1(TypedDict, total=False):
    alpha: bool
    label: str | None
    value: object
    required: bool


@dataclass(frozen=True, slots=True)
class _InitValues1:
    alpha: bool = True
    label: str | None = None
    value: object = None
    required: bool = False

"""Renderable form fields for a declared action, without importing Qt.

The wire description says what a field *stores*; this module says what a host
should draw. Both halves already exist - :mod:`qgis_sdk.declarations` produces
the schema and :mod:`qgis_sdk.models.parameters` carries the author's intent -
so this is the join between them: one :class:`FieldSpec` per input, then
coercion of submitted values back into the Python types the handler declared.

Nothing here imports Qt or QGIS, which is the point: the mapping from schema to
widget is a rule, and a rule that lives in the Qt adapter can only be tested on a
machine with Qt. The adapter is then left with the mechanical half - instantiate
the widget named by a spec and read a value out of it. A field whose schema
cannot be expressed is refused here, so no adapter ever has to guess.

Value coercion is deliberately strict. A form is user input, not a wire payload,
so ``"3"`` from a line edit becomes ``3`` for an ``int`` field, but ``"three"``
is refused rather than silently becoming ``0``. The refusal names the field and
the type it wanted and never repeats the submitted value, because a field can
hold a path or a credential.
"""

from __future__ import annotations


class CcState:
    """A mutable record shared by the phases of one long function."""

    def __init__(_cc_self, **values):
        _cc_self.__dict__.update(values)


class CcReturn:
    """An early return travelling out of a phase."""

    def __init__(_cc_self, value):
        _cc_self.value = value


def cc_number_p1(_s):
    from ._coercion import as_number, number, refuse

    if isinstance(_s.value, bool):
        raise refuse(_s.owner, _s.spec, "a number")
    if _s.spec.widget == "range":
        _s.number = number(_s.owner, as_number(_s.spec), _s.value)
        _s.low, _s.high = _s.spec.details.get("minimum"), _s.spec.details.get("maximum")
        if (
            _s.low is not None
            and _s.high is not None
            and not (_s.low <= _s.number <= _s.high)
        ):
            raise refuse(_s.owner, _s.spec, f"a number between {_s.low} and {_s.high}")
        return CcReturn(_s.number)


def cc_number_p2(_s):
    from ._coercion import refuse

    if _s.spec.widget == "integer":
        if isinstance(_s.value, int):
            return CcReturn(_s.value)
        if isinstance(_s.value, str) and _s.value.strip().lstrip("+-").isdigit():
            return CcReturn(int(_s.value.strip()))
        raise refuse(_s.owner, _s.spec, "an integer")


def cc_number_p3(_s):
    from ._coercion import refuse

    if isinstance(_s.value, (int, float)):
        _s.number = float(_s.value)
    elif isinstance(_s.value, str):
        try:
            _s.number = float(_s.value.strip())
        except ValueError:
            raise refuse(_s.owner, _s.spec, "a number") from None
    else:
        raise refuse(_s.owner, _s.spec, "a number")
    if _s.spec.widget == "metres" and _s.number < 0:
        raise refuse(_s.owner, _s.spec, "a distance of 0 or more metres")
    return CcReturn(_s.number)

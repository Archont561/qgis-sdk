"""The expression subset the fake layers understand, and why it is a subset.

The native adapter hands expressions to ``QgsExpression``: a real parser with
functions, aggregates and provider callbacks. A fake that pretended to run that
language would be worse than one that refuses it, because a test written against
the fake would pass for a syntax the real host rejects. So the fake implements a
small, explicitly documented subset and says so when asked for anything else:

* a comparison of one field against a literal - ``"pop" > 100``, ``name = 'x'``,
  ``field IS NULL``, ``field IS NOT NULL``;
* those comparisons joined with ``and`` / ``or``, evaluated left to right;
* for ``evaluate``: the same comparisons, a bare field name, or a literal.

Anything else - a function call, arithmetic, an aggregate, a nested expression -
raises :class:`QgisSdkUnsupportedCapabilityError` naming the construct. A test
that needs it is a test that needs QGIS.
"""

from __future__ import annotations

import operator as _operator
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from qgis_sdk.models.errors import QgisSdkUnsupportedCapabilityError

__all__ = [
    "ExpressionSubset",
    "ParsedExpression",
    "literal_token",
    "literal_value",
]

_TOKEN = re.compile(
    r"""
    \s*(?:
        (?P<op><=|>=|<>|!=|==|=|<|>)
      | (?P<paren>[()])
      | (?P<isnull>IS\s+NOT\s+NULL|IS\s+NULL)
      | (?P<logic>AND|OR|NOT)\b
      | (?P<number>-?\d+(?:\.\d+)?)
      | (?P<string>'[^']*'|"[^"]*")
      | (?P<name>[A-Za-z_][A-Za-z0-9_]*)
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)


@dataclass(frozen=True, slots=True)
class _Token:
    kind: str
    value: str


def _tokenize(text: str) -> list[_Token]:
    tokens: list[_Token] = []
    at = 0
    stripped = text.rstrip()
    while at < len(stripped):
        match = _TOKEN.match(stripped, at)
        if match is None or match.end() == at:
            raise QgisSdkUnsupportedCapabilityError(
                f"the fake expression subset cannot read {stripped[at:]!r}"
            )
        at = match.end()
        for kind in ("op", "paren", "isnull", "logic", "number", "string", "name"):
            value = match.group(kind)
            if value is not None:
                tokens.append(_Token(kind, value))
                break
    return tokens


def literal_token(text: str) -> _Token:
    """Parse one literal or field name, refusing anything longer.

    ``evaluate`` and ``feature`` read a value rather than a filter, and a value
    is exactly one token; anything else is the caller expecting a filter.
    """
    tokens = _tokenize(text)
    if len(tokens) != 1:
        raise QgisSdkUnsupportedCapabilityError(
            f"the fake expression subset cannot read {text!r}"
        )
    return tokens[0]


def literal_value(token: _Token) -> Any:
    """The Python value of one token: a number, a string, a boolean or null."""
    return _literal(token)


def _literal(token: _Token) -> Any:
    if token.kind == "string":
        return token.value[1:-1]
    if token.kind == "number":
        return float(token.value) if "." in token.value else int(token.value)
    if token.kind == "name":
        lowered = token.value.lower()
        if lowered == "null":
            return None
        if lowered == "true":
            return True
        if lowered == "false":
            return False
    raise QgisSdkUnsupportedCapabilityError(
        f"the fake expression subset has no value {token.value!r}"
    )


@dataclass(frozen=True, slots=True)
class ParsedExpression:
    """One parsed expression: a list of clauses joined by ``and`` / ``or``."""

    #: ``(field, operator, value)`` triples, in order.
    clauses: tuple[tuple[str, str, Any], ...]
    #: The joins between clauses: one fewer than the clauses.
    joins: tuple[str, ...]
    columns: tuple[str, ...]

    def matches(self, row: Mapping[str, Any]) -> bool:
        """Evaluate the clauses against one row, left to right.

        ``and`` binds as tightly as ``or`` here on purpose: the fake refuses
        parentheses, so an expression whose meaning depends on precedence is
        one the fake will not run rather than one it silently reinterprets.
        """
        result = _compare(row, *self.clauses[0])
        for join, clause in zip(self.joins, self.clauses[1:], strict=True):
            value = _compare(row, *clause)
            result = (result and value) if join == "AND" else (result or value)
        return result


_COMPARISONS: dict[str, Callable[[Any, Any], bool]] = {
    "=": _operator.eq,
    "==": _operator.eq,
    "!=": _operator.ne,
    "<>": _operator.ne,
    "<": _operator.lt,
    "<=": _operator.le,
    ">": _operator.gt,
    ">=": _operator.ge,
}
"""The binary operators the expression subset admits, by their QGIS spelling."""


def _compare(row: Mapping[str, Any], field: str, op: str, value: Any) -> bool:
    current = row.get(field)
    if op == "IS NULL":
        return current is None
    if op == "IS NOT NULL":
        return current is not None
    if current is None:
        # A null compares false with everything but its own null test, which is
        # what SQL and QgsExpression both do; returning False here keeps the
        # fake and the native adapter agreeing on the common case.
        return False
    compare = _COMPARISONS.get(op)
    if compare is None:
        raise QgisSdkUnsupportedCapabilityError(op)
    try:
        return compare(current, value)
    except TypeError:
        return False


class _ExpressionReader:
    """The mutable cursor while one expression is read clause by clause."""

    def __init__(self, tokens: Sequence[_Token], known: tuple[str, ...]) -> None:
        self.tokens = tokens
        self.known = known
        self.index = 0
        self.clauses: list[tuple[str, str, Any]] = []
        self.joins: list[str] = []

    def need(self, kind: str) -> _Token:
        """Read one token of ``kind``, or refuse naming what was read."""
        if self.index >= len(self.tokens) or self.tokens[self.index].kind != kind:
            found = (
                self.tokens[self.index].value
                if self.index < len(self.tokens)
                else "the end"
            )
            raise QgisSdkUnsupportedCapabilityError(
                f"the fake expression subset expected {kind} and read {found!r}"
            )
        self.index += 1
        return self.tokens[self.index - 1]

    def field(self) -> str:
        """Read and validate the field name one comparison starts with."""
        if self.index < len(self.tokens) and self.tokens[self.index].kind == "paren":
            raise QgisSdkUnsupportedCapabilityError(
                "the fake expression subset has no parentheses; "
                "use QGIS for a nested expression"
            )
        token = self.tokens[self.index] if self.index < len(self.tokens) else None
        if token is None or token.kind not in ("name", "string"):
            raise QgisSdkUnsupportedCapabilityError(
                "the fake expression subset compares a field with a value"
            )
        self.index += 1
        name = token.value if token.kind == "name" else token.value[1:-1]
        if name.lower() in ("and", "or", "not"):
            raise QgisSdkUnsupportedCapabilityError(
                f"the fake expression subset has no function call {name!r}"
            )
        if name not in self.known:
            raise QgisSdkUnsupportedCapabilityError(
                f"the layer has no field {name!r}; fields are {list(self.known)}"
            )
        return name

    def clause(self, field: str) -> None:
        """Read one ``IS NULL`` or comparison clause for ``field``."""
        if self.index < len(self.tokens) and self.tokens[self.index].kind == "isnull":
            self.clauses.append((field, self.tokens[self.index].value.upper(), None))
            self.index += 1
            return
        operator = self.need("op").value.upper()
        if self.index >= len(self.tokens) or self.tokens[self.index].kind not in (
            "number",
            "string",
            "name",
        ):
            raise QgisSdkUnsupportedCapabilityError(
                "the fake expression subset compares a field with a literal"
            )
        self.clauses.append((field, operator, _literal(self.tokens[self.index])))
        self.index += 1

    def join(self) -> None:
        """Read the and/or joining this clause to the next one."""
        value = self.need("logic").value.upper()
        if value not in ("AND", "OR"):
            raise QgisSdkUnsupportedCapabilityError(
                f"the fake expression subset joins with and/or, not {value!r}"
            )
        self.joins.append(value)

    def expression(self) -> ParsedExpression:
        """Read clauses and joins until the tokens run out."""
        while True:
            self.clause(self.field())
            if self.index >= len(self.tokens):
                break
            self.join()
        return ParsedExpression(
            clauses=tuple(self.clauses),
            joins=tuple(self.joins),
            columns=tuple(self.known),
        )


class ExpressionSubset:
    """Parse and run the subset; one instance, no state between calls."""

    @staticmethod
    @staticmethod
    def parse(text: str, fields: Iterable[str]) -> ParsedExpression:
        """Parse ``text``, refusing anything outside the subset by name."""
        if not isinstance(text, str) or not text.strip():
            raise QgisSdkUnsupportedCapabilityError(
                "an expression is a non-empty string"
            )
        return _ExpressionReader(_tokenize(text), tuple(fields)).expression()

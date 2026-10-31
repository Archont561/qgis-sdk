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

import re
from collections.abc import Iterable, Mapping
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


def _compare(row: Mapping[str, Any], field: str, operator: str, value: Any) -> bool:
    current = row.get(field)
    if operator == "IS NULL":
        return current is None
    if operator == "IS NOT NULL":
        return current is not None
    if current is None:
        # A null compares false with everything but its own null test, which is
        # what SQL and QgsExpression both do; returning False here keeps the
        # fake and the native adapter agreeing on the common case.
        return False
    try:
        if operator in ("=", "=="):
            return current == value
        if operator in ("!=", "<>"):
            return current != value
        if operator == "<":
            return current < value
        if operator == "<=":
            return current <= value
        if operator == ">":
            return current > value
        if operator == ">=":
            return current >= value
    except TypeError:
        return False
    raise QgisSdkUnsupportedCapabilityError(operator)


class ExpressionSubset:
    """Parse and run the subset; one instance, no state between calls."""

    @staticmethod
    def parse(text: str, fields: Iterable[str]) -> ParsedExpression:
        """Parse ``text``, refusing anything outside the subset by name."""
        if not isinstance(text, str) or not text.strip():
            raise QgisSdkUnsupportedCapabilityError(
                "an expression is a non-empty string"
            )
        tokens = _tokenize(text)
        known = tuple(fields)
        clauses: list[tuple[str, str, Any]] = []
        joins: list[str] = []
        index = 0

        def need(kind: str) -> _Token:
            nonlocal index
            if index >= len(tokens) or tokens[index].kind != kind:
                found = tokens[index].value if index < len(tokens) else "the end"
                raise QgisSdkUnsupportedCapabilityError(
                    f"the fake expression subset expected {kind} and read {found!r}"
                )
            index += 1
            return tokens[index - 1]

        while True:
            if index < len(tokens) and tokens[index].kind == "paren":
                raise QgisSdkUnsupportedCapabilityError(
                    "the fake expression subset has no parentheses; "
                    "use QGIS for a nested expression"
                )
            field_token = tokens[index] if index < len(tokens) else None
            if field_token is None or field_token.kind not in ("name", "string"):
                raise QgisSdkUnsupportedCapabilityError(
                    "the fake expression subset compares a field with a value"
                )
            index += 1
            field = (
                field_token.value
                if field_token.kind == "name"
                else field_token.value[1:-1]
            )
            if field.lower() in ("and", "or", "not"):
                raise QgisSdkUnsupportedCapabilityError(
                    f"the fake expression subset has no function call {field!r}"
                )
            if field not in known:
                raise QgisSdkUnsupportedCapabilityError(
                    f"the layer has no field {field!r}; fields are {list(known)}"
                )
            if index < len(tokens) and tokens[index].kind == "isnull":
                clauses.append((field, tokens[index].value.upper(), None))
                index += 1
            else:
                operator = need("op").value.upper()
                if index >= len(tokens) or tokens[index].kind not in (
                    "number",
                    "string",
                    "name",
                ):
                    raise QgisSdkUnsupportedCapabilityError(
                        "the fake expression subset compares a field with a literal"
                    )
                value = _literal(tokens[index])
                index += 1
                clauses.append((field, operator, value))
            if index >= len(tokens):
                break
            join = need("logic").value.upper()
            if join not in ("AND", "OR"):
                raise QgisSdkUnsupportedCapabilityError(
                    f"the fake expression subset joins with and/or, not {join!r}"
                )
            joins.append(join)
        return ParsedExpression(
            clauses=tuple(clauses), joins=tuple(joins), columns=tuple(known)
        )

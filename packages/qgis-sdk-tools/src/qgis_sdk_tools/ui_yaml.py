"""YAML for a captured surface tree, in the developer tools only (decision-51).

The snapshot format itself is canonical JSON: that is what a fixture approves,
what ``qgis-sdk ui diff`` compares, and what the runtime writes. YAML is a
*reading* format for a human or an agent looking at a capture in a terminal, so
it lives here - in the tools - and the runtime never learns about it.

The emitter is deliberately small: a snapshot is mappings, sequences and
scalars (``str``/``int``/``float``/``bool``/``None``), never an alias, anchor or
multi-document stream. Anything a parser could read as a keyword is quoted, so
``yaml.safe_load`` gives the payload back unchanged.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from typing import Any, Final

__all__ = ["to_yaml"]

_PLAIN: Final = re.compile(r"[A-Za-z_][A-Za-z0-9_./\-]*")
"""What needs no quotes: an identifier-shaped string with no YAML punctuation."""

_KEYWORDS: Final = frozenset(
    {"yes", "no", "on", "off", "true", "false", "null", "none", "~"}
)
"""Words YAML 1.1 reads as booleans or null, so a string spelling one is quoted."""


def to_yaml(payload: Any) -> str:
    """Render ``payload`` as a block-style YAML document with a trailing newline."""
    if isinstance(payload, Mapping):
        lines = _mapping(payload, 0)
    elif _is_sequence(payload):
        lines = _sequence(payload, 0)
    else:
        lines = [_scalar(payload)]
    return "\n".join(lines) + "\n"


def _mapping(payload: Mapping[Any, Any], depth: int) -> list[str]:
    if not payload:
        return [" " * depth + "{}"]
    lines: list[str] = []
    for key, value in payload.items():
        lines.extend(_entry(str(key), value, depth))
    return lines


def _entry(key: str, value: Any, depth: int) -> list[str]:
    """One ``key: value`` pair, as the lines that render it at ``depth``."""
    pad = " " * depth
    if _is_container(value):
        if not value:
            return [f"{pad}{_text(key)}: {_empty(value)}"]
        return [f"{pad}{_text(key)}:", *_block(value, depth + 2)]
    return [f"{pad}{_text(key)}: {_scalar(value)}"]


def _sequence(payload: Sequence[Any], depth: int) -> list[str]:
    if not payload:
        return [" " * depth + "[]"]
    lines: list[str] = []
    pad = " " * depth
    for item in payload:
        if _is_container(item) and item:
            inner = _block(item, depth + 2)
            if isinstance(item, Mapping):
                # The first key rides on the dash, the rest line up under it.
                first = inner[0].lstrip()
                lines.append(f"{pad}- {first}")
                lines.extend(inner[1:])
            else:
                lines.append(f"{pad}-")
                lines.extend(inner)
        elif _is_container(item):
            lines.append(f"{pad}- {_empty(item)}")
        else:
            lines.append(f"{pad}- {_scalar(item)}")
    return lines


def _block(value: Any, depth: int) -> list[str]:
    return (
        _mapping(value, depth)
        if isinstance(value, Mapping)
        else _sequence(value, depth)
    )


def _empty(value: Any) -> str:
    return "{}" if isinstance(value, Mapping) else "[]"


def _is_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    )


def _is_container(value: Any) -> bool:
    return isinstance(value, Mapping) or _is_sequence(value)


def _text(value: str) -> str:
    if _PLAIN.fullmatch(value) and value.lower() not in _KEYWORDS:
        return value
    return json.dumps(value)


def _scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        # ``nan``/``inf`` are not YAML scalars a reader can take literally; a
        # string keeps the payload lossless instead of inventing a number.
        return repr(value) if math.isfinite(value) else json.dumps(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, (str, bytes)):
        return _text(value if isinstance(value, str) else value.decode("utf-8"))
    return _text(json.dumps(value, sort_keys=True))

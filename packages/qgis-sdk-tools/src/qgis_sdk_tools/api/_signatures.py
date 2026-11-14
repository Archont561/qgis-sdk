"""One callable's signature, written the same way on every Python.

The inventory is diffed between releases, so its text has to mean the same thing
on every interpreter - and ``inspect`` alone does not give that. An annotation
reaches it as a source string when the module uses ``from __future__ import
annotations``, as an evaluated object when it does not, and as a re-rendered
string on 3.14, which reads annotations lazily; ``typing.Optional[X]`` prints as
``typing.Optional[pathlib.Path]`` on 3.11 and ``pathlib.Path | None`` on 3.14.

So the recorded form is the short name the source would have written, unions are
written in one spelling, and defaults survive only when they are literals.
"""

from __future__ import annotations

import inspect
import re
from typing import Any

__all__ = ["enum_members", "signature_of", "text_of"]

try:  # 3.14 reads annotations lazily; its module is absent before that.
    from annotationlib import Format as _Format
except ImportError:  # older interpreters keep the source text already.
    _Format = None


SIMPLE_DEFAULTS = (str, int, float, bool, type(None))
"""Default values rendered literally; anything else renders as ``...``.

A repr that a release can reword (an enum, a Path, a sentinel) is not something
a contract should depend on, so the document says "there is a default" and stops
there.
"""


def _default(value: Any) -> str:
    """One parameter's default: its literal, or ``...`` when it is not one."""
    return repr(value) if isinstance(value, SIMPLE_DEFAULTS) else "..."


CLASS_REPR = re.compile(r"<class '([\w.]+)'>")
"""How an evaluated annotation prints a class: ``<class 'pathlib.Path'>``."""

DOTTED = re.compile(r"\b[a-zA-Z_]\w*(?:\.[a-zA-Z_]\w*)+")
"""A dotted name: ``qgis_sdk.models.files.FileRef``, ``typing.Any``."""


def _short(match: re.Match[str]) -> str:
    """The last segment of one dotted name, in either spelling."""
    found = match.group(1) if match.re.groups else match.group(0)
    return found.rsplit(".", 1)[-1]


def _matching(text: str, opening: int) -> int:
    """The index of the ``]`` closing the ``[`` at ``opening``, or ``-1``."""
    depth = 0
    for index in range(opening, len(text)):
        depth += {"[": 1, "]": -1}.get(text[index], 0)
        if depth == 0:
            return index
    return -1


def _split(text: str) -> list[str]:
    """Split on the commas that are not inside brackets."""
    parts: list[str] = []
    depth = start = 0
    for index, character in enumerate(text):
        depth += {"[": 1, "]": -1}.get(character, 0)
        if character == "," and depth == 0:
            parts.append(text[start:index].strip())
            start = index + 1
    parts.append(text[start:].strip())
    return parts


def _leftmost(text: str) -> tuple[int, str]:
    """Where the first ``Optional[`` or ``Union[`` starts, and which it is."""
    found = [(text.find(name), name) for name in ("Optional[", "Union[")]
    present = [pair for pair in found if pair[0] >= 0]
    return min(present) if present else (-1, "")


def _expand(text: str) -> str:
    """Rewrite the first ``Optional[...]``/``Union[...]`` as PEP 604, once."""
    start, name = _leftmost(text)
    if start < 0:
        return text
    end = _matching(text, start + len(name) - 1)
    if end < 0:
        return text
    parts = _split(text[start + len(name) : end])
    inner = parts[0] if name == "Optional[" else " | ".join(parts)
    replacement = f"{inner} | None" if name == "Optional[" else inner
    return text[:start] + replacement + text[end + 1 :]


def _unions(text: str) -> str:
    """``Optional[X]`` and ``Union[X, Y]`` as ``X | None`` and ``X | Y``.

    The two spellings are one type, and which one an interpreter prints depends
    on its ``typing`` module: ``str(typing.Optional[Path])`` is
    ``typing.Optional[pathlib.Path]`` on 3.11 and ``pathlib.Path | None`` on
    3.14. One spelling in the document, so one meaning.
    """
    for _ in range(len(text) + 1):
        expanded = _expand(text)
        if expanded == text:
            break
        text = expanded
    return text


def text_of(annotation: Any) -> str:
    """One annotation, as the short name its source would have written.

    The same annotation reaches this function in three shapes - a source string
    when the module uses ``from __future__ import annotations``, an evaluated
    object when it does not, and a re-rendered string on an interpreter that
    reads annotations lazily - and each shape prints differently:
    ``FileRef``, ``<class 'qgis_sdk.models.files.FileRef'>`` and
    ``qgis_sdk.models.files.FileRef``. A contract cannot depend on which shape a
    release happens to produce, so all three collapse to the short name.
    """
    if annotation is inspect.Parameter.empty:
        return ""
    text = CLASS_REPR.sub(_short, str(annotation))
    return _unions(DOTTED.sub(_short, text))


def _parameter(parameter: Any, keyword_only: bool) -> str:
    """One parameter, in the syntax a reader expects to see."""
    marker = {
        inspect.Parameter.VAR_POSITIONAL: "*",
        inspect.Parameter.VAR_KEYWORD: "**",
        inspect.Parameter.KEYWORD_ONLY: "*" if keyword_only else "",
    }.get(parameter.kind, "")
    rendered = f"{marker}{parameter.name}"
    annotation = text_of(parameter.annotation)
    if annotation:
        rendered += f": {annotation}"
    if parameter.default is not inspect.Parameter.empty:
        rendered += f" = {_default(parameter.default)}"
    return rendered


try:  # 3.14 reads annotations lazily; its module is absent before that.
    from annotationlib import Format as _Format
except ImportError:  # older interpreters keep the source text already.
    _Format = None


def _read_signature(value: Any) -> inspect.Signature:
    """One callable's signature, with its annotations left as written.

    No evaluation either way: a name that cannot be resolved yet is not an
    error, and the contract records what the source said rather than what one
    interpreter could make of it.
    """
    if _Format is None:
        return inspect.signature(value, eval_str=False)
    try:
        return inspect.signature(value, annotation_format=_Format.STRING)
    except (TypeError, ValueError):
        return inspect.signature(value, eval_str=False)


def _parameters(signature: inspect.Signature) -> str:
    """The parameter list, in the syntax a reader expects to see."""
    parts: list[str] = []
    keyword_only = variadic = False
    for parameter in signature.parameters.values():
        if parameter.name in {"self", "cls"}:
            continue
        named = parameter.kind is inspect.Parameter.KEYWORD_ONLY
        # The ``*`` is written once, before the first keyword-only parameter,
        # and not at all when ``*args`` already introduced it.
        parts.append(_parameter(parameter, named and not keyword_only and not variadic))
        keyword_only = keyword_only or named
        variadic = variadic or parameter.kind is inspect.Parameter.VAR_POSITIONAL
    return ", ".join(parts)


def signature_of(value: Any) -> str:
    """One callable's signature, normalised so two runs and two Pythons agree.

    Built from the parameters rather than from ``str(inspect.signature(...))``:
    that string embeds the interpreter's own forms - an inherited ``__init__``
    reads ``(*args, **kwargs)`` on one release and ``(self, /, *args, **kwargs)``
    on the next, and ``self`` is dropped here either way. A contract that
    changes with the interpreter is not a contract.
    """
    try:
        signature = _read_signature(value)
    except (TypeError, ValueError):
        return ""
    rendered = "(" + _parameters(signature) + ")"
    returns = text_of(signature.return_annotation)
    if not returns:
        return rendered
    return f"{rendered} -> {returns}"


def enum_members(value: Any) -> str:
    """An enumeration's members, in declaration order.

    Not the class's signature: `inspect.signature(SomeEnum)` is the constructor
    the ``Enum`` machinery happens to expose, and that changed shape between
    3.11 and 3.14 (``(value, names = None, ...)`` became ``(*values)``). What a
    plugin author depends on is which members exist, so that is what is
    recorded - and adding one reads as additive, removing one as breaking.
    """
    return "enum<" + "|".join(member.name for member in value) + ">"

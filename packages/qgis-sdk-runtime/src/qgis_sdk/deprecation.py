"""Mark a public symbol deprecated: what replaces it, and when it goes away.

decision-56 point 3: a deprecation is a promise with a date, not a comment. The
mark carries the version it appeared in (`since=`), the version it may be
removed in (`removal=`) and what to use instead (`use=`), so three tools can
read the same fact instead of guessing it:

* the inventory records every mark, which is what `release.py verify-api` diffs;
* `check` reports a plugin that uses a deprecated name as `API001`;
* the wrapped callable warns once per process, so a plugin author who runs their
  own tests sees it without a wall of repeated lines.

Warn-once is deliberate. A deprecation that fires on every call is noise people
filter out; one line naming the replacement and the removal version is a
sentence they act on.
"""

from __future__ import annotations

import functools
import warnings
from dataclasses import dataclass
from typing import Any

__all__ = ["MARK", "Deprecation", "deprecated", "deprecation_of"]

__stability__ = "stable"
MARK = "__deprecation__"
"""The attribute a marked symbol carries; the inventory and `check` read it."""

_WARNED: set[str] = set()
"""Symbols that already warned in this process - one line each, not one per call."""


@dataclass(frozen=True, slots=True)
class Deprecation:
    """One symbol's removal notice: since when, until when, and instead of.

    Attributes:
        since: The version the mark appeared in, so a reader knows how long ago.
        removal: The version the symbol may go in.
        use: What to use instead, or an empty string when nothing replaces it.
    """

    since: str
    removal: str
    use: str = ""

    def message(self, label: str) -> str:
        """The sentence a caller sees, naming the replacement and the version.

        Args:
            label: The symbol's name, as the warning should spell it.
        """
        remedy = f"; use {self.use} instead" if self.use else ""
        return (
            f"{label} is deprecated since {self.since} and will be removed in "
            f"{self.removal}{remedy}"
        )

    def to_json(self) -> dict[str, str]:
        """The mark as the inventory records it."""
        return {"since": self.since, "removal": self.removal, "use": self.use}


def deprecation_of(value: Any) -> Deprecation | None:
    """The mark on one symbol, or ``None`` when it carries none.

    Args:
        value: The function, class or constant to read the mark off.
    """
    mark = getattr(value, MARK, None)
    return mark if isinstance(mark, Deprecation) else None


def _label(value: Any) -> str:
    """How a caller refers to the symbol in the warning."""
    module = getattr(value, "__module__", "")
    name = getattr(value, "__qualname__", getattr(value, "__name__", repr(value)))
    return f"{module}.{name}" if module else name


def _warn_once(target: Any, mark: Deprecation, label: str):
    """Wrap one callable so it warns the first time it is called, and only then."""

    @functools.wraps(target)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        if label not in _WARNED:
            _WARNED.add(label)
            warnings.warn(mark.message(label), DeprecationWarning, stacklevel=2)
        return target(*args, **kwargs)

    return wrapper


def _mark_class(target: type, mark: Deprecation, label: str) -> type:
    """Mark a class and warn once, on the first construction."""
    original = target.__init__

    def init(self: Any, *args: Any, **kwargs: Any) -> None:
        if label not in _WARNED:
            _WARNED.add(label)
            warnings.warn(mark.message(label), DeprecationWarning, stacklevel=2)
        original(self, *args, **kwargs)

    target.__init__ = functools.wraps(original)(init)
    return target


def deprecated(*, since: str, removal: str, use: str = ""):
    """Mark one public symbol for removal at ``removal``, replaced by ``use``.

    Works on functions, classes and anything else with attributes: a class warns
    on first construction, a function on first call, a constant is only marked -
    the inventory still records it and `check` still reports its uses. The mark
    is what the tooling reads, so a symbol that cannot wrap a call still counts.

    Args:
        since: The version the mark appears in.
        removal: The version the symbol may be removed in.
        use: What replaces it, named as a reader would type it.
    """
    mark = Deprecation(since=since, removal=removal, use=use)

    def mark_it(value: Any) -> Any:
        setattr(value, MARK, mark)
        label = _label(value)
        if isinstance(value, type):
            return _mark_class(value, mark, label)
        return _warn_once(value, mark, label) if callable(value) else value

    return mark_it

"""Expression checks, outcomes, and edit outcomes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = ["EDIT_KINDS", "EditOutcome", "ExpressionCheck", "ExpressionOutcome"]

EDIT_KINDS = ("add", "update", "delete")


@dataclass(frozen=True, slots=True)
class ExpressionCheck:
    """The answer to "does this expression parse": a verdict and, if not, why."""

    valid: bool
    message: str | None = None
    referenced_columns: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.valid and self.message is not None:
            raise ValueError("a valid expression carries no message")
        if not self.valid and not self.message:
            raise ValueError("an invalid expression says why")

    def to_wire(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "message": self.message,
            "referenced_columns": list(self.referenced_columns),
        }


@dataclass(frozen=True, slots=True)
class ExpressionOutcome:
    """One evaluated expression: the value, or the reason there is none.

    ``value`` is a plain JSON value; a parsed expression whose result is null
    is a valid outcome with ``value`` ``None``, which a caller distinguishes
    from a failure by ``valid``.
    """

    valid: bool
    value: Any = None
    message: str | None = None

    def __post_init__(self) -> None:
        if self.valid and self.message is not None:
            raise ValueError("a valid outcome carries no message")
        if not self.valid and not self.message:
            raise ValueError("an invalid outcome says why")

    def to_wire(self) -> dict[str, Any]:
        return {"valid": self.valid, "value": self.value, "message": self.message}


@dataclass(frozen=True, slots=True)
class EditOutcome:
    """What one edit request did, before or after a commit.

    ``feature_ids`` is what the provider assigned for an add - a caller needs
    them to refer to the rows it just wrote - and empty for an update or a
    delete, which name a row the caller already had.
    """

    applied: int
    feature_ids: tuple[int, ...] = ()
    committed: bool = False

    def to_wire(self) -> dict[str, Any]:
        return {
            "applied": self.applied,
            "feature_ids": list(self.feature_ids),
            "committed": self.committed,
        }

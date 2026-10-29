"""The shape of a finding and of a whole report: stable, renderable, serializable."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from qgis_sdk.models import QgisSdkError

if TYPE_CHECKING:  # a report carries the buckets; the module cannot import this one
    from .buckets import BucketReport

__all__ = ["CheckReport", "Diagnostic", "QgisSdkCheckError", "Severity"]

Severity = Literal["error", "warning"]


class QgisSdkCheckError(QgisSdkError):
    """``check`` could not run at all: the root is not a project directory."""


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """One finding: where, which rule, what is wrong, what to do about it.

    ``rule`` is the stable identifier a user greps for or a build suppresses
    by; the ``message`` may be reworded, the rule never. ``path`` is relative
    to the checked root; ``line``/``column`` are 1-based and ``0`` when the
    finding is about a file rather than a position in it.
    """

    rule: str
    path: Path
    line: int
    column: int
    message: str
    remediation: str
    severity: Severity = "error"

    def render(self) -> str:
        """``path:line:col: RULE message`` with the remedy indented beneath."""
        where = (
            f"{self.path.as_posix()}:{self.line}:{self.column}"
            if self.line
            else self.path.as_posix()
        )
        return f"{where}: {self.rule} {self.message}\n    {self.remediation}"

    def to_json(self) -> dict[str, object]:
        """A flat mapping with the same fields, for ``--json``."""
        return {
            "rule": self.rule,
            "severity": self.severity,
            "path": self.path.as_posix(),
            "line": self.line,
            "column": self.column,
            "message": self.message,
            "remediation": self.remediation,
        }


@dataclass(frozen=True, slots=True)
class CheckReport:
    """Everything one ``check_project`` run found, in a stable order."""

    root: Path
    diagnostics: tuple[Diagnostic, ...]
    files_checked: int
    imports: BucketReport | None = None

    @property
    def ok(self) -> bool:
        """True when nothing at ``error`` severity was found."""
        return not any(d.severity == "error" for d in self.diagnostics)

    def to_json(self) -> dict[str, object]:
        """The report as plain data: root, counts, findings."""
        return {
            "root": str(self.root),
            "ok": self.ok,
            "files_checked": self.files_checked,
            "diagnostics": [d.to_json() for d in self.diagnostics],
            "imports": None if self.imports is None else self.imports.to_json(),
        }

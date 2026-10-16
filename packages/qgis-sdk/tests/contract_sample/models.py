"""Example wire DTOs, not public SDK operations or a runtime validation backend."""

from dataclasses import dataclass
from typing import Literal


@dataclass
class RunRequest:
    kind: Literal["run"]
    count: int
    mode: Literal["safe", "fast"] = "safe"
    label: str | None = None


@dataclass
class RunResult:
    processed: int
    note: str | None = None


@dataclass
class RunResultReader(RunResult):
    """Reader explicitly recognizes one compatible extension, not arbitrary extras."""

    revision: str | None = None

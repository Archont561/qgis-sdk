"""Example wire DTOs, not public SDK operations or a runtime validation backend."""

from dataclasses import dataclass
from typing import Annotated, Literal

from mashumaro.jsonschema.annotations import Maximum, Minimum

# Test-only wire policy, not a public SDK type or runtime validator.
SafeInteger = Annotated[int, Minimum(-9007199254740991), Maximum(9007199254740991)]


@dataclass
class RunRequest:
    kind: Literal["run"]
    count: SafeInteger
    mode: Literal["safe", "fast"] = "safe"
    label: str | None = None


@dataclass
class RunResult:
    processed: SafeInteger
    note: str | None = None


@dataclass
class RunResultReader(RunResult):
    """Reader explicitly recognizes one compatible extension, not arbitrary extras."""

    revision: str | None = None

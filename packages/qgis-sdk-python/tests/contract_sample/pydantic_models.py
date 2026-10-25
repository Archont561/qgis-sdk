"""Optional Pydantic wire fixtures kept separate from the plain DTO example."""

from dataclasses import dataclass
from typing import Literal, TypeVar

from pydantic import ConfigDict, with_config
from qgis_sdk.adapters.pydantic_types import SafeJsonInteger

ModelT = TypeVar("ModelT")


def _wire_model(model: type[ModelT]) -> type[ModelT]:
    return with_config(
        ConfigDict(
            strict=True,
            extra="forbid",
            json_schema_serialization_defaults_required=True,
        )
    )(model)


@_wire_model
@dataclass
class RunRequest:
    kind: Literal["run"]
    count: SafeJsonInteger
    mode: Literal["safe", "fast"] = "safe"
    label: str | None = None


@_wire_model
@dataclass
class RunResult:
    processed: SafeJsonInteger
    note: str | None = None


@_wire_model
@dataclass
class RunResultReader:
    """The reader permits one named compatible extension, not arbitrary fields."""

    processed: SafeJsonInteger
    note: str | None = None
    revision: str | None = None

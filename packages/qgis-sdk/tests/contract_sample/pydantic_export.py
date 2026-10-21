"""Test-only Pydantic schema export for the controlled-deployment contract slice."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from qgis_sdk.adapters.pydantic import PydanticContractAdapter

from . import writing
from .pydantic_models import RunRequest, RunResult, RunResultReader


def handle_run(request: RunRequest) -> RunResult:
    """Sample typed handler; it is not a public SDK operation."""
    return RunResult(processed=request.count, note=request.label)


def build_adapter(
    handler: Callable[[RunRequest], RunResult] = handle_run,
) -> PydanticContractAdapter[RunRequest, RunResultReader, RunResult]:
    """Build the shared optional adapter around the ordinary sample dataclasses."""
    return PydanticContractAdapter(
        request_type=RunRequest,
        result_reader_type=RunResultReader,
        result_writer_type=RunResult,
        handler=handler,
    )


def build_schemas() -> dict[str, dict[str, Any]]:
    """Export distinct validation and serialization directions."""
    adapter = build_adapter()
    return {
        "pydantic-run-request": adapter.request_json_schema(),
        "pydantic-run-result-reader": adapter.result_reader_json_schema(),
        "pydantic-run-result-writer": adapter.result_writer_json_schema(),
    }


def write_schemas(output_dir: Path) -> None:
    """Write the three directions through the shared example writer."""
    writing.write_schemas(build_schemas, output_dir)


def main() -> None:
    writing.run(
        build_schemas, "Export the test-only optional Pydantic contract schemas"
    )

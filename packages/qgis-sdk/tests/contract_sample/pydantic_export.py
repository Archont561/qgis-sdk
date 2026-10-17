"""Test-only Pydantic schema export for the controlled-deployment contract slice."""

import argparse
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from qgis_sdk.adapters.pydantic import PydanticContractAdapter

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
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, schema in build_schemas().items():
        path = output_dir / f"{name}.schema.json"
        # Pin LF so a Windows checkout stays byte-identical to the
        # checked-in schema, which the determinism tests compare directly.
        path.write_text(
            json.dumps(schema, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export the test-only optional Pydantic contract schemas"
    )
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    write_schemas(args.output_dir)

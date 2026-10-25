"""Generate the checked sample schemas; this is not a public SDK generator."""

from pathlib import Path
from typing import Any

from mashumaro.jsonschema import build_json_schema

from . import writing
from .models import RunRequest, RunResult, RunResultReader


def build_schemas() -> dict[str, dict[str, Any]]:
    """Keep the three wire directions distinct without a general converter."""
    request = build_json_schema(RunRequest, with_dialect_uri=True).to_dict()
    reader = build_json_schema(RunResultReader, with_dialect_uri=True).to_dict()
    writer = build_json_schema(RunResult, with_dialect_uri=True).to_dict()

    # This example always serializes defaults (including note=None); JSON Schema's
    # default is only an annotation, so the wire writer must require every field.
    writer["title"] = "RunResultWriter"
    writer["required"] = list(writer["properties"])
    return {
        "run-request": request,
        "run-result-reader": reader,
        "run-result-writer": writer,
    }


def write_schemas(output_dir: Path) -> None:
    """Write the three directions through the shared example writer."""
    writing.write_schemas(build_schemas, output_dir)


def main() -> None:
    writing.run(build_schemas, "Export the test-only SDK wire example")

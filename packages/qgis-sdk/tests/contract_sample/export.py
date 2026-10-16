"""Generate the checked sample schemas; this is not a public SDK generator."""

import argparse
import json
from pathlib import Path
from typing import Any

from mashumaro.jsonschema import build_json_schema

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
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, schema in build_schemas().items():
        path = output_dir / f"{name}.schema.json"
        path.write_text(
            json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export the test-only SDK wire example"
    )
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    write_schemas(args.output_dir)

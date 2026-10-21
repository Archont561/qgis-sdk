"""One writer and one CLI shape, shared by both contract examples.

How a schema is named, serialised and line-ended is a single representation here:
the mashumaro and Pydantic examples export the same bytes for the same reason, and
the determinism tests compare those bytes directly. A second copy of the writer is
what lets one example drift while the checked-in schemas still look fine.
"""

import argparse
import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any


def write_schemas(
    build: Callable[[], Mapping[str, dict[str, Any]]], output_dir: Path
) -> None:
    """Write every schema of one builder as its own stable JSON file."""
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, schema in build().items():
        path = output_dir / f"{name}.schema.json"
        # Pin LF so a Windows checkout stays byte-identical to the
        # checked-in schema, which the determinism tests compare directly.
        path.write_text(
            json.dumps(schema, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )


def run(build: Callable[[], Mapping[str, dict[str, Any]]], description: str) -> None:
    """Read the generator's single argument and write the schemas it selects."""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    write_schemas(build, args.output_dir)

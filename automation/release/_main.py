from __future__ import annotations

import argparse
from pathlib import Path

from ._build import checksums, write_checksums
from ._history import QgisSdkReleaseError


def cmd_checksums(args: argparse.Namespace) -> int:
    entries = checksums([Path(item) for item in args.paths])
    write_checksums(Path(args.out), entries)
    for name, digest in entries:
        print(f"{digest}  {name}")
    return 0


DISTRIBUTION_DIRS = {
    "runtime": "packages/qgis-sdk-runtime",
    "tools": "packages/qgis-sdk-tools",
    "kit": "packages/qgis-sdk-python",
}


def main(argv: list[str] | None = None) -> int:
    """Run one subcommand; errors exit 1 with a single-line message."""
    from ._verify import build_parser

    args = build_parser().parse_args(argv)
    try:
        return int(args.handler(args))
    except QgisSdkReleaseError as error:
        print(f"error: {error}")
        return 1

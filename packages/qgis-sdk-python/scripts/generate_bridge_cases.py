#!/usr/bin/env python3
"""Build the checked-in bridge cases that both languages validate (TASK-4).

The file is the contract fixture, not a snapshot: Python rebuilds it from the
dispatcher and refuses to drift from the checked-in copy, and the TypeScript
client parses the same replies and must reach the same verdict. That is what
"Python and TypeScript validate the same contract fixtures" means here - one
producer, two independent readers.

Regenerate with:

    python packages/qgis-sdk-python/scripts/generate_bridge_cases.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "qgis-sdk-tools" / "src"))
sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "qgis-sdk-runtime" / "src")
)

from generate_bridge_cases_cases import build_cases
from generate_bridge_cases_hosts import CASES_PATH

_SCALAR_ARRAY = re.compile(r"\[\n(?P<body>(?:[^\[\]{}\n]*\n)+?)(?P<indent>\t*)\]")


_LINE_WIDTH = 80


_TAB_WIDTH = 2


def _collapse_short_arrays(text: str) -> str:
    """Write arrays of scalars on one line when they fit, as biome would.

    ``json.dumps`` breaks every array; biome's formatter keeps an array of
    scalars on one line while it fits in 80 columns and only re-breaks the
    longer ones. Matching that here keeps the checked-in file identical whether
    the generator or the formatter wrote it last.
    """

    def collapse(match: re.Match[str]) -> str:
        items = [line.strip() for line in match.group("body").splitlines()]
        inline = "[" + " ".join(items) + "]"
        start = text.rfind("\n", 0, match.start()) + 1
        prefix = text[start : match.start()]
        width = len(prefix.expandtabs(_TAB_WIDTH)) + len(inline)
        return inline if width <= _LINE_WIDTH else match.group(0)

    return _SCALAR_ARRAY.sub(collapse, text)


def render(cases: dict[str, Any]) -> str:
    """The file's text: tabs, sorted keys and biome's short arrays."""
    return _collapse_short_arrays(json.dumps(cases, indent="\t", sort_keys=True)) + "\n"


def main() -> int:
    cases = build_cases()
    CASES_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Tabs and sorted keys are what biome writes for the same file, so the
    # generator and the formatter do not fight over it on every run.
    CASES_PATH.write_text(render(cases), encoding="utf-8")
    print(f"wrote {len(cases['cases'])} cases to {CASES_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

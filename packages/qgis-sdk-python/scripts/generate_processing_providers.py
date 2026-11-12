#!/usr/bin/env python3
"""Generate the Processing provider modules from catalogue.json.

Pure Python: reads ``catalogue.json`` (the pinned QGIS registry snapshot,
checked into git) and emits the provider modules (``native.py``, ``gdal.py``,
``qgis.py``, ``pdal.py``, ``p3d.py``) via ``codegen.py``. No QGIS needed.

The provider modules are generated artifacts and are never committed; they
are generated in CI before tests run, and locally by this script.

Usage:
    python packages/qgis-sdk-python/scripts/generate_processing_providers.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_SRC = PROJECT_ROOT.parent / "qgis-sdk-runtime" / "src"
SNAPSHOT_DIR = RUNTIME_SRC / "qgis_sdk" / "processing"

sys.path.insert(0, str(RUNTIME_SRC))

from qgis_sdk.processing.codegen import render_package
from qgis_sdk.processing.snapshot import CORE_PROVIDERS, load_catalogue


def main() -> int:
    catalogue = load_catalogue(SNAPSHOT_DIR / "catalogue.json")
    files = render_package(catalogue, CORE_PROVIDERS, init=False)
    # render_package includes catalogue.json; skip it (it's source).
    written = 0
    for name, content in files.items():
        if name == "catalogue.json":
            continue
        path = SNAPSHOT_DIR / name
        if path.exists() and path.read_text(encoding="utf-8") == content:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        print(f"wrote {path.relative_to(SNAPSHOT_DIR.parent.parent.parent)}")
        written += 1
    print(f"{written} provider module(s) generated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

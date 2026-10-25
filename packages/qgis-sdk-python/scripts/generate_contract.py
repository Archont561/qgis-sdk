"""Script entry point for the sample contract used by the web workspace."""

import sys
from pathlib import Path

# Run from anywhere, with or without an activated environment: the fixture package and
# the SDK it imports are resolved from this script's own directory, not the ambient
# PYTHONPATH, so a bare interpreter gets the same schemas as the workspace task.
PROJECT_ROOT = Path(__file__).resolve().parents[1]

for _path in (
    PROJECT_ROOT / "tests",
    PROJECT_ROOT.parent / "qgis-sdk-tools" / "src",
    PROJECT_ROOT.parent / "qgis-sdk-runtime" / "src",
):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from contract_sample.export import main

if __name__ == "__main__":
    main()

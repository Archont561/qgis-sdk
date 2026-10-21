"""Put the developer scripts and the test-only fixtures on the import path.

The package suite runs from the package directory locally and from the repository
root in CI, and the repository root owns its own top-level ``scripts`` package, so
the module roots are added here by absolute path instead of importing through a
package name that would collide.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

for _path in (PROJECT_ROOT / "tests", PROJECT_ROOT / "scripts"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

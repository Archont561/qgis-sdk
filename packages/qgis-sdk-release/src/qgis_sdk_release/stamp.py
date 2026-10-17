"""Version stamping for the publishable workspace packages.

Stamping happens only inside the release workflow's working tree; manifests in
the repository are never bumped by planning (milestone version policy).
"""

from __future__ import annotations

import json
import re

from .errors import QgisSdkReleaseError
from .semver import Version

__all__ = ["stamp_package_json", "stamp_pyproject"]

_VERSION_LINE = re.compile(r'(?m)^version = "[^"]*"$')


def stamp_pyproject(text: str, version: Version) -> str:
    """Rewrite the first top-level ``version`` line with the PEP 440 form."""
    stamped, count = _VERSION_LINE.subn(
        f'version = "{version.to_pep440()}"', text, count=1
    )
    if count == 0:
        raise QgisSdkReleaseError("no top-level version line found in pyproject.toml")
    return stamped


def stamp_package_json(text: str, version: Version) -> str:
    """Rewrite ``version`` in a package.json, preserving tab indentation."""
    data = json.loads(text)
    data["version"] = str(version)
    return json.dumps(data, indent="\t") + "\n"

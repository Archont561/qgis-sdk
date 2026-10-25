"""Shared fixtures for the release script tests.

Adds ``scripts/`` to ``sys.path`` so tests can import the standalone
``release`` script as a module, matching the pattern used by
``packages/qgis-sdk-python/tests/conftest.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

import pytest
from release import parse_versionrc

SAMPLE_VERSIONRC = """\
header: "# Changelog\\n"
types:
  - type: feat
    increment: Minor
    section: Features
    hidden: false
  - type: fix
    increment: Patch
    section: Fixes
    hidden: false
  - type: docs
    increment: None
    section: Documentation
    hidden: true
preMajor: false
scopeRegex: ^[[:alnum:]]+(?:[-_/][[:alnum:]]+)*$
lineLength: 80
ignoreMessagePattern:
  - ^Initial commit[[:space:]]*$
versionScheme: semver
initialBumpVersion: 0.1.0
"""


@pytest.fixture()
def sample_config():
    return parse_versionrc(SAMPLE_VERSIONRC)

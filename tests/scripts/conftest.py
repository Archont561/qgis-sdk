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
import release
from release import parse_versionrc


@pytest.fixture(autouse=True)
def _no_repository_alias_manifest(tmp_path, monkeypatch):
    """Point the optional alias manifest at nothing unless a test opts in.

    Tests that monkeypatch ``_BRIDGE_PACKAGE`` to a fixture at one version must
    not be compared against the repository's real ``qgis-sdk`` alias at another.
    """
    monkeypatch.setattr(release, "_ALIAS_PACKAGE", tmp_path / "absent-alias.json")


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

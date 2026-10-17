"""Shared fixtures for the qgis-sdk-release tests."""

import pytest
from qgis_sdk_release.versionrc import parse_versionrc

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

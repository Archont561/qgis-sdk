"""Version stamping of pyproject.toml and package.json."""

import pytest
from qgis_sdk_release.errors import QgisSdkReleaseError
from qgis_sdk_release.semver import Version
from qgis_sdk_release.stamp import stamp_package_json, stamp_pyproject

PYPROJECT = """\
[build-system]
requires = ["hatchling==1.32.4"]

[project]
name = "qgis-sdk"
version = "0.1.0"
description = "Kept."
"""

PACKAGE_JSON = (
    '{\n\t"name": "qgis-sdk-bridge",\n\t"version": "0.1.0",\n\t"private": false\n}\n'
)


def test_stamp_pyproject_replaces_first_version_line():
    stamped = stamp_pyproject(PYPROJECT, Version.parse("0.2.0"))
    assert 'version = "0.2.0"' in stamped
    assert 'version = "0.1.0"' not in stamped
    assert 'requires = ["hatchling==1.32.4"]' in stamped  # untouched


def test_stamp_pyproject_uses_pep440_for_prereleases():
    stamped = stamp_pyproject(PYPROJECT, Version.parse("0.2.0-rc.1"))
    assert 'version = "0.2.0rc1"' in stamped


def test_stamp_pyproject_requires_a_version_line():
    with pytest.raises(QgisSdkReleaseError):
        stamp_pyproject("[project]\nname = 'x'\n", Version.parse("0.2.0"))


def test_stamp_package_json_preserves_tabs_and_order():
    stamped = stamp_package_json(PACKAGE_JSON, Version.parse("0.2.0-rc.1"))
    assert stamped == (
        '{\n\t"name": "qgis-sdk-bridge",\n\t"version": "0.2.0-rc.1",\n'
        '\t"private": false\n}\n'
    )

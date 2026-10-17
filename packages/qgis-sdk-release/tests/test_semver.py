"""SemVer parsing, ordering, bumping, and PEP 440 mapping."""

import pytest
from qgis_sdk_release.errors import QgisSdkReleaseVersionError
from qgis_sdk_release.semver import Version, tag_for_version, version_from_tag


def test_parse_release_and_prerelease():
    plain = Version.parse("0.1.0")
    assert (plain.major, plain.minor, plain.patch, plain.pre) == (0, 1, 0, None)
    assert not plain.is_prerelease
    pre = Version.parse("1.2.3-rc.1")
    assert pre.pre == ("rc", "1")
    assert pre.is_prerelease
    assert str(pre) == "1.2.3-rc.1"


@pytest.mark.parametrize("bad", ["", "0.1", "v0.1.0", "01.1.0", "0.1.0-", "x.y.z"])
def test_parse_rejects_invalid(bad):
    with pytest.raises(QgisSdkReleaseVersionError):
        Version.parse(bad)


def test_ordering_puts_prereleases_before_releases():
    versions = [
        Version.parse("0.10.0"),
        Version.parse("0.1.0"),
        Version.parse("0.1.0-rc.1"),
        Version.parse("0.9.0"),
        Version.parse("0.1.0-rc.2"),
    ]
    ordered = sorted(versions, key=Version.sort_key)
    assert [str(v) for v in ordered] == [
        "0.1.0-rc.1",
        "0.1.0-rc.2",
        "0.1.0",
        "0.9.0",
        "0.10.0",
    ]


def test_numeric_prerelease_identifiers_compare_numerically():
    assert (
        Version.parse("0.1.0-rc.9").sort_key() < Version.parse("0.1.0-rc.10").sort_key()
    )


def test_bump_kinds_reset_lower_parts():
    base = Version.parse("1.4.7")
    assert str(base.bump("patch")) == "1.4.8"
    assert str(base.bump("minor")) == "1.5.0"
    assert str(base.bump("major")) == "2.0.0"
    with pytest.raises(QgisSdkReleaseVersionError):
        base.bump("breaking")


def test_with_prerelease_validates_suffix():
    assert str(Version.parse("0.2.0").with_prerelease("rc.1")) == "0.2.0-rc.1"
    with pytest.raises(QgisSdkReleaseVersionError):
        Version.parse("0.2.0").with_prerelease("rc 1")


@pytest.mark.parametrize(
    ("semver_text", "pep440"),
    [
        ("0.1.0", "0.1.0"),
        ("0.1.0-rc.1", "0.1.0rc1"),
        ("0.1.0-alpha.2", "0.1.0a2"),
        ("1.0.0-beta.1", "1.0.0b1"),
    ],
)
def test_to_pep440(semver_text, pep440):
    assert Version.parse(semver_text).to_pep440() == pep440


def test_tag_helpers_roundtrip():
    version = Version.parse("0.2.0")
    tag = tag_for_version(version)
    assert tag == "v0.2.0"
    assert version_from_tag(tag) == version
    with pytest.raises(QgisSdkReleaseVersionError):
        version_from_tag("0.2.0")

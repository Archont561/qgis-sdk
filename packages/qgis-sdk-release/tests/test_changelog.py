"""Changelog rendering per .versionrc sections."""

from qgis_sdk_release.changelog import render_changelog
from qgis_sdk_release.commits import parse_log
from qgis_sdk_release.semver import Version


def _commits():
    return parse_log(
        "a1b2c3d4e5" + "\x1f" + "feat: add x" + "\x1f" + "\x1e\n"
        "f6e5d4c3b2" + "\x1f" + "fix: repair y" + "\x1f" + "\x1e\n"
        "9988776655" + "\x1f" + "docs: hidden note" + "\x1f" + "\x1e\n"
        "1234567890" + "\x1f" + "Merge pull request #2" + "\x1f" + "\x1e\n"
    )


def test_sections_entries_and_header(sample_config):
    text = render_changelog(Version.parse("0.2.0"), _commits(), sample_config)
    assert text.startswith("# Changelog\n\n## v0.2.0\n")
    assert "### Features" in text
    assert "- feat: add x (a1b2c3d)" in text
    assert "### Fixes" in text
    assert "- fix: repair y (f6e5d4c)" in text
    assert "hidden note" not in text
    assert "Merge pull request" not in text
    assert text.endswith("\n")


def test_compare_link_needs_base_and_slug(sample_config):
    plain = render_changelog(Version.parse("0.1.0"), _commits(), sample_config)
    assert "compare" not in plain
    linked = render_changelog(
        Version.parse("0.2.0"),
        _commits(),
        sample_config,
        base_tag="v0.1.0",
        repo_slug="owner/repo",
    )
    assert (
        "[v0.1.0...v0.2.0]: https://github.com/owner/repo/compare/v0.1.0...v0.2.0"
        in linked
    )


def test_breaking_changes_get_their_own_section(sample_config):
    commits = parse_log(
        "abcdef1234" + "\x1f" + "feat!: drop legacy api" + "\x1f" + "\x1e\n"
    )
    text = render_changelog(Version.parse("0.2.0"), commits, sample_config)
    assert "### Breaking changes" in text
    assert "- feat!: drop legacy api (abcdef1)" in text
    assert "### Features" in text  # listed in its own section too

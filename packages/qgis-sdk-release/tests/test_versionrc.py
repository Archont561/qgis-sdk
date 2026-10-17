"""Parsing of the workspace .versionrc subset."""

from pathlib import Path

import pytest
from conftest import SAMPLE_VERSIONRC
from qgis_sdk_release.errors import QgisSdkReleaseError
from qgis_sdk_release.versionrc import parse_versionrc

REPO_VERSIONRC = Path(__file__).resolve().parents[3] / ".versionrc"


def test_parse_sample_rules_and_scalars():
    config = parse_versionrc(SAMPLE_VERSIONRC)
    assert len(config.rules) == 3
    feat = config.rule_for("feat")
    assert feat is not None
    assert (feat.increment, feat.section, feat.hidden) == ("Minor", "Features", False)
    docs = config.rule_for("docs")
    assert docs is not None and docs.hidden
    assert config.rule_for("unknown") is None
    assert str(config.initial_bump_version) == "0.1.0"
    assert config.pre_major is False
    assert config.header == "# Changelog\n"


def test_sections_skip_hidden_and_duplicates():
    config = parse_versionrc(SAMPLE_VERSIONRC)
    assert config.sections == ("Features", "Fixes")


def test_parse_real_repository_versionrc():
    config = parse_versionrc(REPO_VERSIONRC.read_text(encoding="utf-8"))
    assert str(config.initial_bump_version) == "0.1.0"
    assert config.pre_major is False
    types = {rule.type for rule in config.rules}
    assert {"feat", "fix", "chore", "ci", "docs", "refactor", "perf", "test"} <= types
    # ignoreMessagePattern list items must not be mistaken for type rules.
    assert all(rule.type.isalpha() for rule in config.rules)


def test_malformed_entry_raises():
    with pytest.raises(QgisSdkReleaseError):
        parse_versionrc("types:\n  not a mapping\n")


def test_type_entry_without_type_raises():
    with pytest.raises(QgisSdkReleaseError):
        parse_versionrc("types:\n  - increment: Minor\n")

"""Conventional-commit log parsing and classification."""

import pytest
from qgis_sdk_release.commits import LOG_FORMAT, classify, parse_log
from qgis_sdk_release.errors import QgisSdkReleaseError


def _raw(*records):
    return "".join(
        f"{sha}\x1f{subject}\x1f{body}\x1e\n" for sha, subject, body in records
    )


def _one(subject, body=""):
    return parse_log(_raw(("a" * 40, subject, body)))[0]


def test_log_format_uses_separators():
    assert LOG_FORMAT == "%H%x1f%s%x1f%b%x1e"


def test_parse_log_splits_records_and_strips_blanks():
    raw = _raw(
        ("a" * 40, "feat: add x", "some body"),
        ("b" * 40, "Merge pull request #16 from x", ""),
    )
    commits = parse_log(raw)
    assert len(commits) == 2
    assert commits[0].sha == "a" * 40
    assert commits[0].subject == "feat: add x"
    assert commits[0].body == "some body"
    assert commits[1].body == ""


def test_parse_log_rejects_malformed_record():
    with pytest.raises(QgisSdkReleaseError):
        parse_log("only-one-field\x1e\n")


def test_classify_feat_and_fix(sample_config):
    feat = classify(_one("feat: add x"), sample_config)
    assert (feat.bump, feat.section, feat.hidden, feat.breaking) == (
        "minor",
        "Features",
        False,
        False,
    )
    fix = classify(_one("fix(core): patch y"), sample_config)
    assert (fix.bump, fix.section) == ("patch", "Fixes")


def test_classify_hidden_and_unknown_types(sample_config):
    docs = classify(_one("docs: readme"), sample_config)
    assert docs.hidden and docs.bump is None
    merge = classify(_one("Merge pull request #16 from x"), sample_config)
    assert merge.hidden and merge.bump is None and not merge.breaking
    unknown = classify(_one("wip: half done"), sample_config)
    assert unknown.hidden


def test_classify_breaking_marker_and_footer(sample_config):
    bang = classify(_one("fix!: rewrite api"), sample_config)
    assert bang.breaking and bang.bump == "patch"  # escalation happens in plan
    footer = classify(_one("feat: x", "BREAKING CHANGE: dropped y"), sample_config)
    assert footer.breaking
    dashed = classify(_one("feat: x", "BREAKING-CHANGE: dropped y"), sample_config)
    assert dashed.breaking

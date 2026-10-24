"""Tests for the standalone scripts/release.py CLI.

Migrated from packages/qgis-sdk-release/tests. All functions are imported
directly from the ``release`` module (scripts/ is on the pytest pythonpath).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from conftest import SAMPLE_VERSIONRC
from release import (
    QgisSdkReleaseError,
    QgisSdkReleaseVersionError,
    Version,
    checksums,
    classify,
    compute_plan,
    create_release,
    detect_scope_from_files,
    parse_log,
    parse_milestone_tag,
    parse_release_tag,
    parse_versionrc,
    render_changelog,
    sort_tags,
    stamp_package_json,
    stamp_pyproject,
    tag_for_version,
    twine_check,
    upload_asset,
    version_from_tag,
    write_checksums,
)

PYPROJECT = '[build-system]\nrequires = ["hatchling==1.32.4"]\n\n[project]\nname = "qgis-sdk"\nversion = "0.1.0"\ndescription = "Kept."\n'
PACKAGE_JSON = (
    '{\n\t"name": "qgis-sdk-bridge",\n\t"version": "0.1.0",\n\t"private": false\n}\n'
)


# ---------------------------------------------------------------------------
# SemVer
# ---------------------------------------------------------------------------


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


@pytest.mark.parametrize(
    ("raw_tag", "expected_scope", "expected_version"),
    [
        ("milestone-v0.1.0", "all", "0.1.0"),
        ("milestone/v0.2.0", "all", "0.2.0"),
        ("milestone/0.2.0", "all", "0.2.0"),
        ("m-v0.3.0", "all", "0.3.0"),
        ("milestone-v0.1.0-rc.1", "all", "0.1.0-rc.1"),
        ("milestone/python-v0.2.0", "python", "0.2.0"),
        ("milestone/ts-v0.2.0", "typescript", "0.2.0"),
    ],
)
def test_parse_milestone_tag_accepts_supported_patterns(
    raw_tag, expected_scope, expected_version
):
    parsed = parse_milestone_tag(raw_tag)
    assert parsed is not None
    scope, version = parsed
    assert scope == expected_scope
    assert str(version) == expected_version


def test_parse_milestone_tag_returns_none_for_regular_tags_and_rejects_malformed():
    assert parse_milestone_tag("v0.1.0") is None
    assert parse_milestone_tag("python-v0.1.0") is None
    with pytest.raises(QgisSdkReleaseVersionError):
        parse_milestone_tag("milestone-vnot-a-semver")


@pytest.mark.parametrize(
    ("raw_tag", "expected_scope", "expected_version"),
    [
        ("v0.1.0", "all", "0.1.0"),
        ("v0.1.0-rc.1", "all", "0.1.0-rc.1"),
        ("python-v0.1.0", "python", "0.1.0"),
        ("python/v0.1.0", "python", "0.1.0"),
        ("py-v0.2.0", "python", "0.2.0"),
        ("qgis-sdk-v0.2.0", "python", "0.2.0"),
        ("ts-v0.1.0", "typescript", "0.1.0"),
        ("typescript-v0.1.0", "typescript", "0.1.0"),
        ("typescript/v0.1.0", "typescript", "0.1.0"),
        ("bridge-v0.1.0", "typescript", "0.1.0"),
        ("bridge/v0.1.0-rc.1", "typescript", "0.1.0-rc.1"),
        ("qgis-sdk-bridge-v0.1.0", "typescript", "0.1.0"),
    ],
)
def test_parse_release_tag_accepts_general_and_scoped_tags(
    raw_tag, expected_scope, expected_version
):
    scope, version = parse_release_tag(raw_tag)
    assert scope == expected_scope
    assert str(version) == expected_version
    assert version_from_tag(raw_tag) == version


@pytest.mark.parametrize(
    "bad_tag",
    [
        "0.1.0",
        "milestone-v0.1.0",
        "milestone/v0.1.0",
        "m-v0.1.0",
        "unknown-v0.1.0",
        "not-a-tag",
    ],
)
def test_parse_release_tag_rejects_non_release_tags(bad_tag):
    with pytest.raises(QgisSdkReleaseVersionError):
        parse_release_tag(bad_tag)


def test_milestone_trigger_cuts_release_tag_and_ignores_milestone_tag_in_base(
    sample_config,
):
    plan = compute_plan(
        "milestone",
        ("milestone-v0.1.0", "v0.1.0-rc.1"),
        _log("feat: milestone slice"),
        sample_config,
        milestone_tag="milestone-v0.1.0",
    )
    assert plan.action == "tag"
    assert plan.tag == "v0.1.0"
    assert str(plan.version) == "0.1.0"
    assert plan.base_tag == "v0.1.0-rc.1"
    assert "## v0.1.0" in plan.changelog


# ---------------------------------------------------------------------------
# Conventional-commit parsing and classification
# ---------------------------------------------------------------------------


def _raw(*records):
    return "".join(
        f"{sha}\x1f{subject}\x1f{body}\x1e\n" for sha, subject, body in records
    )


def _one(subject, body=""):
    return parse_log(_raw(("a" * 40, subject, body)))[0]


def test_log_format_uses_separators():
    from release import LOG_FORMAT

    assert LOG_FORMAT == "%H%x1f%s%x1f%b%x1e"


def test_parse_log_splits_records_and_strips_blanks():
    raw = _raw(
        (("a" * 40, "feat: add x", "some body")),
        (("b" * 40, "Merge pull request #16 from x", "")),
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
    assert bang.breaking and bang.bump == "patch"
    footer = classify(_one("feat: x", "BREAKING CHANGE: dropped y"), sample_config)
    assert footer.breaking
    dashed = classify(_one("feat: x", "BREAKING-CHANGE: dropped y"), sample_config)
    assert dashed.breaking


# ---------------------------------------------------------------------------
# .versionrc
# ---------------------------------------------------------------------------


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


def test_malformed_entry_raises():
    with pytest.raises(QgisSdkReleaseError):
        parse_versionrc("types:\n  not a mapping\n")


def test_type_entry_without_type_raises():
    with pytest.raises(QgisSdkReleaseError):
        parse_versionrc("types:\n  - increment: Minor\n")


# ---------------------------------------------------------------------------
# Changelog
# ---------------------------------------------------------------------------


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
    assert "### Features" in text


# ---------------------------------------------------------------------------
# Release planning
# ---------------------------------------------------------------------------


def _log(*subjects):
    return parse_log(
        "".join(
            f"{sha}\x1f{subject}\x1f\x1e\n"
            for sha, subject in zip("abcdef0123456789", subjects, strict=False)
        )
    )


def test_sort_tags_orders_by_semver_and_ignores_noise():
    tags = ["v0.9.0", "v0.10.0", "v0.1.0-rc.1", "not-a-tag", "v0.1.0"]
    assert sort_tags(tags) == ("v0.10.0", "v0.9.0", "v0.1.0", "v0.1.0-rc.1")


def test_first_release_refuses_the_push_trigger(sample_config):
    plan = compute_plan("push", (), _log("feat: something"), sample_config)
    assert plan.action == "skip"
    assert plan.first and not plan.stable_exists
    assert "deliberate" in plan.reason


def test_prerelease_only_history_still_refuses_the_push_trigger(sample_config):
    plan = compute_plan(
        "push", ("v0.1.0-rc.2",), _log("feat: next slice"), sample_config
    )
    assert plan.action == "skip"
    assert not plan.first and not plan.stable_exists
    assert "deliberate" in plan.reason


def test_dispatch_continues_the_rc_train_from_a_prerelease_base(sample_config):
    plan = compute_plan(
        "dispatch",
        ("v0.1.0-rc.2",),
        _log("feat: next slice"),
        sample_config,
        suffix="rc.3",
    )
    assert plan.action == "tag" and plan.tag == "v0.2.0-rc.3"


def test_dispatch_can_bootstrap_the_deliberate_stable_release(sample_config):
    plan = compute_plan(
        "dispatch",
        ("v0.1.0-rc.2",),
        _log("chore: anything"),
        sample_config,
        version_override="0.1.0",
    )
    assert plan.action == "tag" and plan.tag == "v0.1.0"


def test_first_release_tags_on_dispatch_with_initial_version(sample_config):
    plan = compute_plan("dispatch", (), _log("feat: something"), sample_config)
    assert plan.action == "tag"
    assert plan.tag == "v0.1.0"
    assert str(plan.version) == "0.1.0"
    assert "## v0.1.0" in plan.changelog


def test_suffix_makes_a_prerelease_tag(sample_config):
    plan = compute_plan(
        "dispatch", (), _log("feat: something"), sample_config, suffix="rc.1"
    )
    assert plan.tag == "v0.1.0-rc.1"
    assert plan.version.is_prerelease


def test_feat_commit_bumps_minor_from_latest_tag(sample_config):
    plan = compute_plan("push", ("v0.1.0",), _log("feat: next slice"), sample_config)
    assert plan.action == "tag" and plan.tag == "v0.2.0"
    assert plan.base_tag == "v0.1.0"
    assert "compare" not in plan.changelog


def test_fix_only_bumps_patch(sample_config):
    plan = compute_plan("push", ("v0.1.0",), _log("fix: repair"), sample_config)
    assert plan.tag == "v0.1.1"


def test_highest_bump_wins(sample_config):
    plan = compute_plan("push", ("v0.1.0",), _log("fix: a", "feat: b"), sample_config)
    assert plan.tag == "v0.2.0"


def test_non_release_commits_skip(sample_config):
    plan = compute_plan(
        "push",
        ("v0.1.0",),
        _log("docs: readme", "chore: tidy", "Merge pull request #16 from x"),
        sample_config,
    )
    assert plan.action == "skip"
    assert "no release-worthy commits since v0.1.0" in plan.reason


def test_breaking_escalates_minor_before_one_and_major_after(sample_config):
    zero_x = compute_plan("push", ("v0.1.0",), _log("fix!: rewrite"), sample_config)
    assert zero_x.tag == "v0.2.0"
    one_x = compute_plan("push", ("v1.2.3",), _log("fix!: rewrite"), sample_config)
    assert one_x.tag == "v2.0.0"


def test_prerelease_base_bumps_from_its_core(sample_config):
    plan = compute_plan("dispatch", ("v0.1.0-rc.1",), _log("feat: next"), sample_config)
    assert plan.tag == "v0.2.0"


def test_existing_tag_skips(sample_config):
    plan = compute_plan(
        "dispatch", ("v0.1.0",), (), sample_config, version_override="0.1.0"
    )
    assert plan.action == "skip" and "already exists" in plan.reason


def test_dispatch_without_release_commits_skips(sample_config):
    plan = compute_plan("dispatch", ("v0.1.0",), (), sample_config, suffix="rc.1")
    assert plan.action == "skip" and "no release-worthy commits" in plan.reason


def test_version_override_wins(sample_config):
    plan = compute_plan(
        "dispatch",
        ("v0.1.0",),
        _log("chore: nothing"),
        sample_config,
        version_override="1.2.3",
    )
    assert plan.action == "tag" and plan.tag == "v1.2.3"


@pytest.mark.parametrize(
    ("changed_files", "expected_scope"),
    [
        (
            ["backlog/tasks/task-1.md", "README.md", ".agents/skills/tdd/SKILL.md"],
            "none",
        ),
        (["packages/qgis-sdk/src/qgis_sdk/declarations.py"], "python"),
        (["packages/qgis-sdk-bridge/src/index.ts"], "typescript"),
        (
            [
                "packages/qgis-sdk/src/qgis_sdk/declarations.py",
                "packages/qgis-sdk-bridge/src/index.ts",
            ],
            "all",
        ),
        (["pixi.toml", "packages/qgis-sdk/src/qgis_sdk/declarations.py"], "all"),
    ],
)
def test_detect_scope_from_files_categorizes_monorepo_paths(
    changed_files, expected_scope
):
    assert detect_scope_from_files(changed_files) == expected_scope


def test_compute_plan_supports_scoped_tags_and_forced_bumps(sample_config):
    py_plan = compute_plan(
        "dispatch",
        ("v0.1.0",),
        _log("chore: internal"),
        sample_config,
        scope="python",
        bump="minor",
    )
    assert py_plan.action == "tag"
    assert py_plan.scope == "python"
    assert py_plan.tag == "python-v0.2.0"
    assert str(py_plan.version) == "0.2.0"

    ts_plan = compute_plan(
        "dispatch",
        ("v0.1.0",),
        _log("chore: internal"),
        sample_config,
        scope="typescript",
        bump="0.3.0",
    )
    assert ts_plan.action == "tag"
    assert ts_plan.scope == "typescript"
    assert ts_plan.tag == "ts-v0.3.0"


def test_compute_plan_skips_when_scope_is_none(sample_config):
    plan = compute_plan(
        "push",
        ("v0.1.0",),
        _log("feat: something"),
        sample_config,
        scope="none",
    )
    assert plan.action == "skip"


def test_unknown_trigger_rejected(sample_config):
    with pytest.raises(QgisSdkReleaseVersionError):
        compute_plan("schedule", (), (), sample_config)


def test_to_json_is_workflow_shaped(sample_config):
    plan = compute_plan("dispatch", (), _log("feat: x"), sample_config)
    payload = plan.to_json()
    assert payload == {
        "trigger": "dispatch",
        "first": True,
        "stable_exists": False,
        "base_tag": None,
        "version": "0.1.0",
        "tag": "v0.1.0",
        "action": "tag",
        "reason": "bootstrap release",
    }


# ---------------------------------------------------------------------------
# Artifacts
# ---------------------------------------------------------------------------


def test_checksums_are_sorted_and_sha256(tmp_path):
    second = tmp_path / "b.whl"
    first = tmp_path / "a.whl"
    first.write_bytes(b"hello\n")
    second.write_bytes(b"world\n")
    entries = checksums([second, first])
    assert [name for name, _ in entries] == ["a.whl", "b.whl"]
    assert entries[0][1] == hashlib.sha256(b"hello\n").hexdigest()


def test_checksums_reject_missing_files(tmp_path):
    with pytest.raises(QgisSdkReleaseError):
        checksums([tmp_path / "nope.whl"])


def test_write_checksums_is_sha256sum_compatible(tmp_path):
    target = tmp_path / "SHA256SUMS"
    write_checksums(target, [("a.whl", "aa" * 32), ("b.tgz", "bb" * 32)])
    assert target.read_text() == f"{'aa' * 32}  a.whl\n{'bb' * 32}  b.tgz\n"


def test_twine_check_needs_a_wheel():
    with pytest.raises(QgisSdkReleaseError):
        twine_check([])


# ---------------------------------------------------------------------------
# Version stamping
# ---------------------------------------------------------------------------


def test_stamp_pyproject_replaces_first_version_line():
    stamped = stamp_pyproject(PYPROJECT, Version.parse("0.2.0"))
    assert 'version = "0.2.0"' in stamped
    assert 'version = "0.1.0"' not in stamped
    assert 'requires = ["hatchling==1.32.4"]' in stamped


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


# ---------------------------------------------------------------------------
# GitHub REST
# ---------------------------------------------------------------------------


import io
from urllib.error import HTTPError


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()
        return False


def _opener(captured, payload=None, error=None):
    def opener(req):
        captured.append(req)
        if error is not None:
            raise error
        return FakeResponse(json.dumps(payload).encode())

    return opener


def test_create_release_request_shape():
    captured = []
    result = create_release(
        "owner/repo",
        "tok",
        "v0.1.0-rc.1",
        "v0.1.0-rc.1",
        "body text",
        prerelease=True,
        opener=_opener(captured, {"upload_url": "https://x{?name}", "html_url": "h"}),
    )
    (req,) = captured
    assert req.full_url == "https://api.github.com/repos/owner/repo/releases"
    assert req.get_method() == "POST"
    assert req.get_header("Authorization") == "Bearer tok"
    payload = json.loads(req.data)
    assert payload == {
        "tag_name": "v0.1.0-rc.1",
        "name": "v0.1.0-rc.1",
        "body": "body text",
        "draft": False,
        "prerelease": True,
        "make_latest": "false",
    }
    assert result["html_url"] == "h"


def test_create_release_stable_marks_latest():
    captured = []
    create_release(
        "o/r",
        "t",
        "v1.0.0",
        "v1.0.0",
        "b",
        prerelease=False,
        opener=_opener(captured, {"upload_url": "https://x"}),
    )
    payload = json.loads(captured[0].data)
    assert payload["make_latest"] == "true" and payload["prerelease"] is False


def test_upload_asset_quotes_name_and_sends_bytes(tmp_path):
    asset = tmp_path / "qgis_sdk-0.1.0-py3-none-any.whl"
    asset.write_bytes(b"wheel-bytes")
    captured = []
    upload_asset(
        "https://uploads.github.com/repos/o/r/releases/1/assets{?name,label}",
        "tok",
        asset,
        opener=_opener(captured, {"name": asset.name}),
    )
    (req,) = captured
    assert req.full_url == (
        "https://uploads.github.com/repos/o/r/releases/1/assets"
        "?name=qgis_sdk-0.1.0-py3-none-any.whl"
    )
    assert req.data == b"wheel-bytes"
    assert req.get_header("Content-type") == "application/octet-stream"


def test_http_errors_become_release_errors():
    error = HTTPError(
        "https://api.github.com/repos/o/r/releases",
        422,
        "Unprocessable Entity",
        {},
        io.BytesIO(b'{"message": "already_exists"}'),
    )
    with pytest.raises(QgisSdkReleaseError, match="already_exists"):
        create_release(
            "o/r",
            "t",
            "v1.0.0",
            "v1.0.0",
            "b",
            False,
            opener=_opener([], error=error),
        )


def test_upload_asset_missing_file_raises(tmp_path):
    with pytest.raises((QgisSdkReleaseError, OSError)):
        upload_asset("https://x{?name}", "t", Path(tmp_path / "ghost.whl"))


# ---------------------------------------------------------------------------
# CLI end-to-end
# ---------------------------------------------------------------------------


def _versionrc(tmp_path):
    path = tmp_path / ".versionrc"
    path.write_text(SAMPLE_VERSIONRC, encoding="utf-8")
    return path


def _fake_git(monkeypatch, tags=(), log=""):
    monkeypatch.setattr("release.list_tags", lambda runner=None: tuple(tags))
    monkeypatch.setattr("release.log_commits", lambda rng=None, runner=None: log)


def test_plan_dispatch_writes_outputs_and_changelog(tmp_path, monkeypatch):
    config = _versionrc(tmp_path)
    out_file = tmp_path / "gh_output"
    out_file.touch()
    monkeypatch.setenv("GITHUB_OUTPUT", str(out_file))
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    _fake_git(
        monkeypatch,
        log="a" * 40 + "\x1f" + "feat: x" + "\x1f" + "\x1e\n",
    )
    from release import main

    assert (
        main(
            [
                "plan",
                "--trigger",
                "dispatch",
                "--config",
                str(config),
                "--json",
            ]
        )
        == 0
    )
    outputs = dict(
        line.split("=", 1) for line in out_file.read_text().splitlines() if line
    )
    assert outputs["action"] == "tag"
    assert outputs["tag"] == "v0.1.0"
    assert outputs["prerelease"] == "false"
    changelog = (tmp_path / "qgis-sdk-release-changelog.md").read_text()
    assert "## v0.1.0" in changelog
    assert outputs["changelog_file"].endswith("qgis-sdk-release-changelog.md")


def test_plan_push_without_tags_skips(tmp_path, monkeypatch):
    config = _versionrc(tmp_path)
    _fake_git(monkeypatch)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    from release import main

    assert main(["plan", "--config", str(config)]) == 0


def test_plan_cli_supports_milestone_scope_bump_and_dry_run(tmp_path, monkeypatch):
    config = _versionrc(tmp_path)
    out_file = tmp_path / "gh_output"
    out_file.touch()
    monkeypatch.setenv("GITHUB_OUTPUT", str(out_file))
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    _fake_git(
        monkeypatch,
        tags=("v0.1.0", "milestone-v0.2.0"),
        log="a" * 40 + "\x1f" + "feat: milestone work" + "\x1f" + "\x1e\n",
    )
    from release import main

    assert (
        main(
            [
                "plan",
                "--trigger",
                "milestone",
                "--milestone-tag",
                "milestone-v0.2.0",
                "--config",
                str(config),
                "--dry-run",
                "true",
                "--json",
            ]
        )
        == 0
    )
    outputs = dict(
        line.split("=", 1) for line in out_file.read_text().splitlines() if line
    )
    assert outputs["action"] == "tag"
    assert outputs["tag"] == "v0.2.0"
    assert outputs["scope"] == "all"
    assert outputs["python"] == "true"
    assert outputs["typescript"] == "true"
    assert outputs["dry_run"] == "true"


def test_classify_reports_prerelease(tmp_path, monkeypatch):
    out_file = tmp_path / "gh_output"
    out_file.touch()
    monkeypatch.setenv("GITHUB_OUTPUT", str(out_file))
    from release import main

    assert main(["classify", "--tag", "v0.1.0-rc.1"]) == 0
    outputs = dict(
        line.split("=", 1) for line in out_file.read_text().splitlines() if line
    )
    assert outputs == {
        "version": "0.1.0-rc.1",
        "pep440": "0.1.0rc1",
        "prerelease": "true",
    }


def test_classify_rejects_bad_tag():
    from release import main

    assert main(["classify", "--tag", "0.1.0"]) == 1


def test_classify_scoped_reports_target_flags(tmp_path, monkeypatch):
    out_file = tmp_path / "gh_output"
    out_file.touch()
    monkeypatch.setenv("GITHUB_OUTPUT", str(out_file))
    from release import main

    assert main(["classify", "--tag", "python-v0.2.0", "--scoped"]) == 0
    outputs = dict(
        line.split("=", 1) for line in out_file.read_text().splitlines() if line
    )
    assert outputs == {
        "version": "0.2.0",
        "pep440": "0.2.0",
        "prerelease": "false",
        "scope": "python",
        "python": "true",
        "typescript": "false",
        "tag_name": "python-v0.2.0",
    }

    out_file.write_text("", encoding="utf-8")
    assert main(["classify", "--tag", "ts/v0.2.0-rc.1", "--scoped"]) == 0
    ts_outputs = dict(
        line.split("=", 1) for line in out_file.read_text().splitlines() if line
    )
    assert ts_outputs == {
        "version": "0.2.0-rc.1",
        "pep440": "0.2.0rc1",
        "prerelease": "true",
        "scope": "typescript",
        "python": "false",
        "typescript": "true",
        "tag_name": "ts/v0.2.0-rc.1",
    }


def test_tag_creates_and_pushes_with_message_file(tmp_path, monkeypatch):
    message = tmp_path / "changelog.md"
    message.write_text("# Changelog\n", encoding="utf-8")
    calls = []
    monkeypatch.setattr("release.create_tag", lambda *a, **k: calls.append((a, k)))
    from release import main

    assert (
        main(
            [
                "tag",
                "--tag",
                "v0.1.0",
                "--message-file",
                str(message),
                "--push",
            ]
        )
        == 0
    )
    (args, kwargs) = calls[0]
    assert args == ("v0.1.0", "# Changelog\n")
    assert kwargs == {"push": True}


def test_tag_needs_a_message():
    from release import main

    assert main(["tag", "--tag", "v0.1.0"]) == 1


def test_stamp_rewrites_both_manifests(tmp_path, monkeypatch):
    pyproject = tmp_path / "pyproject.toml"
    package = tmp_path / "package.json"
    pyproject.write_text(PYPROJECT, encoding="utf-8")
    package.write_text(PACKAGE_JSON, encoding="utf-8")
    import release

    monkeypatch.setattr(release, "_PYPROJECT", pyproject)
    monkeypatch.setattr(release, "_BRIDGE_PACKAGE", package)
    from release import main

    assert main(["stamp", "--version", "0.2.0-rc.1"]) == 0
    assert 'version = "0.2.0rc1"' in pyproject.read_text()
    assert '"version": "0.2.0-rc.1"' in package.read_text()


def test_github_release_publishes_prerelease_with_assets(tmp_path, monkeypatch):
    body = tmp_path / "notes.md"
    body.write_text("# Changelog\n", encoding="utf-8")
    wheel = tmp_path / "qgis_sdk-0.1.0rc1-py3-none-any.whl"
    wheel.write_bytes(b"w")
    sums = tmp_path / "SHA256SUMS"
    sums.write_text("00  wheel\n", encoding="utf-8")
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    created = []
    uploaded = []
    import release

    monkeypatch.setattr(
        release,
        "create_release",
        lambda slug, token, tag, name, text, prerelease, opener=None: (
            created.append((slug, tag, text, prerelease))
            or {"upload_url": "https://u{?name}", "html_url": "https://html"}
        ),
    )
    monkeypatch.setattr(
        release,
        "upload_asset",
        lambda url, token, path, opener=None: uploaded.append(path),
    )
    from release import main

    assert (
        main(
            [
                "github-release",
                "--tag",
                "v0.1.0-rc.1",
                "--body-file",
                str(body),
                "--asset",
                str(wheel),
                str(sums),
            ]
        )
        == 0
    )
    assert created == [("owner/repo", "v0.1.0-rc.1", "# Changelog\n", True)]
    assert uploaded == [wheel, sums]
    assert "https://html" in summary.read_text()


def test_github_release_needs_repo_and_token(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    from release import main

    assert main(["github-release", "--tag", "v0.1.0"]) == 1


# ---------------------------------------------------------------------------
# Workflow contracts (TASK-37)
# ---------------------------------------------------------------------------


def test_autorelease_workflow_has_milestone_triggers_paths_ignore_and_dispatch_inputs():
    repo_root = Path(__file__).resolve().parents[2]
    text = (repo_root / ".github/workflows/autorelease.yml").read_text(encoding="utf-8")
    for pattern in ('"milestone-v*"', '"milestone/*"', '"m-v*"'):
        assert pattern in text
    for ignored in ('"backlog/**"', '".agents/**"', '".devcontainer/**"', '"*.md"'):
        assert ignored in text
    assert "cancel-in-progress: false" in text
    for dispatch_input in ("scope:", "bump:", "dry-run:"):
        assert dispatch_input in text


def test_release_and_publish_sandbox_workflows_match_task_37_contracts():
    repo_root = Path(__file__).resolve().parents[2]
    release_text = (repo_root / ".github/workflows/release.yml").read_text(
        encoding="utf-8"
    )
    assert '"*-v*"' in release_text
    assert '"*/*v*"' in release_text
    assert "id-token: write" in release_text

    publish_text = (repo_root / ".github/workflows/publish-sandbox.yml").read_text(
        encoding="utf-8"
    )
    assert "SHA256SUMS" in publish_text
    assert "pixi global install" not in publish_text

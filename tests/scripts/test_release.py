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
    Commit,
    QgisSdkReleaseError,
    QgisSdkReleaseVersionError,
    Version,
    checksums,
    classify,
    commits_for_scope,
    compute_plan,
    contract_versions,
    create_release,
    detect_scope_from_files,
    main,
    manifest_versions,
    parse_log,
    parse_log_with_files,
    parse_milestone_tag,
    parse_release_tag,
    parse_versionrc,
    read_pyproject_version,
    read_python_contract_version,
    read_recipe_version,
    read_typescript_contract_version,
    render_changelog,
    resolve_dry_run,
    sort_tags,
    stamp_package_json,
    stamp_pyproject,
    stamp_recipe,
    tag_for_version,
    twine_check,
    upload_asset,
    version_from_pep440,
    version_from_tag,
    write_checksums,
)

PYPROJECT = '[build-system]\nrequires = ["hatchling==1.32.4"]\n\n[project]\nname = "qgis-sdk"\nversion = "0.1.0"\ndescription = "Kept."\n'
RECIPE_YAML = 'schema_version: 1\n\ncontext:\n  version: "0.1.0"\n\npackage:\n  name: qgis-sdk\n  version: ${{ version }}\n'
PACKAGE_JSON = '{\n\t"name": "@archont561/qgis-sdk",\n\t"version": "0.1.0",\n\t"private": false\n}\n'


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
        ("qgis-sdk-typescript-v0.1.0", "typescript", "0.1.0"),
        ("qgis-sdk-python-v0.1.0", "python", "0.1.0"),
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
        (["packages/qgis-sdk-python/src/qgis_sdk/declarations.py"], "python"),
        (["packages/qgis-sdk-typescript/src/index.ts"], "typescript"),
        (
            [
                "packages/qgis-sdk-python/src/qgis_sdk/declarations.py",
                "packages/qgis-sdk-typescript/src/index.ts",
            ],
            "all",
        ),
        (
            ["pixi.toml", "packages/qgis-sdk-python/src/qgis_sdk/declarations.py"],
            "python",
        ),
        (
            [
                "scripts/release.py",
                ".github/workflows/autorelease.yml",
                "pixi.toml",
                "bun.lock",
            ],
            "none",
        ),
        (["backlog/decisions/decision-25 - x.md", "packages"], "none"),
    ],
)
def test_detect_scope_from_files_categorizes_monorepo_paths(
    changed_files, expected_scope
):
    assert detect_scope_from_files(changed_files) == expected_scope


def test_tooling_changes_alone_plan_no_release():
    """A release-tool commit is not an artifact, so it cannot move a version.

    Regression for 2026-10-24: `feat(release)!` touching scripts/ and the
    workflows made detect_scope_from_files return "all", and the push planned an
    alignment release of both packages.
    """
    assert detect_scope_from_files(["scripts/release.py", "pixi.toml"]) == "none"


@pytest.mark.parametrize(
    ("trigger", "requested"),
    [("push", False), ("push", True), ("dispatch", False), ("milestone", False)],
)
def test_only_an_unrequested_branch_push_is_forced_into_a_dry_run(trigger, requested):
    dry_run, note = resolve_dry_run(trigger, requested)
    expected = requested or trigger == "push"
    assert dry_run is expected
    assert bool(note) is (trigger == "push" and not requested)


def test_a_branch_push_plans_the_candidate_without_tagging(tmp_path, monkeypatch):
    config = _versionrc(tmp_path)
    out_file = tmp_path / "gh_output"
    out_file.touch()
    monkeypatch.setenv("GITHUB_OUTPUT", str(out_file))
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    _fake_git(
        monkeypatch,
        tags=("v0.1.1",),
        log="a" * 40 + "\x1f" + "feat(sdk): x" + "\x1f" + "\x1e\n",
    )
    from release import main

    assert main(["plan", "--trigger", "push", "--config", str(config)]) == 0
    outputs = dict(
        line.split("=", 1) for line in out_file.read_text().splitlines() if line
    )
    assert outputs["action"] == "tag"
    assert outputs["tag"] == "v0.2.0"
    assert outputs["dry_run"] == "true"
    assert "never tags" in outputs["reason"]


def test_a_dispatch_is_not_forced_into_a_dry_run(tmp_path, monkeypatch):
    config = _versionrc(tmp_path)
    out_file = tmp_path / "gh_output"
    out_file.touch()
    monkeypatch.setenv("GITHUB_OUTPUT", str(out_file))
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    _fake_git(
        monkeypatch,
        tags=("v0.1.1",),
        log="a" * 40 + "\x1f" + "feat(sdk): x" + "\x1f" + "\x1e\n",
    )
    from release import main

    assert main(["plan", "--trigger", "dispatch", "--config", str(config)]) == 0
    outputs = dict(
        line.split("=", 1) for line in out_file.read_text().splitlines() if line
    )
    assert outputs["dry_run"] == "false"


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


def test_write_checksums_creates_the_output_directory(tmp_path):
    """A TypeScript-only release has no dist/ until the checksums are written.

    release.yml downloads wheels into dist/pypi and the tarball into npm/, and
    writes dist/SHA256SUMS; when no Python artifact was built the directory
    does not exist yet. ts-v0.2.0 failed its GitHub Release step on exactly
    that, after npm had already published.
    """
    target = tmp_path / "dist" / "SHA256SUMS"
    write_checksums(target, [("bridge.tgz", "cc" * 32)])
    assert target.read_text() == f"{'cc' * 32}  bridge.tgz\n"


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


def test_stamp_recipe_replaces_context_version_with_pep440():
    stamped = stamp_recipe(RECIPE_YAML, Version.parse("0.2.0-rc.1"))
    assert '  version: "0.2.0rc1"' in stamped
    assert "  version: ${{ version }}" in stamped
    with pytest.raises(QgisSdkReleaseError):
        stamp_recipe("package:\n  name: qgis-sdk\n", Version.parse("0.2.0"))


def test_create_tag_sets_git_identity_and_pushes():
    from release import create_tag

    commands = []
    create_tag(
        "v0.1.0",
        "# Changelog\n",
        push=True,
        runner=lambda cmd: commands.append(list(cmd)) or "",
    )
    assert commands == [
        [
            "git",
            "-c",
            "user.name=github-actions[bot]",
            "-c",
            "user.email=41898282+github-actions[bot]@users.noreply.github.com",
            "tag",
            "-a",
            "v0.1.0",
            "-m",
            "# Changelog\n",
        ],
        ["git", "push", "origin", "refs/tags/v0.1.0"],
    ]


def test_stamp_package_json_preserves_tabs_and_order():
    stamped = stamp_package_json(PACKAGE_JSON, Version.parse("0.2.0-rc.1"))
    assert stamped == (
        '{\n\t"name": "@archont561/qgis-sdk",\n\t"version": "0.2.0-rc.1",\n'
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


def _with_files(raw):
    """Rewrite a plain log record stream into the ``--name-only`` stream."""
    records = [chunk.strip("\n") for chunk in raw.split("\x1e") if chunk.strip()]
    return "".join(f"\x1e{record}\x1d\n" for record in records)


def _fake_git(monkeypatch, tags=(), log=""):
    monkeypatch.setattr("release.list_tags", lambda runner=None: tuple(tags))
    monkeypatch.setattr("release.log_commits", lambda rng=None, runner=None: log)
    monkeypatch.setattr(
        "release.log_commits_with_files", lambda rng=None, runner=None: _with_files(log)
    )


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
    recipe = tmp_path / "recipe.yaml"
    package = tmp_path / "package.json"
    pyproject.write_text(PYPROJECT, encoding="utf-8")
    recipe.write_text(RECIPE_YAML, encoding="utf-8")
    package.write_text(PACKAGE_JSON, encoding="utf-8")
    import release

    monkeypatch.setattr(release, "_PYPROJECT", pyproject)
    monkeypatch.setattr(release, "_RECIPE", recipe)
    monkeypatch.setattr(release, "_BRIDGE_PACKAGE", package)
    from release import main

    assert main(["stamp", "--version", "0.2.0-rc.1"]) == 0
    assert 'version = "0.2.0rc1"' in pyproject.read_text()
    assert '  version: "0.2.0rc1"' in recipe.read_text()
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


def test_github_release_updates_existing_release_when_already_exists(
    tmp_path, monkeypatch
):
    body = tmp_path / "notes.md"
    body.write_text("# Changelog\n", encoding="utf-8")
    wheel = tmp_path / "qgis_sdk-0.1.0-py3-none-any.whl"
    wheel.write_bytes(b"w")
    sums = tmp_path / "SHA256SUMS"
    sums.write_text("00  wheel\n", encoding="utf-8")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    deleted = []
    uploaded = []
    import release

    def raise_exists(*args, **kwargs):
        raise QgisSdkReleaseError(
            "GitHub release creation failed (422): already_exists"
        )

    monkeypatch.setattr(release, "create_release", raise_exists)
    monkeypatch.setattr(
        release,
        "get_release_by_tag",
        lambda slug, token, tag, opener=None: {
            "upload_url": "https://u{?name}",
            "html_url": "https://html/v0.1.0",
            "assets": [{"name": "SHA256SUMS", "id": 99}],
        },
    )
    monkeypatch.setattr(
        release,
        "delete_release_asset",
        lambda slug, token, asset_id, opener=None: deleted.append(asset_id),
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
                "v0.1.0",
                "--body-file",
                str(body),
                "--asset",
                str(wheel),
                str(sums),
            ]
        )
        == 0
    )
    assert deleted == [99]
    assert uploaded == [wheel, sums]


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
    # decision-25: the scope decides which package a release belongs to, so a
    # plain push must derive it instead of defaulting to an alignment release.
    assert 'default: "auto"' in text
    assert "RELEASE_SCOPE" in text


def test_the_autorelease_train_hands_its_tag_to_the_release_workflow():
    """A tag pushed with GITHUB_TOKEN starts no workflow, so the hop is explicit.

    Without the dispatch a dispatch- or milestone-triggered release produced an
    annotated tag that release.yml never saw: the tag existed, nothing was
    published, and no run recorded the gap.
    """
    repo_root = Path(__file__).resolve().parents[2]
    text = (repo_root / ".github/workflows/autorelease.yml").read_text(encoding="utf-8")

    assert "actions: write" in text
    assert "gh workflow run release.yml" in text
    hand_over = text.split("Hand the tag to the release workflow", 1)[1]
    assert "dry_run != 'true'" in hand_over.split("Report dry-run release", 1)[0]


def test_the_coverage_config_is_tracked_so_ci_measures_the_same_code():
    """The QGIS adapter omit lives in `.coveragerc`, which CI must receive.

    `.gitignore` once swallowed it through a `/.coverage*` glob, so CI measured
    the host-only adapters as uncovered (81%) while a local checkout reported
    100% - the same command, two different denominators.
    """
    repo_root = Path(__file__).resolve().parents[2]
    config = repo_root / ".coveragerc"

    assert config.is_file()
    assert "adapters/qgis/*" in config.read_text(encoding="utf-8")


def test_ci_verifies_the_scoped_versions_and_the_contract_on_every_push():
    repo_root = Path(__file__).resolve().parents[2]
    text = (repo_root / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "release-verify-versions" in text


def test_release_and_publish_sandbox_workflows_match_task_37_contracts():
    repo_root = Path(__file__).resolve().parents[2]
    release_text = (repo_root / ".github/workflows/release.yml").read_text(
        encoding="utf-8"
    )
    assert '"*-v*"' in release_text
    assert '"*/*v*"' in release_text
    assert "id-token: write" in release_text
    assert "environment: prefix" in release_text
    assert "publish-conda" in release_text
    assert "github-packages:" in release_text
    assert "https://npm.pkg.github.com" in release_text

    publish_text = (repo_root / ".github/workflows/publish-sandbox.yml").read_text(
        encoding="utf-8"
    )
    assert "SHA256SUMS" in publish_text
    assert "pixi global install" not in publish_text


# ---------------------------------------------------------------------------
# One version across the released manifests (decision-24)
# ---------------------------------------------------------------------------


def test_three_agreeing_manifests_report_their_shared_version():
    versions = manifest_versions(PYPROJECT, PACKAGE_JSON, RECIPE_YAML)

    assert str(versions.agreed()) == "0.1.0"
    assert versions.to_json() == {
        "pyproject.toml": "0.1.0",
        "package.json": "0.1.0",
        "recipe.yaml": "0.1.0",
    }


def test_a_pep440_prerelease_and_its_semver_spelling_agree():
    """stamp writes 0.2.0-rc.1 to package.json as 0.2.0rc1 for hatchling."""
    pyproject = PYPROJECT.replace('version = "0.1.0"', 'version = "0.2.0rc1"')
    package = PACKAGE_JSON.replace('"version": "0.1.0"', '"version": "0.2.0-rc.1"')
    recipe = RECIPE_YAML.replace('version: "0.1.0"', 'version: "0.2.0rc1"')

    versions = manifest_versions(pyproject, package, recipe)

    assert str(versions.agreed()) == "0.2.0-rc.1"


def test_a_disagreeing_manifest_is_named_with_every_value():
    package = PACKAGE_JSON.replace('"version": "0.1.0"', '"version": "0.1.1"')

    with pytest.raises(QgisSdkReleaseVersionError) as error:
        manifest_versions(PYPROJECT, package, RECIPE_YAML).agreed()

    message = str(error.value)
    assert "disagree" in message
    assert "pyproject.toml=0.1.0" in message
    assert "package.json=0.1.1" in message


def test_pep440_prereleases_round_trip_to_the_tag_they_came_from():
    for semver, pep440 in (
        ("0.2.0-alpha.1", "0.2.0a1"),
        ("0.2.0-beta.2", "0.2.0b2"),
        ("0.2.0-rc.1", "0.2.0rc1"),
    ):
        version = Version.parse(semver)

        assert version.to_pep440() == pep440
        assert str(version_from_pep440(pep440)) == semver


def test_a_missing_version_line_is_refused():
    with pytest.raises(QgisSdkReleaseError, match="no top-level version"):
        read_pyproject_version('[project]\nname = "qgis-sdk"\n')
    with pytest.raises(QgisSdkReleaseError, match="no quoted version"):
        read_recipe_version("schema_version: 1\n")


def test_the_recipe_is_optional_because_a_workspace_may_not_build_conda():
    versions = manifest_versions(PYPROJECT, PACKAGE_JSON)

    assert versions.recipe is None
    assert [name for name, _ in versions.items()] == ["pyproject.toml", "package.json"]


def test_the_verify_versions_command_checks_every_scope_on_its_own(capsys):
    assert main(["verify-versions"]) == 0

    out = capsys.readouterr().out
    assert "released manifests for scope python agree on" in out
    assert "released manifests for scope typescript agree on" in out
    assert "contract version 1 agrees" in out


def test_the_verify_versions_command_serializes_for_diagnostics(capsys):
    assert main(["verify-versions", "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    python_scope = payload["scopes"]["python"]
    typescript_scope = payload["scopes"]["typescript"]

    # A release stamps these manifests, so the assertion is about the serialized
    # agreement - every manifest of a scope carrying the scope's one version -
    # rather than about the number the workspace happens to carry today.
    assert set(python_scope["manifests"]) == {"pyproject.toml", "recipe.yaml"}
    assert set(python_scope["manifests"].values()) == {python_scope["version"]}
    assert typescript_scope["manifests"] == {
        "package.json": typescript_scope["version"]
    }
    assert payload["contract"] == {"python": 1, "typescript": 1}


def test_the_repository_contract_versions_agree():
    """The pairing substitute for one shared number (decision-25)."""
    repo_root = Path(__file__).resolve().parents[2]

    contract = contract_versions(
        (repo_root / "packages/qgis-sdk-python/src/qgis_sdk/declarations.py").read_text(
            encoding="utf-8"
        ),
        (repo_root / "packages/qgis-sdk-typescript/src/index.ts").read_text(
            encoding="utf-8"
        ),
    )

    assert contract.agreed() == 1


def test_a_contract_version_that_drifted_is_refused():
    script = "/**\n * Public contract\n */\nPLUGIN_DESCRIPTION_SCHEMA_VERSION = 2\n"
    bridge = "export const PLUGIN_DESCRIPTION_SCHEMA_VERSION: 1 = 1;\n"

    with pytest.raises(QgisSdkReleaseVersionError, match="contract versions disagree"):
        contract_versions(script, bridge).agreed()


def test_a_missing_contract_version_is_named_by_language():
    with pytest.raises(QgisSdkReleaseError, match="Python declarations"):
        read_python_contract_version("schema_version: 1\n")
    with pytest.raises(QgisSdkReleaseError, match="bridge index"):
        read_typescript_contract_version("export const OTHER = 1;\n")


# ---------------------------------------------------------------------------
# Independent package versions and the shared contract (decision-25)
# ---------------------------------------------------------------------------


def _commit(subject, *files, body=""):
    return Commit(sha="a" * 40, subject=subject, body=body, files=tuple(files))


def test_parse_log_with_files_keeps_multiline_bodies_and_paths():
    raw = (
        "\x1e" + "a" * 40 + "\x1ffeat(sdk): x\x1fbody line\n\nsecond para\x1d\n"
        "packages/qgis-sdk-python/src/qgis_sdk/declarations.py\n"
        "pixi.toml\n"
        "\x1e" + "b" * 40 + "\x1fdocs: y\x1f\x1d\n"
        "backlog/tasks/task-1.md\n"
    )

    commits = parse_log_with_files(raw)

    assert commits[0].files == (
        "packages/qgis-sdk-python/src/qgis_sdk/declarations.py",
        "pixi.toml",
    )
    assert "second para" in commits[0].body
    assert commits[1].files == ("backlog/tasks/task-1.md",)


def test_a_record_without_a_path_block_is_refused():
    with pytest.raises(QgisSdkReleaseError, match="malformed git log record"):
        parse_log_with_files("a" * 40 + "\x1ffeat: x\x1f")


def test_a_commit_without_file_information_affects_every_scope():
    """Omitting ``--name-only`` must not silently drop a commit."""
    assert commits_for_scope((_commit("feat: x"),), "python") == (_commit("feat: x"),)


def test_a_scoped_tag_sort_keeps_that_package_history_only():
    tags = ("v0.1.0", "python-v0.2.0", "ts-v0.3.0")

    assert sort_tags(tags, scope="python") == ("python-v0.2.0", "v0.1.0")
    assert sort_tags(tags, scope="typescript") == ("ts-v0.3.0", "v0.1.0")
    assert sort_tags(tags) == ("ts-v0.3.0", "python-v0.2.0", "v0.1.0")


def test_commits_are_kept_for_the_packages_they_touch():
    commits = (
        _commit(
            "feat(sdk): python only", "packages/qgis-sdk-python/src/qgis_sdk/core.py"
        ),
        _commit(
            "feat(bridge): bridge only", "packages/qgis-sdk-typescript/src/index.ts"
        ),
        _commit(
            "feat(both): spans packages",
            "packages/qgis-sdk-python/src/qgis_sdk/core.py",
            "packages/qgis-sdk-typescript/src/index.ts",
        ),
        _commit("docs: backlog", "backlog/tasks/task-1.md"),
    )

    python = [commit.subject for commit in commits_for_scope(commits, "python")]
    bridge = [commit.subject for commit in commits_for_scope(commits, "typescript")]
    both = [commit.subject for commit in commits_for_scope(commits, "all")]

    assert python == ["feat(sdk): python only", "feat(both): spans packages"]
    assert bridge == ["feat(bridge): bridge only", "feat(both): spans packages"]
    assert both == [
        "feat(sdk): python only",
        "feat(bridge): bridge only",
        "feat(both): spans packages",
    ]


def test_a_repository_wide_change_cannot_trigger_a_package_release():
    """CI, pixi.toml and the release tool do not change package contents."""
    commits = (
        _commit("feat!: rewrite the release tool", "scripts/release.py", "pixi.toml"),
    )

    assert commits_for_scope(commits, "python") == ()
    assert commits_for_scope(commits, "typescript") == ()
    assert commits_for_scope(commits, "all") == ()


def test_a_bridge_feature_does_not_move_the_python_version(sample_config):
    commits = (
        _commit("feat(bridge): transport", "packages/qgis-sdk-typescript/src/index.ts"),
    )

    python_plan = compute_plan(
        "dispatch", ("v0.1.0",), commits, sample_config, scope="python"
    )
    bridge_plan = compute_plan(
        "dispatch", ("v0.1.0",), commits, sample_config, scope="typescript"
    )

    assert python_plan.action == "skip"
    assert python_plan.version is None
    assert bridge_plan.tag == "ts-v0.2.0"


def test_each_scope_bumps_from_its_own_last_release(sample_config):
    commits = (
        _commit("fix(bridge): parsing", "packages/qgis-sdk-typescript/src/index.ts"),
    )
    tags = ("v0.1.0", "python-v0.3.0")

    bridge_plan = compute_plan(
        "dispatch", tags, commits, sample_config, scope="typescript"
    )
    python_plan = compute_plan("dispatch", tags, commits, sample_config, scope="python")

    assert bridge_plan.tag == "ts-v0.1.1"
    assert python_plan.action == "skip"
    assert "python-v0.3.0" in python_plan.reason


def test_stamp_scope_python_leaves_the_bridge_manifest_alone(tmp_path, monkeypatch):
    pyproject = tmp_path / "pyproject.toml"
    recipe = tmp_path / "recipe.yaml"
    package = tmp_path / "package.json"
    pyproject.write_text(PYPROJECT, encoding="utf-8")
    recipe.write_text(RECIPE_YAML, encoding="utf-8")
    package.write_text(PACKAGE_JSON, encoding="utf-8")
    import release

    monkeypatch.setattr(release, "_PYPROJECT", pyproject)
    monkeypatch.setattr(release, "_RECIPE", recipe)
    monkeypatch.setattr(release, "_BRIDGE_PACKAGE", package)

    assert main(["stamp", "--version", "0.2.0", "--scope", "python"]) == 0

    assert 'version = "0.2.0"' in pyproject.read_text()
    assert '  version: "0.2.0"' in recipe.read_text()
    assert '"version": "0.1.0"' in package.read_text()


def test_stamp_scope_typescript_leaves_the_python_manifests_alone(
    tmp_path, monkeypatch
):
    pyproject = tmp_path / "pyproject.toml"
    recipe = tmp_path / "recipe.yaml"
    package = tmp_path / "package.json"
    pyproject.write_text(PYPROJECT, encoding="utf-8")
    recipe.write_text(RECIPE_YAML, encoding="utf-8")
    package.write_text(PACKAGE_JSON, encoding="utf-8")
    import release

    monkeypatch.setattr(release, "_PYPROJECT", pyproject)
    monkeypatch.setattr(release, "_RECIPE", recipe)
    monkeypatch.setattr(release, "_BRIDGE_PACKAGE", package)

    assert main(["stamp", "--version", "0.2.0", "--scope", "typescript"]) == 0

    assert '"version": "0.2.0"' in package.read_text()
    assert 'version = "0.1.0"' in pyproject.read_text()
    assert '  version: "0.1.0"' in recipe.read_text()


def _diverged_manifests(tmp_path, monkeypatch, python_version, bridge_version):
    pyproject = tmp_path / "pyproject.toml"
    recipe = tmp_path / "recipe.yaml"
    package = tmp_path / "package.json"
    pyproject.write_text(
        PYPROJECT.replace('version = "0.1.0"', f'version = "{python_version}"'),
        encoding="utf-8",
    )
    recipe.write_text(
        RECIPE_YAML.replace('version: "0.1.0"', f'version: "{python_version}"'),
        encoding="utf-8",
    )
    package.write_text(
        PACKAGE_JSON.replace('"version": "0.1.0"', f'"version": "{bridge_version}"'),
        encoding="utf-8",
    )
    import release

    monkeypatch.setattr(release, "_PYPROJECT", pyproject)
    monkeypatch.setattr(release, "_RECIPE", recipe)
    monkeypatch.setattr(release, "_BRIDGE_PACKAGE", package)


def test_diverged_packages_pass_when_each_scope_agrees(tmp_path, monkeypatch):
    _diverged_manifests(tmp_path, monkeypatch, "0.2.0", "0.1.1")

    assert main(["verify-versions"]) == 0
    assert main(["verify-versions", "--scope", "python", "--version", "0.2.0"]) == 0
    assert main(["verify-versions", "--scope", "typescript", "--version", "0.1.1"]) == 0


def test_a_scope_that_lost_its_release_version_is_refused(
    tmp_path, monkeypatch, capsys
):
    _diverged_manifests(tmp_path, monkeypatch, "0.2.0", "0.1.1")

    assert main(["verify-versions", "--scope", "python", "--version", "0.3.0"]) == 1
    assert "run stamp --scope python --version 0.3.0 first" in capsys.readouterr().out


def test_one_version_needs_one_scope(tmp_path, monkeypatch):
    _diverged_manifests(tmp_path, monkeypatch, "0.2.0", "0.1.1")

    assert main(["verify-versions", "--version", "0.2.0"]) == 1


# ---------------------------------------------------------------------------
# The release policy itself, pinned against the real .versionrc
# ---------------------------------------------------------------------------


def _repository_config():
    repo_root = Path(__file__).resolve().parents[2]
    return parse_versionrc((repo_root / ".versionrc").read_text(encoding="utf-8"))


def test_feature_work_inside_a_milestone_is_a_patch_bump():
    """decision-24: minor is the milestone (breaking) axis, not the feature axis."""
    config = _repository_config()

    plan = compute_plan("dispatch", ("v0.2.0",), _log("feat: another slice"), config)

    assert str(plan.version) == "0.2.1"


def test_a_breaking_change_is_what_moves_the_minor():
    config = _repository_config()

    plan = compute_plan(
        "dispatch", ("v0.2.0",), _log("feat!: drop the old contract"), config
    )

    assert str(plan.version) == "0.3.0"


def test_a_milestone_release_sets_the_minor_explicitly():
    """The one place a minor moves on purpose: the milestone close."""
    config = _repository_config()

    plan = compute_plan(
        "dispatch", ("v0.1.1",), _log("chore: milestone close"), config, bump="minor"
    )

    assert (plan.action, str(plan.version), plan.tag) == ("tag", "0.2.0", "v0.2.0")


def test_the_repository_config_still_keeps_features_visible_in_the_changelog():
    config = _repository_config()

    rule = config.rule_for("feat")

    assert (rule.increment, rule.section, rule.hidden) == ("Patch", "Features", False)

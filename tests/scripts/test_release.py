"""Tests for the standalone scripts/release.py CLI.

Migrated from packages/qgis-sdk-release/tests. All functions are imported
directly from the ``release`` module (scripts/ is on the pytest pythonpath).
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest
import release as release_module
from conftest import SAMPLE_VERSIONRC
from hypothesis import example, given, settings
from hypothesis import strategies as st
from packaging.version import Version as PackagingVersion
from release import (
    Commit,
    QgisSdkReleaseError,
    QgisSdkReleaseVersionError,
    Version,
    checksums,
    classify,
    commit_packages,
    commits_for_scope,
    compute_plan,
    contract_versions,
    create_release,
    detect_scope_from_files,
    main,
    manifest_versions,
    normalize_scope,
    parse_log,
    parse_log_with_files,
    parse_milestone_tag,
    parse_release_tag,
    parse_versionrc,
    plan_base_tag,
    read_alias_versions,
    read_example_windows,
    read_pyproject_version,
    read_python_contract_version,
    read_recipe_version,
    read_scaffold_pin,
    read_typescript_contract_version,
    render_changelog,
    resolve_dry_run,
    sort_tags,
    stamp_alias_package_json,
    stamp_example_windows,
    stamp_package_json,
    stamp_pyproject,
    stamp_recipe,
    stamp_scaffold_pin,
    tag_for_version,
    twine_check,
    upload_asset,
    version_from_pep440,
    version_from_tag,
    write_checksums,
)

PYPROJECT = '[build-system]\nrequires = ["hatchling==1.32.4"]\n\n[project]\nname = "qgis-sdk"\nversion = "0.1.0"\ndescription = "Kept."\n'
RECIPE_YAML = (
    'schema_version: 1\n\ncontext:\n  version: "0.1.0"\n'
    '  runtime_version: "0.1.0"\n  tools_version: "0.1.0"\n'
    '  tools_runtime_requirement: "qgis-sdk-runtime>=0.1.0,<0.2"\n\n'
    "recipe:\n  name: qgis-sdk-kit\n  version: ${{ version }}\n"
)
PACKAGE_JSON = '{\n\t"name": "@archont561/qgis-sdk",\n\t"version": "0.1.0",\n\t"private": false\n}\n'
ALIAS_PACKAGE_JSON = (
    '{\n\t"name": "qgis-sdk",\n\t"version": "0.1.0",\n'
    '\t"dependencies": {\n\t\t"@archont561/qgis-sdk": "0.1.0"\n\t}\n}\n'
)
KIT_PYPROJECT = (
    '[project]\nname = "qgis-sdk"\nversion = "0.1.0"\n'
    'dependencies = [\n  "qgis-sdk-runtime==0.1.0",\n  "qgis-sdk-tools==0.1.0",\n]\n\n'
    "[project.optional-dependencies]\n"
    'controlled-deployment = ["qgis-sdk-runtime[controlled-deployment]==0.1.0"]\n'
)
RUNTIME_PYPROJECT = '[project]\nname = "qgis-sdk-runtime"\nversion = "0.1.0"\n'
TOOLS_PYPROJECT = (
    '[project]\nname = "qgis-sdk-tools"\nversion = "0.1.0"\n'
    'dependencies = [\n  "qgis-sdk-runtime>=0.1.0,<0.2",\n  "typer==0.27.3",\n]\n'
)


@pytest.fixture(autouse=True)
def _the_real_manifests_stay_untouched():
    """A stamp test that forgot to redirect a manifest must not edit the repo."""
    import release

    paths = (
        release._PYPROJECT,
        release._RUNTIME_PYPROJECT,
        release._TOOLS_PYPROJECT,
        release._RECIPE,
        release._BRIDGE_PACKAGE,
        release._ALIAS_PACKAGE,
        release._UI_PACKAGE,
        release._UI_ALIAS_PACKAGE,
        release._EXAMPLE_PYPROJECT,
    )
    before = {
        path: path.read_text(encoding="utf-8") for path in paths if path.is_file()
    }
    yield
    after = {path: path.read_text(encoding="utf-8") for path in paths if path.is_file()}
    assert after == before, "a test rewrote a real manifest"


def _python_manifests(
    tmp_path,
    monkeypatch,
    python_version="0.1.0",
    bridge_version="0.1.0",
    runtime_version=None,
    tools_range=None,
    kit_pin=None,
):
    """Write every released manifest under ``tmp_path`` and point release.py at it."""
    runtime_version = runtime_version or python_version
    pyproject = tmp_path / "pyproject.toml"
    runtime = tmp_path / "runtime-pyproject.toml"
    tools = tmp_path / "tools-pyproject.toml"
    recipe = tmp_path / "recipe.yaml"
    package = tmp_path / "package.json"
    pyproject.write_text(
        KIT_PYPROJECT.replace(
            'version = "0.1.0"', f'version = "{python_version}"'
        ).replace("==0.1.0", f"=={kit_pin or python_version}"),
        encoding="utf-8",
    )
    runtime.write_text(
        RUNTIME_PYPROJECT.replace(
            'version = "0.1.0"', f'version = "{runtime_version}"'
        ),
        encoding="utf-8",
    )
    runtime_range = tools_range or (
        f">={runtime_version},<{release_module.next_minor(Version.parse(runtime_version))}"
    )
    tools.write_text(
        TOOLS_PYPROJECT.replace(
            'version = "0.1.0"', f'version = "{python_version}"'
        ).replace(">=0.1.0,<0.2", runtime_range),
        encoding="utf-8",
    )
    recipe.write_text(
        RECIPE_YAML.replace('  version: "0.1.0"', f'  version: "{python_version}"')
        .replace('runtime_version: "0.1.0"', f'runtime_version: "{runtime_version}"')
        .replace('tools_version: "0.1.0"', f'tools_version: "{python_version}"')
        .replace(">=0.1.0,<0.2", runtime_range),
        encoding="utf-8",
    )
    package.write_text(
        PACKAGE_JSON.replace('"version": "0.1.0"', f'"version": "{bridge_version}"'),
        encoding="utf-8",
    )
    import release

    monkeypatch.setattr(release, "_PYPROJECT", pyproject)
    monkeypatch.setattr(release, "_RUNTIME_PYPROJECT", runtime)
    monkeypatch.setattr(release, "_TOOLS_PYPROJECT", tools)
    monkeypatch.setattr(release, "_RECIPE", recipe)
    monkeypatch.setattr(release, "_BRIDGE_PACKAGE", package)
    monkeypatch.setattr(release, "_ALIAS_PACKAGE", tmp_path / "no-alias.json")
    monkeypatch.setattr(release, "_SCAFFOLD_WEB", tmp_path / "no-web.py")
    monkeypatch.setattr(release, "_EXAMPLE_PYPROJECT", tmp_path / "no-example.toml")
    monkeypatch.setattr(release, "_UI_PACKAGE", tmp_path / "no-ui.json")
    monkeypatch.setattr(release, "_UI_ALIAS_PACKAGE", tmp_path / "no-ui-alias.json")
    return {
        "pyproject": pyproject,
        "runtime": runtime,
        "tools": tools,
        "recipe": recipe,
        "package": package,
    }


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


# -- strategies: the SemVer subset the release tool reads -------------------------

_SEMVER_TEXT = (
    r"\A(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-[0-9A-Za-z.-]+)?\Z"
)
_SCOPE_SEPARATORS = ("-", "/")
prerelease_idents = st.sampled_from(["rc", "alpha", "beta"])
versions = st.builds(
    Version,
    major=st.integers(0, 99),
    minor=st.integers(0, 99),
    patch=st.integers(0, 99),
    pre=st.one_of(
        st.none(),
        st.tuples(prerelease_idents, st.integers(1, 20).map(str)),
    ),
)
release_versions = versions.filter(lambda v: v.pre is None)
#: Every alias ``normalize_scope`` knows that a tag can also spell (the npm
#: name ``@archont561/qgis-sdk`` is a ``--scope`` spelling only).
scope_aliases = st.sampled_from(
    sorted(
        alias
        for alias in release_module._SCOPE_ALIASES
        if re.fullmatch(r"[A-Za-z0-9_+-]+", alias)
    )
)


@given(version=versions)
@settings(max_examples=50, deadline=None, derandomize=True)
def test_parse_round_trips_what_str_renders(version):
    assert Version.parse(str(version)) == version
    assert Version.parse(f"  {version} ") == version  # surrounding whitespace is noise


@given(
    text=st.text(max_size=12).filter(
        lambda t: not re.fullmatch(_SEMVER_TEXT, t.strip())
    )
)
@settings(max_examples=50, deadline=None, derandomize=True)
@example(text="")
@example(text="0.1")
@example(text="v0.1.0")
@example(text="01.1.0")
@example(text="0.1.0-")
def test_parse_rejects_what_is_not_a_semantic_version(text):
    with pytest.raises(QgisSdkReleaseVersionError):
        Version.parse(text)


@given(left=versions, right=versions)
@settings(max_examples=50, deadline=None, derandomize=True)
def test_sort_key_agrees_with_pep440_precedence(left, right):
    """Our SemVer ordering and PEP 440's agree on the subset both can express."""
    ours = (left.sort_key() > right.sort_key()) - (left.sort_key() < right.sort_key())
    a, b = PackagingVersion(left.to_pep440()), PackagingVersion(right.to_pep440())
    theirs = (a > b) - (a < b)
    assert ours == theirs


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


def test_bumping_a_prerelease_graduates_it_to_its_core():
    """A candidate is a preview of its core, so the next release *is* the core."""
    candidate = Version.parse("0.5.0-rc.1")
    assert str(candidate.bump("minor")) == "0.5.0"
    assert str(candidate.bump("patch")) == "0.5.0"
    assert str(candidate.bump("major")) == "1.0.0"
    assert str(Version.parse("0.5.1-rc.1").bump("minor")) == "0.6.0"
    assert str(Version.parse("0.5.1-rc.1").bump("patch")) == "0.5.1"
    assert str(Version.parse("1.0.0-rc.1").bump("major")) == "1.0.0"


def test_with_prerelease_validates_suffix():
    assert str(Version.parse("0.2.0").with_prerelease("rc.1")) == "0.2.0-rc.1"
    with pytest.raises(QgisSdkReleaseVersionError):
        Version.parse("0.2.0").with_prerelease("rc 1")


@given(version=versions)
@settings(max_examples=40, deadline=None, derandomize=True)
@example(version=Version.parse("0.1.0-rc.1"))
@example(version=Version.parse("0.1.0-alpha.2"))
@example(version=Version.parse("1.0.0-beta.1"))
def test_to_pep440_is_the_same_version_in_pep440_spelling(version):
    rendered = PackagingVersion(version.to_pep440())
    assert rendered.release == (version.major, version.minor, version.patch)
    if version.pre is None:
        assert rendered.pre is None and version.to_pep440() == str(version)
    else:
        kind, number = version.pre
        assert rendered.pre == (
            {"rc": "rc", "alpha": "a", "beta": "b"}[kind],
            int(number),
        )


def test_tag_helpers_roundtrip():
    version = Version.parse("0.2.0")
    tag = tag_for_version(version)
    assert tag == "v0.2.0"
    assert version_from_tag(tag) == version
    with pytest.raises(QgisSdkReleaseVersionError):
        version_from_tag("0.2.0")


@given(
    prefix=st.sampled_from(["milestone-", "milestone/", "m-"]),
    scope=st.one_of(st.none(), scope_aliases),
    version=versions,
)
@settings(max_examples=40, deadline=None, derandomize=True)
@example(prefix="milestone/", scope=None, version=Version.parse("0.2.0"))
@example(prefix="milestone/", scope="ts", version=Version.parse("0.2.0"))
def test_parse_milestone_tag_accepts_every_prefix_scope_and_version(
    prefix, scope, version
):
    if prefix == "m-" and scope is not None:
        return  # ``m-<scope>-v…`` is not a milestone spelling
    tag = f"{prefix}{scope}-v{version}" if scope else f"{prefix}v{version}"
    parsed = parse_milestone_tag(tag)
    assert parsed is not None
    expected = normalize_scope(scope) if scope else "all"
    assert parsed == (expected, version)
    if prefix == "milestone/" and scope is None:
        assert parse_milestone_tag(f"{prefix}{version}") == ("all", version)


def test_parse_milestone_tag_returns_none_for_regular_tags_and_rejects_malformed():
    assert parse_milestone_tag("v0.1.0") is None
    assert parse_milestone_tag("python-v0.1.0") is None
    with pytest.raises(QgisSdkReleaseVersionError):
        parse_milestone_tag("milestone-vnot-a-semver")


@given(
    scope=st.one_of(st.none(), scope_aliases),
    separator=st.sampled_from(_SCOPE_SEPARATORS),
    version=versions,
)
@settings(max_examples=50, deadline=None, derandomize=True)
@example(scope=None, separator="-", version=Version.parse("0.1.0-rc.1"))
@example(scope="qgis-sdk-bridge", separator="/", version=Version.parse("0.1.0"))
@example(scope="py", separator="-", version=Version.parse("0.2.0"))
def test_parse_release_tag_accepts_every_alias_separator_and_version(
    scope, separator, version
):
    tag = f"{scope}{separator}v{version}" if scope else f"v{version}"
    parsed_scope, parsed = parse_release_tag(tag)
    assert parsed == version
    assert parsed_scope == (normalize_scope(scope) if scope else "all")
    assert version_from_tag(tag) == version
    # What the tool mints for that scope parses back to the same pair.
    minted = tag_for_version(version, parsed_scope)
    assert parse_release_tag(minted) == (parsed_scope, version)


@given(
    scope=st.from_regex(r"\A[a-z][a-z0-9]{0,8}\Z").filter(
        lambda s: s not in release_module._SCOPE_ALIASES
    ),
    version=versions,
)
@settings(max_examples=30, deadline=None, derandomize=True)
@example(scope="milestone", version=Version.parse("0.1.0"))
@example(scope="unknown", version=Version.parse("0.1.0"))
def test_parse_release_tag_rejects_an_unknown_scope(scope, version):
    with pytest.raises(QgisSdkReleaseVersionError):
        parse_release_tag(f"{scope}-v{version}")


@pytest.mark.parametrize("bad_tag", ["0.1.0", "not-a-tag", "m-v0.1.0"])
def test_parse_release_tag_rejects_what_is_not_v_prefixed(bad_tag):
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
    assert plan.action == "tag" and plan.tag == "v0.1.0-rc.3"
    assert plan.base_tag == "v0.1.0-rc.2"


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


def test_a_prerelease_base_graduates_to_its_core(sample_config):
    plan = compute_plan("dispatch", ("v0.1.0-rc.1",), _log("feat: next"), sample_config)
    assert plan.tag == "v0.1.0"


def test_a_stable_release_after_a_candidate_starts_from_the_last_stable(
    sample_config,
):
    """``python-v0.5.0-rc.1`` rehearsed 0.5.0; the stable 0.5.0 still follows 0.4.0.

    The candidate is not a base for the stable release: the version comes from
    the commits since the last stable tag, and so does the changelog, so the
    release notes cover everything a 0.4.0 user gets.
    """
    tags = ("python-v0.4.0", "python-v0.5.0-rc.1", "ts-v0.3.0")
    commits = _log("feat(python): split", "fix(python): windows path")

    inferred = compute_plan("dispatch", tags, commits, sample_config, scope="python")
    forced = compute_plan(
        "dispatch", tags, commits, sample_config, scope="python", bump="minor"
    )
    patch_only = compute_plan(
        "dispatch", tags, _log("fix(python): one"), sample_config, scope="python"
    )

    assert (inferred.tag, inferred.base_tag) == ("python-v0.5.0", "python-v0.4.0")
    assert (forced.tag, forced.base_tag) == ("python-v0.5.0", "python-v0.4.0")
    assert patch_only.tag == "python-v0.4.1"
    assert (
        "[python-v0.4.0...python-v0.5.0]"
        in compute_plan(
            "dispatch",
            tags,
            commits,
            sample_config,
            scope="python",
            repo_slug="o/r",
        ).changelog
    )


def test_a_second_candidate_follows_the_first_on_the_same_core(sample_config):
    tags = ("python-v0.4.0", "python-v0.5.0-rc.1")

    plan = compute_plan(
        "dispatch",
        tags,
        _log("fix(python): x"),
        sample_config,
        scope="python",
        suffix="rc.2",
    )

    assert (plan.tag, plan.base_tag) == ("python-v0.5.0-rc.2", "python-v0.5.0-rc.1")


def test_plan_base_tag_prefers_the_last_stable_for_a_stable_release():
    ordered = ("v0.5.0-rc.2", "v0.5.0-rc.1", "v0.4.0", "v0.3.0")
    assert plan_base_tag(ordered, suffix="") == "v0.4.0"
    assert plan_base_tag(ordered, suffix="rc.3") == "v0.5.0-rc.2"
    assert plan_base_tag(("v0.1.0-rc.1",), suffix="") == "v0.1.0-rc.1"
    assert plan_base_tag((), suffix="") is None


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
        (["packages/qgis-sdk-runtime/src/qgis_sdk/declarations.py"], "python"),
        (["packages/qgis-sdk-typescript/src/index.ts"], "typescript"),
        (
            [
                "packages/qgis-sdk-runtime/src/qgis_sdk/declarations.py",
                "packages/qgis-sdk-typescript/src/index.ts",
            ],
            "all",
        ),
        (
            ["pixi.toml", "packages/qgis-sdk-runtime/src/qgis_sdk/declarations.py"],
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


def test_build_python_builds_every_distribution_by_default(tmp_path, monkeypatch):
    """One `python-v*` release ships the runtime, the tools and the kit together."""
    outdir = tmp_path / "pypi"
    calls = []

    def fake_runner(command):
        calls.append(list(command))
        if command[1:3] == ["-m", "build"]:
            package = Path(command[-1]).name.replace("-", "_")
            target = Path(command[command.index("--outdir") + 1])
            target.mkdir(parents=True, exist_ok=True)
            (target / f"{package}-0.1.0-py3-none-any.whl").write_bytes(b"w")

    monkeypatch.setattr(release_module, "_default_artifact_runner", fake_runner)

    assert main(["build-python", "--outdir", str(outdir)]) == 0

    built = [
        Path(call[-1]).as_posix() for call in calls if call[1:3] == ["-m", "build"]
    ]
    assert built == [
        "packages/qgis-sdk-runtime",
        "packages/qgis-sdk-tools",
        "packages/qgis-sdk-python",
    ]
    twine = [call for call in calls if call[:2] == ["twine", "check"]]
    assert len(twine) == 1 and len(twine[0]) == 2 + 3
    # One directory per distribution: the workflow publishes each on its own.
    assert sorted(wheel.parent.name for wheel in outdir.glob("*/*.whl")) == [
        "kit",
        "runtime",
        "tools",
    ]


def test_build_python_builds_only_the_distribution_a_scope_ships(tmp_path, monkeypatch):
    outdir = tmp_path / "pypi"
    calls = []

    def fake_runner(command):
        calls.append(list(command))
        if command[1:3] == ["-m", "build"]:
            target = Path(command[command.index("--outdir") + 1])
            target.mkdir(parents=True, exist_ok=True)
            (target / "qgis_sdk_tools-0.1.0-py3-none-any.whl").write_bytes(b"w")

    monkeypatch.setattr(release_module, "_default_artifact_runner", fake_runner)

    assert main(["build-python", "--scope", "tools", "--outdir", str(outdir)]) == 0

    built = [
        Path(call[-1]).as_posix() for call in calls if call[1:3] == ["-m", "build"]
    ]
    assert built == ["packages/qgis-sdk-tools"]
    assert [wheel.parent.name for wheel in outdir.glob("*/*.whl")] == ["tools"]


def test_build_python_accepts_an_explicit_package_list(tmp_path, monkeypatch):
    outdir = tmp_path / "pypi"
    calls = []

    def fake_runner(command):
        calls.append(list(command))
        if command[1:3] == ["-m", "build"]:
            target = Path(command[command.index("--outdir") + 1])
            target.mkdir(parents=True, exist_ok=True)
            (target / "only-0.1.0-py3-none-any.whl").write_bytes(b"w")

    monkeypatch.setattr(release_module, "_default_artifact_runner", fake_runner)

    assert main(["build-python", "--package", "pkg/only", "--outdir", str(outdir)]) == 0

    assert [call[-1] for call in calls if call[1:3] == ["-m", "build"]] == ["pkg/only"]


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


def test_plan_cli_logs_commits_since_the_last_stable_for_a_stable_release(
    tmp_path, monkeypatch
):
    config = _versionrc(tmp_path)
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    ranges: list[str | None] = []
    log = "a" * 40 + "\x1f" + "feat(python): x" + "\x1f" + "\x1e\n"
    monkeypatch.setattr(
        "release.list_tags",
        lambda runner=None: ("python-v0.4.0", "python-v0.5.0-rc.1"),
    )
    monkeypatch.setattr(
        "release.log_commits_with_files",
        lambda rng=None, runner=None: (ranges.append(rng), _with_files(log))[1],
    )
    from release import main

    assert (
        main(
            [
                "plan",
                "--trigger",
                "dispatch",
                "--scope",
                "python",
                "--config",
                str(config),
            ]
        )
        == 0
    )
    assert ranges == ["python-v0.4.0..HEAD"]
    ranges.clear()
    assert (
        main(
            [
                "plan",
                "--trigger",
                "dispatch",
                "--scope",
                "python",
                "--suffix",
                "rc.2",
                "--config",
                str(config),
            ]
        )
        == 0
    )
    assert ranges == ["python-v0.5.0-rc.1..HEAD"]


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
        "kit": "true",
        "runtime": "true",
        "tools": "true",
        "typescript": "false",
        "ui": "false",
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
        "kit": "false",
        "runtime": "false",
        "tools": "false",
        "typescript": "true",
        "ui": "false",
        "tag_name": "ts/v0.2.0-rc.1",
    }

    out_file.write_text("", encoding="utf-8")
    assert main(["classify", "--tag", "tools-v0.5.1", "--scoped"]) == 0
    tools_outputs = dict(
        line.split("=", 1) for line in out_file.read_text().splitlines() if line
    )
    assert tools_outputs["scope"] == "tools"
    assert {
        key: tools_outputs[key] for key in ("python", "kit", "runtime", "tools")
    } == {
        "python": "true",
        "kit": "false",
        "runtime": "false",
        "tools": "true",
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


def test_stamp_rewrites_every_manifest(tmp_path, monkeypatch):
    files = _python_manifests(tmp_path, monkeypatch)
    from release import main

    assert main(["stamp", "--version", "0.2.0-rc.1"]) == 0
    assert 'version = "0.2.0rc1"' in files["pyproject"].read_text()
    assert 'version = "0.2.0rc1"' in files["runtime"].read_text()
    assert 'version = "0.2.0rc1"' in files["tools"].read_text()
    assert '  version: "0.2.0rc1"' in files["recipe"].read_text()
    assert '"version": "0.2.0-rc.1"' in files["package"].read_text()


def test_stamp_pins_the_kit_to_the_runtime_and_the_tools_it_releases_with(
    tmp_path, monkeypatch
):
    """``pip install qgis-sdk==X`` installs runtime X and tools X (TASK-57 AC 1)."""
    files = _python_manifests(tmp_path, monkeypatch)

    assert main(["stamp", "--version", "0.5.0", "--scope", "python"]) == 0

    kit = files["pyproject"].read_text()
    assert '"qgis-sdk-runtime==0.5.0"' in kit
    assert '"qgis-sdk-tools==0.5.0"' in kit
    assert '"qgis-sdk-runtime[controlled-deployment]==0.5.0"' in kit
    assert "0.1.0" not in kit


def test_stamp_moves_the_tools_tested_runtime_range_with_the_runtime(
    tmp_path, monkeypatch
):
    """The tools were tested against the runtime they ship with, up to its next minor."""
    files = _python_manifests(tmp_path, monkeypatch)

    assert main(["stamp", "--version", "0.5.2", "--scope", "python"]) == 0

    tools = files["tools"].read_text()
    assert '"qgis-sdk-runtime>=0.5.2,<0.6"' in tools
    assert '"typer==0.27.3"' in tools
    assert main(["verify-versions", "--scope", "python", "--version", "0.5.2"]) == 0


def test_stamp_kit_pins_refuses_a_kit_without_pins():
    with pytest.raises(QgisSdkReleaseError, match="pins neither"):
        release_module.stamp_kit_pins(PYPROJECT, Version.parse("0.2.0"))


def test_stamp_tools_runtime_range_refuses_a_tools_manifest_without_a_range():
    with pytest.raises(QgisSdkReleaseError, match="no qgis-sdk-runtime"):
        release_module.stamp_tools_runtime_range(
            RUNTIME_PYPROJECT, Version.parse("0.2.0")
        )


@given(
    lower=release_versions,
    upper=st.tuples(st.integers(0, 99), st.integers(0, 99)).map(
        lambda pair: f"{pair[0]}.{pair[1]}"
    ),
    runtime=versions,
)
@settings(max_examples=60, deadline=None, derandomize=True)
@example(lower=Version.parse("0.4.0"), upper="0.5", runtime=Version.parse("0.5.0"))
@example(lower=Version.parse("0.4.0"), upper="0.5", runtime=Version.parse("0.4.9"))
def test_runtime_range_includes_agrees_with_pep440_arithmetic(lower, upper, runtime):
    expected = (
        PackagingVersion(lower.to_pep440())
        <= PackagingVersion(runtime.to_pep440())
        < PackagingVersion(upper)
    )
    assert release_module.runtime_range_includes(lower, upper, runtime) is expected


def test_read_kit_pins_and_tools_range_round_trip():
    assert release_module.read_kit_pins(KIT_PYPROJECT) == (
        ("qgis-sdk-runtime", Version.parse("0.1.0")),
        ("qgis-sdk-tools", Version.parse("0.1.0")),
        ("qgis-sdk-runtime[controlled-deployment]", Version.parse("0.1.0")),
    )
    assert release_module.read_tools_runtime_range(TOOLS_PYPROJECT) == (
        Version.parse("0.1.0"),
        "0.2",
    )


def test_verify_versions_names_a_kit_pin_that_lags_the_release(
    tmp_path, monkeypatch, capsys
):
    _python_manifests(tmp_path, monkeypatch, python_version="0.2.0", kit_pin="0.1.0")

    assert main(["verify-versions", "--scope", "python"]) == 1

    out = capsys.readouterr().out
    assert "kit pin qgis-sdk-runtime=0.1.0" in out


def test_verify_versions_refuses_tools_whose_range_excludes_the_runtime(
    tmp_path, monkeypatch, capsys
):
    """A tools release must include the runtime it ships next to (TASK-57 AC 2)."""
    _python_manifests(
        tmp_path, monkeypatch, python_version="0.5.0", tools_range=">=0.4.0,<0.5"
    )

    assert main(["verify-versions", "--scope", "python"]) == 1

    out = capsys.readouterr().out
    assert "qgis-sdk-runtime>=0.4.0,<0.5" in out
    assert "runtime at HEAD is 0.5.0" in out


# ---------------------------------------------------------------------------
# Independent runtime / tools releases (TASK-57 AC 2)
# ---------------------------------------------------------------------------


def test_runtime_and_tools_are_release_scopes_of_their_own():
    assert normalize_scope("runtime") == "runtime"
    assert normalize_scope("qgis-sdk-tools") == "tools"
    assert tag_for_version(Version.parse("0.5.1"), "runtime") == "runtime-v0.5.1"
    assert parse_release_tag("tools-v0.6.0") == ("tools", Version.parse("0.6.0"))
    assert release_module.scope_ships("runtime") == {
        "python": True,
        "kit": False,
        "runtime": True,
        "tools": False,
        "typescript": False,
        "ui": False,
    }
    assert release_module.scope_ships("python")["tools"] is True


def test_a_kit_tag_is_a_base_for_the_runtime_and_the_tools():
    tags = ("python-v0.5.0", "runtime-v0.5.1", "tools-v0.5.2", "ts-v0.3.0")

    assert sort_tags(tags, scope="runtime") == ("runtime-v0.5.1", "python-v0.5.0")
    assert sort_tags(tags, scope="tools") == ("tools-v0.5.2", "python-v0.5.0")
    assert sort_tags(tags, scope="python") == ("python-v0.5.0",)


def test_commits_are_kept_for_the_distribution_they_touch():
    runtime = _commit("fix(runtime): r", "packages/qgis-sdk-runtime/src/qgis_sdk/a.py")
    tools = _commit("feat(tools): t", "packages/qgis-sdk-tools/src/qgis_sdk_tools/b.py")
    kit = _commit("chore(kit): k", "packages/qgis-sdk-python/pyproject.toml")
    bridge = _commit("fix(bridge): b", "packages/qgis-sdk-typescript/src/index.ts")

    assert release_module.commit_scopes(runtime) == {"python", "runtime"}
    assert release_module.commit_scopes(kit) == {"python"}
    assert commits_for_scope((runtime, tools, kit, bridge), "runtime") == (runtime,)
    assert commits_for_scope((runtime, tools, kit, bridge), "tools") == (tools,)
    assert commits_for_scope((runtime, tools, kit, bridge), "python") == (
        runtime,
        tools,
        kit,
    )


def test_stamp_scope_runtime_moves_the_runtime_alone(tmp_path, monkeypatch):
    files = _python_manifests(tmp_path, monkeypatch)

    assert main(["stamp", "--version", "0.1.1", "--scope", "runtime"]) == 0

    assert 'version = "0.1.1"' in files["runtime"].read_text()
    recipe = files["recipe"].read_text()
    assert 'runtime_version: "0.1.1"' in recipe
    assert '  version: "0.1.0"' in recipe and 'tools_version: "0.1.0"' in recipe
    kit = files["pyproject"].read_text()
    assert 'version = "0.1.0"' in kit and '"qgis-sdk-runtime==0.1.0"' in kit
    assert 'version = "0.1.0"' in files["tools"].read_text()
    # The kit's pin now lags the runtime; that is allowed. Leading is not.
    assert main(["verify-versions"]) == 0
    assert main(["verify-versions", "--scope", "runtime", "--version", "0.1.1"]) == 0


def test_stamp_scope_tools_tests_against_the_runtime_at_head(tmp_path, monkeypatch):
    files = _python_manifests(tmp_path, monkeypatch, runtime_version="0.1.3")

    assert main(["stamp", "--version", "0.2.0", "--scope", "tools"]) == 0

    tools = files["tools"].read_text()
    assert 'version = "0.2.0"' in tools
    assert '"qgis-sdk-runtime>=0.1.3,<0.2"' in tools
    recipe = files["recipe"].read_text()
    assert 'tools_version: "0.2.0"' in recipe
    assert 'tools_runtime_requirement: "qgis-sdk-runtime>=0.1.3,<0.2"' in recipe
    assert 'runtime_version: "0.1.3"' in recipe
    assert 'version = "0.1.3"' in files["runtime"].read_text()
    assert main(["verify-versions", "--scope", "tools", "--version", "0.2.0"]) == 0


def test_a_runtime_release_the_tools_cannot_use_is_refused(
    tmp_path, monkeypatch, capsys
):
    _python_manifests(tmp_path, monkeypatch)

    assert main(["stamp", "--version", "0.2.0", "--scope", "runtime"]) == 0
    assert main(["verify-versions", "--scope", "runtime", "--version", "0.2.0"]) == 1

    out = capsys.readouterr().out
    assert "qgis-sdk-runtime>=0.1.0,<0.2" in out
    assert "runtime at HEAD is 0.2.0" in out
    assert "stamp --scope tools" in out


def test_a_kit_pin_that_leads_the_manifest_it_names_is_refused(
    tmp_path, monkeypatch, capsys
):
    _python_manifests(tmp_path, monkeypatch, kit_pin="0.3.0")

    assert main(["verify-versions"]) == 1

    out = capsys.readouterr().out
    assert "qgis-sdk-runtime==0.3.0" in out
    assert "0.1.0 at HEAD" in out


def test_stamp_recipe_context_names_a_missing_key():
    with pytest.raises(QgisSdkReleaseError, match="no quoted tools_version"):
        release_module.stamp_recipe_context(
            PYPROJECT, "tools_version", Version.parse("0.1.0")
        )
    assert release_module.read_recipe_context(PYPROJECT, "tools_version") is None


def test_verify_versions_reports_the_tools_runtime_range(tmp_path, monkeypatch, capsys):
    _python_manifests(tmp_path, monkeypatch, python_version="0.5.0")

    assert main(["verify-versions", "--scope", "python", "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["scopes"]["python"]["runtime_range"] == ">=0.5.0,<0.6"
    assert set(payload["scopes"]["python"]["manifests"]) == {
        "pyproject.toml",
        "runtime pyproject.toml",
        "tools pyproject.toml",
        "kit pin qgis-sdk-runtime",
        "kit pin qgis-sdk-tools",
        "kit pin qgis-sdk-runtime[controlled-deployment]",
        "recipe.yaml",
        "recipe runtime_version",
        "recipe tools_version",
    }


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
        "recipe runtime_version": "0.1.0",
        "recipe tools_version": "0.1.0",
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
    # Without a release in hand each distribution agrees with itself; the kit
    # is checked on its own because its pins may lag an independent release.
    assert "released manifests for scope runtime agree on" in out
    assert "released manifests for scope tools agree on" in out
    assert "released manifests for scope kit agree on" in out
    assert "released manifests for scope typescript agree on" in out
    assert "contract version 1 agrees" in out


def test_the_verify_versions_command_serializes_for_diagnostics(capsys):
    assert main(["verify-versions", "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    scopes = payload["scopes"]
    typescript_scope = scopes["typescript"]

    # A release stamps these manifests, so the assertion is about the serialized
    # agreement - every manifest of a scope carrying the scope's one version -
    # rather than about the number the workspace happens to carry today.
    assert set(scopes) == {"runtime", "tools", "kit", "typescript", "ui"}
    assert set(scopes["runtime"]["manifests"]) == {
        "runtime pyproject.toml",
        "recipe runtime_version",
    }
    assert set(scopes["tools"]["manifests"]) == {
        "tools pyproject.toml",
        "recipe tools_version",
    }
    assert set(scopes["kit"]["manifests"]) == {"pyproject.toml", "recipe.yaml"}
    assert set(scopes["kit"]["pins"]) >= {"qgis-sdk-runtime", "qgis-sdk-tools"}
    for entry in (scopes["runtime"], scopes["tools"], scopes["kit"]):
        assert set(entry["manifests"].values()) == {entry["version"]}
    assert scopes["tools"]["runtime_range"].startswith(
        f">={scopes['runtime']['version']},<"
    )
    assert typescript_scope["manifests"] == {
        "package.json": typescript_scope["version"]
    }
    assert scopes["ui"]["manifests"] == {"ui package.json": scopes["ui"]["version"]}
    assert scopes["ui"]["bridge_peer_range"].startswith(">=")
    assert payload["contract"] == {"python": 1, "typescript": 1}


def test_the_verify_versions_command_checks_the_whole_kit_on_request(capsys):
    assert main(["verify-versions", "--scope", "python", "--json"]) == 0

    python_scope = json.loads(capsys.readouterr().out)["scopes"]["python"]
    assert set(python_scope["manifests"]) >= {
        "pyproject.toml",
        "runtime pyproject.toml",
        "tools pyproject.toml",
        "kit pin qgis-sdk-runtime",
        "kit pin qgis-sdk-tools",
        "recipe.yaml",
        "recipe runtime_version",
        "recipe tools_version",
    }
    assert set(python_scope["manifests"].values()) == {python_scope["version"]}
    assert python_scope["runtime_range"].startswith(f">={python_scope['version']},<")


def test_the_repository_contract_versions_agree():
    """The pairing substitute for one shared number (decision-25)."""
    repo_root = Path(__file__).resolve().parents[2]

    contract = contract_versions(
        (
            repo_root / "packages/qgis-sdk-runtime/src/qgis_sdk/declarations.py"
        ).read_text(encoding="utf-8"),
        (repo_root / "packages/qgis-sdk-typescript/src/declarations.ts").read_text(
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
    with pytest.raises(QgisSdkReleaseError, match="bridge declarations"):
        read_typescript_contract_version("export const OTHER = 1;\n")


# ---------------------------------------------------------------------------
# Independent package versions and the shared contract (decision-25)
# ---------------------------------------------------------------------------


def _commit(subject, *files, body=""):
    return Commit(sha="a" * 40, subject=subject, body=body, files=tuple(files))


def test_parse_log_with_files_keeps_multiline_bodies_and_paths():
    raw = (
        "\x1e" + "a" * 40 + "\x1ffeat(sdk): x\x1fbody line\n\nsecond para\x1d\n"
        "packages/qgis-sdk-runtime/src/qgis_sdk/declarations.py\n"
        "pixi.toml\n"
        "\x1e" + "b" * 40 + "\x1fdocs: y\x1f\x1d\n"
        "backlog/tasks/task-1.md\n"
    )

    commits = parse_log_with_files(raw)

    assert commits[0].files == (
        "packages/qgis-sdk-runtime/src/qgis_sdk/declarations.py",
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


def test_commits_under_the_pre_rename_package_paths_still_count():
    """The 0.4.0 history straddles the 2026-10-24 directory rename.

    ``python-v0.3.0`` predates it, so the Python commits of PR #65 live under
    ``packages/qgis-sdk/`` and the bridge history before ``ts-v0.3.0`` under
    ``packages/qgis-sdk-bridge/``. Found while planning 0.4.0 (TASK-30): the
    generated changelog silently dropped the derived-ids, ctx-attribute and
    PluginContext-services features.
    """
    old_python = _commit("feat(declarations): derive ids", "packages/qgis-sdk/src/x.py")
    old_bridge = _commit("feat(bridge): y", "packages/qgis-sdk-bridge/src/index.ts")

    assert commit_packages(old_python) == (True, False)
    assert commit_packages(old_bridge) == (False, True)
    assert detect_scope_from_files(["packages/qgis-sdk/src/x.py"]) == "python"
    assert detect_scope_from_files(["packages/qgis-sdk-bridge/a.ts"]) == "typescript"


def test_a_scoped_tag_sort_keeps_that_package_history_only():
    tags = ("v0.1.0", "python-v0.2.0", "ts-v0.3.0")

    assert sort_tags(tags, scope="python") == ("python-v0.2.0", "v0.1.0")
    assert sort_tags(tags, scope="typescript") == ("ts-v0.3.0", "v0.1.0")
    assert sort_tags(tags) == ("ts-v0.3.0", "python-v0.2.0", "v0.1.0")


def test_commits_are_kept_for_the_packages_they_touch():
    commits = (
        _commit(
            "feat(sdk): python only", "packages/qgis-sdk-runtime/src/qgis_sdk/core.py"
        ),
        _commit(
            "feat(bridge): bridge only", "packages/qgis-sdk-typescript/src/index.ts"
        ),
        _commit(
            "feat(both): spans packages",
            "packages/qgis-sdk-runtime/src/qgis_sdk/core.py",
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
    files = _python_manifests(tmp_path, monkeypatch)

    assert main(["stamp", "--version", "0.2.0", "--scope", "python"]) == 0

    assert 'version = "0.2.0"' in files["pyproject"].read_text()
    assert '  version: "0.2.0"' in files["recipe"].read_text()
    assert '"version": "0.1.0"' in files["package"].read_text()


def test_stamp_scope_typescript_leaves_the_python_manifests_alone(
    tmp_path, monkeypatch
):
    files = _python_manifests(tmp_path, monkeypatch)

    assert main(["stamp", "--version", "0.2.0", "--scope", "typescript"]) == 0

    assert '"version": "0.2.0"' in files["package"].read_text()
    for name in ("pyproject", "runtime", "tools"):
        assert 'version = "0.1.0"' in files[name].read_text()
    assert '  version: "0.1.0"' in files["recipe"].read_text()


def _diverged_manifests(tmp_path, monkeypatch, python_version, bridge_version):
    _python_manifests(
        tmp_path,
        monkeypatch,
        python_version=python_version,
        bridge_version=bridge_version,
    )


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


# ---------------------------------------------------------------------------
# The unscoped npm alias ``qgis-sdk`` (decision-33, TASK-55)
# ---------------------------------------------------------------------------


def test_stamp_alias_package_json_pins_the_dependency_to_the_version():
    stamped = stamp_alias_package_json(ALIAS_PACKAGE_JSON, Version.parse("0.3.0"))

    data = json.loads(stamped)
    assert data["version"] == "0.3.0"
    assert data["dependencies"] == {"@archont561/qgis-sdk": "0.3.0"}
    assert stamped.startswith('{\n\t"name": "qgis-sdk"')


def test_stamp_alias_package_json_refuses_a_manifest_without_the_dependency():
    with pytest.raises(QgisSdkReleaseError, match="@archont561/qgis-sdk"):
        stamp_alias_package_json(PACKAGE_JSON, Version.parse("0.3.0"))


def test_read_alias_versions_returns_the_version_and_the_pin():
    assert read_alias_versions(ALIAS_PACKAGE_JSON) == (
        Version.parse("0.1.0"),
        Version.parse("0.1.0"),
    )


def test_read_alias_versions_refuses_a_range_pin():
    loose = ALIAS_PACKAGE_JSON.replace('"0.1.0"\n\t}', '"^0.1.0"\n\t}')

    with pytest.raises(QgisSdkReleaseVersionError):
        read_alias_versions(loose)


def _alias_manifests(tmp_path, monkeypatch, bridge_version="0.1.0", alias_text=None):
    files = _python_manifests(tmp_path, monkeypatch, bridge_version=bridge_version)
    alias = tmp_path / "alias.json"
    alias.write_text(alias_text or ALIAS_PACKAGE_JSON, encoding="utf-8")
    import release

    monkeypatch.setattr(release, "_ALIAS_PACKAGE", alias)
    return files["package"], alias


def test_stamp_scope_typescript_stamps_the_alias_with_the_bridge(tmp_path, monkeypatch):
    package, alias = _alias_manifests(tmp_path, monkeypatch)

    assert main(["stamp", "--version", "0.3.0", "--scope", "typescript"]) == 0

    assert json.loads(package.read_text())["version"] == "0.3.0"
    data = json.loads(alias.read_text())
    assert data["version"] == "0.3.0"
    assert data["dependencies"]["@archont561/qgis-sdk"] == "0.3.0"
    assert main(["verify-versions", "--scope", "typescript", "--version", "0.3.0"]) == 0


def test_stamp_scope_python_leaves_the_alias_alone(tmp_path, monkeypatch):
    _, alias = _alias_manifests(tmp_path, monkeypatch)

    assert main(["stamp", "--version", "0.9.0", "--scope", "python"]) == 0

    assert json.loads(alias.read_text())["version"] == "0.1.0"


def test_verify_versions_names_an_alias_that_lags_the_bridge(
    tmp_path, monkeypatch, capsys
):
    _alias_manifests(tmp_path, monkeypatch, bridge_version="0.1.1")

    assert main(["verify-versions", "--scope", "typescript"]) == 1

    out = capsys.readouterr().out
    assert "alias package.json=0.1.0" in out
    assert "package.json=0.1.1" in out


def test_verify_versions_names_an_alias_pin_that_drifts(tmp_path, monkeypatch, capsys):
    drifted = ALIAS_PACKAGE_JSON.replace('"0.1.0"\n\t}', '"0.0.9"\n\t}')
    _alias_manifests(tmp_path, monkeypatch, alias_text=drifted)

    assert main(["verify-versions", "--scope", "typescript"]) == 1

    assert "alias dependency=0.0.9" in capsys.readouterr().out


def test_verify_versions_for_python_ignores_the_alias(tmp_path, monkeypatch):
    _alias_manifests(tmp_path, monkeypatch, bridge_version="0.1.1")

    assert main(["verify-versions", "--scope", "python", "--version", "0.1.0"]) == 0


SCAFFOLD_WEB_PY = (
    'LF: Final = "\\n"\n'
    "\n"
    'SDK_NPM_PACKAGE: Final = "@archont561/qgis-sdk"\n'
    'SDK_NPM_VERSION: Final = "0.1.0"\n'
    '"""The published bridge this scaffold is written against, pinned exactly."""\n'
)


def test_read_scaffold_pin_returns_the_pinned_bridge_version():
    assert read_scaffold_pin(SCAFFOLD_WEB_PY) == Version.parse("0.1.0")


def test_read_scaffold_pin_refuses_a_missing_or_loose_pin():
    with pytest.raises(QgisSdkReleaseError, match="SDK_NPM_VERSION"):
        read_scaffold_pin('SDK_NPM_PACKAGE: Final = "@archont561/qgis-sdk"\n')
    with pytest.raises(QgisSdkReleaseVersionError):
        read_scaffold_pin(SCAFFOLD_WEB_PY.replace('"0.1.0"', '"^0.1.0"'))


def test_stamp_scaffold_pin_rewrites_only_the_constant():
    stamped = stamp_scaffold_pin(SCAFFOLD_WEB_PY, Version.parse("0.4.0"))

    assert 'SDK_NPM_VERSION: Final = "0.4.0"\n' in stamped
    assert stamped.replace('"0.4.0"', '"0.1.0"') == SCAFFOLD_WEB_PY
    with pytest.raises(QgisSdkReleaseError, match="SDK_NPM_VERSION"):
        stamp_scaffold_pin("nothing here\n", Version.parse("0.4.0"))


def _scaffold_manifests(tmp_path, monkeypatch, bridge_version="0.1.0", web_text=None):
    files = _python_manifests(tmp_path, monkeypatch, bridge_version=bridge_version)
    web = tmp_path / "web.py"
    web.write_text(web_text or SCAFFOLD_WEB_PY, encoding="utf-8")
    import release

    monkeypatch.setattr(release, "_SCAFFOLD_WEB", web)
    return files["package"], web


def test_stamp_scope_typescript_moves_the_scaffold_pin_with_the_bridge(
    tmp_path, monkeypatch
):
    """A tools release pins the newest bridge it was qualified with (decision-41)."""
    package, web = _scaffold_manifests(tmp_path, monkeypatch)

    assert main(["stamp", "--version", "0.3.0", "--scope", "typescript"]) == 0

    assert json.loads(package.read_text())["version"] == "0.3.0"
    assert 'SDK_NPM_VERSION: Final = "0.3.0"' in web.read_text()
    assert main(["verify-versions", "--scope", "typescript", "--version", "0.3.0"]) == 0


def test_stamp_scope_python_leaves_the_scaffold_pin_alone(tmp_path, monkeypatch):
    _, web = _scaffold_manifests(tmp_path, monkeypatch)

    assert main(["stamp", "--version", "0.9.0", "--scope", "python"]) == 0

    assert 'SDK_NPM_VERSION: Final = "0.1.0"' in web.read_text()


def test_verify_versions_names_a_scaffold_pin_that_lags(tmp_path, monkeypatch, capsys):
    _scaffold_manifests(tmp_path, monkeypatch, bridge_version="0.1.1")

    assert main(["verify-versions", "--scope", "typescript"]) == 1

    out = capsys.readouterr().out
    assert "scaffold pin=0.1.0" in out
    assert "package.json=0.1.1" in out


def test_verify_versions_for_python_ignores_the_scaffold_pin(tmp_path, monkeypatch):
    _scaffold_manifests(tmp_path, monkeypatch, bridge_version="0.1.1")

    assert main(["verify-versions", "--scope", "python", "--version", "0.1.0"]) == 0


def test_the_repository_scaffold_pins_the_bridge_at_head(monkeypatch):
    """The committed pin, not a fixture: `qgis-sdk new` offers the latest release."""
    import release

    root = Path(release.__file__).resolve().parent.parent
    bridge = root / "packages" / "qgis-sdk-typescript" / "package.json"
    web = root / "packages/qgis-sdk-tools/src/qgis_sdk_tools/scaffold/web.py"
    monkeypatch.setattr(release, "_SCAFFOLD_WEB", web)

    bridge_version = Version.parse(json.loads(bridge.read_text())["version"])
    assert read_scaffold_pin(web.read_text()) == bridge_version
    assert main(["verify-versions", "--scope", "typescript"]) == 0


def test_alias_changes_count_as_typescript():
    assert commits_for_scope(
        [
            _commit(
                "fix(alias): re-export testing", "packages/qgis-sdk-alias/testing.js"
            )
        ],
        "typescript",
    )
    assert not commits_for_scope(
        [
            _commit(
                "fix(alias): re-export testing", "packages/qgis-sdk-alias/testing.js"
            )
        ],
        "python",
    )
    assert (
        detect_scope_from_files(["packages/qgis-sdk-alias/package.json"])
        == "typescript"
    )


def test_the_repository_alias_agrees_with_the_bridge(monkeypatch):
    """The committed manifests, not fixtures: the alias must track the bridge."""
    import release

    root = Path(release.__file__).resolve().parent.parent
    bridge = root / "packages" / "qgis-sdk-typescript" / "package.json"
    alias = root / "packages" / "qgis-sdk-alias" / "package.json"
    monkeypatch.setattr(release, "_ALIAS_PACKAGE", alias)

    bridge_version = Version.parse(json.loads(bridge.read_text())["version"])
    assert read_alias_versions(alias.read_text()) == (bridge_version, bridge_version)
    assert main(["verify-versions", "--scope", "typescript"]) == 0


EXAMPLE_PYPROJECT = (
    "[project]\n"
    'name = "simple"\n'
    'version = "0.0.0"\n'
    'dependencies = ["qgis-sdk-runtime>=0.1,<0.2"]\n'
    "\n"
    "[dependency-groups]\n"
    'dev = ["qgis-sdk-tools>=0.1,<0.2"]\n'
    "\n"
    "[tool.qgis-sdk]\n"
    'plugin = "simple.plugin:SimplePlugin"\n'
)


def test_read_example_windows_returns_both_minor_windows():
    assert read_example_windows(EXAMPLE_PYPROJECT) == {
        "qgis-sdk-runtime": (Version.parse("0.1.0"), "0.2"),
        "qgis-sdk-tools": (Version.parse("0.1.0"), "0.2"),
    }


def test_read_example_windows_refuses_a_manifest_without_them():
    with pytest.raises(QgisSdkReleaseError, match="qgis-sdk-runtime"):
        read_example_windows('[project]\ndependencies = ["typer"]\n')


def test_stamp_example_windows_moves_each_line_to_the_minor_window():
    """The example declares what the scaffold would write for this release."""
    stamped = stamp_example_windows(
        EXAMPLE_PYPROJECT, runtime=Version.parse("0.6.0"), tools=Version.parse("0.6.0")
    )

    assert 'dependencies = ["qgis-sdk-runtime>=0.6,<0.7"]' in stamped
    assert 'dev = ["qgis-sdk-tools>=0.6,<0.7"]' in stamped
    assert stamped.replace(">=0.6,<0.7", ">=0.1,<0.2") == EXAMPLE_PYPROJECT

    only_runtime = stamp_example_windows(
        EXAMPLE_PYPROJECT, runtime=Version.parse("0.1.4")
    )
    assert (
        '"qgis-sdk-runtime>=0.1,<0.2"' in only_runtime
    )  # the patch stays in the window
    assert '"qgis-sdk-tools>=0.1,<0.2"' in only_runtime
    pre = stamp_example_windows(EXAMPLE_PYPROJECT, tools=Version.parse("0.7.0-rc.1"))
    assert '"qgis-sdk-tools>=0.7,<0.8"' in pre


def _example_manifests(tmp_path, monkeypatch, text=None, **kwargs):
    files = _python_manifests(tmp_path, monkeypatch, **kwargs)
    example = tmp_path / "example-pyproject.toml"
    example.write_text(text or EXAMPLE_PYPROJECT, encoding="utf-8")
    import release

    monkeypatch.setattr(release, "_EXAMPLE_PYPROJECT", example)
    files["example"] = example
    return files


def test_stamp_scope_python_moves_the_example_windows_with_the_kit(
    tmp_path, monkeypatch
):
    """``examples/simple`` is a project the released tools must accept (TASK-65)."""
    files = _example_manifests(tmp_path, monkeypatch)

    assert main(["stamp", "--version", "0.6.0", "--scope", "python"]) == 0

    example = files["example"].read_text()
    assert '"qgis-sdk-runtime>=0.6,<0.7"' in example
    assert '"qgis-sdk-tools>=0.6,<0.7"' in example
    assert 'version = "0.0.0"' in example  # the example's own version is not released
    assert main(["verify-versions", "--scope", "python", "--version", "0.6.0"]) == 0


def test_stamp_scope_runtime_and_tools_move_their_own_example_line(
    tmp_path, monkeypatch
):
    files = _example_manifests(tmp_path, monkeypatch)

    assert main(["stamp", "--version", "0.2.0", "--scope", "runtime"]) == 0
    example = files["example"].read_text()
    assert '"qgis-sdk-runtime>=0.2,<0.3"' in example
    assert '"qgis-sdk-tools>=0.1,<0.2"' in example

    assert main(["stamp", "--version", "0.2.0", "--scope", "tools"]) == 0
    example = files["example"].read_text()
    assert '"qgis-sdk-tools>=0.2,<0.3"' in example


def test_verify_versions_names_an_example_window_that_excludes_the_release(
    tmp_path, monkeypatch, capsys
):
    """A stamped release whose example still declares the old window is refused."""
    _example_manifests(tmp_path, monkeypatch, python_version="0.6.0")

    assert main(["verify-versions", "--scope", "python", "--version", "0.6.0"]) == 1

    out = capsys.readouterr().out
    assert "examples/simple" in out
    assert "qgis-sdk-runtime>=0.1.0,<0.2" in out
    assert "stamp --scope python --version 0.6.0" in out


def test_verify_versions_passes_without_an_example_manifest(tmp_path, monkeypatch):
    _python_manifests(tmp_path, monkeypatch)

    assert main(["verify-versions", "--scope", "python", "--version", "0.1.0"]) == 0


# ---------------------------------------------------------------------------
# The web components: the ``ui`` scope (TASK-70, decision-47)
# ---------------------------------------------------------------------------

UI_PACKAGE_JSON = (
    '{\n\t"name": "@archont561/qgis-sdk-ui",\n\t"version": "0.1.0",\n'
    '\t"peerDependencies": {\n\t\t"@archont561/qgis-sdk": ">=0.1.0 <0.2.0"\n\t}\n}\n'
)


def _ui_manifests(tmp_path, monkeypatch, bridge_version="0.1.0", ui_text=None):
    files = _python_manifests(tmp_path, monkeypatch, bridge_version=bridge_version)
    ui = tmp_path / "ui.json"
    ui.write_text(ui_text or UI_PACKAGE_JSON, encoding="utf-8")
    monkeypatch.setattr(release_module, "_UI_PACKAGE", ui)
    return files["package"], ui


def test_ui_is_a_release_scope_of_its_own_and_never_part_of_all():
    assert normalize_scope("ui") == "ui"
    assert normalize_scope("@archont561/qgis-sdk-ui") == "ui"
    assert tag_for_version(Version.parse("0.1.0"), "ui") == "ui-v0.1.0"
    assert parse_release_tag("ui-v0.2.0") == ("ui", Version.parse("0.2.0"))
    assert release_module.scope_ships("ui") == {
        "python": False,
        "kit": False,
        "runtime": False,
        "tools": False,
        "typescript": False,
        "ui": True,
    }
    assert release_module.scope_ships("all")["ui"] is False
    tags = ("v0.6.0", "ts-v0.4.0", "ui-v0.1.0")
    assert sort_tags(tags, scope="ui") == ("ui-v0.1.0",)
    assert sort_tags(tags, scope="all") == ("v0.6.0", "ts-v0.4.0")
    assert sort_tags(tags, scope="typescript") == ("v0.6.0", "ts-v0.4.0")


def test_ui_commits_move_only_the_ui_scope():
    ui_commit = _commit(
        "feat(ui): add a picker", "packages/qgis-sdk-ui/src/elements/picker.ts"
    )
    bridge_commit = _commit(
        "fix(bridge): parse", "packages/qgis-sdk-typescript/src/x.ts"
    )

    assert commits_for_scope([ui_commit, bridge_commit], "ui") == (ui_commit,)
    assert commits_for_scope([ui_commit, bridge_commit], "typescript") == (
        bridge_commit,
    )
    assert commits_for_scope([ui_commit], "all") == ()
    assert (
        release_module.detect_scope_from_files(["packages/qgis-sdk-ui/src/index.ts"])
        == "ui"
    )
    assert (
        release_module.detect_scope_from_files(
            ["packages/qgis-sdk-ui/src/index.ts", "packages/qgis-sdk-typescript/a.ts"]
        )
        == "typescript"
    )


def test_plan_for_the_ui_scope_reads_only_ui_tags_and_commits(monkeypatch):
    config = parse_versionrc(SAMPLE_VERSIONRC)
    commits = (
        _commit("feat(ui): add a picker", "packages/qgis-sdk-ui/src/picker.ts"),
        _commit("feat(bridge): new store", "packages/qgis-sdk-typescript/src/s.ts"),
    )
    plan = compute_plan(
        trigger="dispatch",
        tags=("v0.6.0", "ts-v0.4.0", "ui-v0.1.0"),
        commits=commits,
        config=config,
        scope="ui",
    )
    assert plan.scope == "ui"
    assert plan.base_tag == "ui-v0.1.0"
    assert plan.tag == "ui-v0.2.0"
    assert "add a picker" in plan.changelog
    assert "new store" not in plan.changelog

    first = compute_plan(
        trigger="dispatch",
        tags=("v0.6.0", "ts-v0.4.0"),
        commits=commits,
        config=config,
        scope="ui",
    )
    assert first.first is True
    assert first.tag == "ui-v0.1.0"


def test_read_ui_peer_range_reads_the_floor_and_the_ceiling():
    assert release_module.read_ui_peer_range(UI_PACKAGE_JSON) == (
        Version.parse("0.1.0"),
        "0.2.0",
    )
    with pytest.raises(QgisSdkReleaseError, match="peerDependencies"):
        release_module.read_ui_peer_range('{"name": "x", "version": "0.1.0"}')
    with pytest.raises(QgisSdkReleaseVersionError, match=">=X.Y.Z <U"):
        release_module.read_ui_peer_range(
            UI_PACKAGE_JSON.replace(">=0.1.0 <0.2.0", "^0.1.0")
        )


def test_stamp_scope_ui_moves_the_ui_manifest_alone(tmp_path, monkeypatch):
    package, ui = _ui_manifests(tmp_path, monkeypatch)

    assert main(["stamp", "--version", "0.2.0", "--scope", "ui"]) == 0

    assert json.loads(ui.read_text())["version"] == "0.2.0"
    assert json.loads(package.read_text())["version"] == "0.1.0"
    assert main(["verify-versions", "--scope", "ui", "--version", "0.2.0"]) == 0

    assert main(["stamp", "--version", "0.3.0", "--scope", "typescript"]) == 0
    assert json.loads(ui.read_text())["version"] == "0.2.0"


def test_verify_versions_refuses_a_ui_peer_range_that_excludes_the_bridge(
    tmp_path, monkeypatch, capsys
):
    _ui_manifests(tmp_path, monkeypatch, bridge_version="0.2.0")

    assert main(["verify-versions", "--scope", "ui"]) == 1

    out = capsys.readouterr().out
    assert "peer" in out
    assert "0.2.0" in out
    # The other scopes are not held hostage by the UI's range.
    assert main(["verify-versions", "--scope", "typescript", "--version", "0.2.0"]) == 0


def test_verify_versions_without_a_scope_covers_the_ui_when_present(
    tmp_path, monkeypatch, capsys
):
    _ui_manifests(tmp_path, monkeypatch)

    assert main(["verify-versions", "--json"]) == 0

    report = json.loads(capsys.readouterr().out)
    assert report["scopes"]["ui"] == {
        "version": "0.1.0",
        "manifests": {"ui package.json": "0.1.0"},
        "bridge_peer_range": ">=0.1.0 <0.2.0",
    }
    assert "ui package.json" not in report["scopes"]["typescript"]["manifests"]


def test_verify_versions_for_all_leaves_the_ui_train_out(tmp_path, monkeypatch):
    _ui_manifests(
        tmp_path, monkeypatch, ui_text=UI_PACKAGE_JSON.replace("0.1.0", "0.9.0", 1)
    )

    assert main(["verify-versions", "--scope", "all", "--version", "0.1.0"]) == 0


def test_the_repository_ui_package_accepts_the_bridge_at_head():
    """The committed manifests, not a fixture: a ui release is possible today."""
    root = Path(release_module.__file__).resolve().parent.parent
    bridge = root / "packages" / "qgis-sdk-typescript" / "package.json"
    ui = root / "packages" / "qgis-sdk-ui" / "package.json"
    bridge_version = Version.parse(json.loads(bridge.read_text())["version"])
    peer = release_module.read_ui_peer_range(ui.read_text())

    assert release_module.ui_peer_range_includes(peer, bridge_version)
    assert main(["verify-versions", "--scope", "ui"]) == 0


# ---------------------------------------------------------------------------
# A ui release moves the scaffold UI pin and the unscoped alias (TASK-110)
# ---------------------------------------------------------------------------

SCAFFOLD_WEB_PY_WITH_UI = (
    SCAFFOLD_WEB_PY + 'UI_NPM_PACKAGE: Final = "@archont561/qgis-sdk-ui"\n'
    'UI_NPM_VERSION: Final = "0.1.0"\n'
    '"""The published web components the templates opt into, pinned exactly."""\n'
)
UI_ALIAS_PACKAGE_JSON = (
    '{\n\t"name": "qgis-sdk-ui",\n\t"version": "0.1.0",\n'
    '\t"dependencies": {\n\t\t"@archont561/qgis-sdk-ui": "0.1.0"\n\t}\n}\n'
)


def test_read_scaffold_ui_pin_returns_the_pinned_components_version():
    assert release_module.read_scaffold_ui_pin(
        SCAFFOLD_WEB_PY_WITH_UI
    ) == Version.parse("0.1.0")
    with pytest.raises(QgisSdkReleaseError, match="UI_NPM_VERSION"):
        release_module.read_scaffold_ui_pin(SCAFFOLD_WEB_PY)
    with pytest.raises(QgisSdkReleaseVersionError):
        release_module.read_scaffold_ui_pin(
            SCAFFOLD_WEB_PY_WITH_UI.replace(
                'UI_NPM_VERSION: Final = "0.1.0"', 'UI_NPM_VERSION: Final = "^0.1.0"'
            )
        )


def test_stamp_scaffold_ui_pin_rewrites_only_the_ui_constant():
    stamped = release_module.stamp_scaffold_ui_pin(
        SCAFFOLD_WEB_PY_WITH_UI, Version.parse("0.2.0")
    )

    assert 'UI_NPM_VERSION: Final = "0.2.0"\n' in stamped
    assert 'SDK_NPM_VERSION: Final = "0.1.0"\n' in stamped
    assert (
        stamped.replace(
            'UI_NPM_VERSION: Final = "0.2.0"', 'UI_NPM_VERSION: Final = "0.1.0"'
        )
        == SCAFFOLD_WEB_PY_WITH_UI
    )
    with pytest.raises(QgisSdkReleaseError, match="UI_NPM_VERSION"):
        release_module.stamp_scaffold_ui_pin(SCAFFOLD_WEB_PY, Version.parse("0.2.0"))


def _ui_train_manifests(
    tmp_path,
    monkeypatch,
    bridge_version="0.1.0",
    ui_text=None,
    web_text=None,
    alias_text=None,
):
    package, ui = _ui_manifests(
        tmp_path, monkeypatch, bridge_version=bridge_version, ui_text=ui_text
    )
    web = tmp_path / "web.py"
    web.write_text(web_text or SCAFFOLD_WEB_PY_WITH_UI, encoding="utf-8")
    monkeypatch.setattr(release_module, "_SCAFFOLD_WEB", web)
    alias = tmp_path / "ui-alias.json"
    alias.write_text(alias_text or UI_ALIAS_PACKAGE_JSON, encoding="utf-8")
    monkeypatch.setattr(release_module, "_UI_ALIAS_PACKAGE", alias)
    return package, ui, web, alias


def test_stamp_scope_ui_moves_the_scaffold_ui_pin_and_the_alias(tmp_path, monkeypatch):
    """A UI release moves the pin `qgis-sdk new --ui-dependency` writes and the alias."""
    package, ui, web, alias = _ui_train_manifests(tmp_path, monkeypatch)

    assert main(["stamp", "--version", "0.2.0", "--scope", "ui"]) == 0

    assert json.loads(ui.read_text())["version"] == "0.2.0"
    assert 'UI_NPM_VERSION: Final = "0.2.0"' in web.read_text()
    assert 'SDK_NPM_VERSION: Final = "0.1.0"' in web.read_text()
    assert json.loads(alias.read_text()) == {
        "name": "qgis-sdk-ui",
        "version": "0.2.0",
        "dependencies": {"@archont561/qgis-sdk-ui": "0.2.0"},
    }
    assert json.loads(package.read_text())["version"] == "0.1.0"
    assert main(["verify-versions", "--scope", "ui", "--version", "0.2.0"]) == 0


def test_stamp_scope_typescript_leaves_the_scaffold_ui_pin_and_the_ui_alias_alone(
    tmp_path, monkeypatch
):
    _, ui, web, alias = _ui_train_manifests(tmp_path, monkeypatch)

    assert main(["stamp", "--version", "0.3.0", "--scope", "typescript"]) == 0

    assert 'SDK_NPM_VERSION: Final = "0.3.0"' in web.read_text()
    assert 'UI_NPM_VERSION: Final = "0.1.0"' in web.read_text()
    assert json.loads(ui.read_text())["version"] == "0.1.0"
    assert json.loads(alias.read_text())["version"] == "0.1.0"


def test_verify_versions_names_a_scaffold_ui_pin_that_lags(
    tmp_path, monkeypatch, capsys
):
    _ui_train_manifests(
        tmp_path,
        monkeypatch,
        ui_text=UI_PACKAGE_JSON.replace("0.1.0", "0.1.1", 1),
        alias_text=UI_ALIAS_PACKAGE_JSON.replace("0.1.0", "0.1.1"),
    )

    assert main(["verify-versions", "--scope", "ui"]) == 1

    out = capsys.readouterr().out
    assert "scaffold ui pin=0.1.0" in out
    assert "ui package.json=0.1.1" in out
    # The bridge train is not held hostage by a stale UI pin.
    assert main(["verify-versions", "--scope", "typescript", "--version", "0.1.0"]) == 0


def test_verify_versions_names_a_ui_alias_that_lags(tmp_path, monkeypatch, capsys):
    _ui_train_manifests(
        tmp_path,
        monkeypatch,
        ui_text=UI_PACKAGE_JSON.replace("0.1.0", "0.1.1", 1),
        web_text=SCAFFOLD_WEB_PY_WITH_UI.replace(
            'UI_NPM_VERSION: Final = "0.1.0"', 'UI_NPM_VERSION: Final = "0.1.1"'
        ),
    )

    assert main(["verify-versions", "--scope", "ui", "--json"]) == 1

    out = capsys.readouterr().out
    assert "ui alias package.json=0.1.0" in out
    assert "ui alias dependency=0.1.0" in out


def test_verify_versions_reports_the_whole_ui_train(tmp_path, monkeypatch, capsys):
    _ui_train_manifests(tmp_path, monkeypatch)

    assert main(["verify-versions", "--scope", "ui", "--json"]) == 0

    report = json.loads(capsys.readouterr().out)
    assert report["scopes"]["ui"]["manifests"] == {
        "ui package.json": "0.1.0",
        "ui alias package.json": "0.1.0",
        "ui alias dependency": "0.1.0",
        "scaffold ui pin": "0.1.0",
    }


def test_a_scaffold_without_a_ui_pin_is_a_bridge_pin_only(tmp_path, monkeypatch):
    """The fixture of the bridge tests predates the UI pin; it still verifies."""
    _ui_train_manifests(tmp_path, monkeypatch, web_text=SCAFFOLD_WEB_PY)

    assert main(["verify-versions", "--scope", "ui", "--version", "0.1.0"]) == 0
    assert main(["stamp", "--version", "0.2.0", "--scope", "ui"]) == 0


def test_ui_alias_changes_count_as_ui():
    assert (
        release_module.detect_scope_from_files(["packages/qgis-sdk-ui-alias/index.js"])
        == "ui"
    )
    assert release_module.commit_scopes(
        _commit("fix(ui): alias re-exports uno", "packages/qgis-sdk-ui-alias/uno.js")
    ) == frozenset({"ui"})


def test_the_repository_ui_train_agrees_at_head(monkeypatch):
    """The committed manifests: the scaffold UI pin and the alias follow the package."""
    root = Path(release_module.__file__).resolve().parent.parent
    ui = root / "packages" / "qgis-sdk-ui" / "package.json"
    alias = root / "packages" / "qgis-sdk-ui-alias" / "package.json"
    web = root / "packages/qgis-sdk-tools/src/qgis_sdk_tools/scaffold/web.py"
    monkeypatch.setattr(release_module, "_SCAFFOLD_WEB", web)
    monkeypatch.setattr(release_module, "_UI_ALIAS_PACKAGE", alias)
    ui_version = Version.parse(json.loads(ui.read_text())["version"])

    assert release_module.read_scaffold_ui_pin(web.read_text()) == ui_version
    assert release_module.read_alias_versions(
        alias.read_text(), dependency="@archont561/qgis-sdk-ui"
    ) == (ui_version, ui_version)
    assert main(["verify-versions", "--scope", "ui"]) == 0


def test_release_workflow_publishes_the_ui_train(monkeypatch):
    """A ``ui-v*`` tag reaches npm the way ``ts-v*`` tags do (TASK-110 AC #1, #4).

    The ``ui`` job is gated on the classify flag, runs under the ``npm``
    trusted-publishing environment, packs the scoped package and its unscoped
    alias, dry-runs a prerelease under ``next`` and publishes the alias only
    after the scoped package it pins.
    """
    import yaml

    repo_root = Path(__file__).resolve().parents[2]
    workflow = yaml.safe_load(
        (repo_root / ".github/workflows/release.yml").read_text(encoding="utf-8")
    )
    jobs = workflow["jobs"]
    assert jobs["build"]["outputs"]["ui"] == "${{ steps.classify.outputs.ui }}"
    build_steps = {step.get("name"): step for step in jobs["build"]["steps"]}
    assert build_steps["Install JavaScript dependencies"]["if"] == (
        "steps.classify.outputs.typescript == 'true' || "
        "steps.classify.outputs.ui == 'true'"
    )
    assert build_steps["Build the web components"]["if"] == (
        "steps.classify.outputs.ui == 'true'"
    )
    assert "@archont561/qgis-sdk-ui" in build_steps["Build the web components"]["run"]
    assert build_steps["Upload UI package artifact"]["with"]["name"] == "ui-package"
    assert (
        build_steps["Upload UI alias package artifact"]["with"]["name"]
        == "ui-alias-package"
    )

    ui = jobs["ui"]
    assert ui["needs"] == "build"
    assert ui["if"] == "needs.build.outputs.ui == 'true'"
    assert ui["environment"] == "npm"
    assert ui["permissions"] == {"id-token": "write", "contents": "read"}
    steps = {step.get("name"): step for step in ui["steps"]}
    pack = steps["Pack the UI tarball and check what it holds"]["run"]
    assert "npm pack --dry-run" in pack
    for allowed in ("dist/", "README.md", "LICENSE", "package.json"):
        assert allowed in pack
    assert "npm pkg delete devDependencies" in pack
    smoke = steps["Smoke-test the alias against the UI tarball"]["run"]
    assert "qgis-sdk-ui" in smoke and "@archont561/qgis-sdk-ui" in smoke
    dry = steps["Dry-run the publish"]
    assert dry["if"] == "needs.build.outputs.prerelease == 'true'"
    assert dry["run"].count("npm publish --dry-run --access public --tag next") == 2
    publish = steps["Publish to npm"]
    assert publish["if"] == "needs.build.outputs.prerelease == 'false'"
    assert "@archont561/qgis-sdk-ui@" in publish["run"]
    assert "--provenance" in publish["run"]
    alias = steps["Publish the alias to npm"]
    assert alias["if"] == "needs.build.outputs.prerelease == 'false'"
    assert '"qgis-sdk-ui@' in alias["run"]
    names = [step.get("name") for step in ui["steps"]]
    assert names.index("Publish to npm") < names.index("Publish the alias to npm")
    assert steps["Upload tarball artifact"]["with"]["name"] == "ui-npm-tgz"

    release = jobs["github-release"]
    assert "ui" in release["needs"]
    ui_gate = "needs.ui.result == 'success' || needs.ui.result == 'skipped'"
    assert ui_gate in release["if"]
    release_steps = {step.get("name"): step for step in release["steps"]}
    assert release_steps["Download UI tarball artifact"]["if"] == (
        "needs.build.outputs.ui == 'true'"
    )
    assert release_steps["Download UI tarball artifact"]["with"]["name"] == (
        "ui-npm-tgz"
    )

"""Release planning decisions and policy."""

import pytest
from qgis_sdk_release.commits import parse_log
from qgis_sdk_release.errors import QgisSdkReleaseVersionError
from qgis_sdk_release.plan import compute_plan, sort_tags


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
    # The rc bootstrap must not arm clean publishes: with only prerelease tags,
    # a landed feat/fix would otherwise tag a stable version and hit registries.
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
    assert "compare" not in plan.changelog  # no slug known


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

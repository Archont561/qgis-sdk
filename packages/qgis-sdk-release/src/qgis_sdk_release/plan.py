"""Release planning: pick the next version and decide whether to tag.

Policy (decided 2026-10-17 with the trusted-publishing gating):

* The push-to-main trigger never tags while no *stable* (non-prerelease) tag
  exists: bootstrapping the train and the first stable release are deliberate
  ``workflow_dispatch`` acts (TASK-27 territory). A prerelease suffix keeps
  iterating the rc train without arming clean publishes.
* Once a stable tag exists, every landed feat/fix continues the train
  automatically.
* ``release.yml`` publishes to PyPI/npm only for clean ``vX.Y.Z`` tags and
  dry-runs both registries for prereleases.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .changelog import render_changelog
from .commits import Commit, classify
from .errors import QgisSdkReleaseVersionError
from .semver import Version, tag_for_version, version_from_tag
from .versionrc import VersionConfig

__all__ = ["Plan", "compute_plan", "sort_tags"]

_RANK = {"patch": 0, "minor": 1, "major": 2}


def sort_tags(tags: Iterable[str]) -> tuple[str, ...]:
    """Sort v-prefixed SemVer tags newest first; unknown tags are ignored."""
    known: list[tuple[tuple, str]] = []
    for tag in tags:
        try:
            known.append((version_from_tag(tag).sort_key(), tag))
        except QgisSdkReleaseVersionError:
            continue
    known.sort(key=lambda item: item[0], reverse=True)
    return tuple(tag for _, tag in known)


@dataclass(frozen=True)
class Plan:
    """One planning decision, ready to serialize for the workflow."""

    trigger: str
    first: bool
    stable_exists: bool
    base_tag: str | None
    version: Version | None
    tag: str | None
    action: str  # "tag" | "skip"
    reason: str
    changelog: str

    def to_json(self) -> dict:
        """Return the workflow-facing payload (the changelog travels as a file)."""
        return {
            "trigger": self.trigger,
            "first": self.first,
            "stable_exists": self.stable_exists,
            "base_tag": self.base_tag,
            "version": str(self.version) if self.version else None,
            "tag": self.tag,
            "action": self.action,
            "reason": self.reason,
        }


def _bump_from(base: Version, commits: tuple[Commit, ...], config: VersionConfig):
    best: str | None = None
    for commit in commits:
        info = classify(commit, config)
        bump = info.bump
        if info.breaking:
            bump = "major" if (base.major > 0 or config.pre_major) else "minor"
        if bump is not None and (best is None or _RANK[bump] > _RANK[best]):
            best = bump
    return base.bump(best) if best else None


def compute_plan(
    trigger: str,
    tags: Iterable[str],
    commits: tuple[Commit, ...],
    config: VersionConfig,
    suffix: str = "",
    version_override: str | None = None,
    repo_slug: str | None = None,
) -> Plan:
    """Decide the next release action for the current history."""
    if trigger not in ("push", "dispatch"):
        raise QgisSdkReleaseVersionError(f"unknown trigger: {trigger!r}")
    ordered = sort_tags(tags)
    base_tag = ordered[0] if ordered else None
    first = base_tag is None
    stable_exists = any(not version_from_tag(tag).is_prerelease for tag in ordered)
    if version_override:
        version = Version.parse(version_override)
    elif first:
        version = config.initial_bump_version
    else:
        base = version_from_tag(base_tag)
        version = _bump_from(base, commits, config)
        if version is None:
            return Plan(
                trigger,
                first,
                stable_exists,
                base_tag,
                None,
                None,
                "skip",
                f"no release-worthy commits since {base_tag}",
                "",
            )
    if suffix:
        version = version.with_prerelease(suffix)
    tag = tag_for_version(version)
    if tag in ordered:
        return Plan(
            trigger,
            first,
            stable_exists,
            base_tag,
            version,
            tag,
            "skip",
            f"tag {tag} already exists",
            "",
        )
    if not stable_exists and trigger == "push":
        return Plan(
            trigger,
            first,
            stable_exists,
            base_tag,
            version,
            tag,
            "skip",
            "no stable tag exists yet; the first stable release is deliberate - "
            "run the autorelease workflow dispatch (a prerelease suffix "
            "continues the rc train without arming registry publishes)",
            "",
        )
    reason = (
        "bootstrap release" if first else f"release-worthy commits since {base_tag}"
    )
    changelog = render_changelog(version, commits, config, base_tag, repo_slug)
    return Plan(
        trigger,
        first,
        stable_exists,
        base_tag,
        version,
        tag,
        "tag",
        reason,
        changelog,
    )

"""Changelog rendering that follows the workspace ``.versionrc`` sections."""

from __future__ import annotations

from .commits import Commit, classify
from .semver import Version, tag_for_version
from .versionrc import VersionConfig

__all__ = ["render_changelog"]


def _entry(commit: Commit) -> str:
    return f"- {commit.subject} ({commit.sha[:7]})"


def render_changelog(
    version: Version,
    commits: tuple[Commit, ...],
    config: VersionConfig,
    base_tag: str | None = None,
    repo_slug: str | None = None,
) -> str:
    """Render the markdown changelog for one release.

    Sections and their order come from ``.versionrc``; hidden types are left
    out. ``linkCompare`` semantics are honoured with a trailing compare link
    whenever both the base tag and the repository slug are known.
    """
    tag = tag_for_version(version)
    lines = [config.header.rstrip("\n"), "", f"## {tag}", ""]
    breaking = [commit for commit in commits if classify(commit, config).breaking]
    if breaking:
        lines += ["### Breaking changes", ""]
        lines += [_entry(commit) for commit in breaking]
        lines.append("")
    grouped: dict[str, list[Commit]] = {section: [] for section in config.sections}
    for commit in commits:
        info = classify(commit, config)
        if info.hidden or info.section is None or info.section not in grouped:
            continue
        grouped[info.section].append(commit)
    for section in config.sections:
        entries = grouped[section]
        if not entries:
            continue
        lines += [f"### {section}", ""]
        lines += [_entry(commit) for commit in entries]
        lines.append("")
    if base_tag and repo_slug:
        lines.append(
            f"[{base_tag}...{tag}]: "
            f"https://github.com/{repo_slug}/compare/{base_tag}...{tag}"
        )
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"

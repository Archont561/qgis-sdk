from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from ._history import Commit, QgisSdkReleaseError, QgisSdkReleaseVersionError, classify
from ._version import (
    RANK,
    SCOPE_SHIPPED_BY,
    Draft,
    Version,
    VersionConfig,
    normalize_scope,
    parse_milestone_tag,
    parse_release_tag,
    tag_for_version,
    version_from_tag,
)


def parse_versionrc(text: str) -> VersionConfig:
    """Parse the ``.versionrc`` YAML subset this tool consumes."""
    draft = Draft()
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if len(raw_line) - len(raw_line.lstrip()) == 0:
            draft.close_rule()
            draft.read_top_level(stripped)
            continue
        if draft.top_key != "types":
            continue
        if stripped.startswith("- "):
            draft.open_rule()
            stripped = stripped[2:].strip()
            if not stripped:
                continue
        if draft.current is None:
            raise QgisSdkReleaseError(
                f"unexpected indented line in .versionrc: {raw_line!r}"
            )
        draft.add_field(stripped, raw_line)
    return draft.config()


def _entry(commit: Commit) -> str:
    return f"- {commit.subject} ({commit.sha[:7]})"


@dataclass(frozen=True, slots=True)
class ChangelogOptions:
    """What a rendered changelog needs beyond the release it describes."""

    base_tag: str | None = None
    repo_slug: str | None = None
    scope: str = "all"


def _changelog_entries(
    commits: tuple[Commit, ...], config: VersionConfig
) -> tuple[list[Commit], dict[str, list[Commit]]]:
    """The breaking commits and the sections every other commit belongs to."""
    breaking = [commit for commit in commits if classify(commit, config).breaking]
    grouped: dict[str, list[Commit]] = {section: [] for section in config.sections}
    for commit in commits:
        info = classify(commit, config)
        if info.hidden or info.section is None or info.section not in grouped:
            continue
        grouped[info.section].append(commit)
    return breaking, grouped


def render_changelog(
    version: Version,
    commits: tuple[Commit, ...],
    config: VersionConfig,
    options: ChangelogOptions | None = None,
) -> str:
    """Render the markdown changelog for one release."""
    options = options if options is not None else ChangelogOptions()
    tag = tag_for_version(version, scope=options.scope)
    lines = [config.header.rstrip("\n"), "", f"## {tag}", ""]
    breaking, grouped = _changelog_entries(commits, config)
    if breaking:
        lines += ["### Breaking changes", ""]
        lines += [_entry(commit) for commit in breaking]
        lines.append("")
    for section in config.sections:
        entries = grouped[section]
        if not entries:
            continue
        lines += [f"### {section}", ""]
        lines += [_entry(commit) for commit in entries]
        lines.append("")
    if options.base_tag and options.repo_slug:
        lines.append(
            f"[{options.base_tag}...{tag}]: "
            f"https://github.com/{options.repo_slug}/compare/{options.base_tag}...{tag}"
        )
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def plan_base_tag(ordered: Sequence[str], suffix: str = "") -> str | None:
    """The tag a release is computed and described from.

    ``ordered`` is :func:`sort_tags` output, newest first. A prerelease
    continues the candidate train from the newest tag of any kind. A stable
    release starts from the newest *stable* tag: the candidates after it were
    previews of the version being released, so its commits and its changelog
    reach back to what the last stable user has. With candidates only, the
    newest candidate is the base.
    """
    if not ordered:
        return None
    if suffix:
        return ordered[0]
    for tag in ordered:
        if not version_from_tag(tag).is_prerelease:
            return tag
    return ordered[0]


def sort_tags(tags: Iterable[str], scope: str = "all") -> tuple[str, ...]:
    """Sort release tags newest first, optionally for one scope only.

    A scoped sort keeps every tag that shipped the requested package: an
    unscoped ``v*`` tag releases both, while ``python-v*``/``ts-v*`` release one
    side. That is what makes each package's base tag its own.
    """
    wanted = normalize_scope(scope)
    known: list[tuple[tuple, str]] = []
    for tag in tags:
        try:
            tag_scope, version = parse_release_tag(tag)
        except QgisSdkReleaseVersionError:
            continue
        if wanted == "all":
            # The UI train never joins an alignment release, so its tags are
            # no base for one.
            if tag_scope == "ui":
                continue
        elif tag_scope not in SCOPE_SHIPPED_BY[wanted]:
            continue
        known.append((version.sort_key(), tag))
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
    action: str
    reason: str
    changelog: str
    scope: str = "all"

    def to_json(self) -> dict:
        payload = {
            "trigger": self.trigger,
            "first": self.first,
            "stable_exists": self.stable_exists,
            "base_tag": self.base_tag,
            "version": str(self.version) if self.version else None,
            "tag": self.tag,
            "action": self.action,
            "reason": self.reason,
        }
        if self.scope != "all":
            payload["scope"] = self.scope
        return payload


def _bump_from(base: Version, commits: tuple[Commit, ...], config: VersionConfig):
    best: str | None = None
    for commit in commits:
        info = classify(commit, config)
        bump = info.bump
        if info.breaking:
            bump = "major" if (base.major > 0 or config.pre_major) else "minor"
        if bump is not None and (best is None or RANK[bump] > RANK[best]):
            best = bump
    return base.bump(best) if best else None


def _resolve_forced_bump(
    bump: str, first: bool, base_tag: str | None, config: VersionConfig
) -> Version:
    kind = bump.strip().lower()
    if kind in RANK:
        if first or base_tag is None:
            return config.initial_bump_version
        return version_from_tag(base_tag).bump(kind)
    return Version.parse(bump.strip())


@dataclass(frozen=True, slots=True)
class PlanOptions:
    """The knobs a release plan can be computed with."""

    suffix: str = ""
    version_override: str | None = None
    repo_slug: str | None = None
    milestone_tag: str | None = None
    scope: str = "all"
    bump: str = ""


@dataclass(frozen=True, slots=True)
class _PlanFacts:
    """Everything a plan's outcomes share, whatever the decision is."""

    trigger: str
    first: bool
    stable_exists: bool
    base_tag: str | None
    scope: str
    ordered: tuple[str, ...]
    tags: tuple[str, ...]

    def skip(
        self,
        reason: str,
        *,
        scope: str | None = None,
        version: Version | None = None,
        tag: str | None = None,
    ) -> Plan:
        return Plan(
            self.trigger,
            self.first,
            self.stable_exists,
            self.base_tag,
            version,
            tag,
            "skip",
            reason,
            "",
            scope=scope if scope is not None else self.scope,
        )

    def tagged(self, version: Version, tag: str, reason: str, changelog: str) -> Plan:
        return Plan(
            self.trigger,
            self.first,
            self.stable_exists,
            self.base_tag,
            version,
            tag,
            "tag",
            reason,
            changelog,
            scope=self.scope,
        )


def _plan_scope(options: PlanOptions, milestone_info) -> str:
    """The package train this plan is about."""
    if options.scope.strip() and options.scope.strip().lower() not in ("all", "none"):
        return normalize_scope(options.scope)
    if milestone_info is not None:
        return milestone_info[0]
    return "all"


def plan_facts(trigger, tags, options: PlanOptions, milestone_info) -> _PlanFacts:
    """Sort the tags and record what is already true of this history."""
    scope = _plan_scope(options, milestone_info)
    ordered = tuple(sort_tags(tags, scope))
    base_tag = plan_base_tag(ordered, options.suffix)
    stable_exists = any(not version_from_tag(tag).is_prerelease for tag in ordered)
    return _PlanFacts(
        trigger,
        base_tag is None,
        stable_exists,
        base_tag,
        scope,
        ordered,
        tuple(tags),
    )


def plan_version(options, facts, scoped_commits, config, milestone_info):
    """The version this run would release, or ``None`` when nothing warrants it."""
    if options.version_override:
        return Version.parse(options.version_override)
    if options.bump.strip():
        return _resolve_forced_bump(options.bump, facts.first, facts.base_tag, config)
    if milestone_info is not None:
        return milestone_info[1]
    if facts.first:
        return config.initial_bump_version
    return _bump_from(version_from_tag(facts.base_tag), scoped_commits, config)


def early_skip(facts, version, tag, milestone_info) -> Plan | None:
    """The two histories that are already answered before any work is done."""
    if tag in facts.ordered or tag in set(facts.tags):
        return facts.skip(f"tag {tag} already exists", version=version, tag=tag)
    if not facts.stable_exists and facts.trigger == "push" and milestone_info is None:
        return facts.skip(
            "no stable tag exists yet; the first stable release is deliberate - "
            "run the autorelease workflow dispatch (a prerelease suffix "
            "continues the rc train without arming registry publishes)",
            version=version,
            tag=tag,
        )
    return None


def plan_reason(options: PlanOptions, facts: _PlanFacts, milestone_info) -> str:
    """Why this run decided to tag."""
    if milestone_info is not None:
        return f"milestone release from {options.milestone_tag}"
    if facts.first:
        return "bootstrap release"
    if options.bump.strip() or options.version_override:
        return f"forced release from {facts.base_tag}"
    return f"release-worthy commits since {facts.base_tag}"


def plan_milestone(trigger: str, options: PlanOptions):
    """Validate the trigger and resolve the optional milestone tag."""
    if trigger not in ("push", "dispatch", "milestone"):
        raise QgisSdkReleaseVersionError(f"unknown trigger: {trigger!r}")
    if not options.milestone_tag:
        return None
    info = parse_milestone_tag(options.milestone_tag)
    if info is None:
        raise QgisSdkReleaseVersionError(
            f"not a milestone tag: {options.milestone_tag!r}"
        )
    return info

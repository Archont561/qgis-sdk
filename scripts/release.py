#!/usr/bin/env python3
"""Release planning and publishing CLI for the QGIS SDK workspace.

Standalone, stdlib-only script replacing the ``packages/qgis-sdk-release``
package.  Repository paths are resolved from ``__file__`` so the script runs
from any working directory without a Pixi environment or ``PYTHONPATH``:

    python scripts/release.py plan --trigger dispatch --suffix rc.1 --json
    python scripts/release.py tag --tag v0.1.0 --message-file changelog.md --push
    python scripts/release.py stamp --version 0.1.0
    python scripts/release.py build-python
    python scripts/release.py checksums --out SHA256SUMS dist/pypi/*.whl npm/*.tgz
    python scripts/release.py github-release --tag v0.1.0 --body-file notes.md --asset dist/pypi/*.whl

Subcommands mirror the pixi ``release-*`` tasks: plan, classify, tag, stamp,
build-python, verify-python, checksums, github-release.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from urllib import request as urlrequest
from urllib.error import HTTPError
from urllib.parse import quote

_REPO_ROOT = Path(__file__).resolve().parent.parent
_PYPROJECT = _REPO_ROOT / "packages/qgis-sdk-python/pyproject.toml"
_RECIPE = _REPO_ROOT / "packages/qgis-sdk-python/recipe.yaml"
_BRIDGE_PACKAGE = _REPO_ROOT / "packages/qgis-sdk-typescript/package.json"
# The unscoped npm alias ``qgis-sdk`` re-exports ``@archont561/qgis-sdk`` at an
# exact pin (decision-33); it is stamped and verified with the bridge whenever
# it exists, and ignored when it does not.
_ALIAS_PACKAGE = _REPO_ROOT / "packages/qgis-sdk-alias/package.json"
_ALIAS_DEPENDENCY = "@archont561/qgis-sdk"
_PY_DECLARATIONS = _REPO_ROOT / "packages/qgis-sdk-python/src/qgis_sdk/declarations.py"
_TS_INDEX = _REPO_ROOT / "packages/qgis-sdk-typescript/src/index.ts"
_VERSIONRC = _REPO_ROOT / ".versionrc"

__all__ = [
    "QgisSdkReleaseError",
    "QgisSdkReleaseVersionError",
    "__version__",
]

__version__ = "0.1.0"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class QgisSdkReleaseError(Exception):
    """Base error for every qgis-sdk-release failure."""


class QgisSdkReleaseVersionError(QgisSdkReleaseError, ValueError):
    """Raised when a version, tag, or prerelease suffix cannot be parsed."""


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

Runner = Callable[[Sequence[str]], str]


def _default_runner(command: Sequence[str]) -> str:
    result = subprocess.run(list(command), check=True, capture_output=True, text=True)
    return result.stdout


def list_tags(runner: Runner | None = None) -> tuple[str, ...]:
    """List every git tag in the repository."""
    run = runner or _default_runner
    out = run(["git", "tag", "--list"])
    return tuple(line.strip() for line in out.splitlines() if line.strip())


def list_changed_files(
    revision_range: str | None = None, runner: Runner | None = None
) -> tuple[str, ...]:
    """List files changed in ``revision_range`` (or tracked files when omitted)."""
    run = runner or _default_runner
    command = (
        ["git", "diff", "--name-only", revision_range]
        if revision_range
        else ["git", "ls-files"]
    )
    out = run(command)
    return tuple(line.strip() for line in out.splitlines() if line.strip())


def detect_scope_from_files(files: Iterable[str]) -> str:
    """Classify changed paths into ``all``, ``python``, ``typescript``, or ``none``.

    Only shipped package paths count. Tooling, CI, backlog and root files are
    not artifacts of either package, so changing them must not manufacture a
    release. Before 2026-10-24 any other path forced ``all``, which meant a
    commit to ``scripts/release.py`` and the workflows planned an *alignment*
    release of both packages at a package minor - an act decision-25 reserves
    for a deliberate dispatch or milestone tag.
    """
    py = False
    ts = False
    for raw in files:
        path = raw.strip()
        if path.startswith(_PYTHON_PREFIXES):
            py = True
        elif path.startswith(_TYPESCRIPT_PREFIXES):
            ts = True
    if py and ts:
        return "all"
    if py:
        return "python"
    if ts:
        return "typescript"
    return "none"


LOG_FORMAT = "%H%x1f%s%x1f%b%x1e"
# Same record shape, but each commit is followed by its changed paths. ``\x1d``
# terminates the metadata so a multi-line body cannot be confused with the file
# list that ``--name-only`` appends.
FILES_LOG_FORMAT = "%x1e%H%x1f%s%x1f%b%x1d"


def log_commits(revision_range: str | None = None, runner: Runner | None = None) -> str:
    """Return raw ``git log`` output in the tool's record format."""
    run = runner or _default_runner
    command = ["git", "log", f"--format={LOG_FORMAT}", "--reverse"]
    if revision_range:
        command.append(revision_range)
    return run(command)


def log_commits_with_files(
    revision_range: str | None = None, runner: Runner | None = None
) -> str:
    """Return ``git log`` output that also lists each commit's changed paths."""
    run = runner or _default_runner
    command = ["git", "log", f"--format={FILES_LOG_FORMAT}", "--name-only", "--reverse"]
    if revision_range:
        command.append(revision_range)
    return run(command)


def create_tag(
    tag: str,
    message: str,
    push: bool,
    runner: Runner | None = None,
    remote: str = "origin",
) -> None:
    """Create an annotated tag and optionally push it to the remote."""
    run = runner or _default_runner
    run(
        [
            "git",
            "-c",
            "user.name=github-actions[bot]",
            "-c",
            "user.email=41898282+github-actions[bot]@users.noreply.github.com",
            "tag",
            "-a",
            tag,
            "-m",
            message,
        ]
    )
    if push:
        run(["git", "push", remote, f"refs/tags/{tag}"])


# ---------------------------------------------------------------------------
# Conventional-commit parsing and classification
# ---------------------------------------------------------------------------

_HEADER = re.compile(
    r"^(?P<type>[A-Za-z]+)(?:\((?P<scope>[^()]*)\))?(?P<breaking>!)?: "
    r"(?P<subject>.*)$"
)
_BREAKING_FOOTER = re.compile(r"^BREAKING[ -]CHANGE:", re.MULTILINE)
_BUMPS = {"major": "major", "minor": "minor", "patch": "patch"}
LOG_FIELD_COUNT = 3


@dataclass(frozen=True)
class Commit:
    """One parsed commit from the release range.

    ``files`` is empty when the log was read without ``--name-only``; an unknown
    file list is treated as "affects every scope" rather than as "affects none",
    so a caller cannot silently lose a commit by omitting it.
    """

    sha: str
    subject: str
    body: str
    files: tuple[str, ...] = ()


@dataclass(frozen=True)
class Classification:
    """How a commit affects the next version and the changelog."""

    bump: str | None
    section: str | None
    hidden: bool
    breaking: bool


def parse_log(raw: str) -> tuple[Commit, ...]:
    """Parse ``git log --format=$LOG_FORMAT`` output into commits."""
    commits: list[Commit] = []
    for chunk in raw.split("\x1e"):
        record = chunk.strip("\n")
        if not record.strip():
            continue
        parts = record.split("\x1f")
        if len(parts) != LOG_FIELD_COUNT:
            raise QgisSdkReleaseError(f"malformed git log record: {record!r}")
        commits.append(Commit(sha=parts[0].strip(), subject=parts[1], body=parts[2]))
    return tuple(commits)


def parse_log_with_files(raw: str) -> tuple[Commit, ...]:
    """Parse ``git log --format=$FILES_LOG_FORMAT --name-only`` output."""
    commits: list[Commit] = []
    for chunk in raw.split("\x1e"):
        record = chunk.strip("\n")
        if not record.strip():
            continue
        meta, separator, file_block = record.partition("\x1d")
        parts = meta.split("\x1f")
        if not separator or len(parts) != LOG_FIELD_COUNT:
            raise QgisSdkReleaseError(f"malformed git log record: {record!r}")
        files = tuple(line.strip() for line in file_block.splitlines() if line.strip())
        commits.append(
            Commit(
                sha=parts[0].strip(),
                subject=parts[1],
                body=parts[2].rstrip("\n"),
                files=files,
            )
        )
    return tuple(commits)


# The package directories were renamed on 2026-10-24 (PR #66). History before
# that commit - and the whole 0.4.0 Python range starts before it - lives under
# the old names, so both spellings count for scope detection.
_PYTHON_PREFIXES = ("packages/qgis-sdk-python/", "packages/qgis-sdk/")
# The alias ships with the bridge: a change to either is a TypeScript release.
_TYPESCRIPT_PREFIXES = (
    "packages/qgis-sdk-typescript/",
    "packages/qgis-sdk-alias/",
    "packages/qgis-sdk-bridge/",
)


def commit_packages(commit: Commit) -> tuple[bool, bool]:
    """Return ``(touches_python, touches_typescript)`` for one commit.

    Only the package directories count. Repository-wide files (CI, pixi.toml,
    the release tool, docs) change how a package is built or released but not
    what the package contains, so they must not be able to trigger a release on
    their own - that is what made a `feat!` in the release tool look like an npm
    minor.
    """
    if not commit.files:
        return True, True
    return (
        any(path.startswith(_PYTHON_PREFIXES) for path in commit.files),
        any(path.startswith(_TYPESCRIPT_PREFIXES) for path in commit.files),
    )


def commits_for_scope(commits: Iterable[Commit], scope: str) -> tuple[Commit, ...]:
    """Keep the commits that can move the given scope's version."""
    wanted = normalize_scope(scope)
    kept: list[Commit] = []
    for commit in commits:
        python, typescript = commit_packages(commit)
        if wanted == "all":
            relevant = python or typescript
        elif wanted == "python":
            relevant = python
        else:
            relevant = typescript
        if relevant:
            kept.append(commit)
    return tuple(kept)


def classify(commit: Commit, config: VersionConfig) -> Classification:
    """Classify one commit against the ``.versionrc`` rules."""
    match = _HEADER.match(commit.subject)
    if match is None:
        return Classification(None, None, True, False)
    breaking = bool(match.group("breaking")) or bool(
        _BREAKING_FOOTER.search(commit.body)
    )
    rule = config.rule_for(match.group("type").lower())
    if rule is None:
        return Classification(None, None, True, breaking)
    bump = _BUMPS.get(rule.increment.lower())
    return Classification(bump, rule.section or None, rule.hidden, breaking)


# ---------------------------------------------------------------------------
# SemVer
# ---------------------------------------------------------------------------

_SEMVER = re.compile(
    r"^(?P<major>0|[1-9][0-9]*)\.(?P<minor>0|[1-9][0-9]*)"
    r"\.(?P<patch>0|[1-9][0-9]*)(?:-(?P<pre>[0-9A-Za-z.-]+))?$"
)
_SUFFIX = re.compile(r"^[0-9A-Za-z.-]+$")


def _pre_key(pre: tuple[str, ...] | None) -> tuple:
    """Order prereleases before their release, numeric identifiers numerically."""
    if pre is None:
        return (1,)
    return (
        0,
        tuple((0, int(p), "") if p.isdigit() else (1, 0, p) for p in pre),
    )


@dataclass(frozen=True)
class Version:
    """One semantic version, optionally with a dot-separated prerelease."""

    major: int
    minor: int
    patch: int
    pre: tuple[str, ...] | None = None

    @classmethod
    def parse(cls, text: str) -> Version:
        """Parse a SemVer string such as ``0.1.0`` or ``0.1.0-rc.1``."""
        match = _SEMVER.match(text.strip())
        if match is None:
            raise QgisSdkReleaseVersionError(f"not a semantic version: {text!r}")
        pre = match.group("pre")
        return cls(
            major=int(match.group("major")),
            minor=int(match.group("minor")),
            patch=int(match.group("patch")),
            pre=tuple(pre.split(".")) if pre else None,
        )

    @property
    def is_prerelease(self) -> bool:
        """Whether this version carries a prerelease suffix."""
        return self.pre is not None

    def __str__(self) -> str:
        core = f"{self.major}.{self.minor}.{self.patch}"
        return f"{core}-{'.'.join(self.pre)}" if self.pre else core

    def sort_key(self) -> tuple:
        """Total ordering key matching the SemVer precedence rules."""
        return (self.major, self.minor, self.patch, _pre_key(self.pre))

    def bump(self, kind: str) -> Version:
        """Return the next release version for ``major``, ``minor``, or ``patch``."""
        if kind == "major":
            return Version(self.major + 1, 0, 0)
        if kind == "minor":
            return Version(self.major, self.minor + 1, 0)
        if kind == "patch":
            return Version(self.major, self.minor, self.patch + 1)
        raise QgisSdkReleaseVersionError(f"unknown bump kind: {kind!r}")

    def with_prerelease(self, suffix: str) -> Version:
        """Return this version's core with a validated prerelease suffix."""
        if not _SUFFIX.match(suffix):
            raise QgisSdkReleaseVersionError(
                f"not a valid prerelease suffix: {suffix!r}"
            )
        return Version(self.major, self.minor, self.patch, tuple(suffix.split(".")))

    def to_pep440(self) -> str:
        """Render as a PEP 440 version so hatchling accepts prereleases."""
        if self.pre is None:
            return str(self)
        text = "".join(self.pre).lower()
        for long_form, short_form in (("alpha", "a"), ("beta", "b")):
            text = text.replace(long_form, short_form)
        return f"{self.major}.{self.minor}.{self.patch}{text}"


_SCOPE_ALIASES = {
    "all": "all",
    "python": "python",
    "py": "python",
    "qgis-sdk": "python",
    "qgis-sdk-python": "python",
    "typescript": "typescript",
    "ts": "typescript",
    "bridge": "typescript",
    "qgis-sdk-typescript": "typescript",
    "@archont561/qgis-sdk": "typescript",
    # Legacy alias: the npm package was published as @archont561/qgis-sdk-bridge
    # through ts-v0.2.0 (decision-33).
    "qgis-sdk-bridge": "typescript",
    "bun": "typescript",
}
_SCOPE_PREFIXES = {
    "all": "v",
    "python": "python-v",
    "typescript": "ts-v",
}


def normalize_scope(scope: str) -> str:
    """Normalize a scope alias to ``all``, ``python``, or ``typescript``."""
    key = scope.strip().lower()
    if not key:
        return "all"
    if key not in _SCOPE_ALIASES:
        raise QgisSdkReleaseVersionError(f"unknown release scope: {scope!r}")
    return _SCOPE_ALIASES[key]


def parse_milestone_tag(tag: str) -> tuple[str, Version] | None:
    """Parse ``milestone-v*``, ``milestone/*``, or ``m-v*`` into ``(scope, Version)``.

    Returns ``None`` when ``tag`` is not a milestone tag, and raises
    :class:`QgisSdkReleaseVersionError` when a milestone prefix carries an
    invalid scope or version.
    """
    text = tag.strip()
    if text.startswith("milestone-"):
        rest = text[len("milestone-") :]
    elif text.startswith("milestone/"):
        rest = text[len("milestone/") :]
    elif text.startswith("m-v"):
        rest = text[len("m-") :]
    else:
        return None

    scope = "all"
    if "-v" in rest and not rest.startswith("v"):
        raw_scope, _, ver_part = rest.partition("-v")
        scope = normalize_scope(raw_scope)
        ver_text = ver_part
    elif rest.startswith("v"):
        ver_text = rest[1:]
    else:
        ver_text = rest
    return scope, Version.parse(ver_text)


def tag_for_version(version: Version, scope: str = "all") -> str:
    """Return the git tag carrying this version and optional scope."""
    canonical = normalize_scope(scope)
    prefix = _SCOPE_PREFIXES[canonical]
    return f"{prefix}{version}"


_SCOPED_TAG = re.compile(r"^(?P<scope>[A-Za-z0-9_+-]+)[/-]v(?P<ver>.+)$")


def parse_release_tag(tag: str) -> tuple[str, Version]:
    """Parse ``vX.Y.Z`` or ``<scope>[-/]vX.Y.Z`` into ``(scope, Version)``."""
    text = tag.strip()
    if text.startswith("v"):
        return "all", Version.parse(text[1:])
    match = _SCOPED_TAG.match(text)
    if match is None:
        raise QgisSdkReleaseVersionError(f"release tags are v-prefixed: {tag!r}")
    scope = normalize_scope(match.group("scope"))
    return scope, Version.parse(match.group("ver"))


def version_from_tag(tag: str) -> Version:
    """Parse a release git tag into a version."""
    _, version = parse_release_tag(tag)
    return version


# ---------------------------------------------------------------------------
# .versionrc reader
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TypeRule:
    """One conventional-commit type rule from ``.versionrc``."""

    type: str
    increment: str
    section: str
    hidden: bool


@dataclass(frozen=True)
class VersionConfig:
    """The release-relevant content of ``.versionrc``."""

    rules: tuple[TypeRule, ...]
    initial_bump_version: Version
    pre_major: bool
    header: str

    def rule_for(self, commit_type: str) -> TypeRule | None:
        """Return the rule for a commit type, or None when unconfigured."""
        for rule in self.rules:
            if rule.type == commit_type:
                return rule
        return None

    @property
    def sections(self) -> tuple[str, ...]:
        """Visible changelog section names in declaration order."""
        seen: list[str] = []
        for rule in self.rules:
            if not rule.hidden and rule.section and rule.section not in seen:
                seen.append(rule.section)
        return tuple(seen)


_MIN_QUOTED_LENGTH = 2


def _scalar(raw: str) -> str:
    text = raw.strip()
    if len(text) >= _MIN_QUOTED_LENGTH and text[0] == text[-1] and text[0] in "\"'":
        inner = text[1:-1]
        if text[0] == '"':
            inner = inner.replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\")
        return inner
    return text


def _rule_from(item: dict[str, str]) -> TypeRule:
    if "type" not in item:
        raise QgisSdkReleaseError(f".versionrc type entry is missing 'type': {item}")
    return TypeRule(
        type=item["type"],
        increment=item.get("increment", "None"),
        section=item.get("section", ""),
        hidden=item.get("hidden", "false") == "true",
    )


class _Draft:
    """State machine for parsing .versionrc lines."""

    def __init__(self) -> None:
        self.rules: list[TypeRule] = []
        self.current: dict[str, str] | None = None
        self.top_key: str = ""
        self.initial: str = "0.1.0"
        self.pre_major: bool = False
        self.header: str = "# Changelog\n"

    def close_rule(self) -> None:
        if self.current is not None:
            self.rules.append(_rule_from(self.current))
            self.current = None

    def read_top_level(self, line: str) -> None:
        key, _, value = line.partition(":")
        self.top_key = key.strip()
        if self.top_key == "initialBumpVersion":
            self.initial = _scalar(value)
        elif self.top_key == "preMajor":
            self.pre_major = _scalar(value) == "true"
        elif self.top_key == "header":
            self.header = _scalar(value)

    def open_rule(self) -> None:
        self.close_rule()
        self.current = {}

    def add_field(self, line: str, raw_line: str) -> None:
        key, sep, value = line.partition(":")
        if not sep:
            raise QgisSdkReleaseError(
                f"unexpected list entry in .versionrc: {raw_line!r}"
            )
        if self.current is not None:
            self.current[key.strip()] = _scalar(value)

    def config(self) -> VersionConfig:
        self.close_rule()
        return VersionConfig(
            tuple(self.rules),
            Version.parse(self.initial),
            self.pre_major,
            self.header,
        )


def parse_versionrc(text: str) -> VersionConfig:
    """Parse the ``.versionrc`` YAML subset this tool consumes."""
    draft = _Draft()
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


# ---------------------------------------------------------------------------
# Changelog rendering
# ---------------------------------------------------------------------------


def _entry(commit: Commit) -> str:
    return f"- {commit.subject} ({commit.sha[:7]})"


def render_changelog(
    version: Version,
    commits: tuple[Commit, ...],
    config: VersionConfig,
    base_tag: str | None = None,
    repo_slug: str | None = None,
    scope: str = "all",
) -> str:
    """Render the markdown changelog for one release."""
    tag = tag_for_version(version, scope=scope)
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


# ---------------------------------------------------------------------------
# Release planning
# ---------------------------------------------------------------------------

_RANK = {"patch": 0, "minor": 1, "major": 2}


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
        if wanted != "all" and tag_scope not in ("all", wanted):
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
        if bump is not None and (best is None or _RANK[bump] > _RANK[best]):
            best = bump
    return base.bump(best) if best else None


def _resolve_forced_bump(
    bump: str, first: bool, base_tag: str | None, config: VersionConfig
) -> Version:
    kind = bump.strip().lower()
    if kind in _RANK:
        if first or base_tag is None:
            return config.initial_bump_version
        return version_from_tag(base_tag).bump(kind)
    return Version.parse(bump.strip())


def compute_plan(
    trigger: str,
    tags: Iterable[str],
    commits: tuple[Commit, ...],
    config: VersionConfig,
    suffix: str = "",
    version_override: str | None = None,
    repo_slug: str | None = None,
    milestone_tag: str | None = None,
    scope: str = "all",
    bump: str = "",
) -> Plan:
    """Decide the next release action for the current history."""
    if trigger not in ("push", "dispatch", "milestone"):
        raise QgisSdkReleaseVersionError(f"unknown trigger: {trigger!r}")
    milestone_info = parse_milestone_tag(milestone_tag) if milestone_tag else None
    if milestone_tag and milestone_info is None:
        raise QgisSdkReleaseVersionError(f"not a milestone tag: {milestone_tag!r}")
    if scope.strip() and scope.strip().lower() not in ("all", "none"):
        resolved_scope = normalize_scope(scope)
    elif milestone_info is not None:
        resolved_scope = milestone_info[0]
    else:
        resolved_scope = "all"
    ordered = sort_tags(tags, resolved_scope)
    base_tag = ordered[0] if ordered else None
    first = base_tag is None
    stable_exists = any(not version_from_tag(tag).is_prerelease for tag in ordered)
    if scope.strip().lower() == "none":
        return Plan(
            trigger,
            first,
            stable_exists,
            base_tag,
            None,
            None,
            "skip",
            "no release-worthy changes for scope",
            "",
            scope="none",
        )
    # Each package only owes a version for the commits that touch it (or the
    # repository-wide files both depend on). Decisions are per package, so a
    # bridge-only change cannot move the Python minor and vice versa.
    scoped_commits = commits_for_scope(commits, resolved_scope)

    if version_override:
        version = Version.parse(version_override)
    elif bump.strip():
        version = _resolve_forced_bump(bump, first, base_tag, config)
    elif milestone_info is not None:
        _, version = milestone_info
    elif first:
        version = config.initial_bump_version
    else:
        base = version_from_tag(base_tag)
        version = _bump_from(base, scoped_commits, config)
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
                scope=resolved_scope,
            )
    if suffix:
        version = version.with_prerelease(suffix)
    tag = tag_for_version(version, scope=resolved_scope)
    if tag in ordered or tag in set(tags):
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
            scope=resolved_scope,
        )
    if not stable_exists and trigger == "push" and milestone_info is None:
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
            scope=resolved_scope,
        )
    if milestone_info is not None:
        reason = f"milestone release from {milestone_tag}"
    elif first:
        reason = "bootstrap release"
    elif bump.strip() or version_override:
        reason = f"forced release from {base_tag}"
    else:
        reason = f"release-worthy commits since {base_tag}"
    changelog = render_changelog(
        version, scoped_commits, config, base_tag, repo_slug, scope=resolved_scope
    )
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
        scope=resolved_scope,
    )


# ---------------------------------------------------------------------------
# Artifacts
# ---------------------------------------------------------------------------

ArtifactRunner = Callable[[Sequence[str]], None]


def _default_artifact_runner(command: Sequence[str]) -> None:
    subprocess.run(list(command), check=True)


def build_wheel(
    package_dir: str | Path,
    outdir: str | Path,
    runner: ArtifactRunner | None = None,
) -> None:
    """Build one wheel with python-build, without build isolation."""
    run = runner or _default_artifact_runner
    run(
        [
            sys.executable,
            "-m",
            "build",
            "--wheel",
            "--no-isolation",
            "--outdir",
            str(outdir),
            str(package_dir),
        ]
    )


def twine_check(wheels: Iterable[Path], runner: ArtifactRunner | None = None) -> None:
    """Validate wheel metadata and readme rendering with twine."""
    run = runner or _default_artifact_runner
    paths = [str(wheel) for wheel in wheels]
    if not paths:
        raise QgisSdkReleaseError("twine check needs at least one wheel")
    run(["twine", "check", *paths])


def checksums(paths: Iterable[Path]) -> list[tuple[str, str]]:
    """Return ``(basename, sha256)`` pairs sorted by path."""
    entries: list[tuple[str, str]] = []
    for path in sorted(paths, key=str):
        target = Path(path)
        if not target.is_file():
            raise QgisSdkReleaseError(f"not a file: {target}")
        entries.append((target.name, hashlib.sha256(target.read_bytes()).hexdigest()))
    return entries


def write_checksums(out_path: Path, entries: Iterable[tuple[str, str]]) -> None:
    """Write a ``sha256sum -c`` compatible SHA256SUMS file.

    The parent directory is created: a TypeScript-only release downloads no
    wheel, so ``dist/`` does not exist before this file is written there.
    """
    lines = "".join(f"{digest}  {name}\n" for name, digest in entries)
    target = Path(out_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(lines, encoding="utf-8")


# ---------------------------------------------------------------------------
# Version stamping
# ---------------------------------------------------------------------------

_VERSION_LINE = re.compile(r'(?m)^version = "[^"]*"$')
_RECIPE_VERSION_LINE = re.compile(r'(?m)^(\s*version:\s*)"[^"]*"$')


def stamp_pyproject(text: str, version: Version) -> str:
    """Rewrite the first top-level ``version`` line with the PEP 440 form."""
    stamped, count = _VERSION_LINE.subn(
        f'version = "{version.to_pep440()}"', text, count=1
    )
    if count == 0:
        raise QgisSdkReleaseError("no top-level version line found in pyproject.toml")
    return stamped


def stamp_recipe(text: str, version: Version) -> str:
    """Rewrite the first quoted ``version:`` line in recipe.yaml with the PEP 440 form."""
    stamped, count = _RECIPE_VERSION_LINE.subn(
        rf'\g<1>"{version.to_pep440()}"', text, count=1
    )
    if count == 0:
        raise QgisSdkReleaseError("no quoted version line found in recipe.yaml")
    return stamped


def stamp_package_json(text: str, version: Version) -> str:
    """Rewrite ``version`` in a package.json, preserving tab indentation."""
    data = json.loads(text)
    data["version"] = str(version)
    return json.dumps(data, indent="\t") + "\n"


def stamp_alias_package_json(
    text: str, version: Version, dependency: str = _ALIAS_DEPENDENCY
) -> str:
    """Stamp the alias manifest: its own version and its exact pin on the bridge.

    The alias has no surface of its own, so the two numbers are one number; a
    pin that floats (``^``) or lags would let ``qgis-sdk@X`` install a bridge
    that is not ``@archont561/qgis-sdk@X``.
    """
    data = json.loads(text)
    dependencies = data.get("dependencies")
    if not isinstance(dependencies, dict) or dependency not in dependencies:
        raise QgisSdkReleaseError(
            f"alias package.json does not depend on {dependency}; "
            "it cannot re-export what it does not install"
        )
    data["version"] = str(version)
    dependencies[dependency] = str(version)
    return json.dumps(data, indent="\t") + "\n"


_PEP440 = re.compile(r"^(?P<core>\d+\.\d+\.\d+)(?:(?P<pre>a|b|rc)(?P<num>\d+))?$")
# ``to_pep440`` shortens these; the inverse has to expand them back, or
# ``0.2.0-rc.1`` and ``0.2.0-alpha.1`` read back as ``rc.1``/``a.1`` and stop
# comparing equal to the tag that produced them.
_PEP440_PRE = {"a": "alpha", "b": "beta", "rc": "rc"}


def version_from_pep440(text: str) -> Version:
    """Turn a PEP 440 rendering back into the SemVer form the tool works in.

    ``stamp`` writes ``0.2.0-rc.1`` into package.json as ``0.2.0rc1`` for
    hatchling; comparing the two manifests therefore needs the inverse.
    """
    match = _PEP440.fullmatch(text.strip())
    if match is None:
        raise QgisSdkReleaseVersionError(f"not a PEP 440 version: {text!r}")
    pre = match.group("pre")
    if pre is None:
        return Version.parse(match.group("core"))
    long_form = _PEP440_PRE.get(pre, pre)
    return Version.parse(f"{match.group('core')}-{long_form}.{match.group('num')}")


def read_pyproject_version(text: str) -> Version:
    """Read the stamped version out of ``pyproject.toml``."""
    match = _VERSION_LINE.search(text)
    if match is None:
        raise QgisSdkReleaseError("no top-level version line found in pyproject.toml")
    return version_from_pep440(match.group(0).split('"')[1])


def read_recipe_version(text: str) -> Version:
    """Read the stamped version out of ``recipe.yaml``."""
    match = _RECIPE_VERSION_LINE.search(text)
    if match is None:
        raise QgisSdkReleaseError("no quoted version line found in recipe.yaml")
    return version_from_pep440(match.group(0).rsplit('"', 2)[1])


def read_package_json_version(text: str) -> Version:
    """Read the stamped version out of the bridge ``package.json``."""
    return Version.parse(str(json.loads(text)["version"]))


def read_alias_versions(
    text: str, dependency: str = _ALIAS_DEPENDENCY
) -> tuple[Version, Version]:
    """Return ``(alias version, pinned bridge version)`` from the alias manifest.

    The pin has to be an exact version: ``Version.parse`` refuses ranges, which
    is the point.
    """
    data = json.loads(text)
    dependencies = data.get("dependencies")
    if not isinstance(dependencies, dict) or dependency not in dependencies:
        raise QgisSdkReleaseError(f"alias package.json does not depend on {dependency}")
    return (
        Version.parse(str(data["version"])),
        Version.parse(str(dependencies[dependency])),
    )


@dataclass(frozen=True)
class ManifestVersions:
    """The version each released manifest currently carries."""

    pyproject: Version
    package_json: Version
    recipe: Version | None = None
    alias: Version | None = None
    alias_dependency: Version | None = None

    def items(self) -> tuple[tuple[str, Version], ...]:
        """Return the labelled versions that exist, in reporting order."""
        found = [
            ("pyproject.toml", self.pyproject),
            ("package.json", self.package_json),
        ]
        if self.recipe is not None:
            found.append(("recipe.yaml", self.recipe))
        if self.alias is not None:
            found.append(("alias package.json", self.alias))
        if self.alias_dependency is not None:
            found.append(("alias dependency", self.alias_dependency))
        return tuple(found)

    def agreed(self) -> Version:
        """Return the version every manifest carries, or name the disagreement.

        Manifests only have to agree *within* a release scope: ``pyproject.toml``
        and ``recipe.yaml`` ship the Python package, ``package.json`` ships the
        bridge, and the two packages version independently.
        """
        return require_one_version(self.items())

    def to_json(self) -> dict:
        """Serialize the versions for diagnostics."""
        return {name: str(version) for name, version in self.items()}


def manifest_versions(
    pyproject_text: str,
    package_text: str,
    recipe_text: str | None = None,
    alias_text: str | None = None,
) -> ManifestVersions:
    """Read all released manifests and return what each one carries."""
    alias, alias_dependency = (
        read_alias_versions(alias_text) if alias_text is not None else (None, None)
    )
    return ManifestVersions(
        pyproject=read_pyproject_version(pyproject_text),
        package_json=read_package_json_version(package_text),
        recipe=read_recipe_version(recipe_text) if recipe_text is not None else None,
        alias=alias,
        alias_dependency=alias_dependency,
    )


_PYTHON_MANIFESTS = ("pyproject.toml", "recipe.yaml")
_TYPESCRIPT_MANIFESTS = ("package.json", "alias package.json", "alias dependency")


def scoped_manifest_versions(
    versions: ManifestVersions, scope: str
) -> tuple[tuple[str, Version], ...]:
    """Return only the manifests a release scope is allowed to stamp.

    The Python package owns ``pyproject.toml`` and the conda ``recipe.yaml``;
    the bridge owns ``package.json``. An unscoped ``v*`` release owns all three,
    which is what an alignment release is.
    """
    wanted = normalize_scope(scope)
    if wanted == "all":
        return versions.items()
    allowed = _PYTHON_MANIFESTS if wanted == "python" else _TYPESCRIPT_MANIFESTS
    return tuple(
        (name, version) for name, version in versions.items() if name in allowed
    )


def require_one_version(items: Sequence[tuple[str, Version]]) -> Version:
    """Return the one version ``items`` carries, or name every disagreement."""
    if not items:
        raise QgisSdkReleaseVersionError("no released manifest belongs to this scope")
    versions = {version for _, version in items}
    if len(versions) > 1:
        listed = ", ".join(f"{name}={version}" for name, version in items)
        raise QgisSdkReleaseVersionError(
            f"released manifests disagree: {listed}; one version is required per scope"
        )
    return items[0][1]


@dataclass(frozen=True)
class ContractVersions:
    """The plugin-description contract version each language declares.

    Package versions are independent, so the pair is held together by this
    number instead: the bridge mirrors the Python wire contract, and a release
    that moves one side without the other must at least agree on what crosses
    the boundary.
    """

    python: int
    typescript: int

    def agreed(self) -> int:
        """Return the shared contract version, or refuse the pair."""
        if self.python != self.typescript:
            raise QgisSdkReleaseVersionError(
                "plugin description contract versions disagree: "
                f"python={self.python}, typescript={self.typescript}"
            )
        return self.python

    def to_json(self) -> dict:
        """Serialize the contract versions for diagnostics."""
        return {"python": self.python, "typescript": self.typescript}


_PY_CONTRACT_VERSION = re.compile(
    r"(?m)^PLUGIN_DESCRIPTION_SCHEMA_VERSION\s*=\s*(\d+)\s*$"
)
_TS_CONTRACT_VERSION = re.compile(r"PLUGIN_DESCRIPTION_SCHEMA_VERSION[^=\n]*=\s*(\d+)")


def read_python_contract_version(text: str) -> int:
    """Read ``PLUGIN_DESCRIPTION_SCHEMA_VERSION`` from the Python declarations."""
    match = _PY_CONTRACT_VERSION.search(text)
    if match is None:
        raise QgisSdkReleaseError(
            "no PLUGIN_DESCRIPTION_SCHEMA_VERSION in the Python declarations"
        )
    return int(match.group(1))


def read_typescript_contract_version(text: str) -> int:
    """Read ``PLUGIN_DESCRIPTION_SCHEMA_VERSION`` from the bridge index."""
    match = _TS_CONTRACT_VERSION.search(text)
    if match is None:
        raise QgisSdkReleaseError(
            "no PLUGIN_DESCRIPTION_SCHEMA_VERSION in the bridge index"
        )
    return int(match.group(1))


def contract_versions(python_text: str, typescript_text: str) -> ContractVersions:
    """Read both declarations of the plugin description contract version."""
    return ContractVersions(
        python=read_python_contract_version(python_text),
        typescript=read_typescript_contract_version(typescript_text),
    )


# ---------------------------------------------------------------------------
# GitHub REST
# ---------------------------------------------------------------------------

Opener = Callable[[urlrequest.Request], object]


def _default_opener(req: urlrequest.Request) -> object:
    return urlrequest.urlopen(req)


def _request(
    url: str,
    token: str,
    payload: dict | None = None,
    data: bytes | None = None,
    content_type: str | None = None,
) -> urlrequest.Request:
    body = json.dumps(payload).encode() if payload is not None else data
    req = urlrequest.Request(url, data=body, method="POST" if body else "GET")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    if payload is not None:
        req.add_header("Content-Type", "application/json")
    elif content_type:
        req.add_header("Content-Type", content_type)
    return req


def _read_json(opener: Opener, req: urlrequest.Request, what: str) -> dict:
    try:
        with opener(req) as response:  # type: ignore[attr-defined]
            return json.load(response)
    except HTTPError as error:
        detail = error.read().decode(errors="replace")[:400]
        raise QgisSdkReleaseError(f"{what} failed ({error.code}): {detail}") from error


def create_release(
    slug: str,
    token: str,
    tag: str,
    name: str,
    body: str,
    prerelease: bool,
    opener: Opener | None = None,
) -> dict:
    """Create one GitHub Release and return the API response."""
    open_it = opener or _default_opener
    payload = {
        "tag_name": tag,
        "name": name,
        "body": body,
        "draft": False,
        "prerelease": prerelease,
        "make_latest": "false" if prerelease else "true",
    }
    req = _request(f"https://api.github.com/repos/{slug}/releases", token, payload)
    return _read_json(open_it, req, "GitHub release creation")


def get_release_by_tag(
    slug: str,
    token: str,
    tag: str,
    opener: Opener | None = None,
) -> dict:
    """Fetch an existing GitHub Release by tag name."""
    open_it = opener or _default_opener
    req = _request(
        f"https://api.github.com/repos/{slug}/releases/tags/{quote(tag)}", token
    )
    return _read_json(open_it, req, f"GitHub release lookup for {tag}")


def delete_release_asset(
    slug: str,
    token: str,
    asset_id: int,
    opener: Opener | None = None,
) -> None:
    """Delete an existing release asset before re-uploading."""
    open_it = opener or _default_opener
    req = _request(
        f"https://api.github.com/repos/{slug}/releases/assets/{asset_id}", token
    )
    req.method = "DELETE"
    try:
        with open_it(req):  # type: ignore[attr-defined]
            pass
    except HTTPError as error:
        detail = error.read().decode(errors="replace")[:400]
        raise QgisSdkReleaseError(
            f"asset deletion {asset_id} failed ({error.code}): {detail}"
        ) from error


def upload_asset(
    upload_url: str,
    token: str,
    path: Path,
    opener: Opener | None = None,
) -> dict:
    """Upload one release asset through the release's upload URL template."""
    open_it = opener or _default_opener
    target = Path(path)
    base = upload_url.split("{")[0]
    req = _request(
        f"{base}?name={quote(target.name)}",
        token,
        data=target.read_bytes(),
        content_type="application/octet-stream",
    )
    return _read_json(open_it, req, f"asset upload for {target.name}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

_github_output_env = "GITHUB_OUTPUT"
_step_summary_env = "GITHUB_STEP_SUMMARY"


def _github_output() -> Path | None:
    raw = os.environ.get(_github_output_env)
    return Path(raw) if raw else None


def _write_output(pairs: dict[str, str]) -> None:
    path = _github_output()
    if path is None:
        return
    with path.open("a", encoding="utf-8") as handle:
        for key, value in pairs.items():
            handle.write(f"{key}={value}\n")


def _step_summary(line: str) -> None:
    raw = os.environ.get(_step_summary_env)
    if raw:
        with Path(raw).open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")


def resolve_dry_run(trigger: str, requested: bool) -> tuple[bool, str]:
    """Decide whether this plan may cut a tag, and say why when it may not.

    A branch push never tags. The train still plans and gates the candidate on
    every merge, but cutting the tag stays an explicit act - a dispatch or a
    milestone tag - so a merge cannot consume a version, and a package minor
    (which is what a ``feat!`` landing on ``packages/qgis-sdk-python`` derives) cannot
    bypass its release gate. On 2026-10-24 a merge planned ``v0.2.0`` for both
    packages this way and the only thing that stopped it was luck.
    """
    if trigger == "push" and not requested:
        return (
            True,
            "dry run: a branch push never tags, cut the release with a dispatch "
            + "or a milestone tag",
        )
    return requested, ""


def _cmd_plan(args: argparse.Namespace) -> int:
    config = parse_versionrc(Path(args.config).read_text(encoding="utf-8"))
    tags = list_tags()
    requested_scope = (getattr(args, "scope", "") or "").strip()
    milestone_tag = getattr(args, "milestone_tag", "") or ""
    if requested_scope.lower() == "auto":
        newest = sort_tags(tags)
        auto_range = f"{newest[0]}..HEAD" if newest else None
        requested_scope = detect_scope_from_files(list_changed_files(auto_range))
    if requested_scope and requested_scope.lower() not in ("all", "none"):
        plan_scope = normalize_scope(requested_scope)
    elif milestone_tag:
        milestone_info = parse_milestone_tag(milestone_tag)
        plan_scope = milestone_info[0] if milestone_info is not None else "all"
    else:
        plan_scope = "all"
    ordered = sort_tags(tags, plan_scope)
    base_tag = ordered[0] if ordered else None
    revision_range = f"{base_tag}..HEAD" if base_tag else None
    commits = parse_log_with_files(log_commits_with_files(revision_range))
    dry_run_raw = str(getattr(args, "dry_run", "false")).strip().lower()
    dry_run, dry_run_note = resolve_dry_run(
        args.trigger, dry_run_raw in ("true", "1", "yes")
    )
    plan = compute_plan(
        trigger=args.trigger,
        tags=tags,
        commits=commits,
        config=config,
        suffix=args.suffix,
        version_override=args.version_override or None,
        repo_slug=os.environ.get("GITHUB_REPOSITORY"),
        milestone_tag=milestone_tag or None,
        scope=requested_scope or "all",
        bump=getattr(args, "bump", "") or "",
    )
    if dry_run_note:
        plan = replace(plan, reason=f"{plan.reason} ({dry_run_note})")
    changelog_file = ""
    if plan.changelog:
        target = (
            Path(os.environ.get("RUNNER_TEMP", ".")) / "qgis-sdk-release-changelog.md"
        )
        target.write_text(plan.changelog, encoding="utf-8")
        changelog_file = str(target.resolve())
    _write_output(
        {
            "action": plan.action,
            "tag": plan.tag or "",
            "version": str(plan.version) if plan.version else "",
            "prerelease": (
                "true" if plan.version and plan.version.is_prerelease else "false"
            ),
            "scope": plan.scope,
            "python": "true" if plan.scope in ("all", "python") else "false",
            "typescript": "true" if plan.scope in ("all", "typescript") else "false",
            "dry_run": "true" if dry_run else "false",
            "reason": plan.reason,
            "changelog_file": changelog_file,
        }
    )
    if args.json:
        payload = plan.to_json()
        payload["scope"] = plan.scope
        payload["dry_run"] = dry_run
        payload["changelog_file"] = changelog_file
        print(json.dumps(payload, indent=2))
    else:
        print(
            f"action={plan.action} scope={plan.scope} "
            f"tag={plan.tag or '-'} reason={plan.reason}"
        )
    return 0


def _cmd_classify(args: argparse.Namespace) -> int:
    scope, version = parse_release_tag(args.tag)
    outputs = {
        "version": str(version),
        "pep440": version.to_pep440(),
        "prerelease": "true" if version.is_prerelease else "false",
    }
    if getattr(args, "scoped", False):
        outputs.update(
            {
                "scope": scope,
                "python": "true" if scope in ("all", "python") else "false",
                "typescript": "true" if scope in ("all", "typescript") else "false",
                "tag_name": args.tag,
            }
        )
    _write_output(outputs)
    payload: dict[str, object] = {
        "tag": args.tag,
        "version": str(version),
        "pep440": version.to_pep440(),
        "prerelease": version.is_prerelease,
    }
    if getattr(args, "scoped", False):
        payload.update(
            {
                "scope": scope,
                "python": scope in ("all", "python"),
                "typescript": scope in ("all", "typescript"),
            }
        )
    print(json.dumps(payload, indent=2))
    return 0


def _cmd_tag(args: argparse.Namespace) -> int:
    tag_name = args.tag_name if hasattr(args, "tag_name") else args.tag
    if args.message_file:
        message = Path(args.message_file).read_text(encoding="utf-8")
    elif args.message:
        message = args.message
    else:
        raise QgisSdkReleaseError("tag needs --message or --message-file")
    version_from_tag(tag_name)
    create_tag(tag_name, message, push=args.push)
    where = "and pushed it" if args.push else "locally"
    print(f"created tag {tag_name} {where}")
    return 0


def _cmd_stamp(args: argparse.Namespace) -> int:
    version = Version.parse(args.version)
    scope = normalize_scope(getattr(args, "scope", "all") or "all")
    stamped: list[str] = []
    if scope in ("all", "python"):
        pyproject_text = _PYPROJECT.read_text(encoding="utf-8")
        _PYPROJECT.write_text(
            stamp_pyproject(pyproject_text, version), encoding="utf-8"
        )
        stamped.append(f"{_PYPROJECT} (PEP 440: {version.to_pep440()})")
        if _RECIPE.is_file():
            recipe_text = _RECIPE.read_text(encoding="utf-8")
            _RECIPE.write_text(stamp_recipe(recipe_text, version), encoding="utf-8")
            stamped.append(str(_RECIPE))
    if scope in ("all", "typescript"):
        package_text = _BRIDGE_PACKAGE.read_text(encoding="utf-8")
        _BRIDGE_PACKAGE.write_text(
            stamp_package_json(package_text, version), encoding="utf-8"
        )
        stamped.append(str(_BRIDGE_PACKAGE))
        if _ALIAS_PACKAGE.is_file():
            alias_text = _ALIAS_PACKAGE.read_text(encoding="utf-8")
            _ALIAS_PACKAGE.write_text(
                stamp_alias_package_json(alias_text, version), encoding="utf-8"
            )
            stamped.append(f"{_ALIAS_PACKAGE} (and its pin on {_ALIAS_DEPENDENCY})")
    print(f"stamped {version} for scope {scope} into {', '.join(stamped)}")
    return 0


def _cmd_verify_versions(args: argparse.Namespace) -> int:
    scope_raw = (getattr(args, "scope", "") or "").strip()
    expected_raw = (getattr(args, "version", "") or "").strip()
    recipe_text = _RECIPE.read_text(encoding="utf-8") if _RECIPE.is_file() else None
    alias_text = (
        _ALIAS_PACKAGE.read_text(encoding="utf-8") if _ALIAS_PACKAGE.is_file() else None
    )
    versions = manifest_versions(
        _PYPROJECT.read_text(encoding="utf-8"),
        _BRIDGE_PACKAGE.read_text(encoding="utf-8"),
        recipe_text,
        alias_text,
    )
    contract = contract_versions(
        _PY_DECLARATIONS.read_text(encoding="utf-8"),
        _TS_INDEX.read_text(encoding="utf-8"),
    )
    shared_contract = contract.agreed()
    wanted_scopes = (
        (normalize_scope(scope_raw),) if scope_raw else ("python", "typescript")
    )
    expected = Version.parse(expected_raw) if expected_raw else None
    if expected is not None and len(wanted_scopes) > 1:
        raise QgisSdkReleaseVersionError(
            "--version needs --scope: one release targets one package"
        )
    reported: dict[str, dict[str, object]] = {}
    for scope in wanted_scopes:
        scoped = scoped_manifest_versions(versions, scope)
        version = require_one_version(scoped)
        if expected is not None and version != expected:
            listed = ", ".join(f"{name}={value}" for name, value in scoped)
            raise QgisSdkReleaseVersionError(
                f"scope {scope} is releasing {expected}, but its manifests carry "
                f"{listed}; run stamp --scope {scope} --version {expected} first"
            )
        reported[scope] = {
            "version": str(version),
            "manifests": {name: str(value) for name, value in scoped},
        }
    if getattr(args, "json", False):
        print(
            json.dumps(
                {
                    "scopes": reported,
                    "contract": contract.to_json(),
                },
                indent=2,
            )
        )
        return 0
    for scope in wanted_scopes:
        entry = reported[scope]
        listed = ", ".join(entry["manifests"])
        print(
            f"released manifests for scope {scope} agree on {entry['version']}: {listed}"
        )
    print(
        f"plugin description contract version {shared_contract} agrees across "
        "the Python declarations and the TypeScript bridge"
    )
    return 0


def _cmd_build_python(args: argparse.Namespace) -> int:
    outdir = Path(args.outdir)
    build_wheel(args.package, outdir)
    wheels = sorted(outdir.glob("*.whl"))
    if not wheels:
        raise QgisSdkReleaseError(f"no wheel appeared in {outdir}")
    twine_check(wheels)
    print(f"built and checked {[wheel.name for wheel in wheels]}")
    return 0


def _cmd_verify_python(args: argparse.Namespace) -> int:
    wheels = sorted(Path(args.dist).glob("*.whl"))
    if not wheels:
        raise QgisSdkReleaseError(f"no wheels under {args.dist}")
    twine_check(wheels)
    print(f"twine check passed for {[wheel.name for wheel in wheels]}")
    return 0


def _cmd_checksums(args: argparse.Namespace) -> int:
    entries = checksums([Path(item) for item in args.paths])
    write_checksums(Path(args.out), entries)
    for name, digest in entries:
        print(f"{digest}  {name}")
    return 0


def _cmd_github_release(args: argparse.Namespace) -> int:
    slug = args.repo or os.environ.get("GITHUB_REPOSITORY")
    token = args.token or os.environ.get("GITHUB_TOKEN")
    if not slug or not token:
        raise QgisSdkReleaseError(
            "github-release needs --repo/GITHUB_REPOSITORY and --token/GITHUB_TOKEN"
        )
    version = version_from_tag(args.tag)
    body = (
        Path(args.body_file).read_text(encoding="utf-8")
        if args.body_file
        else f"Release {args.tag}"
    )
    try:
        release = create_release(
            slug, token, args.tag, args.tag, body, version.is_prerelease
        )
    except QgisSdkReleaseError as exc:
        if "already_exists" not in str(exc):
            raise
        release = get_release_by_tag(slug, token, args.tag)
    upload_url = release.get("upload_url")
    if not upload_url:
        raise QgisSdkReleaseError(f"release response lacked upload_url: {release}")
    existing_assets = {
        item.get("name"): item.get("id")
        for item in release.get("assets", ())
        if isinstance(item, dict) and item.get("name") and item.get("id")
    }
    for asset in args.asset:
        asset_path = Path(asset)
        existing_id = existing_assets.get(asset_path.name)
        if existing_id is not None:
            delete_release_asset(slug, token, int(existing_id))
        upload_asset(upload_url, token, asset_path)
        print(f"uploaded {asset_path.name}")
    html_url = release.get("html_url", "")
    print(f"release {args.tag}: {html_url}")
    _step_summary(
        f"- GitHub Release [{args.tag}]({html_url}) with {len(args.asset)} asset(s)"
    )
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="release",
        description="Release planning and publishing CLI for the QGIS SDK workspace.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan", help="decide the next release action")
    plan.add_argument(
        "--trigger", choices=("push", "dispatch", "milestone"), default="push"
    )
    plan.add_argument("--config", default=str(_VERSIONRC))
    plan.add_argument("--suffix", default="")
    plan.add_argument("--version-override", default="")
    plan.add_argument("--scope", default="")
    plan.add_argument("--bump", default="")
    plan.add_argument("--milestone-tag", default="")
    plan.add_argument("--dry-run", default="false")
    plan.add_argument("--json", action="store_true")
    plan.set_defaults(handler=_cmd_plan)

    classify = sub.add_parser("classify", help="classify one release tag")
    classify.add_argument("--tag", required=True)
    classify.add_argument("--scoped", action="store_true")
    classify.set_defaults(handler=_cmd_classify)

    tag = sub.add_parser("tag", help="create an annotated release tag")
    tag.add_argument("--tag", required=True, dest="tag_name", metavar="TAG")
    tag.add_argument("--message")
    tag.add_argument("--message-file")
    tag.add_argument("--push", action="store_true")
    tag.set_defaults(handler=_cmd_tag)

    stamp = sub.add_parser("stamp", help="stamp versions into manifests")
    stamp.add_argument("--version", required=True)
    stamp.add_argument(
        "--scope",
        default="all",
        help="which package to stamp: all, python, or typescript",
    )
    stamp.set_defaults(handler=_cmd_stamp)

    versions = sub.add_parser(
        "verify-versions",
        help="require one version per released scope and one shared contract version",
    )
    versions.add_argument(
        "--scope",
        default="",
        help=(
            "which package is being released: all, python, or typescript; "
            "omit to check every scope on its own"
        ),
    )
    versions.add_argument(
        "--version",
        default="",
        help="version this scope is releasing; the scoped manifests must carry it",
    )
    versions.add_argument("--json", action="store_true", help="machine-readable output")
    versions.set_defaults(handler=_cmd_verify_versions)

    build = sub.add_parser("build-python", help="build and check the wheel")
    build.add_argument("--package", default="packages/qgis-sdk-python")
    build.add_argument("--outdir", default="dist/pypi")
    build.set_defaults(handler=_cmd_build_python)

    verify = sub.add_parser("verify-python", help="twine check built wheels")
    verify.add_argument("--dist", default="dist/pypi")
    verify.set_defaults(handler=_cmd_verify_python)

    sums = sub.add_parser("checksums", help="write a SHA256SUMS file")
    sums.add_argument("--out", default="SHA256SUMS")
    sums.add_argument("paths", nargs="+")
    sums.set_defaults(handler=_cmd_checksums)

    release = sub.add_parser("github-release", help="publish a GitHub Release")
    release.add_argument("--tag", required=True)
    release.add_argument("--body-file")
    release.add_argument("--asset", nargs="+", default=[])
    release.add_argument("--repo")
    release.add_argument("--token")
    release.set_defaults(handler=_cmd_github_release)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Run one subcommand; errors exit 1 with a single-line message."""
    args = _build_parser().parse_args(argv)
    try:
        return int(args.handler(args))
    except QgisSdkReleaseError as error:
        print(f"error: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

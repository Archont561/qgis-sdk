"""Conventional-commit parsing and classification for git log output."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .errors import QgisSdkReleaseError
from .versionrc import VersionConfig

__all__ = ["LOG_FORMAT", "Classification", "Commit", "classify", "parse_log"]

# Unit/record separators keep subject and body splittable without quoting.
LOG_FORMAT = "%H%x1f%s%x1f%b%x1e"

_HEADER = re.compile(
    r"^(?P<type>[A-Za-z]+)(?:\((?P<scope>[^()]*)\))?(?P<breaking>!)?: "
    r"(?P<subject>.*)$"
)
_BREAKING_FOOTER = re.compile(r"^BREAKING[ -]CHANGE:", re.MULTILINE)

_BUMPS = {"major": "major", "minor": "minor", "patch": "patch"}


@dataclass(frozen=True)
class Commit:
    """One parsed commit from the release range."""

    sha: str
    subject: str
    body: str


@dataclass(frozen=True)
class Classification:
    """How a commit affects the next version and the changelog."""

    bump: str | None  # "major" | "minor" | "patch" | None
    section: str | None
    hidden: bool
    breaking: bool


def parse_log(raw: str) -> tuple[Commit, ...]:
    """Parse ``git log --format=$LOG_FORMAT`` output into commits."""
    commits: list[Commit] = []
    for record in raw.split("\x1e"):
        record = record.strip("\n")
        if not record.strip():
            continue
        parts = record.split("\x1f")
        if len(parts) != 3:
            raise QgisSdkReleaseError(f"malformed git log record: {record!r}")
        commits.append(Commit(sha=parts[0].strip(), subject=parts[1], body=parts[2]))
    return tuple(commits)


def classify(commit: Commit, config: VersionConfig) -> Classification:
    """Classify one commit against the ``.versionrc`` rules.

    Non-conventional subjects (merge commits, free text) are hidden and never
    bump. Breaking markers are reported so planning can escalate the bump for
    the concrete base version; the escalation itself lives in ``plan``.
    """
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

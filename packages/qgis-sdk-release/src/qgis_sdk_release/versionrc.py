"""Reader for the workspace ``.versionrc`` conventional-changelog config.

Only the subset the release train consumes is understood: the ``types`` rule
list plus the ``initialBumpVersion``, ``preMajor``, and ``header`` scalars.
Every other key is data for other tools and is ignored on purpose.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .errors import QgisSdkReleaseError
from .semver import Version

__all__ = ["TypeRule", "VersionConfig", "parse_versionrc"]


@dataclass(frozen=True)
class TypeRule:
    """One conventional-commit type rule from ``.versionrc``."""

    type: str
    increment: str  # "Major" | "Minor" | "Patch" | "None"
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


# A quoted scalar needs an opening and a closing mark to be a quote pair at all.
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


@dataclass
class _Draft:
    """What the line loop accumulates, so parsing stays one decision per line.

    The subset is small enough to read as a state machine: an unindented line either
    opens a section or sets a top-level value, and an indented line belongs to a
    ``types`` entry or is ignored with the section it fell under.
    """

    rules: list[TypeRule] = field(default_factory=list)
    current: dict[str, str] | None = None
    top_key: str = ""
    initial: str = "0.1.0"
    pre_major: bool = False
    header: str = "# Changelog\n"

    def close_rule(self) -> None:
        """Finish the entry being read, if any, so the next line starts fresh."""
        if self.current is not None:
            self.rules.append(_rule_from(self.current))
            self.current = None

    def read_top_level(self, line: str) -> None:
        """Record an unindented ``key: value`` and remember the section it opened."""
        key, _, value = line.partition(":")
        self.top_key = key.strip()
        if self.top_key == "initialBumpVersion":
            self.initial = _scalar(value)
        elif self.top_key == "preMajor":
            self.pre_major = _scalar(value) == "true"
        elif self.top_key == "header":
            self.header = _scalar(value)

    def open_rule(self) -> None:
        """Begin a ``types`` list entry."""
        self.close_rule()
        self.current = {}

    def add_field(self, line: str, raw_line: str) -> None:
        """Put one ``key: value`` pair on the entry being read."""
        key, sep, value = line.partition(":")
        if not sep:
            raise QgisSdkReleaseError(
                f"unexpected list entry in .versionrc: {raw_line!r}"
            )
        if self.current is not None:
            self.current[key.strip()] = _scalar(value)

    def config(self) -> VersionConfig:
        """Return the finished configuration, with the last entry closed."""
        self.close_rule()
        return VersionConfig(
            tuple(self.rules), Version.parse(self.initial), self.pre_major, self.header
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
            continue  # List or nested data under a key this tool ignores.
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

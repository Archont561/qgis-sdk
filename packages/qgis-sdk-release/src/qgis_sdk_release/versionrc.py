"""Reader for the workspace ``.versionrc`` conventional-changelog config.

Only the subset the release train consumes is understood: the ``types`` rule
list plus the ``initialBumpVersion``, ``preMajor``, and ``header`` scalars.
Every other key is data for other tools and is ignored on purpose.
"""

from __future__ import annotations

from dataclasses import dataclass

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


def _scalar(raw: str) -> str:
    text = raw.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
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


def parse_versionrc(text: str) -> VersionConfig:
    """Parse the ``.versionrc`` YAML subset this tool consumes."""
    rules: list[TypeRule] = []
    current: dict[str, str] | None = None
    top_key = ""
    initial = "0.1.0"
    pre_major = False
    header = "# Changelog\n"
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip())
        if indent == 0:
            if current is not None:
                rules.append(_rule_from(current))
                current = None
            key, _, value = stripped.partition(":")
            top_key = key.strip()
            if top_key == "initialBumpVersion":
                initial = _scalar(value)
            elif top_key == "preMajor":
                pre_major = _scalar(value) == "true"
            elif top_key == "header":
                header = _scalar(value)
            continue
        if top_key != "types":
            continue  # List or nested data under a key this tool ignores.
        line = stripped
        if line.startswith("- "):
            if current is not None:
                rules.append(_rule_from(current))
            current = {}
            line = line[2:].strip()
            if not line:
                continue
        if current is None:
            raise QgisSdkReleaseError(
                f"unexpected indented line in .versionrc: {raw_line!r}"
            )
        key, sep, value = line.partition(":")
        if not sep:
            raise QgisSdkReleaseError(
                f"unexpected list entry in .versionrc: {raw_line!r}"
            )
        current[key.strip()] = _scalar(value)
    if current is not None:
        rules.append(_rule_from(current))
    return VersionConfig(tuple(rules), Version.parse(initial), pre_major, header)

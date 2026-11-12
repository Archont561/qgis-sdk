from __future__ import annotations

import re
from dataclasses import dataclass

from ._history import (
    SEMVER,
    SUFFIX,
    QgisSdkReleaseError,
    QgisSdkReleaseVersionError,
    pre_key,
)

RANK = {"patch": 0, "minor": 1, "major": 2}


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
        match = SEMVER.match(text.strip())
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
        return (self.major, self.minor, self.patch, pre_key(self.pre))

    def bump(self, kind: str) -> Version:
        """Return the next release version for ``major``, ``minor``, or ``patch``.

        A prerelease is a preview of its core: when the core already is the
        release ``kind`` asks for (``0.5.0-rc.1`` for a minor or a patch,
        ``1.0.0-rc.1`` for a major), the next release is that core, not the one
        after it. Otherwise the core moves as usual.
        """
        if kind not in RANK:
            raise QgisSdkReleaseVersionError(f"unknown bump kind: {kind!r}")
        core = Version(self.major, self.minor, self.patch)
        if self.is_prerelease and (
            kind == "patch"
            or (kind == "minor" and self.patch == 0)
            or (kind == "major" and self.minor == 0 and self.patch == 0)
        ):
            return core
        if kind == "major":
            return Version(self.major + 1, 0, 0)
        if kind == "minor":
            return Version(self.major, self.minor + 1, 0)
        return Version(self.major, self.minor, self.patch + 1)

    def with_prerelease(self, suffix: str) -> Version:
        """Return this version's core with a validated prerelease suffix."""
        if not SUFFIX.match(suffix):
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
    "kit": "python",
    # The two Python distributions that may release on their own (decision-35,
    # decision-36). A `python-v*` release ships them together with the kit.
    "runtime": "runtime",
    "qgis-sdk-runtime": "runtime",
    "tools": "tools",
    "qgis-sdk-tools": "tools",
    "typescript": "typescript",
    "ts": "typescript",
    "bridge": "typescript",
    "qgis-sdk-typescript": "typescript",
    "@archont561/qgis-sdk": "typescript",
    # Legacy alias: the npm package was published as @archont561/qgis-sdk-bridge
    # through ts-v0.2.0 (decision-33).
    "qgis-sdk-bridge": "typescript",
    "bun": "typescript",
    # The web components (decision-47): their own train, never in ``all``.
    "ui": "ui",
    "qgis-sdk-ui": "ui",
    "@archont561/qgis-sdk-ui": "ui",
}
_SCOPE_PREFIXES = {
    "all": "v",
    "python": "python-v",
    "runtime": "runtime-v",
    "tools": "tools-v",
    "typescript": "ts-v",
    "ui": "ui-v",
}
SCOPE_SHIPPED_BY = {
    "all": ("all",),
    "python": ("all", "python"),
    "runtime": ("all", "python", "runtime"),
    "tools": ("all", "python", "tools"),
    "typescript": ("all", "typescript"),
    "ui": ("ui",),
}


def scope_ships(scope: str) -> dict[str, bool]:
    """Which artifacts a release of ``scope`` publishes, as workflow flags.

    ``python`` means "at least one Python distribution"; ``kit``, ``runtime``
    and ``tools`` name the distributions so the workflow can run one publish
    step per wheel (TASK-57).
    """
    canonical = normalize_scope(scope)
    kit = canonical in ("all", "python")
    return {
        "python": canonical in ("all", "python", "runtime", "tools"),
        "kit": kit,
        "runtime": kit or canonical == "runtime",
        "tools": kit or canonical == "tools",
        "typescript": canonical in ("all", "typescript"),
        "ui": canonical == "ui",
    }


def normalize_scope(scope: str) -> str:
    """Normalize a scope alias to ``all``, ``python``, ``runtime``, ``tools``, ``typescript`` or ``ui``."""
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


class Draft:
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

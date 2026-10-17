"""Minimal SemVer parsing, ordering, bumping, and PEP 440 mapping."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .errors import QgisSdkReleaseVersionError

__all__ = ["Version", "tag_for_version", "version_from_tag"]

_SEMVER = re.compile(
    r"^(?P<major>0|[1-9][0-9]*)\.(?P<minor>0|[1-9][0-9]*)"
    r"\.(?P<patch>0|[1-9][0-9]*)(?:-(?P<pre>[0-9A-Za-z.-]+))?$"
)
_SUFFIX = re.compile(r"^[0-9A-Za-z.-]+$")


def _pre_key(pre: tuple[str, ...] | None) -> tuple:
    """Order prereleases before their release, numeric identifiers numerically."""
    if pre is None:
        return (1,)
    return (0, tuple((0, int(p), "") if p.isdigit() else (1, 0, p) for p in pre))


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


def tag_for_version(version: Version) -> str:
    """Return the git tag carrying this version."""
    return f"v{version}"


def version_from_tag(tag: str) -> Version:
    """Parse a ``v``-prefixed git tag into a version."""
    if not tag.startswith("v"):
        raise QgisSdkReleaseVersionError(f"release tags are v-prefixed: {tag!r}")
    return Version.parse(tag[1:])

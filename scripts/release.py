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
from dataclasses import dataclass
from pathlib import Path
from urllib import request as urlrequest
from urllib.error import HTTPError
from urllib.parse import quote

_REPO_ROOT = Path(__file__).resolve().parent.parent
_PYPROJECT = _REPO_ROOT / "packages/qgis-sdk/pyproject.toml"
_BRIDGE_PACKAGE = _REPO_ROOT / "packages/qgis-sdk-bridge/package.json"
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
    """List every ``v``-prefixed tag in the repository."""
    run = runner or _default_runner
    out = run(["git", "tag", "--list", "v*"])
    return tuple(line.strip() for line in out.splitlines() if line.strip())


LOG_FORMAT = "%H%x1f%s%x1f%b%x1e"


def log_commits(revision_range: str | None = None, runner: Runner | None = None) -> str:
    """Return raw ``git log`` output in the tool's record format."""
    run = runner or _default_runner
    command = ["git", "log", f"--format={LOG_FORMAT}", "--reverse"]
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
    run(["git", "tag", "-a", tag, "-m", message])
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
    """One parsed commit from the release range."""

    sha: str
    subject: str
    body: str


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


def tag_for_version(version: Version) -> str:
    """Return the git tag carrying this version."""
    return f"v{version}"


def version_from_tag(tag: str) -> Version:
    """Parse a ``v``-prefixed git tag into a version."""
    if not tag.startswith("v"):
        raise QgisSdkReleaseVersionError(f"release tags are v-prefixed: {tag!r}")
    return Version.parse(tag[1:])


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
) -> str:
    """Render the markdown changelog for one release."""
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


# ---------------------------------------------------------------------------
# Release planning
# ---------------------------------------------------------------------------

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
    action: str
    reason: str
    changelog: str

    def to_json(self) -> dict:
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
    """Write a ``sha256sum -c`` compatible SHA256SUMS file."""
    lines = "".join(f"{digest}  {name}\n" for name, digest in entries)
    Path(out_path).write_text(lines, encoding="utf-8")


# ---------------------------------------------------------------------------
# Version stamping
# ---------------------------------------------------------------------------

_VERSION_LINE = re.compile(r'(?m)^version = "[^"]*"$')


def stamp_pyproject(text: str, version: Version) -> str:
    """Rewrite the first top-level ``version`` line with the PEP 440 form."""
    stamped, count = _VERSION_LINE.subn(
        f'version = "{version.to_pep440()}"', text, count=1
    )
    if count == 0:
        raise QgisSdkReleaseError("no top-level version line found in pyproject.toml")
    return stamped


def stamp_package_json(text: str, version: Version) -> str:
    """Rewrite ``version`` in a package.json, preserving tab indentation."""
    data = json.loads(text)
    data["version"] = str(version)
    return json.dumps(data, indent="\t") + "\n"


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


def _cmd_plan(args: argparse.Namespace) -> int:
    config = parse_versionrc(Path(args.config).read_text(encoding="utf-8"))
    tags = list_tags()
    ordered = sort_tags(tags)
    base_tag = ordered[0] if ordered else None
    raw = log_commits(f"{base_tag}..HEAD" if base_tag else None)
    plan = compute_plan(
        trigger=args.trigger,
        tags=tags,
        commits=parse_log(raw),
        config=config,
        suffix=args.suffix,
        version_override=args.version_override or None,
        repo_slug=os.environ.get("GITHUB_REPOSITORY"),
    )
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
            "reason": plan.reason,
            "changelog_file": changelog_file,
        }
    )
    if args.json:
        payload = plan.to_json()
        payload["changelog_file"] = changelog_file
        print(json.dumps(payload, indent=2))
    else:
        print(f"action={plan.action} tag={plan.tag or '-'} reason={plan.reason}")
    return 0


def _cmd_classify(args: argparse.Namespace) -> int:
    version = version_from_tag(args.tag)
    _write_output(
        {
            "version": str(version),
            "pep440": version.to_pep440(),
            "prerelease": "true" if version.is_prerelease else "false",
        }
    )
    print(
        json.dumps(
            {
                "tag": args.tag,
                "version": str(version),
                "pep440": version.to_pep440(),
                "prerelease": version.is_prerelease,
            },
            indent=2,
        )
    )
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
    pyproject_text = _PYPROJECT.read_text(encoding="utf-8")
    _PYPROJECT.write_text(stamp_pyproject(pyproject_text, version), encoding="utf-8")
    package_text = _BRIDGE_PACKAGE.read_text(encoding="utf-8")
    _BRIDGE_PACKAGE.write_text(
        stamp_package_json(package_text, version), encoding="utf-8"
    )
    print(
        f"stamped {version} into {_PYPROJECT} "
        f"(PEP 440: {version.to_pep440()}) and {_BRIDGE_PACKAGE}"
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
    release = create_release(
        slug, token, args.tag, args.tag, body, version.is_prerelease
    )
    upload_url = release.get("upload_url")
    if not upload_url:
        raise QgisSdkReleaseError(f"release response lacked upload_url: {release}")
    for asset in args.asset:
        upload_asset(upload_url, token, Path(asset))
        print(f"uploaded {Path(asset).name}")
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
    plan.add_argument("--trigger", choices=("push", "dispatch"), default="push")
    plan.add_argument("--config", default=str(_VERSIONRC))
    plan.add_argument("--suffix", default="")
    plan.add_argument("--version-override", default="")
    plan.add_argument("--json", action="store_true")
    plan.set_defaults(handler=_cmd_plan)

    classify = sub.add_parser("classify", help="classify one release tag")
    classify.add_argument("--tag", required=True)
    classify.set_defaults(handler=_cmd_classify)

    tag = sub.add_parser("tag", help="create an annotated release tag")
    tag.add_argument("--tag", required=True, dest="tag_name", metavar="TAG")
    tag.add_argument("--message")
    tag.add_argument("--message-file")
    tag.add_argument("--push", action="store_true")
    tag.set_defaults(handler=_cmd_tag)

    stamp = sub.add_parser("stamp", help="stamp versions into manifests")
    stamp.add_argument("--version", required=True)
    stamp.set_defaults(handler=_cmd_stamp)

    build = sub.add_parser("build-python", help="build and check the wheel")
    build.add_argument("--package", default="packages/qgis-sdk")
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

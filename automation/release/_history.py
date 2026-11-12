"""Release planning and publishing CLI for the QGIS SDK workspace.

Standalone, stdlib-only script replacing the ``packages/qgis-sdk-release``
package.  Repository paths are resolved from ``__file__`` so the script runs
from any working directory without a Pixi environment or ``PYTHONPATH``:

    python -m automation.release plan --trigger dispatch --suffix rc.1 --json
    python -m automation.release tag --tag v0.1.0 --message-file changelog.md --push
    python -m automation.release stamp --version 0.1.0
    python -m automation.release build-python
    python -m automation.release checksums --out SHA256SUMS dist/pypi/*.whl npm/*.tgz
    python -m automation.release github-release --tag v0.1.0 --body-file notes.md --asset dist/pypi/*.whl

Subcommands mirror the pixi ``release-*`` tasks: plan, classify, tag, stamp,
build-python, verify-python, checksums, github-release.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from automation.release._version import VersionConfig

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PYPROJECT = REPO_ROOT / "packages/qgis-sdk-python/pyproject.toml"
RUNTIME_PYPROJECT = REPO_ROOT / "packages/qgis-sdk-runtime/pyproject.toml"
TOOLS_PYPROJECT = REPO_ROOT / "packages/qgis-sdk-tools/pyproject.toml"
_PYTHON_PACKAGE_DIRS = (
    "packages/qgis-sdk-runtime",
    "packages/qgis-sdk-tools",
    "packages/qgis-sdk-python",
)
RECIPE = REPO_ROOT / "packages/qgis-sdk-python/recipe.yaml"
BRIDGE_PACKAGE = REPO_ROOT / "packages/qgis-sdk-typescript/package.json"
ALIAS_PACKAGE = REPO_ROOT / "packages/qgis-sdk-alias/package.json"
ALIAS_DEPENDENCY = "@archont561/qgis-sdk"
UI_PACKAGE = REPO_ROOT / "packages/qgis-sdk-ui/package.json"
UI_PEER = "@archont561/qgis-sdk"
UI_ALIAS_PACKAGE = REPO_ROOT / "packages/qgis-sdk-ui-alias/package.json"
UI_ALIAS_DEPENDENCY = "@archont561/qgis-sdk-ui"
SCAFFOLD_WEB = (
    REPO_ROOT / "packages/qgis-sdk-tools/src/qgis_sdk_tools/scaffold/web/_plan.py"
)
EXAMPLE_PYPROJECTS = (
    REPO_ROOT / "examples/simple/pyproject.toml",
    REPO_ROOT / "examples/server/pyproject.toml",
)
PY_DECLARATIONS = (
    REPO_ROOT / "packages/qgis-sdk-runtime/src/qgis_sdk/declarations/_contract.py"
)
TS_DECLARATIONS = REPO_ROOT / "packages/qgis-sdk-typescript/src/declarations.ts"
VERSIONRC = REPO_ROOT / ".versionrc"
__version__ = "0.1.0"


class QgisSdkReleaseError(Exception):
    """Base error for every qgis-sdk-release failure."""


class QgisSdkReleaseVersionError(QgisSdkReleaseError, ValueError):
    """Raised when a version, tag, or prerelease suffix cannot be parsed."""


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
    """Classify changed paths into ``all``, ``python``, ``typescript``, ``ui`` or ``none``.

    ``ui`` is only detected when the web components are the one package that
    changed: the UI train is deliberate (``--scope ui``), and an alignment
    release never carries it.

    Only shipped package paths count. Tooling, CI, backlog and root files are
    not artifacts of either package, so changing them must not manufacture a
    release. Before 2026-10-24 any other path forced ``all``, which meant a
    commit to ``automation/release.py`` and the workflows planned an *alignment*
    release of both packages at a package minor - an act decision-25 reserves
    for a deliberate dispatch or milestone tag.
    """
    return _scope_from_flags(*_changed_package_flags(files))


def _changed_package_flags(files: Iterable[str]) -> tuple[bool, bool, bool]:
    """Which shipped packages the changed paths belong to."""
    py = ts = ui = False
    for raw in files:
        path = raw.strip()
        if path.startswith(_PYTHON_PREFIXES):
            py = True
        elif path.startswith(_TYPESCRIPT_PREFIXES):
            ts = True
        elif path.startswith(_UI_PREFIXES):
            ui = True
    return py, ts, ui


def _scope_from_flags(py: bool, ts: bool, ui: bool) -> str:
    """Combine the package flags into one release scope."""
    if py and ts:
        return "all"
    if py:
        return "python"
    if ts:
        return "typescript"
    if ui:
        return "ui"
    return "none"


LOG_FORMAT = "%H%x1f%s%x1f%b%x1e"
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


_RUNTIME_PREFIXES = ("packages/qgis-sdk-runtime/",)
_TOOLS_PREFIXES = ("packages/qgis-sdk-tools/",)
_PYTHON_PREFIXES = (
    "packages/qgis-sdk-python/",
    *_RUNTIME_PREFIXES,
    *_TOOLS_PREFIXES,
    "packages/qgis-sdk/",
)
_TYPESCRIPT_PREFIXES = (
    "packages/qgis-sdk-typescript/",
    "packages/qgis-sdk-alias/",
    "packages/qgis-sdk-bridge/",
)
_UI_PREFIXES = ("packages/qgis-sdk-ui/", "packages/qgis-sdk-ui-alias/")


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


def commit_scopes(commit: Commit) -> frozenset[str]:
    """Return the release scopes one commit can move.

    ``python`` is the whole Python kit; ``runtime`` and ``tools`` are the two
    distributions that may release on their own (decision-35). A commit with
    no file list is treated as touching everything, like :func:`commit_packages`.
    """
    if not commit.files:
        return frozenset({"python", "runtime", "tools", "typescript", "ui"})
    scopes = set()
    for path in commit.files:
        if path.startswith(_RUNTIME_PREFIXES):
            scopes.update({"python", "runtime"})
        elif path.startswith(_TOOLS_PREFIXES):
            scopes.update({"python", "tools"})
        elif path.startswith(_PYTHON_PREFIXES):
            scopes.add("python")
        elif path.startswith(_TYPESCRIPT_PREFIXES):
            scopes.add("typescript")
        elif path.startswith(_UI_PREFIXES):
            scopes.add("ui")
    return frozenset(scopes)


def commits_for_scope(commits: Iterable[Commit], scope: str) -> tuple[Commit, ...]:
    """Keep the commits that can move the given scope's version."""
    from ._version import normalize_scope

    wanted = normalize_scope(scope)
    kept: list[Commit] = []
    for commit in commits:
        scopes = commit_scopes(commit)
        relevant = bool(scopes - {"ui"}) if wanted == "all" else wanted in scopes
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


SEMVER = re.compile(
    r"^(?P<major>0|[1-9][0-9]*)\.(?P<minor>0|[1-9][0-9]*)"
    r"\.(?P<patch>0|[1-9][0-9]*)(?:-(?P<pre>[0-9A-Za-z.-]+))?$"
)
SUFFIX = re.compile(r"^[0-9A-Za-z.-]+$")


def pre_key(pre: tuple[str, ...] | None) -> tuple:
    """Order prereleases before their release, numeric identifiers numerically."""
    if pre is None:
        return (1,)
    return (
        0,
        tuple((0, int(p), "") if p.isdigit() else (1, 0, p) for p in pre),
    )

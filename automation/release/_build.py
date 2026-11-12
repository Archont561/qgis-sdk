from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path

from ._changelog import (
    ChangelogOptions,
    Plan,
    PlanOptions,
    early_skip,
    plan_facts,
    plan_milestone,
    plan_reason,
    plan_version,
    render_changelog,
)
from ._history import (
    ALIAS_DEPENDENCY,
    REPO_ROOT,
    Commit,
    QgisSdkReleaseError,
    QgisSdkReleaseVersionError,
    commits_for_scope,
)
from ._version import Version, VersionConfig, tag_for_version


def compute_plan(
    trigger: str,
    tags: Iterable[str],
    commits: tuple[Commit, ...],
    config: VersionConfig,
    options: PlanOptions | None = None,
) -> Plan:
    """Decide the next release action for the current history."""
    options = options if options is not None else PlanOptions()
    milestone_info = plan_milestone(trigger, options)
    facts = plan_facts(trigger, tags, options, milestone_info)
    if options.scope.strip().lower() == "none":
        return facts.skip("no release-worthy changes for scope", scope="none")
    scoped_commits = commits_for_scope(commits, facts.scope)
    version = plan_version(options, facts, scoped_commits, config, milestone_info)
    if version is None:
        return facts.skip(f"no release-worthy commits since {facts.base_tag}")
    if options.suffix:
        version = version.with_prerelease(options.suffix)
    tag = tag_for_version(version, scope=facts.scope)
    if (skip := early_skip(facts, version, tag, milestone_info)) is not None:
        return skip
    reason = plan_reason(options, facts, milestone_info)
    changelog = render_changelog(
        version,
        scoped_commits,
        config,
        ChangelogOptions(facts.base_tag, options.repo_slug, facts.scope),
    )
    return facts.tagged(version, tag, reason, changelog)


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


def _recipe_context_line(key: str) -> re.Pattern[str]:
    return re.compile(rf'(?m)^(\s*{re.escape(key)}:\s*)"[^"]*"$')


def stamp_recipe_context(text: str, key: str, version: Version) -> str:
    """Rewrite the quoted ``<key>:`` context line of the multi-output recipe."""
    stamped, count = _recipe_context_line(key).subn(
        rf'\g<1>"{version.to_pep440()}"', text, count=1
    )
    if count == 0:
        raise QgisSdkReleaseError(f"no quoted {key} line found in recipe.yaml")
    return stamped


def read_recipe_context(text: str, key: str) -> Version | None:
    """Read one quoted context version out of the recipe, ``None`` when absent."""
    match = _recipe_context_line(key).search(text)
    if match is None:
        return None
    return version_from_pep440(match.group(0).rsplit('"', 2)[1])


_KIT_PIN = re.compile(r'("qgis-sdk-(?:runtime|tools)(?:\[[^\]]*\])?==)[^"]+"')
TOOLS_RUNTIME_RANGE = re.compile(r'"qgis-sdk-runtime>=[^,"]+,<[^"]+"')


def stamp_kit_pins(text: str, version: Version) -> str:
    """Pin the kit's ``qgis-sdk-runtime`` / ``qgis-sdk-tools`` dependencies to ``version``.

    The kit has no code, so its version and its pins are one number: a pin that
    lagged would let ``qgis-sdk==X`` install a runtime that is not ``X``. Every
    occurrence is rewritten, extras included (``qgis-sdk-runtime[...]==X``).
    """
    stamped, count = _KIT_PIN.subn(rf'\g<1>{version.to_pep440()}"', text)
    if count == 0:
        raise QgisSdkReleaseError(
            "the kit pyproject.toml pins neither qgis-sdk-runtime nor qgis-sdk-tools"
        )
    return stamped


def next_minor(version: Version) -> str:
    """``0.5`` for ``0.4.x``: the exclusive upper bound of a tested runtime range."""
    return f"{version.major}.{version.minor + 1}"


def stamp_tools_runtime_range(text: str, runtime: Version) -> str:
    """Set the tools' tested runtime range to ``>=runtime,<next minor``.

    The range is the tools release's promise to a developer (decision-35); a
    release that ships both at once tests exactly this runtime, so the lower
    bound is it and the upper bound is the next minor, where the runtime may
    change shape.
    """
    stamped, count = TOOLS_RUNTIME_RANGE.subn(
        f'"qgis-sdk-runtime>={runtime.to_pep440()},<{next_minor(runtime)}"',
        text,
        count=1,
    )
    if count == 0:
        raise QgisSdkReleaseError(
            "the tools pyproject.toml declares no qgis-sdk-runtime>=X,<Y range"
        )
    return stamped


_EXAMPLE_WINDOW = re.compile(r'"(qgis-sdk-(?:runtime|tools))>=([^,"]+),<([^"]+)"')


def minor_window(version: Version) -> str:
    """``>=0.6,<0.7`` for ``0.6.x``: what ``qgis-sdk new`` writes for an install."""
    return f">={version.major}.{version.minor},<{next_minor(version)}"


def example_label(manifest: Path) -> str:
    """How a finding names one example manifest: repo-relative when it can be."""
    try:
        return manifest.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return manifest.name


def read_example_windows(text: str) -> dict[str, tuple[Version, str]]:
    """Read the example's ``qgis-sdk-runtime`` / ``qgis-sdk-tools`` windows.

    Each is ``(lower, upper)`` with ``upper`` as ``major.minor``, like the
    tools' tested range; a ``major.minor`` lower bound reads as ``.0``. Both
    lines must be there: the example is the project the released tools are
    qualified against.
    """
    found: dict[str, tuple[Version, str]] = {}
    for match in _EXAMPLE_WINDOW.finditer(text):
        name, lower, upper = match.groups()
        if lower.count(".") == 1 and lower.replace(".", "").isdigit():
            lower = f"{lower}.0"
        found.setdefault(name, (Version.parse(lower), upper))
    for name in ("qgis-sdk-runtime", "qgis-sdk-tools"):
        if name not in found:
            raise QgisSdkReleaseError(
                f"the example pyproject.toml declares no {name}>=X,<Y window"
            )
    return found


def stamp_example_windows(
    text: str, *, runtime: Version | None = None, tools: Version | None = None
) -> str:
    """Move the example's dependency windows to the minor window of each release.

    ``runtime`` moves the ``qgis-sdk-runtime`` line, ``tools`` the
    ``qgis-sdk-tools`` line; a side that is not releasing keeps its window.
    """
    read_example_windows(text)
    wanted = {"qgis-sdk-runtime": runtime, "qgis-sdk-tools": tools}

    def rewrite(match: re.Match[str]) -> str:
        name = match.group(1)
        version = wanted[name]
        if version is None:
            return match.group(0)
        return f'"{name}{minor_window(version)}"'

    return _EXAMPLE_WINDOW.sub(rewrite, text)


def stamp_package_json(text: str, version: Version) -> str:
    """Rewrite ``version`` in a package.json, preserving tab indentation."""
    data = json.loads(text)
    data["version"] = str(version)
    return json.dumps(data, indent="\t") + "\n"


def stamp_alias_package_json(
    text: str, version: Version, dependency: str = ALIAS_DEPENDENCY
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


def read_kit_pins(text: str) -> tuple[tuple[str, Version], ...]:
    """Return every ``(requirement, pinned version)`` the kit carries, in order."""
    found = []
    for match in _KIT_PIN.finditer(text):
        requirement = match.group(1)[1:-2]  # strip the quote and the ``==``
        pinned = match.group(0).rsplit("==", 1)[1].rstrip('"')
        found.append((requirement, version_from_pep440(pinned)))
    if not found:
        raise QgisSdkReleaseError(
            "the kit pyproject.toml pins neither qgis-sdk-runtime nor qgis-sdk-tools"
        )
    return tuple(found)


def read_tools_runtime_range(text: str) -> tuple[Version, str]:
    """Return ``(lower bound, exclusive upper bound text)`` of the tools' runtime range."""
    match = TOOLS_RUNTIME_RANGE.search(text)
    if match is None:
        raise QgisSdkReleaseError(
            "the tools pyproject.toml declares no qgis-sdk-runtime>=X,<Y range"
        )
    lower, upper = (
        match.group(0).strip('"').removeprefix("qgis-sdk-runtime>=").split(",<")
    )
    return version_from_pep440(lower), upper


def runtime_range_includes(lower: Version, upper: str, runtime: Version) -> bool:
    """Whether ``runtime`` falls in ``>=lower,<upper`` (``upper`` is ``major.minor``)."""
    major, minor = (int(part) for part in upper.split(".")[:2])
    below_upper = (runtime.major, runtime.minor) < (major, minor)
    return runtime.sort_key() >= lower.sort_key() and below_upper


def example_window_includes(lower: Version, upper: str, shipped: Version) -> bool:
    """Whether the example's ``>=lower,<upper`` window admits ``shipped``.

    Read on release segments only, as the tools' ``VERSION004`` reads it: an
    example declares the minor line (``>=0.7,<0.8``), never a prerelease, so
    ``0.7.0-rc.1`` is inside the window ``stamp`` writes for it.
    """
    core = Version(shipped.major, shipped.minor, shipped.patch)
    return runtime_range_includes(lower, upper, core)


def read_package_json_version(text: str) -> Version:
    """Read the stamped version out of the bridge ``package.json``."""
    return Version.parse(str(json.loads(text)["version"]))

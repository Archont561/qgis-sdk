"""The release train steps, forwarding named options to ``automation.release``."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from automation import release

__all__ = [
    "release_build_python",
    "release_checksums",
    "release_classify",
    "release_github_release",
    "release_plan",
    "release_stamp",
    "release_tag",
    "release_verify_python",
    "release_verify_versions",
]


def _omitted(value: object) -> bool:
    """Whether an option was left at its default and is not forwarded.

    A flag is only passed on when the caller gave it a value: ``None`` is an
    absent option, ``False`` and ``""`` and ``[]`` are what argparse and the
    release parser would have produced for a flag nobody set.
    """
    if value is None or value == "":
        return True
    return value is False or value == []


def _release_command(command: str, **options: object) -> int:
    """Forward a set of named options to one ``release`` subcommand."""
    argv = [command]
    for name, value in options.items():
        if _omitted(value):
            continue
        flag = "--" + name.replace("_", "-")
        if value is True:
            argv.append(flag)
        elif isinstance(value, (list, tuple)):
            argv.append(flag)
            argv.extend(str(item) for item in value)
        else:
            argv.extend([flag, str(value)])
    return release.main(argv)


@dataclass(frozen=True)
class _ReleasePlan:
    """The nine plan options doit passes, as one record (decision-81)."""

    trigger: str = "push"
    config: str = ""
    suffix: str = ""
    version_override: str = ""
    scope: str = ""
    bump: str = ""
    milestone_tag: str = ""
    dry_run: str = "false"
    json: bool = False


def release_plan(**options) -> int:
    """Decide what the next release is: nothing, a rehearsal, or a tag."""
    plan = _ReleasePlan(**options)
    return _release_command(
        "plan",
        trigger=plan.trigger,
        config=plan.config,
        suffix=plan.suffix,
        version_override=plan.version_override,
        scope=plan.scope,
        bump=plan.bump,
        milestone_tag=plan.milestone_tag,
        dry_run=plan.dry_run,
        json=plan.json,
    )


def release_classify(tag: str, scoped: bool = False) -> int:
    """Classify one release tag into its scope."""
    return _release_command("classify", tag=tag, scoped=scoped)


def release_tag(
    tag: str = "", message: str = "", message_file: str = "", push: bool = False
) -> int:
    """Create the annotated release tag, optionally pushing it."""
    return _release_command(
        "tag", tag=tag, message=message, message_file=message_file, push=push
    )


def release_stamp(version: str, scope: str = "all") -> int:
    """Stamp one version into the manifests of a scope."""
    return _release_command("stamp", version=version, scope=scope)


def release_verify_versions(
    scope: str = "", version: str = "", json: bool = False
) -> int:
    """Require one version per released scope and one shared contract version."""
    return _release_command("verify-versions", scope=scope, version=version, json=json)


def release_build_python(
    package: Sequence[str] | None = None, scope: str = "all", outdir: str = "dist/pypi"
) -> int:
    """Build and check the wheel of every Python distribution in scope."""
    return _release_command(
        "build-python", package=list(package or []), scope=scope, outdir=outdir
    )


def release_verify_python(dist: str = "dist/pypi") -> int:
    """Twine-check the wheels that were built."""
    return _release_command("verify-python", dist=dist)


def release_checksums(paths: Sequence[str], out: str = "SHA256SUMS") -> int:
    """Write a ``SHA256SUMS`` file over the release assets."""
    return _release_command("checksums", out=out, paths=list(paths))


def release_github_release(
    tag: str,
    body_file: str = "",
    asset: Sequence[str] | None = None,
    repo: str = "",
    token: str = "",
) -> int:
    """Publish the GitHub Release for a tag."""
    return _release_command(
        "github-release",
        tag=tag,
        body_file=body_file,
        asset=list(asset or []),
        repo=repo,
        token=token,
    )

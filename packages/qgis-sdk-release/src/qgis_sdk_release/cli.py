"""Command line interface for the qgis-sdk-release tool.

Every workflow step in ``autorelease.yml`` and ``release.yml`` reaches this CLI
through a ``pixi run`` task, and the identical invocations work locally from a
restored sandbox. Side effects on GitHub Actions (step outputs, summaries) are
written only when the corresponding environment variables are present.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from . import artifacts, github, gitops
from .commits import parse_log
from .errors import QgisSdkReleaseError
from .plan import compute_plan, sort_tags
from .semver import Version, version_from_tag
from .stamp import stamp_package_json, stamp_pyproject
from .versionrc import parse_versionrc

__all__ = ["main"]

_PYPROJECT = Path("packages/qgis-sdk/pyproject.toml")
_BRIDGE_PACKAGE = Path("packages/qgis-sdk-bridge/package.json")


def _github_output() -> Path | None:
    raw = os.environ.get("GITHUB_OUTPUT")
    return Path(raw) if raw else None


def _write_output(pairs: dict[str, str]) -> None:
    path = _github_output()
    if path is None:
        return
    with path.open("a", encoding="utf-8") as handle:
        for key, value in pairs.items():
            handle.write(f"{key}={value}\n")


def _step_summary(line: str) -> None:
    raw = os.environ.get("GITHUB_STEP_SUMMARY")
    if raw:
        with Path(raw).open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")


def _cmd_plan(args: argparse.Namespace) -> int:
    config = parse_versionrc(Path(args.config).read_text(encoding="utf-8"))
    tags = gitops.list_tags()
    ordered = sort_tags(tags)
    base_tag = ordered[0] if ordered else None
    raw = gitops.log_commits(f"{base_tag}..HEAD" if base_tag else None)
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
    if args.message_file:
        message = Path(args.message_file).read_text(encoding="utf-8")
    elif args.message:
        message = args.message
    else:
        raise QgisSdkReleaseError("tag needs --message or --message-file")
    version_from_tag(args.tag)  # Validate before creating anything.
    gitops.create_tag(args.tag, message, push=args.push)
    where = "and pushed it" if args.push else "locally"
    print(f"created tag {args.tag} {where}")
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
    artifacts.build_wheel(args.package, outdir)
    wheels = sorted(outdir.glob("*.whl"))
    if not wheels:
        raise QgisSdkReleaseError(f"no wheel appeared in {outdir}")
    artifacts.twine_check(wheels)
    print(f"built and checked {[wheel.name for wheel in wheels]}")
    return 0


def _cmd_verify_python(args: argparse.Namespace) -> int:
    wheels = sorted(Path(args.dist).glob("*.whl"))
    if not wheels:
        raise QgisSdkReleaseError(f"no wheels under {args.dist}")
    artifacts.twine_check(wheels)
    print(f"twine check passed for {[wheel.name for wheel in wheels]}")
    return 0


def _cmd_checksums(args: argparse.Namespace) -> int:
    entries = artifacts.checksums([Path(item) for item in args.paths])
    artifacts.write_checksums(Path(args.out), entries)
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
    release = github.create_release(
        slug, token, args.tag, args.tag, body, version.is_prerelease
    )
    upload_url = release.get("upload_url")
    if not upload_url:
        raise QgisSdkReleaseError(f"release response lacked upload_url: {release}")
    for asset in args.asset:
        github.upload_asset(upload_url, token, Path(asset))
        print(f"uploaded {Path(asset).name}")
    html_url = release.get("html_url", "")
    print(f"release {args.tag}: {html_url}")
    _step_summary(
        f"- GitHub Release [{args.tag}]({html_url}) with {len(args.asset)} asset(s)"
    )
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="qgis-sdk-release")
    sub = parser.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan", help="decide the next release action")
    plan.add_argument("--trigger", choices=("push", "dispatch"), default="push")
    plan.add_argument("--config", default=".versionrc")
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
    # `tag --tag` lands in tag_name to avoid shadowing the subcommand name.
    if args.command == "tag":
        args.tag = args.tag_name
    try:
        return int(args.handler(args))
    except QgisSdkReleaseError as error:
        print(f"error: {error}")
        return 1

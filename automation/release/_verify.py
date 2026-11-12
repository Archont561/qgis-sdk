from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from ._build import build_wheel, twine_check
from ._contracts import (
    ReleaseDraft,
    contract_versions,
    create_release,
    delete_release_asset,
    get_release_by_tag,
    kit_pins_behind_or_at,
    require_one_version,
    step_summary,
    upload_asset,
    write_output,
)
from ._history import (
    PY_DECLARATIONS,
    REPO_ROOT,
    TS_DECLARATIONS,
    VERSIONRC,
    QgisSdkReleaseError,
    QgisSdkReleaseVersionError,
    create_tag,
)
from ._main import DISTRIBUTION_DIRS, cmd_checksums
from ._pins import (
    ManifestSources,
    ManifestVersions,
    manifest_versions,
    scoped_manifest_versions,
)
from ._stamp import (
    check_expected_version,
    check_runtime_range,
    check_ui_peer,
    cmd_plan,
    cmd_stamp,
    manifest_sources,
    reported_example_windows,
    wanted_scopes,
)
from ._version import Version, parse_release_tag, scope_ships, version_from_tag


def _verify_one_scope(
    scope: str,
    versions: ManifestVersions,
    expected: Version | None,
    sources: ManifestSources,
) -> dict[str, object]:
    """Everything one scope has to agree on, as its diagnostic entry."""
    scoped = scoped_manifest_versions(versions, scope)
    version = require_one_version(scoped)
    check_expected_version(scope, scoped, version, expected)
    entry: dict[str, object] = {
        "version": str(version),
        "manifests": {name: str(value) for name, value in scoped},
    }
    if scope == "kit":
        kit_pins_behind_or_at(versions)
        entry["pins"] = {
            requirement: str(pinned) for requirement, pinned in versions.kit_pins
        }
    check_ui_peer(scope, versions, entry)
    check_runtime_range(scope, versions, sources.tools_text, entry)
    if scope in ("python", "runtime", "tools"):
        windows = reported_example_windows(scope, versions)
        if windows:
            entry["example_windows"] = windows
    return entry


def _emit_verification(
    reported: dict, contract, shared_contract, wanted_scopes, as_json: bool
) -> None:
    """Print the same verdict for the workflow and for a human."""
    if as_json:
        print(
            json.dumps({"scopes": reported, "contract": contract.to_json()}, indent=2)
        )
        return
    for scope in wanted_scopes:
        entry = reported[scope]
        listed = ", ".join(entry["manifests"])
        print(
            f"released manifests for scope {scope} agree on {entry['version']}: {listed}"
        )
    print(
        f"plugin description contract version {shared_contract} agrees across "
        "the Python declarations and the TypeScript bridge"
    )


def _cmd_verify_versions(args: argparse.Namespace) -> int:
    scope_raw = (getattr(args, "scope", "") or "").strip()
    expected_raw = (getattr(args, "version", "") or "").strip()
    sources = manifest_sources()
    versions = manifest_versions(sources)
    contract = contract_versions(
        PY_DECLARATIONS.read_text(encoding="utf-8"),
        TS_DECLARATIONS.read_text(encoding="utf-8"),
    )
    scopes = wanted_scopes(sources, scope_raw)
    expected = Version.parse(expected_raw) if expected_raw else None
    if expected is not None and len(scopes) > 1:
        raise QgisSdkReleaseVersionError(
            "--version needs --scope: one release targets one package"
        )
    reported = {
        scope: _verify_one_scope(scope, versions, expected, sources) for scope in scopes
    }
    _emit_verification(
        reported,
        contract,
        contract.agreed(),
        scopes,
        getattr(args, "json", False),
    )
    return 0


def _release_or_existing(draft: ReleaseDraft) -> dict:
    """Create the release, or reuse one a retried run already published."""
    try:
        return create_release(draft)
    except QgisSdkReleaseError as exc:
        if "already_exists" not in str(exc):
            raise
    return get_release_by_tag(draft.slug, draft.token, draft.tag)


def _upload_assets(release: dict, slug: str, token: str, assets) -> None:
    """Replace same-named assets, then upload every asset the run produced."""
    upload_url = release.get("upload_url")
    if not upload_url:
        raise QgisSdkReleaseError(f"release response lacked upload_url: {release}")
    existing_assets = {
        item.get("name"): item.get("id")
        for item in release.get("assets", ())
        if isinstance(item, dict) and item.get("name") and item.get("id")
    }
    for asset in assets:
        asset_path = Path(asset)
        existing_id = existing_assets.get(asset_path.name)
        if existing_id is not None:
            delete_release_asset(slug, token, int(existing_id))
        upload_asset(upload_url, token, asset_path)
        print(f"uploaded {asset_path.name}")


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
    draft = ReleaseDraft(slug, token, args.tag, args.tag, body, version.is_prerelease)
    release = _release_or_existing(draft)
    _upload_assets(release, slug, token, args.asset)
    html_url = release.get("html_url", "")
    print(f"release {args.tag}: {html_url}")
    step_summary(
        f"- GitHub Release [{args.tag}]({html_url}) with {len(args.asset)} asset(s)"
    )
    return 0


def _add_planning_parsers(sub) -> None:
    plan = sub.add_parser("plan", help="decide the next release action")
    plan.add_argument(
        "--trigger", choices=("push", "dispatch", "milestone"), default="push"
    )
    plan.add_argument("--config", default=str(VERSIONRC))
    plan.add_argument("--suffix", default="")
    plan.add_argument("--version-override", default="")
    plan.add_argument("--scope", default="")
    plan.add_argument("--bump", default="")
    plan.add_argument("--milestone-tag", default="")
    plan.add_argument("--dry-run", default="false")
    plan.add_argument("--json", action="store_true")
    plan.set_defaults(handler=cmd_plan)

    classify = sub.add_parser("classify", help="classify one release tag")
    classify.add_argument("--tag", required=True)
    classify.add_argument("--scoped", action="store_true")
    classify.set_defaults(handler=_cmd_classify)


def _add_stamping_parsers(sub) -> None:
    tag = sub.add_parser("tag", help="create an annotated release tag")
    tag.add_argument("--tag", required=True, dest="tag_name", metavar="TAG")
    tag.add_argument("--message")
    tag.add_argument("--message-file")
    tag.add_argument("--push", action="store_true")
    tag.set_defaults(handler=_cmd_tag)

    stamp = sub.add_parser("stamp", help="stamp versions into manifests")
    stamp.add_argument("--version", required=True)
    stamp.add_argument(
        "--scope",
        default="all",
        help="which package to stamp: all, python, or typescript",
    )
    stamp.set_defaults(handler=cmd_stamp)


def _add_verify_versions_parser(sub) -> None:
    versions = sub.add_parser(
        "verify-versions",
        help="require one version per released scope and one shared contract version",
    )
    versions.add_argument(
        "--scope",
        default="",
        help=(
            "which package is being released: all, python, or typescript; "
            "omit to check every scope on its own"
        ),
    )
    versions.add_argument(
        "--version",
        default="",
        help="version this scope is releasing; the scoped manifests must carry it",
    )
    versions.add_argument("--json", action="store_true", help="machine-readable output")
    versions.set_defaults(handler=_cmd_verify_versions)


def _add_build_parsers(sub) -> None:
    build = sub.add_parser(
        "build-python", help="build and check the wheel of every Python distribution"
    )
    build.add_argument(
        "--package",
        action="append",
        help="a package directory to build; repeatable; default: every "
        "distribution the scope ships",
    )
    build.add_argument(
        "--scope",
        default="all",
        help="release scope deciding which distributions to build "
        "(all/python: the three; runtime; tools)",
    )
    build.add_argument("--outdir", default="dist/pypi")
    build.set_defaults(handler=_cmd_build_python)

    verify = sub.add_parser("verify-python", help="twine check built wheels")
    verify.add_argument("--dist", default="dist/pypi")
    verify.set_defaults(handler=_cmd_verify_python)


def _add_publish_parsers(sub) -> None:
    sums = sub.add_parser("checksums", help="write a SHA256SUMS file")
    sums.add_argument("--out", default="SHA256SUMS")
    sums.add_argument("paths", nargs="+")
    sums.set_defaults(handler=cmd_checksums)

    release = sub.add_parser("github-release", help="publish a GitHub Release")
    release.add_argument("--tag", required=True)
    release.add_argument("--body-file")
    release.add_argument("--asset", nargs="+", default=[])
    release.add_argument("--repo")
    release.add_argument("--token")
    release.set_defaults(handler=_cmd_github_release)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="release",
        description="Release planning and publishing CLI for the QGIS SDK workspace.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    _add_planning_parsers(sub)
    _add_stamping_parsers(sub)
    _add_verify_versions_parser(sub)
    _add_build_parsers(sub)
    _add_publish_parsers(sub)
    return parser


def ship_flags(scope: str) -> dict[str, str]:
    if scope == "none":
        return {name: "false" for name in scope_ships("all")}
    return {name: str(value).lower() for name, value in scope_ships(scope).items()}


def _cmd_classify(args: argparse.Namespace) -> int:
    scope, version = parse_release_tag(args.tag)
    outputs = {
        "version": str(version),
        "pep440": version.to_pep440(),
        "prerelease": "true" if version.is_prerelease else "false",
    }
    if getattr(args, "scoped", False):
        outputs.update({"scope": scope, **ship_flags(scope), "tag_name": args.tag})
    write_output(outputs)
    payload: dict[str, object] = {
        "tag": args.tag,
        "version": str(version),
        "pep440": version.to_pep440(),
        "prerelease": version.is_prerelease,
    }
    if getattr(args, "scoped", False):
        payload.update({"scope": scope, **scope_ships(scope)})
    print(json.dumps(payload, indent=2))
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


def read_if_file(path: Path) -> str | None:
    return path.read_text(encoding="utf-8") if path.is_file() else None


def _cmd_build_python(args: argparse.Namespace) -> int:
    """Build each Python distribution into its own ``<outdir>/<name>`` directory.

    One directory per wheel is what lets the workflow run one publish step per
    distribution (TASK-57): a failure names the wheel it belongs to.
    """
    outdir = Path(args.outdir)
    ships = scope_ships(getattr(args, "scope", "") or "all")
    if args.package:
        targets = [(Path(package).name, package) for package in args.package]
    else:
        targets = [
            (name, directory)
            for name, directory in DISTRIBUTION_DIRS.items()
            if ships[name] and (REPO_ROOT / directory / "pyproject.toml").is_file()
        ]
    if not targets:
        raise QgisSdkReleaseError("no Python distribution to build for this scope")
    for name, package in targets:
        build_wheel(package, outdir / name)
    wheels = sorted(outdir.glob("*/*.whl"))
    if not wheels:
        raise QgisSdkReleaseError(f"no wheel appeared under {outdir}")
    twine_check(wheels)
    print(
        f"built and checked {[wheel.parent.name + '/' + wheel.name for wheel in wheels]}"
    )
    return 0


def _cmd_verify_python(args: argparse.Namespace) -> int:
    wheels = sorted(Path(args.dist).glob("**/*.whl"))
    if not wheels:
        raise QgisSdkReleaseError(f"no wheels under {args.dist}")
    twine_check(wheels)
    print(f"twine check passed for {[wheel.name for wheel in wheels]}")
    return 0

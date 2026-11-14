"""The last step of a release: hash every artifact, then publish the page.

It used to be nine lines of shell inside ``release.yml`` - glob the artifacts,
build a ``--paths`` list, build a ``--asset`` list - and nothing else in the
pipeline ran it: pull requests exercise every gate except this one, so a release
was the first execution of it. ``python-v0.11.0`` proved what that costs. The
step reached PyPI, then exited 3 because the ``doit`` command it called could
not accept a list, and the tag kept a release page with no artifacts on it
(TASK-169, PR #222).

So the step lives here instead, with two callers: ``release.yml`` names one
command, and ``automation -- release_rehearsal`` runs the same command over a
fabricated artifact tree on every pull request. The rehearsal is a rehearsal
because of ``--dry-run``, not because it is a separate implementation.
"""

from __future__ import annotations

import argparse
import os
import tempfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from ._build import checksums, write_checksums
from ._contracts import (
    ReleaseDraft,
    create_release,
    delete_release_asset,
    get_release_by_tag,
    step_summary,
    upload_asset,
)
from ._history import REPO_ROOT, QgisSdkReleaseError
from ._version import version_from_tag

ASSET_PATTERNS = (
    "dist/pypi/*/*.whl",
    "dist/conda/*.conda",
    "npm/*.tgz",
    "npm/*/*.tgz",
)
"""What a release run downloads, as the globs that find it.

One wheel directory per distribution, the Conda outputs, and the npm tarballs
under their pack directories. Named here rather than in the workflow: while the
shell spelled them, the rehearsal could only rehearse a different list.
"""

REHEARSAL_TAG = "python-v0.0.0-rehearsal"
REHEARSAL_ASSETS = (
    "dist/pypi/runtime/qgis_sdk_runtime-0.0.0-py3-none-any.whl",
    "dist/pypi/tools/qgis_sdk_tools-0.0.0-py3-none-any.whl",
    "dist/pypi/kit/qgis_sdk-0.0.0-py3-none-any.whl",
    "dist/conda/qgis-sdk-0.0.0-pyh0000000_0.conda",
    "npm/bridge/archont561-qgis-sdk-0.0.0.tgz",
    "npm/alias/qgis-sdk-0.0.0.tgz",
)


def matched_assets(
    patterns: Sequence[str] = ASSET_PATTERNS, root: str | Path = REPO_ROOT
) -> tuple[Path, ...]:
    """Every artifact the patterns find under ``root``, sorted by path.

    An empty result is an error rather than an empty release: a publish run
    that has nothing to attach means the artifacts never arrived, which is how
    a TypeScript-only tag failed on 2026-09-30 after npm had already published.
    """
    base = Path(root)
    found = {
        path for pattern in patterns for path in base.glob(pattern) if path.is_file()
    }
    if not found:
        raise QgisSdkReleaseError(
            f"no release assets matched {', '.join(patterns)} under {base}; "
            "nothing arrived to publish"
        )
    return tuple(sorted(found, key=str))


def credentials(repo: str = "", token: str = "") -> tuple[str, str]:
    """The repository slug and token a real publish needs, from flags or env."""
    slug = repo or os.environ.get("GITHUB_REPOSITORY") or ""
    secret = token or os.environ.get("GITHUB_TOKEN") or ""
    if not slug or not secret:
        raise QgisSdkReleaseError(
            "publish needs --repo/GITHUB_REPOSITORY and --token/GITHUB_TOKEN; "
            "use --dry-run to rehearse it without them"
        )
    return slug, secret


def release_body(tag: str, body_file: str = "") -> str:
    """The release notes, from the file the train wrote or a one-line stand-in."""
    if body_file:
        return Path(body_file).read_text(encoding="utf-8")
    return f"Release {tag}"


def _release_or_existing(draft: ReleaseDraft) -> dict:
    """Create the release, or reuse one a retried run already published."""
    try:
        return create_release(draft)
    except QgisSdkReleaseError as exc:
        if "already_exists" not in str(exc):
            raise
    return get_release_by_tag(draft.slug, draft.token, draft.tag)


def _upload_assets(
    release: dict, slug: str, token: str, assets: Iterable[Path]
) -> None:
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


def publish_release(
    tag: str, body: str, assets: Sequence[Path], slug: str, token: str
) -> str:
    """Create the release (or reuse one) and upload every asset; return its URL."""
    prerelease = version_from_tag(tag).is_prerelease
    draft = ReleaseDraft(slug, token, tag, tag, body, prerelease)
    release = _release_or_existing(draft)
    _upload_assets(release, slug, token, assets)
    return str(release.get("html_url", ""))


@dataclass(frozen=True, slots=True)
class PublishRequest:
    """The options one publish step takes, as one record (decision-81)."""

    tag: str
    out: str = "SHA256SUMS"
    root: str = str(REPO_ROOT)
    body_file: str = ""
    repo: str = ""
    token: str = ""
    dry_run: bool = False


def _describe(assets: Sequence[Path], sums: Path, tag: str) -> None:
    """Say what a real run would do, without a token or a network call."""
    for path in (*assets, sums):
        print(f"would attach {path} ({path.stat().st_size} bytes)")
    kind = "a prerelease" if version_from_tag(tag).is_prerelease else "a release"
    print(
        f"would publish the GitHub release {tag} as {kind} "
        f"with {len(assets) + 1} asset(s)"
    )


def publish(request: PublishRequest) -> int:
    """Hash the artifacts, write the sums file, then publish or describe."""
    assets = matched_assets(ASSET_PATTERNS, request.root)
    # Absolute, so the dry run lists the same shape of path the uploads use.
    sums = Path(request.out).resolve()
    write_checksums(sums, checksums(assets))
    if request.dry_run:
        _describe(assets, sums, request.tag)
        return 0
    slug, token = credentials(request.repo, request.token)
    url = publish_release(
        request.tag,
        release_body(request.tag, request.body_file),
        (*assets, sums),
        slug,
        token,
    )
    print(f"release {request.tag}: {url}")
    step_summary(
        f"- GitHub Release [{request.tag}]({url}) with {len(assets) + 1} asset(s)"
    )
    return 0


def _request(args: argparse.Namespace) -> PublishRequest:
    """The publish options a command line names."""
    return PublishRequest(
        tag=args.tag,
        out=args.out,
        root=args.root or str(REPO_ROOT),
        body_file=args.body_file or "",
        repo=args.repo or "",
        token=args.token or "",
        dry_run=bool(args.dry_run),
    )


def cmd_publish(args: argparse.Namespace) -> int:
    """Hash the artifacts that are really there and publish the release page."""
    return publish(_request(args))


def _fabricate(root: Path) -> None:
    """Write the artifact tree a release run would have downloaded."""
    for relative in REHEARSAL_ASSETS:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"rehearsal {path.name}\n".encode())


def cmd_rehearsal(args: argparse.Namespace) -> int:
    """Rehearse the publish step on a tree this command made up."""
    root = (
        Path(args.root)
        if args.root
        else Path(tempfile.mkdtemp(prefix="release-rehearsal-"))
    )
    _fabricate(root)
    print(f"rehearsal tree: {root}")
    return publish(
        PublishRequest(
            tag=REHEARSAL_TAG,
            out=str(root / "SHA256SUMS"),
            root=str(root),
            dry_run=True,
        )
    )

from __future__ import annotations

import json
import os
import re
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from urllib import request as urlrequest
from urllib.error import HTTPError
from urllib.parse import quote

from ._changelog import Plan, PlanOptions, plan_base_tag, sort_tags
from ._history import (
    QgisSdkReleaseError,
    QgisSdkReleaseVersionError,
    detect_scope_from_files,
    list_changed_files,
    log_commits_with_files,
    parse_log_with_files,
)
from ._pins import ManifestVersions
from ._version import Version, normalize_scope, parse_milestone_tag


def kit_pins_behind_or_at(versions: ManifestVersions) -> None:
    """Refuse a kit pin that names a runtime or tools version newer than HEAD.

    Between kit releases the runtime or the tools may release alone, so a kit
    pin may lag the manifest next to it - but it can never lead it: a version
    that does not exist cannot be installed.
    """
    at_head = {"qgis-sdk-runtime": versions.runtime, "qgis-sdk-tools": versions.tools}
    for requirement, pinned in versions.kit_pins:
        head = at_head.get(requirement.split("[", 1)[0])
        if head is not None and pinned.sort_key() > head.sort_key():
            raise QgisSdkReleaseVersionError(
                f"the kit pins {requirement}=={pinned} but that distribution is "
                f"{head} at HEAD; a pin cannot lead the manifest it names"
            )


def require_one_version(items: Sequence[tuple[str, Version]]) -> Version:
    """Return the one version ``items`` carries, or name every disagreement."""
    if not items:
        raise QgisSdkReleaseVersionError("no released manifest belongs to this scope")
    versions = {version for _, version in items}
    if len(versions) > 1:
        listed = ", ".join(f"{name}={version}" for name, version in items)
        raise QgisSdkReleaseVersionError(
            f"released manifests disagree: {listed}; one version is required per scope"
        )
    return items[0][1]


@dataclass(frozen=True)
class ContractVersions:
    """The plugin-description contract version each language declares.

    Package versions are independent, so the pair is held together by this
    number instead: the bridge mirrors the Python wire contract, and a release
    that moves one side without the other must at least agree on what crosses
    the boundary.
    """

    python: int
    typescript: int

    def agreed(self) -> int:
        """Return the shared contract version, or refuse the pair."""
        if self.python != self.typescript:
            raise QgisSdkReleaseVersionError(
                "plugin description contract versions disagree: "
                f"python={self.python}, typescript={self.typescript}"
            )
        return self.python

    def to_json(self) -> dict:
        """Serialize the contract versions for diagnostics."""
        return {"python": self.python, "typescript": self.typescript}


_PY_CONTRACT_VERSION = re.compile(
    r"(?m)^PLUGIN_DESCRIPTION_SCHEMA_VERSION\s*=\s*(\d+)\s*$"
)
_TS_CONTRACT_VERSION = re.compile(r"PLUGIN_DESCRIPTION_SCHEMA_VERSION[^=\n]*=\s*(\d+)")


def read_python_contract_version(text: str) -> int:
    """Read ``PLUGIN_DESCRIPTION_SCHEMA_VERSION`` from the Python declarations."""
    match = _PY_CONTRACT_VERSION.search(text)
    if match is None:
        raise QgisSdkReleaseError(
            "no PLUGIN_DESCRIPTION_SCHEMA_VERSION in the Python declarations"
        )
    return int(match.group(1))


def read_typescript_contract_version(text: str) -> int:
    """Read ``PLUGIN_DESCRIPTION_SCHEMA_VERSION`` from the bridge declarations."""
    match = _TS_CONTRACT_VERSION.search(text)
    if match is None:
        raise QgisSdkReleaseError(
            "no PLUGIN_DESCRIPTION_SCHEMA_VERSION in the bridge declarations"
        )
    return int(match.group(1))


def contract_versions(python_text: str, typescript_text: str) -> ContractVersions:
    """Read both declarations of the plugin description contract version."""
    return ContractVersions(
        python=read_python_contract_version(python_text),
        typescript=read_typescript_contract_version(typescript_text),
    )


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


@dataclass(frozen=True, slots=True)
class ReleaseDraft:
    """One GitHub Release to create."""

    slug: str
    token: str
    tag: str
    name: str
    body: str
    prerelease: bool


def create_release(draft: ReleaseDraft, opener: Opener | None = None) -> dict:
    """Create one GitHub Release and return the API response."""
    open_it = opener or _default_opener
    payload = {
        "tag_name": draft.tag,
        "name": draft.name,
        "body": draft.body,
        "draft": False,
        "prerelease": draft.prerelease,
        "make_latest": "false" if draft.prerelease else "true",
    }
    req = _request(
        f"https://api.github.com/repos/{draft.slug}/releases", draft.token, payload
    )
    return _read_json(open_it, req, "GitHub release creation")


def get_release_by_tag(
    slug: str,
    token: str,
    tag: str,
    opener: Opener | None = None,
) -> dict:
    """Fetch an existing GitHub Release by tag name."""
    open_it = opener or _default_opener
    req = _request(
        f"https://api.github.com/repos/{slug}/releases/tags/{quote(tag)}", token
    )
    return _read_json(open_it, req, f"GitHub release lookup for {tag}")


def delete_release_asset(
    slug: str,
    token: str,
    asset_id: int,
    opener: Opener | None = None,
) -> None:
    """Delete an existing release asset before re-uploading."""
    open_it = opener or _default_opener
    req = _request(
        f"https://api.github.com/repos/{slug}/releases/assets/{asset_id}", token
    )
    req.method = "DELETE"
    try:
        with open_it(req):  # type: ignore[attr-defined]
            pass
    except HTTPError as error:
        detail = error.read().decode(errors="replace")[:400]
        raise QgisSdkReleaseError(
            f"asset deletion {asset_id} failed ({error.code}): {detail}"
        ) from error


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


_github_output_env = "GITHUB_OUTPUT"
_step_summary_env = "GITHUB_STEP_SUMMARY"


def _github_output() -> Path | None:
    raw = os.environ.get(_github_output_env)
    return Path(raw) if raw else None


def write_output(pairs: dict[str, str]) -> None:
    path = _github_output()
    if path is None:
        return
    with path.open("a", encoding="utf-8") as handle:
        for key, value in pairs.items():
            handle.write(f"{key}={value}\n")


def step_summary(line: str) -> None:
    raw = os.environ.get(_step_summary_env)
    if raw:
        with Path(raw).open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")


def resolve_dry_run(trigger: str, requested: bool) -> tuple[bool, str]:
    """Decide whether this plan may cut a tag, and say why when it may not.

    A branch push never tags. The train still plans and gates the candidate on
    every merge, but cutting the tag stays an explicit act - a dispatch or a
    milestone tag - so a merge cannot consume a version, and a package minor
    (which is what a ``feat!`` landing on ``packages/qgis-sdk-python`` derives) cannot
    bypass its release gate. On 2026-10-24 a merge planned ``v0.2.0`` for both
    packages this way and the only thing that stopped it was luck.
    """
    if trigger == "push" and not requested:
        return (
            True,
            "dry run: a branch push never tags, cut the release with a dispatch "
            + "or a milestone tag",
        )
    return requested, ""


def requested_scope(args, tags, milestone_tag: str) -> str:
    """Resolve ``--scope auto`` from the changed files since the newest tag."""
    requested = (getattr(args, "scope", "") or "").strip()
    if requested.lower() != "auto":
        return requested
    newest = sort_tags(tags)
    auto_range = f"{newest[0]}..HEAD" if newest else None
    return detect_scope_from_files(list_changed_files(auto_range))


def cli_plan_scope(requested: str, milestone_tag: str) -> str:
    """Which package train the CLI's history is about."""
    if requested and requested.lower() not in ("all", "none"):
        return normalize_scope(requested)
    if milestone_tag:
        info = parse_milestone_tag(milestone_tag)
        return info[0] if info is not None else "all"
    return "all"


def commits_since(tags, plan_scope: str, suffix: str):
    """The commits the plan's changelog and bump are computed from."""
    ordered = sort_tags(tags, plan_scope)
    base_tag = plan_base_tag(ordered, suffix)
    revision_range = f"{base_tag}..HEAD" if base_tag else None
    return parse_log_with_files(log_commits_with_files(revision_range))


def plan_options(args, requested: str, milestone_tag: str) -> PlanOptions:
    """The plan knobs as the CLI spelled them."""
    return PlanOptions(
        suffix=args.suffix,
        version_override=args.version_override or None,
        repo_slug=os.environ.get("GITHUB_REPOSITORY"),
        milestone_tag=milestone_tag or None,
        scope=requested or "all",
        bump=getattr(args, "bump", "") or "",
    )


def plan_changelog_directory(env: Mapping[str, str] | None = None) -> Path:
    """Where a plan writes its changelog: the runner's temp dir, never the tree.

    The workflow sets ``RUNNER_TEMP`` and hands the path to `tag --message-file`
    in a later step. A local run has no such variable, and writing to the
    current directory left an untracked `qgis-sdk-release-changelog.md` in the
    checkout after every plan - the file is a build artifact of one command, so
    it goes to this process's temp directory instead.
    """
    values = os.environ if env is None else env
    configured = values.get("RUNNER_TEMP", "").strip()
    if configured:
        return Path(configured)
    return Path(tempfile.mkdtemp(prefix="qgis-sdk-release-"))


def write_plan_changelog(plan: Plan) -> str:
    """Write the changelog where the workflow expects it, and name the file."""
    if not plan.changelog:
        return ""
    target = plan_changelog_directory() / "qgis-sdk-release-changelog.md"
    target.write_text(plan.changelog, encoding="utf-8")
    return str(target.resolve())


def emit_plan(plan: Plan, dry_run: bool, changelog_file: str, as_json: bool) -> None:
    """Write the workflow outputs and print the same decision for a human."""
    from ._verify import ship_flags

    write_output(
        {
            "action": plan.action,
            "tag": plan.tag or "",
            "version": str(plan.version) if plan.version else "",
            "prerelease": (
                "true" if plan.version and plan.version.is_prerelease else "false"
            ),
            "scope": plan.scope,
            **ship_flags(plan.scope),
            "dry_run": "true" if dry_run else "false",
            "reason": plan.reason,
            "changelog_file": changelog_file,
        }
    )
    if as_json:
        payload = plan.to_json()
        payload["scope"] = plan.scope
        payload["dry_run"] = dry_run
        payload["changelog_file"] = changelog_file
        print(json.dumps(payload, indent=2))
    else:
        print(
            f"action={plan.action} scope={plan.scope} "
            f"tag={plan.tag or '-'} reason={plan.reason}"
        )

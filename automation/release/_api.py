"""``release verify-api``: what a release changes in the public API.

decision-56 point 2: the inventory is the contract, so a release is checked by
diffing two of them - the one a tag committed and the one this tree produces -
and classifying every difference as additive, deprecating or breaking. A
breaking change in a stable symbol cannot ship as a minor, and this is where
that is refused rather than remembered.

The ``qgis_sdk_tools`` package is imported inside the handlers, not at module
import: `automation` runs in jobs that install nothing but the release tooling,
and only this subcommand needs the SDK to dump the tree.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path

from ._history import REPO_ROOT, QgisSdkReleaseError

INVENTORY = Path("api/python.json")
"""The tracked inventory: what the last tag promised, in one reviewable diff."""


def _tools():
    """The SDK side of this command, imported where it is needed."""
    try:
        from qgis_sdk_tools import api
    except ImportError as error:
        raise QgisSdkReleaseError(
            f"verify-api needs the qgis-sdk-tools package installed: {error}"
        ) from error
    return api


def _git(*argv: str) -> subprocess.CompletedProcess[str]:
    """Run one git command in the repository, capturing both streams."""
    return subprocess.run(
        ["git", *argv],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _git_inventory(tag: str) -> dict | None:
    """The inventory as one tag committed it, or ``None`` when it recorded none.

    None is not a failure: the tags cut before this inventory existed cannot be
    diffed, and a release train that pretends otherwise reports every name as
    new. A tag that does not exist *is* a failure - a typo must not pass.
    """
    if _git("cat-file", "-e", f"{tag}^{{commit}}").returncode != 0:
        raise QgisSdkReleaseError(f"{tag} is not a tag in this checkout")
    shown = _git("show", f"{tag}:{INVENTORY.as_posix()}")
    if shown.returncode != 0:
        return None
    return json.loads(shown.stdout)


def _tracked_inventory() -> dict:
    """The inventory committed in this checkout."""
    path = REPO_ROOT / INVENTORY
    if not path.is_file():
        raise QgisSdkReleaseError(
            f"{INVENTORY.as_posix()} is missing; run `qgis-sdk api dump` and commit it"
        )
    return _tools().read(path)


def _dump_tree() -> dict:
    """The inventory this working tree produces right now."""
    return _tools().inventory().document()


def _baseline(args: argparse.Namespace) -> dict | None:
    """What the changes are measured against: a tag, a file, or the tracked copy."""
    if getattr(args, "tag", ""):
        return _git_inventory(args.tag)
    if getattr(args, "baseline", ""):
        return _tools().read(Path(args.baseline))
    return _tracked_inventory()


def _current(args: argparse.Namespace) -> dict:
    """What the changes are measured on: a file, or this working tree."""
    if getattr(args, "current", ""):
        return _tools().read(Path(args.current))
    return _dump_tree()


def _stale(tracked: Mapping, dumped: Mapping) -> bool:
    """Whether the committed inventory still describes this tree."""
    return json.dumps(tracked, sort_keys=True) != json.dumps(dumped, sort_keys=True)


def _emit(changes: Sequence, version: str, as_json: bool) -> None:
    """Print every change and the release it requires."""
    api = _tools()
    verdict = api.verdict(changes)
    lines = [change.line() for change in changes]
    required = api.consequence(verdict, version or "<version>")
    if as_json:
        print(
            json.dumps(
                {
                    "changes": [change.to_json() for change in changes],
                    "verdict": verdict,
                    "required": required,
                },
                indent=2,
            )
        )
        return
    for line in lines:
        print(line)
    print(f"verdict: {verdict} ({len(changes)} change(s))")
    print(required)


def _refuse(changes: Sequence, version: str, old: Mapping, new: Mapping) -> None:
    """Stop the release when the version cannot carry what changed.

    Two ways it cannot: the change is breaking and the version is not a major
    after 1.0, or a deprecated symbol is removed before the version its mark
    announced (decision-56 points 2 and 3).
    """
    if not version:
        return
    api = _tools()
    reasons = [
        *api.refusals(changes, version),
        *api.early_removals(old, new, version),
    ]
    if reasons:
        raise QgisSdkReleaseError("; ".join(reasons))


def cmd_verify_api(args: argparse.Namespace) -> int:
    """Diff two inventories, print every change, and refuse a wrong version."""
    baseline = _baseline(args)
    if baseline is None:
        print(
            f"{args.tag} records no {INVENTORY.as_posix()}; "
            "the first tag that carries one is the first that can be diffed"
        )
        return 0
    current = _current(args)
    if getattr(args, "check", False) and _stale(baseline, current):
        raise QgisSdkReleaseError(
            f"{INVENTORY.as_posix()} does not describe this tree; "
            "run `qgis-sdk api dump` and commit the result"
        )
    changes = _tools().diff(baseline, current)
    _emit(changes, getattr(args, "version", ""), getattr(args, "json", False))
    _refuse(changes, getattr(args, "version", ""), baseline, current)
    return 0


def add_parser(sub) -> None:
    """Register ``verify-api`` beside the other release subcommands."""
    api = sub.add_parser(
        "verify-api", help="classify what a release changes in the public API"
    )
    api.add_argument(
        "--tag",
        default="",
        help="compare against the inventory this tag committed; default: the "
        "tracked file",
    )
    api.add_argument(
        "--baseline", default="", help="an inventory file to compare against"
    )
    api.add_argument(
        "--current", default="", help="an inventory file to compare; default: this tree"
    )
    api.add_argument(
        "--version",
        default="",
        help="version this release ships; a breaking change is refused unless it "
        "is a major",
    )
    api.add_argument(
        "--check",
        action="store_true",
        help="also fail when the tracked inventory no longer describes this tree",
    )
    api.add_argument("--json", action="store_true", help="machine-readable output")
    api.set_defaults(handler=cmd_verify_api)

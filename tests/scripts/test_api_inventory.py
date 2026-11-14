"""The public API gates a pull request and a release have to pass.

The inventory's *behaviour* - what counts as additive or breaking, when a
version may carry a change, what a deprecation mark does - is unit-tested in
`packages/qgis-sdk-python/tests/test_api_contract.py`, where the coverage the
release reports is measured. What is tested here is the wiring that makes it a
gate: the tracked file describes this tree, every public module declares the
tier the guide shows, the guide's table is the rendered one, and the workflows
call the command that refuses a wrong release.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "apps" / "docs" / "guides" / "doc-12 - qgis-sdk-Python-package-guide.md"


def _difference(tracked: dict, dumped: dict) -> str:
    """The first place two inventories disagree, in one readable line."""
    for section in sorted(set(tracked) | set(dumped)):
        before, after = tracked.get(section), dumped.get(section)
        if before == after:
            continue
        if isinstance(before, dict) and isinstance(after, dict):
            return _module_difference(section, before, after)
        added = set(after or ()) - set(before or ())
        removed = set(before or ()) - set(after or ())
        return f"{section}: committed only {sorted(removed)[:3]}, tree only {sorted(added)[:3]}"
    return "no difference"


def _module_difference(section: str, before: dict, after: dict) -> str:
    """Up to five names, tiers or signatures the two module maps disagree on."""
    found: list[str] = []
    for module in sorted(set(before) | set(after)):
        old, new = before.get(module), after.get(module)
        if old == new:
            continue
        if old is None or new is None:
            found.append(
                f"{section}.{module}: present only in {old and 'the tree' or 'the file'}"
            )
            continue
        for key in sorted(set(old) | set(new)):
            if old.get(key) != new.get(key):
                found.append(
                    f"{section}.{module}.{key}: committed {old.get(key)!r} / tree {new.get(key)!r}"
                )
    return " | ".join(found[:5]) or f"{section}: differs"


def test_the_tracked_inventory_describes_this_tree():
    """`api/python.json` is what a release diffs, so it may not be stale."""
    from qgis_sdk_tools.api import inventory

    tracked = json.loads((ROOT / "api/python.json").read_text(encoding="utf-8"))
    dumped = inventory().document()

    difference = _difference(tracked, dumped)
    if difference != "no difference":
        # A GitHub annotation, so a CI failure says which name moved even when
        # the runner's log is not readable from where the failure is triaged.
        print(f"::error title=api inventory::{difference}")
    assert tracked == dumped, (
        "api/python.json is stale; run `qgis-sdk api dump` and commit the result. "
        + difference
    )


def test_every_public_module_declares_its_tier():
    """decision-56 point 1: the tier lives in code, not in a table beside it."""
    from importlib import import_module

    from qgis_sdk_tools.api import PUBLIC_MODULES

    for name in PUBLIC_MODULES:
        declared = getattr(import_module(name), "__stability__", None)
        assert declared in {"stable", "evolving", "internal"}, (
            f"{name} declares {declared!r}"
        )


def test_the_inventory_records_the_tier_each_module_declares():
    from importlib import import_module

    from qgis_sdk_tools.api import inventory

    for name, entry in inventory().document()["modules"].items():
        assert entry["tier"] == import_module(name).__stability__


def test_the_guide_renders_the_tiers_the_code_declares():
    """doc-12's table is pasted from `qgis-sdk api stability`, not written."""
    from qgis_sdk_tools.api import inventory, render_stability

    text = GUIDE.read_text(encoding="utf-8")
    begin, end = "<!-- stability:begin -->", "<!-- stability:end -->"
    assert begin in text and end in text, "doc-12 must carry the rendered tier table"
    rendered = text.split(begin, 1)[1].split(end, 1)[0].strip()

    assert rendered == render_stability(inventory().document()), (
        "doc-12's tier table drifted from the marks; "
        "paste `qgis-sdk api stability` between the markers"
    )


def _document(**sections) -> dict:
    """A minimal inventory document, with one name that a mark retires."""
    document = {
        "api_version": 1,
        "modules": {
            "qgis_sdk.ui": {"tier": "stable", "names": {"OldPanel": "()"}},
            "qgis_sdk.models": {"tier": "stable", "names": {"Legacy": "()"}},
        },
        "rules": [],
        "host_operations": [],
        "cli": [],
        "deprecations": [
            {
                "module": "qgis_sdk.ui",
                "name": "OldPanel",
                "since": "0.12.0",
                "removal": "1.0.0",
                "use": "Panel",
            }
        ],
    }
    document.update(sections)
    return document


def _arguments(tmp_path: Path, baseline: dict, current: dict, **flags):
    """The namespace ``release verify-api`` builds, over two written documents."""
    from automation.release import _api

    old, new = tmp_path / "old.json", tmp_path / "new.json"
    old.write_text(json.dumps(baseline), encoding="utf-8")
    new.write_text(json.dumps(current), encoding="utf-8")
    return _api.argparse.Namespace(
        baseline=str(old),
        current=str(new),
        tag="",
        version=flags.get("version", ""),
        check=flags.get("check", False),
        json=flags.get("json", False),
    )


def test_verify_api_check_fails_only_when_the_tracked_copy_is_stale(tmp_path: Path):
    from automation.release import _api
    from automation.release._history import QgisSdkReleaseError

    stale = _document(rules=["UI001"])

    assert _api._stale(_document(), stale) is True
    assert _api._stale(_document(), _document()) is False
    with pytest.raises(QgisSdkReleaseError, match="does not describe this tree"):
        _api.cmd_verify_api(_arguments(tmp_path, _document(), stale, check=True))


def test_verify_api_refuses_a_breaking_minor_and_passes_a_breakless_one(tmp_path: Path):
    from automation.release import _api
    from automation.release._history import QgisSdkReleaseError

    # No marks in these documents: this is the SemVer rule on its own.
    plain = _document(deprecations=[])
    broken = _document(
        modules={"qgis_sdk.ui": {"tier": "stable", "names": {}}}, deprecations=[]
    )

    with pytest.raises(QgisSdkReleaseError, match="cannot ship as 1.2.0"):
        _api.cmd_verify_api(_arguments(tmp_path, plain, broken, version="1.2.0"))
    assert (
        _api.cmd_verify_api(_arguments(tmp_path, plain, broken, version="0.12.0")) == 0
    )


@pytest.mark.parametrize(
    ("version", "reason"),
    [
        ("0.13.0", "announced for removal in 1.0.0"),
        # The SemVer rule fires first here: a removal after 1.0 is a major
        # whatever its window says, so the two refusals stay independent.
        ("1.1.0", "cannot ship as 1.1.0"),
        ("2.0.0", ""),
    ],
)
def test_verify_api_refuses_removing_a_name_before_its_window_closes(
    tmp_path: Path, version: str, reason: str
):
    from automation.release import _api
    from automation.release._history import QgisSdkReleaseError

    removed = _document(
        modules={
            "qgis_sdk.ui": {"tier": "stable", "names": {}},
            "qgis_sdk.models": {"tier": "stable", "names": {"Legacy": "()"}},
        }
    )
    arguments = _arguments(tmp_path, _document(), removed, version=version)

    if not reason:
        assert _api.cmd_verify_api(arguments) == 0
        return
    with pytest.raises(QgisSdkReleaseError, match=reason):
        _api.cmd_verify_api(arguments)


def test_the_release_parser_offers_verify_api():
    from automation.release._verify import build_parser

    args = build_parser().parse_args(["verify-api", "--check", "--version", "0.12.0"])

    assert args.handler.__name__ == "cmd_verify_api"
    assert args.check is True
    assert args.version == "0.12.0"


def test_the_release_train_gates_the_api_against_the_previous_python_tag():
    """The refusal is only a gate when the release workflow runs it."""
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )

    assert "release_verify_api" in workflow
    assert "git tag --sort=-creatordate --list 'python-v*'" in workflow


def test_a_pull_request_keeps_the_inventory_current():
    """`api/python.json` only gates a change if CI compares it to the tree."""
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "release_verify_api --check" in workflow

"""The public API inventory, and the release gate that reads it.

decision-56 makes a generated JSON document the 1.0 contract: `qgis-sdk api
dump` writes it, `release.py verify-api` diffs two of them and refuses a
breaking change that the version cannot carry. Four properties are worth a test,
because the gate is only as good as them: the document is deterministic, the
tracked copy still describes this tree, the classifier tells additive from
breaking, and the refusal fires only where the promise says it should.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

BASE = {
    "api_version": 1,
    "modules": {
        "qgis_sdk.ui": {
            "tier": "stable",
            "names": {"Button": "(text: str)", "Dialog": "()"},
        }
    },
    "rules": ["UI001", "UI002"],
    "host_operations": ["canvas.capture"],
    "cli": ["build", "check", "check --json"],
}


def _with(**sections) -> dict:
    """``BASE`` with one or more top-level sections replaced."""
    document = copy.deepcopy(BASE)
    document.update(sections)
    return document


def _kinds(document: dict, baseline: dict | None = None) -> list[str]:
    """The kinds ``diff`` reports, in order."""
    from qgis_sdk_tools.api import diff

    return [change.kind for change in diff(baseline or BASE, document)]


def test_two_dumps_of_one_tree_are_byte_identical(tmp_path: Path):
    """A gate diffs files, so the same tree must always write the same bytes.

    This compares two dumps in one process; the cross-process case is decided by
    CI, which dumps the tree and diffs it against the committed copy.
    """
    from qgis_sdk_tools.api import inventory, write

    first, second = tmp_path / "first.json", tmp_path / "second.json"
    write(inventory().document(), first)
    write(inventory().document(), second)

    assert first.read_bytes() == second.read_bytes()


def test_the_inventory_is_complete_for_every_public_module():
    """Every public module is listed, and every name it exports is described."""
    from importlib import import_module

    from qgis_sdk_tools.api import PUBLIC_MODULES, inventory

    modules = inventory().document()["modules"]

    assert set(PUBLIC_MODULES) == set(modules)
    for name in PUBLIC_MODULES:
        exported = set(import_module(name).__all__)
        described = set(modules[name]["names"])
        assert exported, f"{name} exports no name to promise"
        assert exported == described, f"{name} exports {exported - described} unlisted"
    for internal in ("qgis_sdk.adapters", "qgis_sdk.bridge"):
        assert internal not in modules


def test_the_tracked_inventory_describes_this_tree():
    """`api/python.json` is what a release diffs, so it may not be stale."""
    from qgis_sdk_tools.api import inventory

    tracked = json.loads((ROOT / "api/python.json").read_text(encoding="utf-8"))

    assert tracked == inventory().document(), (
        "api/python.json is stale; run `qgis-sdk api dump` and commit the result"
    )


def test_a_name_added_is_additive_and_a_name_removed_is_breaking():
    names = {"Button": "(text: str)", "Dialog": "()", "Panel": "()"}
    added = copy.deepcopy(BASE["modules"]["qgis_sdk.ui"]["names"])
    added["Panel"] = "()"
    grown = _with(modules={"qgis_sdk.ui": {"tier": "stable", "names": added}})
    shrunk = _with(
        modules={
            "qgis_sdk.ui": {
                "tier": "stable",
                "names": {"Button": names["Button"]},
            }
        }
    )

    assert _kinds(grown) == ["additive"]
    assert _kinds(shrunk) == ["breaking"]


def test_a_changed_signature_is_breaking_and_says_old_from_new():
    from qgis_sdk_tools.api import diff

    changed = copy.deepcopy(BASE["modules"]["qgis_sdk.ui"]["names"])
    changed["Button"] = "(text: str, kind: str)"
    document = _with(modules={"qgis_sdk.ui": {"tier": "stable", "names": changed}})

    (change,) = diff(BASE, document)

    assert change.kind == "breaking"
    assert "(text: str) -> (text: str, kind: str)" in change.detail


def test_an_internal_module_is_not_a_promise():
    internal = _with(
        modules={"qgis_sdk.adapter": {"tier": "internal", "names": {"Gone": "()"}}}
    )

    assert _kinds(_with()) == []
    assert _kinds(internal, _with(modules={})) == ["additive"]


def test_a_removed_rule_or_cli_flag_is_breaking():
    assert _kinds(_with(rules=["UI001"])) == ["breaking"]
    assert _kinds(_with(cli=["build", "check"])) == ["breaking"]


@pytest.mark.parametrize(
    ("version", "verdict", "refused"),
    [
        ("0.12.0", "breaking", False),
        ("1.0.0", "breaking", False),
        ("1.2.0", "breaking", True),
    ],
)
def test_a_breaking_change_is_refused_only_after_1_0_and_by_a_major(
    version: str, verdict: str, refused: bool
):
    from qgis_sdk_tools.api import diff, refusals
    from qgis_sdk_tools.api import verdict as classify

    document = _with(modules={"qgis_sdk.ui": {"tier": "stable", "names": {}}})
    changes = diff(BASE, document)

    assert classify(changes) == verdict
    assert bool(refusals(changes, version)) is refused


def test_an_additive_release_is_never_refused():
    from qgis_sdk_tools.api import diff, refusals

    names = {**BASE["modules"]["qgis_sdk.ui"]["names"], "Panel": "()"}
    document = _with(modules={"qgis_sdk.ui": {"tier": "stable", "names": names}})

    assert refusals(diff(BASE, document), "1.2.0") == []


def test_verify_api_check_fails_only_when_the_tracked_copy_is_stale(tmp_path: Path):
    from automation.release import _api
    from automation.release._history import QgisSdkReleaseError

    stale = _with(rules=["UI001"])
    assert _api._stale(BASE, stale) is True
    assert _api._stale(BASE, copy.deepcopy(BASE)) is False
    with pytest.raises(QgisSdkReleaseError, match="does not describe this tree"):
        _api.cmd_verify_api(
            _arguments(_api, tmp_path, stale, copy.deepcopy(BASE), check=True)
        )


def _arguments(_api, tmp_path: Path, baseline: dict, current: dict, **flags):
    """The namespace ``release verify-api`` builds, over two written documents."""
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


def test_verify_api_refuses_a_breaking_minor_and_passes_a_breakless_one(tmp_path: Path):
    from automation.release import _api
    from automation.release._history import QgisSdkReleaseError

    broken = _with(modules={"qgis_sdk.ui": {"tier": "stable", "names": {}}})
    with pytest.raises(QgisSdkReleaseError, match="cannot ship as 1.2.0"):
        _api.cmd_verify_api(_arguments(_api, tmp_path, BASE, broken, version="1.2.0"))
    assert (
        _api.cmd_verify_api(_arguments(_api, tmp_path, BASE, broken, version="0.12.0"))
        == 0
    )


def test_the_release_parser_offers_verify_api():
    from automation.release._verify import build_parser

    args = build_parser().parse_args(["verify-api", "--check", "--version", "0.12.0"])

    assert args.handler.__name__ == "cmd_verify_api"
    assert args.check is True
    assert args.version == "0.12.0"


def test_the_release_train_gates_the_api_against_the_previous_python_tag():
    """The refusal is only a gate when the release workflow runs it."""
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")

    assert "release_verify_api" in workflow
    assert "git tag --sort=-creatordate --list 'python-v*'" in workflow

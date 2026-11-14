"""The public API contract: the document, the classifier and the marks.

decision-56 makes a generated inventory the 1.0 contract, so the code that
produces and reads it is unit-tested here, where the coverage the release gate
reports is measured. The *gate* half - the tracked file matching this tree, the
tier table in doc-12, the release workflow calling the command - lives in
`tests/scripts/test_api_inventory.py`, beside the other repository checks.

Four properties matter: the document is deterministic and complete, the
classifier tells additive from breaking, the refusals fire only where the
promise says they should, and a deprecation mark is readable by all three tools
that promise to honour it.
"""

from __future__ import annotations

import copy
import json
import warnings
from pathlib import Path

import pytest
from qgis_sdk_tools.api import _inventory as inventory_module
from qgis_sdk_tools.api import (
    diff,
    early_removals,
    inventory,
    render_stability,
    verdict,
)

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
    "deprecations": [],
}


def _with(**sections) -> dict:
    """``BASE`` with one or more top-level sections replaced."""
    document = copy.deepcopy(BASE)
    document.update(sections)
    return document


def _kinds(document: dict, baseline: dict | None = None) -> list[str]:
    """The kinds ``diff`` reports, in order."""
    return [change.kind for change in diff(baseline or BASE, document)]


def test_two_dumps_of_one_tree_are_byte_identical():
    """A gate diffs files, so the same tree must always write the same bytes."""
    first = json.dumps(inventory().document(), sort_keys=True)
    second = json.dumps(inventory().document(), sort_keys=True)

    assert first == second


def test_the_inventory_is_complete_for_every_public_module():
    """Every public module is listed, and every name it exports is described."""
    from importlib import import_module

    from qgis_sdk_tools.api import PUBLIC_MODULES

    document = inventory().document()

    assert set(PUBLIC_MODULES) == set(document["modules"])
    for name in PUBLIC_MODULES:
        exported = set(import_module(name).__all__)
        described = set(document["modules"][name]["names"])
        assert exported, f"{name} exports no name to promise"
        assert exported == described, f"{name} exports {exported - described} unlisted"


def test_the_inventory_leaves_the_internal_trees_out():
    modules = inventory().document()["modules"]

    for internal in ("qgis_sdk.adapters", "qgis_sdk.bridge"):
        assert internal not in modules


def test_a_signature_names_parameters_without_the_interpreters_own_forms():
    """The recorded signature must not embed what a release happens to print."""

    def plain(a, b=1, *args, key=None, **kwargs):
        """A function with one of everything."""

    class Inherited(Exception):
        """No ``__init__`` of its own: the interpreter describes this one."""

    assert inventory_module._signature(plain) == (
        "(a, b = 1, *args, key = None, **kwargs)"
    )
    assert "self" not in inventory_module._signature(Inherited)


def test_a_name_added_is_additive_and_a_name_removed_is_breaking():
    grown = _with(
        modules={
            "qgis_sdk.ui": {
                "tier": "stable",
                "names": {"Button": "(text: str)", "Dialog": "()", "Panel": "()"},
            }
        }
    )
    shrunk = _with(
        modules={"qgis_sdk.ui": {"tier": "stable", "names": {"Button": "(text: str)"}}}
    )

    assert _kinds(grown) == ["additive"]
    assert _kinds(shrunk) == ["breaking"]


def test_a_changed_signature_is_breaking_and_says_old_from_new():
    changed = _with(
        modules={
            "qgis_sdk.ui": {
                "tier": "stable",
                "names": {"Button": "(text: str, kind: str)", "Dialog": "()"},
            }
        }
    )

    (change,) = diff(BASE, changed)

    assert change.kind == "breaking"
    assert change.detail == "Button signature (text: str) -> (text: str, kind: str)"


def test_an_internal_module_is_not_a_promise():
    internal = _with(
        modules={"qgis_sdk.adapter": {"tier": "internal", "names": {"Gone": "()"}}}
    )

    assert _kinds(internal, _with(modules={})) == ["additive"]


def test_a_removed_rule_or_cli_flag_is_breaking():
    assert _kinds(_with(rules=["UI001"])) == ["breaking"]
    assert _kinds(_with(cli=["build", "check"])) == ["breaking"]


def test_a_new_mark_is_deprecating_and_the_removal_is_breaking():
    mark = {
        "module": "qgis_sdk.ui",
        "name": "Dialog",
        "since": "0.12.0",
        "removal": "1.0.0",
        "use": "Panel",
    }
    marked = _with(deprecations=[mark])
    removed = _with(
        modules={"qgis_sdk.ui": {"tier": "stable", "names": {"Button": "(text: str)"}}}
    )

    assert verdict(diff(BASE, marked)) == "deprecating"
    assert verdict(diff(marked, removed)) == "breaking"
    assert verdict(diff(marked, BASE)) == "none"


@pytest.mark.parametrize(
    ("version", "answer", "refused"),
    [
        ("0.12.0", "breaking", False),
        ("1.0.0", "breaking", False),
        ("1.2.0", "breaking", True),
    ],
)
def test_a_breaking_change_is_refused_only_after_1_0_and_by_a_major(
    version: str, answer: str, refused: bool
):
    from qgis_sdk_tools.api import refusals

    changes = diff(
        BASE, _with(modules={"qgis_sdk.ui": {"tier": "stable", "names": {}}})
    )

    assert verdict(changes) == answer
    assert bool(refusals(changes, version)) is refused


def test_an_additive_release_is_never_refused():
    from qgis_sdk_tools.api import refusals

    grown = _with(
        modules={
            "qgis_sdk.ui": {
                "tier": "stable",
                "names": {"Button": "(text: str)", "Dialog": "()", "Panel": "()"},
            }
        }
    )

    assert refusals(diff(BASE, grown), "1.2.0") == []


def test_a_removal_before_its_announced_window_is_reported():
    mark = {
        "module": "qgis_sdk.ui",
        "name": "Dialog",
        "since": "0.12.0",
        "removal": "1.0.0",
        "use": "",
    }
    marked = _with(deprecations=[mark])
    removed = _with(
        modules={"qgis_sdk.ui": {"tier": "stable", "names": {"Button": "(text: str)"}}},
        deprecations=[],
    )

    assert early_removals(marked, removed, "0.13.0")
    assert early_removals(marked, removed, "1.0.0") == []
    assert early_removals(marked, removed, "1.10.0") == []
    assert early_removals(marked, removed, "") == []


def test_the_rendered_table_lists_every_module_with_its_tier():
    document = _with(
        modules={
            "qgis_sdk.ui": {"tier": "stable", "names": {"Button": "(text: str)"}},
            "qgis_sdk.core": {"tier": "internal", "names": {}},
        }
    )

    lines = render_stability(document).splitlines()

    assert lines[0] == "| Module | Tier | Public names | Deprecated |"
    assert lines[2] == "| `qgis_sdk.core` | internal | 0 | 0 |"
    assert lines[3] == "| `qgis_sdk.ui` | stable | 1 | 0 |"


def test_a_deprecated_function_warns_once_and_names_what_replaces_it():
    from qgis_sdk import deprecation

    deprecation._WARNED.clear()

    @deprecation.deprecated(since="0.12.0", removal="1.0.0", use="new_panel()")
    def old_panel() -> str:
        return "panel"

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert old_panel() == "panel"
        old_panel()

    assert deprecation.deprecation_of(old_panel).removal == "1.0.0"
    assert len(caught) == 1
    message = str(caught[0].message)
    assert "deprecated since 0.12.0" in message
    assert "removed in 1.0.0" in message
    assert "new_panel()" in message
    deprecation._WARNED.clear()


def test_a_deprecated_class_warns_once_on_first_construction():
    from qgis_sdk import deprecation

    deprecation._WARNED.clear()

    @deprecation.deprecated(since="0.12.0", removal="1.0.0", use="Panel")
    class OldPanel:
        """A retired panel."""

        def __init__(self, name: str) -> None:
            self.name = name

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        first, second = OldPanel("a"), OldPanel("b")

    assert (first.name, second.name) == ("a", "b")
    assert len(caught) == 1
    deprecation._WARNED.clear()


def _table():
    """Two marks, as `check` would read them off the installed SDK."""
    from qgis_sdk.deprecation import Deprecation

    return {
        ("qgis_sdk.ui", "OldPanel"): Deprecation("0.12.0", "1.0.0", "Panel"),
        ("qgis_sdk.models", "Legacy"): Deprecation("0.12.0", "1.0.0", ""),
    }


def test_api001_reports_both_import_spellings_as_warnings():
    from qgis_sdk_tools.check.api import check_deprecated_usage

    source = (
        "from qgis_sdk.ui import Button, OldPanel\n"
        "import qgis_sdk.models as models\n"
        "\n"
        "panel = OldPanel()\n"
        "legacy = models.Legacy()\n"
    )

    found = check_deprecated_usage(
        source, path=Path("plugin.py"), deprecations=_table()
    )

    assert [(d.rule, d.line) for d in found] == [("API001", 1), ("API001", 5)]
    assert {d.severity for d in found} == {"warning"}
    assert "use Panel instead" in found[0].message
    assert "1.0.0" in found[0].remediation


def test_api001_says_nothing_about_a_name_that_is_not_marked():
    from qgis_sdk_tools.check.api import check_deprecated_usage

    source = "from qgis_sdk.ui import Button\n"

    assert (
        check_deprecated_usage(source, path=Path("plugin.py"), deprecations=_table())
        == []
    )


def test_api001_leaves_a_file_it_cannot_parse_to_syntax001():
    from qgis_sdk_tools.check.api import check_deprecated_usage

    assert (
        check_deprecated_usage("def (:", path=Path("broken.py"), deprecations=_table())
        == []
    )


def test_the_installed_sdk_offsets_its_marks_by_module_and_name():
    from qgis_sdk_tools.check.api import deprecated_names

    marks = deprecated_names()

    assert all(isinstance(key, tuple) and len(key) == 2 for key in marks)
    assert all(key[0].startswith("qgis_sdk") for key in marks)

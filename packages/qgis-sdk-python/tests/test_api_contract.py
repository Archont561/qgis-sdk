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
from qgis_sdk_tools.api import _signatures as signatures_module
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

    assert signatures_module.signature_of(plain) == (
        "(a, b = 1, *args, key = None, **kwargs)"
    )
    assert "self" not in signatures_module.signature_of(Inherited)


def test_an_annotation_reads_the_same_however_the_interpreter_prints_it():
    """A source string, an evaluated class and a lazy re-render collapse alike.

    Which shape arrives depends on whether the module uses
    ``from __future__ import annotations`` and on how the interpreter reads
    annotations - so the contract records the short name, and a release on one
    Python cannot disagree with a release on another.
    """
    import typing
    from pathlib import Path as PathType

    text = signatures_module.text_of

    assert text("qgis_sdk.models.files.FileRef") == "FileRef"
    assert text(PathType) == "Path"
    assert text(int | None) == "int | None"
    # `Optional[X]` and `X | None` are one type, and which an interpreter prints
    # depends on its `typing`: 3.11 says `typing.Optional[pathlib.Path]`, 3.14
    # says `pathlib.Path | None`. Both record the PEP 604 spelling.
    assert text(typing.Optional[PathType]) == "Path | None"  # noqa: UP045
    assert text("Optional[dict[str, int]]") == "dict[str, int] | None"
    assert text("Union[int, str]") == "int | str"
    assert text("dict[str, Any]") == "dict[str, Any]"
    assert text(None) == "None"


def test_a_recorded_signature_carries_no_module_path_and_no_class_repr():
    signatures = inventory().document()["modules"]

    for entry in signatures.values():
        for rendered in entry["names"].values():
            assert "<class" not in rendered, rendered
            assert "qgis_sdk." not in rendered, rendered


def test_a_type_variable_loses_the_tilde_and_an_inherited_init_is_blank():
    """Two more interpreter habits the recorded text must not inherit."""
    from qgis_sdk_tools.api import _signatures

    class Wide:
        """Takes anything, and says so in the only way the record cannot use."""

        def __init__(self, *args, **kwargs) -> None:
            self.args = args

    class Inherited(Wide):
        """No ``__init__`` of its own."""

    assert _signatures.text_of("Callable[[type[~T]], type[~T]]") == (
        "Callable[[type[T]], type[T]]"
    )
    assert _signatures.signature_of(Inherited) == ""


def test_an_alias_is_recorded_by_shape_even_where_it_is_callable():
    """3.14 makes some aliases callable; the record must not depend on that."""
    import typing

    from qgis_sdk_tools.api import _inventory

    assert _inventory._describe(typing.Sequence[int]) == "Sequence"
    assert _inventory._describe(tuple[int, ...]) == "tuple"


def test_an_enumeration_is_recorded_by_its_members_not_its_constructor():
    """`inspect.signature(SomeEnum)` is the machinery's, and it moves between Pythons."""
    import enum

    from qgis_sdk_tools.api import _signatures

    class Host(enum.Enum):
        DESKTOP = "desktop"
        SERVER = "server"

    assert _signatures.enum_members(Host) == "enum<DESKTOP|SERVER>"


def test_a_value_records_its_kind_not_its_interpreters_class_name():
    """`X | Y` is `UnionType` on 3.11 and `Union` on 3.14; both record `Union`."""
    import typing

    from qgis_sdk_tools.api import _inventory

    assert _inventory._kind(int | str) == "Union"
    # The legacy alias is the point: it is a `typing` object on every release.
    assert _inventory._kind(typing.Optional[int]) == "Union"  # noqa: UP045
    assert _inventory._kind(list[int]) == "list"
    assert _inventory._kind(typing.Sequence[int]) == "Sequence"
    assert _inventory._kind(frozenset()) == "frozenset"


def test_an_enumeration_gains_members_additively_and_loses_them_breaking():
    grown = _with(
        modules={
            "qgis_sdk.ui": {
                "tier": "stable",
                "names": {"Dialog": "()", "Host": "enum<SERVER|APP|DESKTOP>"},
            }
        }
    )
    base = _with(
        modules={
            "qgis_sdk.ui": {
                "tier": "stable",
                "names": {"Dialog": "()", "Host": "enum<DESKTOP|SERVER>"},
            }
        }
    )

    assert _kinds(grown, base) == ["additive"]
    assert _kinds(base, grown) == ["breaking"]


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


def test_a_change_inside_an_internal_module_is_not_reported():
    """The tier is read from the *old* side: what was never promised cannot break."""
    before = _with(
        modules={
            "qgis_sdk.adapters.qt": {
                "tier": "internal",
                "names": {"Helper": "()", "Gone": "()"},
            }
        }
    )
    after = _with(
        modules={
            "qgis_sdk.adapters.qt": {
                "tier": "internal",
                "names": {"Helper": "(width: int)"},
            }
        }
    )

    assert diff(before, after) == []


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


def test_a_removal_announced_inside_a_module_that_is_gone_is_still_early():
    """The names are compared inside the module; a vanished module loses them all."""
    mark = {
        "module": "qgis_sdk.ui",
        "name": "Dialog",
        "since": "0.12.0",
        "removal": "1.0.0",
        "use": "",
    }
    marked = _with(deprecations=[mark])

    assert early_removals(marked, _with(modules={}, deprecations=[]), "0.13.0")


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


def _marked_probe(monkeypatch, module_name: str = "qgis_sdk.probe"):
    """A module holding one deprecated name, registered under ``module_name``."""
    import sys
    import types

    from qgis_sdk import deprecation

    @deprecation.deprecated(since="0.12.0", removal="1.0.0", use="Panel")
    def OldPanel() -> str:
        """A retired panel."""
        return "panel"

    probe = types.ModuleType(module_name)
    probe.OldPanel = OldPanel
    probe.__all__ = ["OldPanel"]
    monkeypatch.setitem(sys.modules, module_name, probe)
    return probe, OldPanel


def test_the_document_records_a_mark_where_the_checker_reads_it(monkeypatch):
    """The inventory and `check` read the same marks off the same modules."""
    from qgis_sdk import deprecation
    from qgis_sdk_tools.api import _inventory
    from qgis_sdk_tools.check.api import _table, deprecated_names

    name = "qgis_sdk.probe"
    _, marked = _marked_probe(monkeypatch, name)
    monkeypatch.setattr(_table, "PUBLIC_MODULES", (name,))
    monkeypatch.setattr(_inventory, "PUBLIC_MODULES", (name,))

    assert deprecated_names() == {
        (name, "OldPanel"): deprecation.deprecation_of(marked)
    }
    assert _inventory._deprecations() == [
        {
            "module": name,
            "name": "OldPanel",
            "since": "0.12.0",
            "removal": "1.0.0",
            "use": "Panel",
        }
    ]


def test_a_tier_without_a_declaration_is_read_from_where_the_module_lives():
    """No `__stability__`, so the prefix decides: the internal trees are internal."""
    import types

    from qgis_sdk_tools.api import _inventory

    plain = types.SimpleNamespace()
    assert _inventory._tier(plain, "qgis_sdk.ui") == "stable"
    assert _inventory._tier(plain, "qgis_sdk.adapters.qt") == "internal"
    declared = types.SimpleNamespace(__stability__="evolving")
    assert _inventory._tier(declared, "qgis_sdk.ui") == "evolving"


def test_a_written_inventory_round_trips_and_an_unknown_version_is_refused(tmp_path):
    from qgis_sdk_tools.api import read, write

    nested = tmp_path / "api" / "python.json"
    write(BASE, nested)

    assert read(nested) == BASE
    assert json.loads(nested.read_text(encoding="utf-8")) == BASE
    nested.write_text(json.dumps({**BASE, "api_version": 99}), encoding="utf-8")
    with pytest.raises(ValueError, match="api_version 99"):
        read(nested)


def test_a_change_prints_as_a_line_and_as_a_record():
    from qgis_sdk_tools.api import Change

    change = Change("additive", "qgis_sdk.ui", "ScrollArea")

    assert change.line() == "additive    qgis_sdk.ui: ScrollArea"
    assert change.to_json() == {
        "kind": "additive",
        "where": "qgis_sdk.ui",
        "detail": "ScrollArea",
    }


def test_a_removed_module_loses_every_name_it_carried():
    """Nothing to compare against, so every name it had counts as gone."""
    gone = _with(modules={})
    changes = diff(BASE, gone)

    assert sorted(change.detail for change in changes) == [
        "removed Button",
        "removed Dialog",
    ]
    assert {change.kind for change in changes} == {"breaking"}


def test_a_change_is_described_by_the_version_it_would_need():
    from qgis_sdk_tools.api import consequence

    assert "major" in consequence("breaking", "1.1.0")
    assert "minor" in consequence("deprecating", "0.12.0")
    assert "minor or patch" in consequence("additive", "0.12.0")
    assert consequence("none", "0.12.0") == "0.12.0: no change to the public API"


def test_an_unbalanced_bracket_leaves_the_annotation_as_the_source_wrote_it():
    """A truncated `Optional[` is not a union the rewriter can prove, so it stops."""
    from qgis_sdk_tools.api import _signatures

    assert _signatures._matching("Optional[int", 8) == -1
    assert _signatures._expand("Optional[int") == "Optional[int"


def test_a_signature_read_through_annotationlib_falls_back_when_it_refuses(monkeypatch):
    """3.14's `Format.STRING` path, and the fallback for what it will not take."""
    import types

    from qgis_sdk_tools.api import _signatures

    monkeypatch.setattr(_signatures, "_Format", types.SimpleNamespace(STRING=object()))

    def describe(width: int = 3) -> str:
        return ""

    assert _signatures._read_signature(describe).parameters["width"].default == 3
    with pytest.raises(TypeError):
        _signatures._read_signature(3)

    # The other side of the same branch, on the interpreters that have no
    # `Format` to ask for. Pinning it means both paths are read on every
    # version rather than whichever one the runner happens to be.
    monkeypatch.setattr(_signatures, "_Format", None)
    assert _signatures._read_signature(describe).parameters["width"].default == 3
    assert _signatures.signature_of(3) == ""


def test_the_api_commands_write_the_inventory_and_print_the_tier_table(tmp_path):
    """`qgis-sdk api dump` and `api stability`, over the real tree."""
    from qgis_sdk_tools.__main__ import app
    from qgis_sdk_tools.testing import FakeCliRuntime
    from typer.testing import CliRunner

    runtime = FakeCliRuntime(cwd=tmp_path)
    result = CliRunner().invoke(app, ["api", "dump"], obj=runtime)

    assert result.exit_code == 0, runtime.stderr + result.output
    written = tmp_path / "api" / "python.json"
    assert written.is_file()
    summary = inventory().document()
    names = sum(len(entry["names"]) for entry in summary["modules"].values())
    assert f"{len(summary['modules'])} modules, {names} names" in runtime.stdout

    table = FakeCliRuntime(cwd=tmp_path)
    shown = CliRunner().invoke(app, ["api", "stability"], obj=table)

    assert shown.exit_code == 0, table.stderr + shown.output
    assert "qgis_sdk.ui" in table.stdout
    assert "| stable |" in table.stdout

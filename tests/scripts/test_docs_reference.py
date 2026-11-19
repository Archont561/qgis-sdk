"""The scope of the generated Python reference (decision-86).

Two things are worth a test here, and neither of them needs Fumero installed.

* **The scope is the inventory.** The reference documents the modules
  `api/python.json` publishes, and it must keep doing that when a module is
  added to the package: a module that is rendered is a page, and a module the
  walk is not allowed into is a gap nobody sees. So the list is read from the
  committed inventory rather than from the tree.
* **The gap is counted.** Fumero renders a parameter list whether or not the
  docstring describes the parameters, so the undescribed ones are only visible
  if something counts them. `main` prints that count; this holds the counting.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from automation.docs import reference


def test_the_scope_is_every_module_the_inventory_publishes() -> None:
    modules = reference.published_modules()

    inventory = json.loads(reference.INVENTORY.read_text(encoding="utf-8"))
    assert modules == tuple(sorted(inventory["modules"]))
    assert modules == tuple(sorted(set(modules))), "a module is documented once"
    assert all(name == "qgis_sdk" or name.startswith("qgis_sdk.") for name in modules)


def test_the_walk_is_opened_only_for_published_modules() -> None:
    published = set(reference.published_modules())

    for name in reference.SKIPPED:
        assert f"qgis_sdk.{name}" not in published, (
            f"{name} is excluded from the walk and must not be published either"
        )


def test_every_exclusion_pattern_covers_a_whole_subtree() -> None:
    patterns = reference.exclude_patterns(("adapters", "bridge"))

    assert patterns == ("qgis_sdk.adapters*", "qgis_sdk.bridge*")


def test_the_group_wrapper_is_not_counted_as_a_parameter(tmp_path: Path) -> None:
    page = tmp_path / "index.mdx"
    page.write_text(
        "<PdxParameters>\n"
        '<PdxParameter name={"a"} type={"str"}>\n\nA described parameter.\n\n</PdxParameter>\n'
        "</PdxParameters>\n",
        encoding="utf-8",
    )

    assert reference.undescribed_parameters([page]) == (0, 1)


def test_a_parameter_with_no_description_is_counted(tmp_path: Path) -> None:
    page = tmp_path / "index.mdx"
    page.write_text(
        '<PdxParameter name={"a"} type={"str"}>\n\nA described parameter.\n\n</PdxParameter>\n'
        '<PdxParameter name={"b"} type={"int"}>\n\n</PdxParameter>\n'
        '<PdxParameter name={"c"} type={"int"} value={"3"}>\n\n</PdxParameter>\n',
        encoding="utf-8",
    )

    assert reference.undescribed_parameters([page]) == (2, 3)


def test_a_page_with_no_parameters_counts_nothing(tmp_path: Path) -> None:
    page = tmp_path / "index.mdx"
    page.write_text("# A module\n\nProse only.\n", encoding="utf-8")

    assert reference.undescribed_parameters([page]) == (0, 0)


def test_a_published_signature_replaces_the_one_record_parameter() -> None:
    pytest.importorskip("griffe")
    import inspect

    signature = inspect.Signature(
        [
            inspect.Parameter(
                "x", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=float
            ),
            inspect.Parameter(
                "label",
                inspect.Parameter.KEYWORD_ONLY,
                annotation=str | None,
                default=None,
            ),
        ]
    )

    built = reference._runtime_parameters(signature)

    assert [(parameter.name, parameter.annotation) for parameter in built] == [
        ("x", "float"),
        ("label", "str | None"),
    ]
    assert built[1].default == "None"
    assert built[1].kind.value == "keyword-only"

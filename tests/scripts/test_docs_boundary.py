"""Keeps implementation-only names out of the code a plugin author copies.

decision-56 gives the public surface a tier; TASK-139 gives the documentation the
same boundary. A reader who copies `from qgis_sdk.adapters.desktop import host`
out of a getting-started page treats it as an interface, pins it, and files a bug
when 1.0 moves it.

Two rules, because prose and snippets do different work:

* **A fenced code block is a template.** Anything it imports or calls must be a
  name the inventory carries, or be listed in :data:`INTERNAL_IN_SNIPPETS` with
  the reason it is there - the "explicit reviewable allowlist" of TASK-139 AC 4.
* **Prose may name an internal.** The pages explain where names moved, what the
  bridge does behind a host, and which adapter the framework calls on a reader's
  behalf; hiding those names would make the reference half of the package guide
  useless. What it must not do is present them as the authoring API, which the
  Stability section states and the test below reads.

The boundary is not re-declared here. It is read from the committed inventory -
the same document `release verify-api` diffs between releases - so a module that
leaves the public list leaves the documentation's promise with it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

INVENTORY = ROOT / "api" / "python.json"
TS_PACKAGE = ROOT / "packages" / "qgis-sdk-typescript" / "package.json"
PYTHON_GUIDE = (
    ROOT / "apps" / "docs" / "guides" / "doc-12 - qgis-sdk-Python-package-guide.md"
)

# The hand-written site, plus the two guide sources the site renders for users.
USER_FACING = (
    *sorted((ROOT / "apps" / "docs" / "content" / "docs").rglob("*.md")),
    *sorted((ROOT / "apps" / "docs" / "content" / "docs").rglob("*.mdx")),
    PYTHON_GUIDE,
    ROOT / "apps" / "docs" / "guides" / "doc-13 - qgis-sdk-TypeScript-package-guide.md",
    ROOT / "README.md",
)

FENCE = re.compile(r"^```[^\n]*\n(.*?)^```", re.DOTALL | re.MULTILINE)
PYTHON_NAME = re.compile(r"\bqgis_sdk(?:\.[a-zA-Z_][a-zA-Z0-9_]*)+")
TS_IMPORT = re.compile(r"@archont561/qgis-sdk(?:/[a-z]+)?")

# Every internal Python module a user-facing snippet reaches into, and why. A
# reference is allowed when it is the module or a name below it; the reason is
# what a reviewer reads when a new entry is proposed.
INTERNAL_IN_SNIPPETS = {
    "qgis_sdk.adapters": (
        "the layer a plugin author writes against when they bring their own host "
        "or read the transport; doc-12's Stability section says it may change"
    ),
    "qgis_sdk.bridge": (
        "the host half of the wire protocol, shown where a plugin registers the "
        "operations a web view calls (decision-56 calls the inside internal)"
    ),
}


def _sources() -> list[tuple[str, str]]:
    """Every user-facing page, as ``(repository-relative path, text)``."""
    return [
        (path.relative_to(ROOT).as_posix(), path.read_text(encoding="utf-8"))
        for path in USER_FACING
        if path.is_file()
    ]


def _public_python() -> set[str]:
    """The inventory's modules, plus every name each of them exports."""
    document = json.loads(INVENTORY.read_text(encoding="utf-8"))
    public = set(document["modules"])
    for module, entry in document["modules"].items():
        public |= {f"{module}.{name}" for name in entry["names"]}
    return public


def _references(text: str) -> set[str]:
    """Every `qgis_sdk...` dotted path in ``text``, as written."""
    return {match.group(0) for match in PYTHON_NAME.finditer(text)}


def _snippets(text: str) -> set[str]:
    """The references that appear inside a fenced code block."""
    return set().union(*(_references(block) for block in FENCE.findall(text)), set())


def _allowed(reference: str) -> bool:
    """A reference the allowlist covers, whole or by the module it reaches into."""
    return any(
        reference == module or reference.startswith(f"{module}.")
        for module in INTERNAL_IN_SNIPPETS
    )


def _is_dunder(reference: str) -> bool:
    """`qgis_sdk.__all__` is a documented module attribute, not an internal API."""
    return reference.split(".", 1)[-1].startswith("__")


def _internal(references: set[str], public: set[str]) -> set[str]:
    """The references that are neither a public module, a public name, nor allowed."""
    return {
        reference
        for reference in references
        if reference not in public
        and not _is_dunder(reference)
        and not _allowed(reference)
    }


def test_the_page_set_is_what_the_boundary_claims_to_cover():
    """A gate over an empty set of pages passes for the wrong reason."""
    sources = _sources()

    assert len(sources) >= 10
    assert any(name.startswith("apps/docs/content/docs/start/") for name, _ in sources)
    assert any("doc-13" in name for name, _ in sources)


def test_no_snippet_copies_a_python_name_the_inventory_does_not_carry():
    public = _public_python()
    leaks = {
        name: sorted(_internal(_snippets(text), public)) for name, text in _sources()
    }

    assert not {name: found for name, found in leaks.items() if found}, (
        "internal Python names in snippets a reader copies; either use the public "
        "name or add the module to INTERNAL_IN_SNIPPETS with its reason"
    )


def test_every_allowlisted_module_is_still_reached_by_a_snippet():
    """An allowlist entry nothing uses is a claim about a page that changed."""
    reached = set().union(*(_snippets(text) for _, text in _sources()))

    assert set(INTERNAL_IN_SNIPPETS) <= {
        module
        for module in INTERNAL_IN_SNIPPETS
        if _allowed(module)
        and any(
            reference == module or reference.startswith(f"{module}.")
            for reference in reached
        )
    }


def test_every_typescript_subpath_import_is_a_declared_export():
    exports = json.loads(TS_PACKAGE.read_text(encoding="utf-8"))["exports"]
    declared = {"@archont561/qgis-sdk"}
    declared |= {
        f"@archont561/qgis-sdk/{subpath.removeprefix('./')}"
        for subpath in exports
        if subpath != "."
    }
    imported = {found for _, text in _sources() for found in TS_IMPORT.findall(text)}

    assert imported <= declared, (
        "user-facing documentation imports a subpath the TypeScript package does "
        "not declare in `exports`: " + ", ".join(sorted(imported - declared))
    )


def test_the_boundary_is_stated_where_a_reader_meets_the_tiers():
    """The gates above are only honest if the pages say what they promise."""
    guide = PYTHON_GUIDE.read_text(encoding="utf-8")
    stability = guide[guide.index("## Stability") : guide.index("## Declarations")]

    assert "internal" in stability.lower()
    for module in ("qgis_sdk.adapters", "qgis_sdk.bridge", "qgis_sdk.core"):
        assert f"`{module}`" in stability, module


@pytest.mark.parametrize(
    "reference",
    ["qgis_sdk.core._loop", "qgis_sdk.cli._app", "qgis_sdk.devtools._serve"],
)
def test_a_new_internal_reference_is_reported_by_name(reference):
    """The message a failure produces has to say which name and which page."""
    public = _public_python()
    text = f"```python\nimport {reference}\n```\n"

    assert _internal(_snippets(text), public) == {reference}

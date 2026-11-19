"""Generate the Python reference the documentation site renders (decision-86).

The reference is read out of the package rather than written by hand: `fumero`
loads the published surface with `griffe`, takes every signature and default
from the source, and takes the prose from the docstrings. One page per module
and one per class, under `apps/docs/content/docs/reference/python/`, which is
gitignored like the rest of the generated content.

Three things are worth knowing before changing this module.

**The scope comes from the inventory, not from `__all__`.** `qgis_sdk/__init__.py`
holds a ten-name `__all__`, and fumero reads that as the documentation boundary:
it decides which names are public, and it stops the walk from descending into a
submodule the package does not name. The reference documents the module tree the
inventory publishes instead - 22 modules - so the walk is opened up and the
modules beside it are excluded by name. The inventory is committed and
drift-checked (`api/python.json`), so the surface the reference covers is the
same one the per-tag diff and the freshness check read.

**Undescribed parameters are counted, not hidden.** Fumero renders the parameter
list of every documented function whether or not the docstring describes the
parameters, which is the honest rendering: the signature is real and the prose is
missing. This module counts the gap and prints it, because the number is what the
docstring pass in decision-86 has to move, and it is invisible in a green build.

**The output is a build product.** Nothing here is committed, so a checkout
without this step renders the hand-written reference pages and reports the gap
itself (`scripts/generate.ts` omits the section when the folder is missing).

Usage:
    python -m automation.docs.reference
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from automation.lib.shell import ROOT

INVENTORY = ROOT / "api" / "python.json"
"""The committed inventory, which is what says which modules are public."""

OUTPUT = ROOT / "apps" / "docs" / "content" / "docs" / "reference" / "python"
"""Where the pages go. Gitignored: `/content/docs/reference/*` in apps/docs."""

BASE_URL = "/reference/python"
"""The URL the output is served at, which is what the links between pages use."""

SKIPPED = ("_published", "layouts", "adapters", "bridge", "resources")
"""The top-level modules beside the published ones.

Fumero needs the whole tree loaded to build one link table across it, and the
walk descends into every submodule it is shown. These are the ones the site does
not publish - the adapter layer, the transport, the resource tree and the private
entry point - so the walk is not allowed into them.
"""


def published_modules(inventory: Path = INVENTORY) -> tuple[str, ...]:
    """The module paths the inventory publishes, sorted.

    Args:
        inventory: The committed `api/python.json`.

    Returns:
        Every module path it names, such as `qgis_sdk.declarations`.
    """

    return tuple(sorted(json.loads(inventory.read_text(encoding="utf-8"))["modules"]))


def exclude_patterns(skipped: tuple[str, ...] = SKIPPED) -> tuple[str, ...]:
    """Fumero's glob patterns for the modules the reference does not publish.

    Matched against a dotted path and a short name, so the trailing `*` is what
    keeps a module out together with everything under it.

    Args:
        skipped: The top-level module names to leave out.

    Returns:
        One pattern per name.
    """

    return tuple(f"qgis_sdk.{name}*" for name in skipped)


def undescribed_parameters(pages: list[Path]) -> tuple[int, int]:
    """How many rendered parameters have no description, and how many there are.

    A `<PdxParameter>` whose body is empty is a signature row the docstring says
    nothing about. Counted from the rendered pages rather than from the source so
    the number is what a reader sees.

    Args:
        pages: The `.mdx` files a run wrote.

    Returns:
        The undescribed count and the total.
    """

    empty = 0
    total = 0
    for page in pages:
        text = page.read_text(encoding="utf-8")
        for block in text.split("<PdxParameter")[1:]:
            total += 1
            body = block.split(">", 1)[1].split("</PdxParameter>", 1)[0]
            if not body.strip():
                empty += 1
    return empty, total


def main() -> int:
    """Write the reference into the content collection.

    Returns:
        `0` when every page was written and every internal link resolved, `1`
        otherwise. An unresolved link is a docstring naming an item that has no
        page, which is a typo rather than a missing feature.
    """

    # Imported here so the module can be imported - by a test, or by a caller
    # that only wants `published_modules` - without Fumero installed.
    import fumero

    config = fumero.Config(
        output=OUTPUT,
        base_url=BASE_URL,
        no_inspect=True,
        clean=True,
        with_meta=True,
        exclude=exclude_patterns(),
    )

    shutil.rmtree(OUTPUT, ignore_errors=True)
    root = fumero.load_module("qgis_sdk", config)
    # The star-import list, which fumero would otherwise take for the
    # documentation boundary. See the module docstring.
    root.exports = None

    result = fumero.Renderer(config).render(root, OUTPUT)
    missing, total = undescribed_parameters(result.pages)

    _ = (OUTPUT / "meta.json").write_text(
        json.dumps({"title": "Python API", "pages": ["qgis_sdk"]}, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        f"reference: {len(result.pages)} pages in {len(published_modules())} modules "
        f"({missing} of {total} parameters have no description)"
    )
    for link in result.unresolved:
        print(f"reference: {link}")

    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

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

import importlib
import inspect
import json
import re
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from automation.lib.shell import ROOT

if TYPE_CHECKING:
    import fumero

INVENTORY = ROOT / "api" / "python.json"
"""The committed inventory, which is what says which modules are public."""

OUTPUT = ROOT / "apps" / "docs" / "content" / "docs" / "reference" / "python"
"""Where the pages go. Gitignored: `/content/docs/reference/*` in apps/docs."""

BASE_URL = "/reference/python"
"""The URL the output is served at, which is what the links between pages use."""

EMPTY = inspect.Parameter.empty
"""What `inspect` answers for a parameter with no annotation, or with no default."""

RECORD = "_published_values"
"""The parameter a `@published` implementation takes instead of its own.

Several published functions take one record and have the real parameter list
installed on a wrapper (`qgis_sdk/_published.py`). Griffe reads the `def` line,
so without this the reference would document `_published_values` - a name no
author can pass - for every one of them.
"""

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


PARAMETER = re.compile(r"<PdxParameter\s[^>]*>(.*?)</PdxParameter>", re.DOTALL)
"""One rendered parameter and its description.

Anchored on the whitespace after the tag name, because `<PdxParameters>` opens
the group that holds them. Splitting on the bare `<PdxParameter` counts the
wrapper as a parameter with no description, which reads as a gap in the
docstrings that is not there.
"""


def undescribed_parameters(pages: list[Path]) -> tuple[int, int]:
    """How many rendered parameters have no description, and how many there are.

    A parameter whose body is empty is a signature row the docstring says
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
        bodies = PARAMETER.findall(text)
        total += len(bodies)
        empty += sum(1 for body in bodies if not body.strip())
    return empty, total


def _runtime_parameters(signature: inspect.Signature) -> list[object]:
    """Rebuild griffe's parameters from the published signature."""

    import griffe

    kinds = {
        inspect.Parameter.POSITIONAL_ONLY: griffe.ParameterKind.positional_only,
        inspect.Parameter.POSITIONAL_OR_KEYWORD: griffe.ParameterKind.positional_or_keyword,
        inspect.Parameter.VAR_POSITIONAL: griffe.ParameterKind.var_positional,
        inspect.Parameter.KEYWORD_ONLY: griffe.ParameterKind.keyword_only,
        inspect.Parameter.VAR_KEYWORD: griffe.ParameterKind.var_keyword,
    }
    built = []
    for parameter in signature.parameters.values():
        built.append(
            griffe.Parameter(
                parameter.name,
                annotation=(
                    None
                    if parameter.annotation is EMPTY
                    else inspect.formatannotation(parameter.annotation)
                ),
                kind=kinds[parameter.kind],
                default=None if parameter.default is EMPTY else repr(parameter.default),
            )
        )
    return built


def _runtime_object(path: str) -> object:
    """The object a dotted path names, imported.

    Args:
        path: A dotted path below the package, such as
            `qgis_sdk.models.canvas.CanvasExtent.from_bounds`.

    Returns:
        What `getattr` finds there.
    """

    parts = path.split(".")
    for split in range(len(parts), 0, -1):
        try:
            module = importlib.import_module(".".join(parts[:split]))
        except ImportError:
            continue
        found: object = module
        for name in parts[split:]:
            found = getattr(found, name)
        return found
    raise ImportError(path)


def _publish_signatures(root: object) -> int:
    """Put each `@published` function's real parameters back on its page.

    Args:
        root: The loaded package.

    Returns:
        How many signatures were replaced.
    """

    import griffe

    replaced = 0
    for function in _functions(root, griffe):
        if function.path.split(".")[1] in SKIPPED:
            # the adapter and transport layers import QGIS, and are not
            # published, so nothing is documented from them either.
            continue
        if [parameter.name for parameter in function.parameters] != [RECORD]:
            continue
        signature = inspect.signature(_runtime_object(function.path))
        function.parameters = griffe.Parameters(*_runtime_parameters(signature))
        replaced += 1
    return replaced


def _functions(owner: object, griffe: object) -> list[object]:
    """Every function in the tree, methods included.

    Args:
        owner: The module or class to walk.
        griffe: The module itself, passed in so this needs no import of its own.

    Returns:
        The functions, in tree order.
    """

    found: list[object] = []
    for member in owner.members.values():
        if isinstance(member, griffe.Alias):
            try:
                member = member.target
            except (griffe.AliasResolutionError, griffe.CyclicAliasError):
                continue
        if isinstance(member, (griffe.Module, griffe.Class)):
            found.extend(_functions(member, griffe))
        elif isinstance(member, griffe.Function):
            found.append(member)
    return found


def _render(config: fumero.Config) -> fumero.Result:
    """Load the published tree and write it, with one link table across the lot.

    Args:
        config: The `fumero.Config` the run was built with.

    Returns:
        Fumero's `Result`: the pages written and the links that resolved to
        nothing.
    """

    # Imported here so the module can be imported - by a test, or by a caller
    # that only wants `published_modules` - without Fumero installed.
    import fumero

    root = fumero.load_module("qgis_sdk", config)
    # The star-import list, which fumero would otherwise take for the
    # documentation boundary. See the module docstring.
    root.exports = None
    _ = _publish_signatures(root)

    return fumero.Renderer(config).render(root, OUTPUT)


def _write_meta() -> None:
    """Name the section, and say what is in it.

    Fumero writes a `meta.json` inside a module's own directory; this is the one
    for the folder the module pages sit in, which it does not own.
    """

    _ = (OUTPUT / "meta.json").write_text(
        json.dumps({"title": "Python API", "pages": ["qgis_sdk"]}, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _report(result: fumero.Result) -> int:
    """Print what the run wrote, and what it could not do.

    Args:
        result: Fumero's `Result`.

    Returns:
        `0` when every internal link resolved, `1` otherwise. An unresolved link
        is a docstring naming an item that has no page, which is a typo rather
        than a missing feature.
    """

    missing, total = undescribed_parameters(result.pages)
    print(
        f"reference: {len(result.pages)} pages in {len(published_modules())} modules "
        f"({missing} of {total} parameters have no description)"
    )
    for link in result.unresolved:
        print(f"reference: {link}")

    return 0 if result.ok else 1


def main() -> int:
    """Write the reference into the content collection.

    Returns:
        `0` when every page was written and every internal link resolved, `1`
        otherwise.
    """

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
    result = _render(config)
    _write_meta()

    return _report(result)


if __name__ == "__main__":
    raise SystemExit(main())

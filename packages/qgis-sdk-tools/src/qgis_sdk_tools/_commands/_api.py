"""``qgis-sdk api dump``: the public API of this tree, as one JSON document.

decision-56 point 2 makes a *generated* inventory the 1.0 contract, so the file
this command writes is meant to be committed next to the code it describes.
`release.py verify-api` diffs it against a tag; doc-12 renders the tiers from it.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Annotated

import typer

from qgis_sdk_tools._commands._app import app
from qgis_sdk_tools.api import inventory, write
from qgis_sdk_tools.cli import CliRuntime

api_app = typer.Typer(
    add_completion=False, help="Write the public API of this tree as JSON."
)
app.add_typer(api_app, name="api")

DEFAULT_INVENTORY = Path("api/python.json")
"""Where the inventory is tracked: `api/<scope>.json` at the repository root."""


def _summary(document: Mapping) -> str:
    """One line saying what was written, in counts a reviewer can diff."""
    modules = document["modules"]
    names = sum(len(entry["names"]) for entry in modules.values())
    return (
        f"{len(modules)} modules, {names} names, {len(document['rules'])} rules, "
        f"{len(document['host_operations'])} host operations, "
        f"{len(document['cli'])} CLI entries"
    )


@api_app.command("dump")
def dump(
    ctx: typer.Context,
    out: Annotated[
        Path, typer.Option("--out", help="Where to write the inventory.")
    ] = DEFAULT_INVENTORY,
) -> None:
    """Write public names and signatures, rule ids, host operations and the CLI.

    The document is deterministic - sorted, no timestamps, no absolute paths - so
    two dumps of one tree are byte-identical and a diff shows only what changed.
    That is what lets `release verify-api` compare two commits by comparing two
    files.
    """
    runtime: CliRuntime = ctx.obj
    document = inventory().document()
    target = runtime.resolve(out)
    write(document, target)
    typer.echo(f"{target}: {_summary(document)}", file=runtime.out)

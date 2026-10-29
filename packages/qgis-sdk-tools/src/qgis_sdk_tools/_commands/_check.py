"""``qgis-sdk check``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from qgis_sdk_tools._commands._app import app
from qgis_sdk_tools.check import QgisSdkCheckError, check_project
from qgis_sdk_tools.cli import CliRuntime


@app.command("check")
def check(
    ctx: typer.Context,
    path: Annotated[
        Path | None,
        typer.Argument(help="Plugin project root; defaults to the working directory."),
    ] = None,
    native: Annotated[
        list[str] | None,
        typer.Option(
            "--native",
            help="Module glob allowed to import QGIS at load time (repeatable).",
        ),
    ] = None,
    as_json: Annotated[
        bool, typer.Option("--json", help="Print the report as JSON.")
    ] = False,
    imports: Annotated[
        bool,
        typer.Option(
            "--imports",
            help="Print every import root with the bucket it sorts into.",
        ),
    ] = False,
) -> None:
    """Read a plugin project and report problems; import, install and change nothing."""
    runtime: CliRuntime = ctx.obj
    root = runtime.resolve(path or Path("."))
    try:
        report = check_project(root, native_modules=tuple(native or ()))
    except QgisSdkCheckError as error:
        typer.echo(str(error), file=runtime.err)
        raise typer.Exit(code=2) from error
    if as_json:
        typer.echo(json.dumps(report.to_json(), indent=2), file=runtime.out)
    else:
        for diagnostic in report.diagnostics:
            typer.echo(diagnostic.render(), file=runtime.out)
        if imports and report.imports is not None:
            listing = report.imports.render()
            if listing:
                typer.echo(listing, file=runtime.out)
        count = len(report.diagnostics)
        problems = (
            "no problems"
            if count == 0
            else f"{count} problem{'s' if count != 1 else ''}"
        )
        typer.echo(
            f"checked {report.files_checked} files: {problems}", file=runtime.out
        )
    if not report.ok:
        raise typer.Exit(code=1)

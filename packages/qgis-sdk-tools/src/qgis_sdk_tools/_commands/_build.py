"""``qgis-sdk build``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from qgis_sdk_tools._commands._app import app
from qgis_sdk_tools.bundle import (
    QgisSdkBuildError,
    QgisSdkBuildRefusedError,
    build_plugin,
)
from qgis_sdk_tools.cli import CliRuntime


@app.command("build")
def build(
    ctx: typer.Context,
    path: Annotated[
        Path | None,
        typer.Argument(help="Plugin project root; defaults to the working directory."),
    ] = None,
    out: Annotated[
        Path | None,
        typer.Option(help="Where to write the archive; defaults to <root>/dist."),
    ] = None,
    no_web: Annotated[
        bool,
        typer.Option(
            "--no-web",
            help="Do not run the web build; ship <plugin>/web as it is.",
        ),
    ] = False,
    as_json: Annotated[
        bool, typer.Option("--json", help="Print the result as JSON.")
    ] = False,
) -> None:
    """Check the project and write an installable plugin ZIP with the runtime inside."""
    runtime: CliRuntime = ctx.obj
    root = runtime.resolve(path or Path("."))
    try:
        result = build_plugin(
            root,
            out=None if out is None else runtime.resolve(out),
            web=not no_web,
            run=lambda argv, cwd: runtime.run_process(argv, cwd),
        )
    except QgisSdkBuildRefusedError as error:
        for diagnostic in error.diagnostics:
            typer.echo(diagnostic.render(), file=runtime.out)
        typer.echo(str(error), file=runtime.err)
        raise typer.Exit(code=1) from error
    except QgisSdkBuildError as error:
        typer.echo(str(error), file=runtime.err)
        raise typer.Exit(code=2) from error
    if as_json:
        typer.echo(json.dumps(result.to_json(), indent=2), file=runtime.out)
        return
    for diagnostic in result.report.diagnostics:
        typer.echo(diagnostic.render(), file=runtime.out)
    typer.echo(
        f"built {result.plugin} {result.version}: {result.archive} "
        f"({len(result.files)} files, runtime {result.runtime_version}, "
        f"web: {result.web})",
        file=runtime.out,
    )

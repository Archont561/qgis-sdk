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
from qgis_sdk_tools.bundle.app import build_app
from qgis_sdk_tools.cli import CliRuntime

#: ``--target``: the plugin ZIP QGIS installs, or an installable app distribution.
TARGETS = ("plugin", "app")


@app.command("build")
def build(
    ctx: typer.Context,
    path: Annotated[
        Path | None,
        typer.Argument(help="Plugin project root; defaults to the working directory."),
    ] = None,
    target: Annotated[
        str,
        typer.Option(
            help="plugin (default): the ZIP QGIS's Install-from-ZIP reads. "
            "app: a pip-installable distribution whose console script runs the "
            "application as a standalone PyQGIS app.",
        ),
    ] = "plugin",
    out: Annotated[
        Path | None,
        typer.Option(
            help="Where to write the archive or the distribution directory; "
            "defaults to <root>/dist."
        ),
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
    """Check the project and write what QGIS, or a launcher, installs and runs."""
    runtime: CliRuntime = ctx.obj
    root = runtime.resolve(path or Path())
    if target not in TARGETS:
        typer.echo(
            f"unknown target {target!r}; choose one of {', '.join(TARGETS)}",
            file=runtime.err,
        )
        raise typer.Exit(code=2)
    destination = None if out is None else runtime.resolve(out)
    run = lambda argv, cwd: runtime.run_process(argv, cwd)
    try:
        result = (
            build_app(root, out=destination, web=not no_web, run=run)
            if target == "app"
            else build_plugin(root, out=destination, web=not no_web, run=run)
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
    if target == "app":
        typer.echo(
            f"built {result.plugin} {result.version}: {result.directory} "
            f"({len(result.files)} files, runtime {result.runtime_version}, "
            f"web: {result.web}); install it with `pip install "
            f"{result.directory}` and run `{result.launcher}`",
            file=runtime.out,
        )
        return
    typer.echo(
        f"built {result.plugin} {result.version}: {result.archive} "
        f"({len(result.files)} files, runtime {result.runtime_version}, "
        f"web: {result.web})",
        file=runtime.out,
    )

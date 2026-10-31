"""``qgis-sdk run``: start the project as a standalone app, with the found QGIS."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Annotated

import typer

from qgis_sdk_tools._commands._app import app
from qgis_sdk_tools.cli import CliRuntime
from qgis_sdk_tools.devtools import QgisSdkQgisNotFoundError, find_qgis_install
from qgis_sdk_tools.devtools.dev import (
    QgisSdkDevError,
    inspect_project,
    plan_app,
)


@app.command("run")
def run(
    ctx: typer.Context,
    path: Annotated[
        Path | None,
        typer.Argument(help="Plugin project root; defaults to the working directory."),
    ] = None,
    headless: Annotated[
        bool,
        typer.Option(
            "--headless",
            help="No window: jobs, the project and the services still work, the UI "
            "is refused by name.",
        ),
    ] = False,
    once: Annotated[
        bool,
        typer.Option(
            "--once",
            help="Start, deliver what is already queued, stop - the smoke run a "
            "script or a CI job makes.",
        ),
    ] = False,
    grace: Annotated[
        float | None,
        typer.Option(
            help="Seconds shutdown waits for running jobs before abandoning them "
            "(default: the runtime's 15)."
        ),
    ] = None,
    title: Annotated[
        str | None,
        typer.Option(help="Window title; defaults to the application's own title."),
    ] = None,
    qgis_prefix: Annotated[
        Path | None, typer.Option(help="QGIS install prefix to run.")
    ] = None,
) -> None:
    """Run the plugin as a standalone PyQGIS app instead of inside QGIS.

    The app host owns the ``QgsApplication`` (decision-52 point 3): it starts the
    project's ``<plugin>/__main__.py`` through the discovered QGIS interpreter,
    with the SDK's own packages on that interpreter's path. Nothing is installed
    and nothing is written into the project; a project without an app entry runs
    through a generated probe, so a Desktop plugin can be tried as an app.
    """
    runtime: CliRuntime = ctx.obj
    root = runtime.resolve(path or Path())
    workspace = Path(tempfile.mkdtemp(prefix="qgis-sdk-run-"))
    try:
        try:
            project = inspect_project(root)
            install = find_qgis_install(runtime.env, prefix=qgis_prefix, project=root)
            plan = plan_app(
                project,
                install,
                env=runtime.env,
                workspace=workspace,
                gui=not headless,
                once=once,
                grace=grace,
                title=title,
            )
        except (QgisSdkDevError, QgisSdkQgisNotFoundError) as error:
            typer.echo(str(error), file=runtime.err)
            raise typer.Exit(code=2) from error
        for note in plan.notes:
            typer.echo(note, file=runtime.err)
        exit_code = runtime.run_process(plan.argv, plan.cwd, plan.env)
    finally:
        # The generated probe lives here, so the workspace is removed only once
        # the app has exited - never before the process that reads it.
        shutil.rmtree(workspace, ignore_errors=True)
    if exit_code == 127:
        typer.echo(f"{plan.argv[0]} was not found", file=runtime.err)
    raise typer.Exit(code=exit_code)

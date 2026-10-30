"""``qgis-sdk dev``."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Annotated

import typer

from qgis_sdk_tools._commands._app import app
from qgis_sdk_tools.cli import CliRuntime
from qgis_sdk_tools.devtools import (
    QgisSdkQgisNotFoundError,
    find_qgis_install,
    wants_headless,
)
from qgis_sdk_tools.devtools.dev import (
    MODES,
    QgisSdkDevError,
    free_port,
    inspect_project,
    plan_dev,
    plan_web_server,
    wait_for_port,
)


@app.command("dev")
def dev(
    ctx: typer.Context,
    path: Annotated[
        Path | None,
        typer.Argument(help="Plugin project root; defaults to the working directory."),
    ] = None,
    mode: Annotated[
        str,
        typer.Option(
            "--mode",
            "--host",
            help="desktop (default: real QGIS Desktop, isolated profile, Reload), "
            "standalone (bare QgsApplication: no iface, no lifecycle) or "
            "server (a local QgsServer loop on loopback that reloads on save).",
        ),
    ] = "desktop",
    qgis_prefix: Annotated[
        Path | None, typer.Option(help="QGIS install prefix to run.")
    ] = None,
    no_web: Annotated[
        bool,
        typer.Option(
            "--no-web", help="Do not start the Vite dev server; serve web/ as built."
        ),
    ] = False,
    port: Annotated[
        int | None,
        typer.Option(
            help="Loopback port: the Vite dev server, or the server loop in "
            "--mode server (defaults to a free port)."
        ),
    ] = None,
    no_watch: Annotated[
        bool,
        typer.Option(
            "--no-watch",
            help="Do not reload on saved Python changes; "
            "only the Reload button (Ctrl+Shift+R) reloads.",
        ),
    ] = False,
    exercise: Annotated[
        Path | None, typer.Option(hidden=True, help="Self-drive and write a report.")
    ] = None,
) -> None:
    """Run the source plugin inside QGIS, reloading on save, with HMR for a web UI."""
    runtime: CliRuntime = ctx.obj
    root = runtime.resolve(path or Path())
    try:
        if mode not in MODES:
            raise QgisSdkDevError(
                f"unknown mode {mode!r}; choose one of {', '.join(MODES)}"
            )
        project = inspect_project(root)
        install = find_qgis_install(runtime.env, prefix=qgis_prefix, project=root)
        chosen_port = port or free_port()
        # A server plugin has no page (HOST001 keeps one out of a server-only
        # project), so the server mode never starts Vite.
        server_plan = (
            None
            if no_web or mode == "server"
            else plan_web_server(project, chosen_port)
        )
    except (QgisSdkDevError, QgisSdkQgisNotFoundError) as error:
        typer.echo(str(error), file=runtime.err)
        raise typer.Exit(code=2) from error
    workspace = Path(tempfile.mkdtemp(prefix="qgis-sdk-dev-"))
    server = None
    origin = None
    try:
        if server_plan is not None:
            shown = " ".join(server_plan.argv)
            typer.echo(f"web: {shown} in web/", file=runtime.err)
            server = runtime.start_process(
                server_plan.argv, server_plan.cwd, runtime.env
            )
            if server is None:
                typer.echo(
                    f"{server_plan.argv[0]} was not found; install it or pass --no-web",
                    file=runtime.err,
                )
                raise typer.Exit(code=2)
            if not wait_for_port(
                server_plan.port, still_running=lambda: server.poll() is None
            ):
                typer.echo(
                    f"the dev server did not answer on {server_plan.origin}; see its "
                    "output above, or pass --no-web to run without it",
                    file=runtime.err,
                )
                raise typer.Exit(code=2)
            origin = server_plan.origin
            typer.echo(f"web: {origin} (hot module replacement)", file=runtime.err)
        plan = plan_dev(
            project,
            mode,
            install,
            env=runtime.env,
            workspace=workspace,
            headless=wants_headless(runtime.env),
            dev_server=origin,
            exercise=exercise,
            watch=not no_watch,
            port=chosen_port,
        )
        for note in plan.notes:
            typer.echo(note, file=runtime.err)
        exit_code = runtime.run_process(plan.argv, plan.cwd, plan.env)
    except QgisSdkDevError as error:
        typer.echo(str(error), file=runtime.err)
        raise typer.Exit(code=2) from error
    finally:
        if server is not None and server.poll() is None:
            server.terminate()
            server.wait(timeout=10)
        shutil.rmtree(workspace, ignore_errors=True)
    if exit_code == 127:
        typer.echo(f"{plan.argv[0]} was not found", file=runtime.err)
    raise typer.Exit(code=exit_code)

"""``qgis-sdk dev``."""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
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

_PathArg = Annotated[
    Path | None,
    typer.Argument(help="Plugin project root; defaults to the working directory."),
]
_ModeOpt = Annotated[
    str,
    typer.Option(
        "--mode",
        "--host",
        help="desktop (default: real QGIS Desktop, isolated profile, Reload), "
        "standalone (bare QgsApplication: no iface, no lifecycle) or "
        "server (a local QgsServer loop on loopback that reloads on save).",
    ),
]
_PrefixOpt = Annotated[Path | None, typer.Option(help="QGIS install prefix to run.")]
_NoWebOpt = Annotated[
    bool,
    typer.Option(
        "--no-web", help="Do not start the Vite dev server; serve web/ as built."
    ),
]
_PortOpt = Annotated[
    int | None,
    typer.Option(
        help="Loopback port: the Vite dev server, or the server loop in "
        "--mode server (defaults to a free port)."
    ),
]
_NoWatchOpt = Annotated[
    bool,
    typer.Option(
        "--no-watch",
        help="Do not reload on saved Python changes; "
        "only the Reload button (Ctrl+Shift+R) reloads.",
    ),
]
_ExerciseOpt = Annotated[
    Path | None, typer.Option(hidden=True, help="Self-drive and write a report.")
]


@dataclass(frozen=True, slots=True)
class _DevOptions:
    """The resolved ``dev`` knobs, as one record."""

    path: Path | None
    mode: str
    qgis_prefix: Path | None
    no_web: bool
    port: int | None
    no_watch: bool
    exercise: Path | None


@dataclass(frozen=True, slots=True)
class _DevSetup:
    """What discovery and the free-port choice produced before any process."""

    root: Path
    project: object
    install: object
    chosen_port: int
    server_plan: object | None


def _dev_setup(runtime: CliRuntime, options: _DevOptions, root: Path) -> _DevSetup:
    """Validate the mode and discover the project, QGIS install and free port."""
    if options.mode not in MODES:
        raise QgisSdkDevError(
            f"unknown mode {options.mode!r}; choose one of {', '.join(MODES)}"
        )
    project = inspect_project(root)
    install = find_qgis_install(runtime.env, prefix=options.qgis_prefix, project=root)
    chosen_port = options.port or free_port()
    # A server plugin has no page (HOST001 keeps one out of a server-only
    # project), so the server mode never starts Vite.
    server_plan = (
        None
        if options.no_web or options.mode == "server"
        else plan_web_server(project, chosen_port)
    )
    return _DevSetup(root, project, install, chosen_port, server_plan)


def _start_web(runtime: CliRuntime, server_plan):
    """Start Vite, wait for its port, and return the process and origin."""
    if server_plan is None:
        return None, None
    shown = " ".join(server_plan.argv)
    typer.echo(f"web: {shown} in web/", file=runtime.err)
    server = runtime.start_process(server_plan.argv, server_plan.cwd, runtime.env)
    if server is None:
        typer.echo(
            f"{server_plan.argv[0]} was not found; install it or pass --no-web",
            file=runtime.err,
        )
        raise typer.Exit(code=2)
    if not wait_for_port(server_plan.port, still_running=lambda: server.poll() is None):
        typer.echo(
            f"the dev server did not answer on {server_plan.origin}; see its "
            "output above, or pass --no-web to run without it",
            file=runtime.err,
        )
        server.terminate()
        server.wait(timeout=10)
        raise typer.Exit(code=2)
    typer.echo(f"web: {server_plan.origin} (hot module replacement)", file=runtime.err)
    return server, server_plan.origin


def _dev_plan(
    runtime: CliRuntime,
    options: _DevOptions,
    setup: _DevSetup,
    workspace: Path,
    origin: str | None,
):
    """The QGIS process this run will execute."""
    return plan_dev(
        setup.project,
        options.mode,
        setup.install,
        env=runtime.env,
        workspace=workspace,
        headless=wants_headless(runtime.env),
        dev_server=origin,
        exercise=options.exercise,
        watch=not options.no_watch,
        port=setup.chosen_port,
    )


def _run_dev(runtime: CliRuntime, options: _DevOptions) -> int:
    """Discover, run, and always stop the dev server and remove the workspace."""
    root = runtime.resolve(options.path or Path())
    try:
        setup = _dev_setup(runtime, options, root)
    except (QgisSdkDevError, QgisSdkQgisNotFoundError) as error:
        typer.echo(str(error), file=runtime.err)
        raise typer.Exit(code=2) from error
    workspace = Path(tempfile.mkdtemp(prefix="qgis-sdk-dev-"))
    server = None
    plan = None
    try:
        server, origin = _start_web(runtime, setup.server_plan)
        plan = _dev_plan(runtime, options, setup, workspace, origin)
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
    if exit_code == 127 and plan is not None:
        typer.echo(f"{plan.argv[0]} was not found", file=runtime.err)
    return exit_code


@app.command("dev")
def dev(
    ctx: typer.Context,
    path: _PathArg = None,
    mode: _ModeOpt = "desktop",
    qgis_prefix: _PrefixOpt = None,
    no_web: _NoWebOpt = False,
    port: _PortOpt = None,
    no_watch: _NoWatchOpt = False,
    exercise: _ExerciseOpt = None,
) -> None:
    """Run the source plugin inside QGIS, reloading on save, with HMR for a web UI."""
    options = _DevOptions(path, mode, qgis_prefix, no_web, port, no_watch, exercise)
    raise typer.Exit(code=_run_dev(ctx.obj, options))

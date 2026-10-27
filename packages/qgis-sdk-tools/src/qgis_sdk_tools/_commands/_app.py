"""The Typer applications, the runtime callback and the shared install lookup."""

from __future__ import annotations

from pathlib import Path

import typer

from qgis_sdk_tools.cli import CliRuntime
from qgis_sdk_tools.scaffold import (
    ScaffoldOptions,
)
from qgis_sdk_tools.scaffold.web import (
    install_command,
)

app = typer.Typer(
    add_completion=False,
    help="Generate and inspect qgis-sdk plugin projects.",
)
bridge_app = typer.Typer(
    add_completion=False,
    help="Generate the TypeScript side of a plugin's bridge contract.",
)
app.add_typer(bridge_app, name="bridge")
processing_app = typer.Typer(
    add_completion=False,
    help="Generate the typed Processing catalogue of a project's QGIS.",
)
app.add_typer(processing_app, name="processing")


@app.callback()
def _callback(ctx: typer.Context) -> None:
    """Keep ``new`` a subcommand, and give every command its runtime."""
    if ctx.obj is None:
        ctx.obj = CliRuntime.for_process()


def _install(
    runtime: CliRuntime, options: ScaffoldOptions, target: Path, root: Path
) -> None:
    """Run the manager's install in web/; on failure keep every file and say how to retry."""
    assert options.web is not None
    command = install_command(options.web.package_manager)
    shown = " ".join(command)
    # Forward slashes: valid in every shell the managers run in, and the
    # message reads the same on every platform.
    web = (target / "web").as_posix()
    typer.echo(f"{shown} in {web} ...", file=runtime.out)
    exit_code = runtime.run_process(command, root / "web")
    if exit_code == 0:
        typer.echo(f"{shown}: done", file=runtime.out)
        return
    typer.echo(
        f"{shown} failed (exit {exit_code}). The project is complete; retry with:\n"
        f"  cd {web} && {shown}",
        file=runtime.err,
    )
    raise typer.Exit(code=1)

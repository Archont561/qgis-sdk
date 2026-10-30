"""The optional ``qgis-sdk mcp`` stdio server."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from qgis_sdk_tools._commands._app import app
from qgis_sdk_tools.cli import CliRuntime


@app.command("mcp")
def mcp_command(
    ctx: typer.Context,
    project: Annotated[
        Path | None,
        typer.Option(
            help="Working directory for SDK commands; defaults to the current directory."
        ),
    ] = None,
) -> None:
    """Serve SDK command tools over MCP stdio (requires the mcp extra)."""
    runtime: CliRuntime = ctx.obj
    try:
        import mcp  # noqa: F401 - defer the optional dependency until invocation
    except ModuleNotFoundError as error:
        if error.name != "mcp":
            raise
        typer.echo(
            'MCP support is not installed. Run: pip install "qgis-sdk[mcp]"',
            file=runtime.err,
        )
        raise typer.Exit(code=2) from error
    root = runtime.resolve(project or Path())
    if not root.is_dir():
        typer.echo(f"MCP working directory does not exist: {root}", file=runtime.err)
        raise typer.Exit(code=2)
    from qgis_sdk_tools.mcp import serve

    serve(root)

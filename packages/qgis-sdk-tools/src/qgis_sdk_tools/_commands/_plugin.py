"""Call explicitly hosted plugin HTTP APIs from outside QGIS."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from qgis_sdk_tools._commands._app import app
from qgis_sdk_tools.cli import CliRuntime
from qgis_sdk_tools.rest import PluginClient, PluginClientError

plugin_app = typer.Typer(
    add_completion=False, help="Connect to a local plugin HTTP server."
)
app.add_typer(plugin_app, name="plugin")


def _client(url: str, token_file: Path, runtime: CliRuntime) -> PluginClient:
    return PluginClient(url, token_file=runtime.resolve(token_file))


def _args(value: str) -> dict:
    try:
        result = json.loads(value)
    except ValueError as error:
        raise PluginClientError(f"Invalid JSON arguments: {error}") from error
    if not isinstance(result, dict):
        raise PluginClientError("Arguments must be a JSON object")
    return result


def _error(runtime: CliRuntime, error: Exception) -> None:
    typer.echo(str(error), file=runtime.err)
    raise typer.Exit(code=2)


@plugin_app.command("describe")
def describe_plugin(
    ctx: typer.Context,
    url: Annotated[
        str, typer.Option(help="Local server URL (http://127.0.0.1:<port>).")
    ],
    token_file: Annotated[
        Path, typer.Option(help="Private token file created by the host.")
    ],
) -> None:
    """Print the exposed plugin actions and streams as JSON."""
    runtime: CliRuntime = ctx.obj
    try:
        result = _client(url, token_file, runtime).describe()
    except PluginClientError as error:
        _error(runtime, error)
    typer.echo(json.dumps(result, ensure_ascii=False), file=runtime.out)


@plugin_app.command("call")
def call_plugin(
    ctx: typer.Context,
    action: Annotated[str, typer.Argument(help="Exposed action ID.")],
    url: Annotated[str, typer.Option(help="Local plugin server URL.")],
    token_file: Annotated[Path, typer.Option(help="Private token file.")],
    args: Annotated[str, typer.Option(help="JSON object of action arguments.")] = "{}",
) -> None:
    """Call an exposed plugin action and print its JSON result."""
    runtime: CliRuntime = ctx.obj
    try:
        result = _client(url, token_file, runtime).call(action, _args(args))
    except PluginClientError as error:
        _error(runtime, error)
    typer.echo(json.dumps(result, ensure_ascii=False), file=runtime.out)


@plugin_app.command("stream")
def stream_plugin(
    ctx: typer.Context,
    stream: Annotated[str, typer.Argument(help="Exposed stream ID.")],
    url: Annotated[str, typer.Option(help="Local plugin server URL.")],
    token_file: Annotated[Path, typer.Option(help="Private token file.")],
    args: Annotated[str, typer.Option(help="JSON object of stream arguments.")] = "{}",
) -> None:
    """Print stream frames as newline-delimited JSON until completion."""
    runtime: CliRuntime = ctx.obj
    try:
        for frame in _client(url, token_file, runtime).stream(stream, _args(args)):
            typer.echo(json.dumps(frame, ensure_ascii=False), file=runtime.out)
    except PluginClientError as error:
        _error(runtime, error)

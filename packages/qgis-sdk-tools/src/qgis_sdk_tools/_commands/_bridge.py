"""``qgis-sdk bridge generate``."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import typer
from qgis_sdk.bridge.host import host_description
from qgis_sdk.models import QgisSdkBridgeError

from qgis_sdk_tools._commands._app import bridge_app
from qgis_sdk_tools.generate import (
    DEFAULT_SCHEMA_PATH,
    SCHEMA_SUFFIX,
    check_generated,
    describe_plugin_spec,
    generate_host_typescript,
    generate_schema_typescript,
    generate_typescript,
    load_description,
    write_generated,
)
from qgis_sdk_tools.scaffold import (
    QgisSdkScaffoldError,
)


@bridge_app.command("generate")
def bridge_generate(
    plugin: Annotated[
        str | None,
        typer.Option(
            help="Plugin application as module:app, described without QGIS; "
            "defaults to [tool.qgis-sdk] plugin in ./pyproject.toml."
        ),
    ] = None,
    description: Annotated[
        Path | None,
        typer.Option(help="Plugin description JSON a host already produced."),
    ] = None,
    host: Annotated[
        bool,
        typer.Option(
            "--host", help="Render the curated host surface instead of a plugin."
        ),
    ] = False,
    out: Annotated[
        Path | None,
        typer.Option(
            help="TypeScript module to write or check; a plugin defaults to "
            "web/src/bridge.schema.ts."
        ),
    ] = None,
    check: Annotated[
        bool, typer.Option(help="Fail when OUT differs from a fresh generation.")
    ] = False,
    show: Annotated[
        bool, typer.Option("--print", help="Write the module to stdout instead.")
    ] = False,
) -> None:
    """Turn one plugin description into its typed bridge.schema.ts module.

    The module carries the declaration and its types; ``QgisSdk.fromBridgeSchema``
    gives a page the typed calls and the runtime checks (decision-44). An ``--out``
    whose name does not end in ``.schema.ts`` still renders the legacy
    self-contained client, with a note, for one minor release.
    """
    try:
        described, generator = _describe(plugin, description, host)
        if out is None and not show and not host:
            out = DEFAULT_SCHEMA_PATH
        if out is not None and not host and not out.name.endswith(SCHEMA_SUFFIX):
            generator = generate_typescript
            typer.echo(
                f"note: {out} is the legacy client module, kept for one minor "
                f"release; name the output *{SCHEMA_SUFFIX} to generate the "
                "schema module QgisSdk.fromBridgeSchema reads",
                err=True,
            )
        if show:
            typer.echo(generator(described), nl=False)
        elif out is None:
            raise QgisSdkBridgeError("give --out or --print")
        elif check:
            message = check_generated(out, described, generate=generator)
            if message is not None:
                typer.echo(message, err=True)
                raise typer.Exit(code=1)
            typer.echo(f"{out} is up to date")
        else:
            changed = write_generated(out, described, generate=generator)
            typer.echo(f"{'wrote' if changed else 'unchanged'} {out}")
    except (QgisSdkBridgeError, QgisSdkScaffoldError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1) from error


def _describe(
    plugin: str | None, description: Path | None, host: bool
) -> tuple[dict, Callable[[dict], str]]:
    """Return the description and the renderer named by exactly one source."""
    if host:
        if plugin is not None or description is not None:
            raise QgisSdkBridgeError(
                "--host renders the curated host surface; give no --plugin or --description"
            )
        return host_description(), generate_host_typescript
    if plugin is None and description is None:
        plugin = _configured_plugin()
    if (plugin is None) == (description is None):
        raise QgisSdkBridgeError(
            "give exactly one of --plugin or --description (or set "
            "[tool.qgis-sdk] plugin in pyproject.toml)"
        )
    if plugin is not None:
        return describe_plugin_spec(plugin), generate_schema_typescript
    return load_description(description), generate_schema_typescript


def _configured_plugin() -> str | None:
    """``[tool.qgis-sdk] plugin`` of the working directory's project, if any."""
    from qgis_sdk_tools.project import load_project

    config, _findings = load_project(Path.cwd())
    return None if config is None else config.spec

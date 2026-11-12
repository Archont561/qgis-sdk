"""``qgis-sdk bridge generate``."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import typer
from qgis_sdk._published import published
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

_PluginOpt = Annotated[
    str | None,
    typer.Option(
        help="Plugin application as module:app, described without QGIS; "
        "defaults to [tool.qgis-sdk] plugin in ./pyproject.toml."
    ),
]
_DescriptionOpt = Annotated[
    Path | None,
    typer.Option(help="Plugin description JSON a host already produced."),
]
_HostOpt = Annotated[
    bool,
    typer.Option("--host", help="Render the curated host surface instead of a plugin."),
]
_OutOpt = Annotated[
    Path | None,
    typer.Option(
        help="TypeScript module to write or check; a plugin defaults to "
        "web/src/bridge.schema.ts."
    ),
]
_CheckOpt = Annotated[
    bool, typer.Option(help="Fail when OUT differs from a fresh generation.")
]
_ShowOpt = Annotated[
    bool, typer.Option("--print", help="Write the module to stdout instead.")
]


@dataclass(frozen=True, slots=True)
class _BridgeOptions:
    """The resolved ``bridge generate`` options, as one record."""

    plugin: str | None
    description: Path | None
    host: bool
    out: Path | None
    check: bool
    show: bool


def _bridge_output(options: _BridgeOptions, generator):
    """Choose the output path and generator, warning for a legacy name."""
    out = options.out
    if out is None and not options.show and not options.host:
        out = DEFAULT_SCHEMA_PATH
    if out is not None and not options.host and not out.name.endswith(SCHEMA_SUFFIX):
        typer.echo(
            f"note: {out} is the legacy client module, kept for one minor "
            f"release; name the output *{SCHEMA_SUFFIX} to generate the "
            "schema module QgisSdk.fromBridgeSchema reads",
            err=True,
        )
        return out, generate_typescript
    return out, generator


def _emit_bridge(options: _BridgeOptions, described, out, generator) -> None:
    """Print, check or write the generated module, as the options ask."""
    if options.show:
        typer.echo(generator(described), nl=False)
        return
    if out is None:
        raise QgisSdkBridgeError("give --out or --print")
    if options.check:
        message = check_generated(out, described, generate=generator)
        if message is not None:
            typer.echo(message, err=True)
            raise typer.Exit(code=1)
        typer.echo(f"{out} is up to date")
        return
    changed = write_generated(out, described, generate=generator)
    typer.echo(f"{'wrote' if changed else 'unchanged'} {out}")


def _generate_bridge(options: _BridgeOptions) -> None:
    """Describe the plugin and emit its bridge module, translating errors."""
    try:
        described, generator = _describe(
            options.plugin, options.description, options.host
        )
        out, generator = _bridge_output(options, generator)
        _emit_bridge(options, described, out, generator)
    except (QgisSdkBridgeError, QgisSdkScaffoldError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1) from error


_CC_SPECS_bridge_generate_1 = (
    ("plugin", _PluginOpt, None, "positional"),
    ("description", _DescriptionOpt, None, "positional"),
    ("host", _HostOpt, False, "positional"),
    ("out", _OutOpt, None, "positional"),
    ("check", _CheckOpt, False, "positional"),
    ("show", _ShowOpt, False, "positional"),
)


@bridge_app.command("generate")
@bridge_app.command("generate")
@published(_CC_SPECS_bridge_generate_1, returns=type(None))
def bridge_generate(_published_values):
    """Turn one plugin description into its typed bridge.schema.ts module.

    ``QgisSdk.fromBridgeSchema`` gives a page the typed calls and runtime checks
    (decision-44). An ``--out`` not ending in ``.schema.ts`` still renders the
    legacy self-contained client, with a note, for one minor release.
    """
    options = _BridgeOptions(
        _published_values.plugin,
        _published_values.description,
        _published_values.host,
        _published_values.out,
        _published_values.check,
        _published_values.show,
    )
    _generate_bridge(options)


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

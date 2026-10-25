"""The ``qgis-sdk`` command line: argument parsing over the public API, nothing else.

This module is what the wheel's ``qgis-sdk`` console script points at, and
``python -m qgis_sdk`` reaches the same :func:`main`, so a pip or
``pixi add --pypi`` install gets the command without an activated environment. It is
the one executable-shaped file inside ``src/qgis_sdk`` and it is there for that
reason: unlike the automation tools in ``packages/qgis-sdk-python/scripts``, which are
development-only and are not part of either distribution, generating a project is a
library operation with no display, no QGIS and no Qt, so shipping it is the point.

All behaviour lives in :mod:`qgis_sdk.scaffold` and :mod:`qgis_sdk.bridge.generate`,
so callers that do not want a shell reach the same API directly.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import typer

from qgis_sdk.bridge.generate import (
    check_generated,
    describe_plugin_spec,
    generate_host_typescript,
    generate_typescript,
    load_description,
    write_generated,
)
from qgis_sdk.bridge.host import host_description
from qgis_sdk.models import QgisSdkBridgeError
from qgis_sdk.scaffold import (
    QgisSdkScaffoldError,
    ScaffoldOptions,
    plan_scaffold,
    write_scaffold,
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


@app.command("new")
def new(
    target: Annotated[
        Path, typer.Argument(help="Directory to create the plugin project in.")
    ],
    plugin: Annotated[
        str | None,
        typer.Option(help="Plugin package name; defaults to the target name."),
    ] = None,
    title: Annotated[
        str | None, typer.Option(help="Human-readable plugin title.")
    ] = None,
    author: Annotated[
        str | None, typer.Option(help="Author recorded in metadata.txt.")
    ] = None,
    email: Annotated[
        str | None, typer.Option(help="Author email recorded in metadata.txt.")
    ] = None,
    version: Annotated[
        str | None, typer.Option(help="Plugin version recorded in metadata.txt.")
    ] = None,
    qgis_minimum_version: Annotated[
        str | None,
        typer.Option(help="Lowest QGIS version allowed to load the plugin."),
    ] = None,
    dry_run: Annotated[
        bool, typer.Option(help="Print the file plan and write nothing.")
    ] = False,
    force: Annotated[
        bool, typer.Option(help="Regenerate files that already exist.")
    ] = False,
) -> None:
    """Write a minimal, loadable plugin project at TARGET."""
    try:
        options = _resolve(
            target,
            plugin=plugin,
            title=title,
            author=author,
            email=email,
            version=version,
            qgis_minimum_version=qgis_minimum_version,
        )
        _report(options, target, dry_run=dry_run, force=force)
    except QgisSdkScaffoldError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1) from error


# ``scaffold`` was the command's name through 0.3.0. It keeps working so an
# existing script or tutorial does not break, but it is hidden from --help and
# marked deprecated; ``new`` is the spelling from here on.
app.command("scaffold", hidden=True, deprecated=True)(new)


@bridge_app.command("generate")
def bridge_generate(
    plugin: Annotated[
        str | None,
        typer.Option(help="Plugin class as module:Attribute, described without QGIS."),
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
        Path | None, typer.Option(help="TypeScript module to write or check.")
    ] = None,
    check: Annotated[
        bool, typer.Option(help="Fail when OUT differs from a fresh generation.")
    ] = False,
    show: Annotated[
        bool, typer.Option("--print", help="Write the module to stdout instead.")
    ] = False,
) -> None:
    """Turn one plugin description into a typed TypeScript client."""
    try:
        described, generator = _describe(plugin, description, host)
        if show:
            typer.echo(generator(described), nl=False)
        elif out is None:
            raise QgisSdkBridgeError("give --out, --check or --print")
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
    if (plugin is None) == (description is None):
        raise QgisSdkBridgeError("give exactly one of --plugin or --description")
    if plugin is not None:
        return describe_plugin_spec(plugin), generate_typescript
    return load_description(description), generate_typescript


@app.callback()
def _callback() -> None:
    """Keep ``new`` a subcommand, so the verb stays explicit."""


def _resolve(
    target: Path,
    *,
    plugin: str | None,
    title: str | None,
    author: str | None,
    email: str | None,
    version: str | None,
    qgis_minimum_version: str | None,
) -> ScaffoldOptions:
    """Pass only what the caller chose, so the API keeps its own defaults."""
    given = {"plugin": plugin or target.name}
    for key, value in (
        ("title", title),
        ("author", author),
        ("email", email),
        ("version", version),
        ("qgis_minimum_version", qgis_minimum_version),
    ):
        if value is not None:
            given[key] = value
    return ScaffoldOptions.resolve(**given)


def _report(
    options: ScaffoldOptions, target: Path, *, dry_run: bool, force: bool
) -> None:
    """Echo one project-relative path per line, planned or written."""
    if dry_run:
        for file in plan_scaffold(options):
            typer.echo(file.path)
        return
    for path in write_scaffold(options, target, force=force):
        typer.echo(path.relative_to(target).as_posix())


def main() -> None:
    """Run the command line; the wheel registers this as ``qgis-sdk``."""
    app()


if __name__ == "__main__":
    main()

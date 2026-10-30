"""``qgis-sdk processing generate``."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from qgis_sdk_tools._commands._app import processing_app
from qgis_sdk_tools.cli import CliRuntime
from qgis_sdk_tools.devtools import (
    QgisSdkQgisNotFoundError,
    find_qgis_install,
)
from qgis_sdk_tools.processing import DEFAULT_WEB_PATH


@processing_app.command("generate")
def processing_generate(
    ctx: typer.Context,
    project: Annotated[
        Path | None,
        typer.Option(help="Plugin project root; defaults to the working directory."),
    ] = None,
    provider: Annotated[
        list[str] | None,
        typer.Option(
            "--provider",
            help="Provider id to generate (repeatable); default: every provider "
            "the host registers.",
        ),
    ] = None,
    out: Annotated[
        Path | None,
        typer.Option(
            help="Python package directory to write or check; defaults to "
            "<plugin package>/processing. Give --no-python to skip."
        ),
    ] = None,
    no_python: Annotated[
        bool, typer.Option("--no-python", help="Write no Python package.")
    ] = False,
    web_out: Annotated[
        Path | None,
        typer.Option(
            help="TypeScript module to write or check; defaults to "
            f"{DEFAULT_WEB_PATH} when the project has a web/ directory."
        ),
    ] = None,
    no_web: Annotated[
        bool, typer.Option("--no-web", help="Write no TypeScript module.")
    ] = False,
    catalogue: Annotated[
        Path | None,
        typer.Option(
            help="Catalogue JSON a reader already wrote; skips the QGIS subprocess."
        ),
    ] = None,
    check: Annotated[
        bool, typer.Option(help="Fail when any output differs from a fresh generation.")
    ] = False,
    qgis_prefix: Annotated[
        Path | None, typer.Option(help="QGIS install prefix to read the registry from.")
    ] = None,
) -> None:
    """Read the QGIS Processing registry and write typed Python and TypeScript.

    The registry is read inside the project's QGIS install (never in this
    process); per provider you get a Python module with a TypedDict and a
    request class per algorithm, plus one TypeScript module with the
    parameter and result types and the AlgorithmRegistry map (decision-64).
    """
    from qgis_sdk_tools.processing import (
        QgisSdkProcessingGenerateError,
        check_files,
        read_host_catalogue,
        render_files,
        write_files,
    )

    runtime: CliRuntime = ctx.obj
    root = runtime.resolve(project or Path())
    try:
        if catalogue is not None:
            from qgis_sdk.models import Catalogue

            described = Catalogue.from_json(
                runtime.resolve(catalogue).read_text(encoding="utf-8")
            )
        else:
            install = find_qgis_install(runtime.env, prefix=qgis_prefix, project=root)
            typer.echo(
                f"reading the Processing registry of {install.prefix} ({install.source})",
                file=runtime.err,
            )
            described = read_host_catalogue(
                install,
                runtime.env,
                runtime.run_process,
                cwd=root,
                providers=provider,
            )
        python_out = None if no_python else _processing_package(root, out)
        typescript_out = None
        if not no_web:
            if web_out is not None:
                typescript_out = root / web_out
            elif (root / "web").is_dir():
                typescript_out = root / DEFAULT_WEB_PATH
        if python_out is None and typescript_out is None:
            raise QgisSdkProcessingGenerateError(
                "nothing to write: give --out, --web-out, or a project with a plugin "
                "package or a web/ directory"
            )
        generated = render_files(
            described, out=python_out, web_out=typescript_out, providers=provider
        )
        if check:
            messages = check_files(generated)
            for message in messages:
                typer.echo(message, file=runtime.err)
            if messages:
                raise typer.Exit(code=1)
            typer.echo(f"{len(generated.files)} generated files are up to date")
            return
        changed = write_files(generated)
        count = len(described.algorithms)
        for path in changed:
            typer.echo(f"wrote {path}")
        typer.echo(
            f"{count} algorithms from {len(described.providers)} providers; "
            f"{len(changed)} of {len(generated.files)} files changed"
        )
    except (QgisSdkQgisNotFoundError, QgisSdkProcessingGenerateError) as error:
        typer.echo(str(error), file=runtime.err)
        raise typer.Exit(code=2) from error


def _processing_package(root: Path, out: Path | None) -> Path | None:
    """``--out`` resolved, else ``<plugin package>/processing`` if there is one."""
    if out is not None:
        return root / out
    from qgis_sdk_tools.project import load_project

    config, _findings = load_project(root)
    if config is None:
        return None
    package = config.module.split(".")[0]
    return root / package / "processing"

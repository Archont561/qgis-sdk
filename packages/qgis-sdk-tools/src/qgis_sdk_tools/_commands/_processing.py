"""``qgis-sdk processing generate``."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import typer

from qgis_sdk_tools._commands._app import processing_app
from qgis_sdk_tools.cli import CliRuntime
from qgis_sdk_tools.devtools import (
    QgisSdkQgisNotFoundError,
    find_qgis_install,
)
from qgis_sdk_tools.processing import (
    DEFAULT_WEB_PATH,
    QgisSdkProcessingGenerateError,
    check_files,
    read_host_catalogue,
    render_files,
    write_files,
)

_ProjectOpt = Annotated[
    Path | None,
    typer.Option(help="Plugin project root; defaults to the working directory."),
]
_ProviderOpt = Annotated[
    list[str] | None,
    typer.Option(
        "--provider",
        help="Provider id to generate (repeatable); default: every provider "
        "the host registers.",
    ),
]
_OutOpt = Annotated[
    Path | None,
    typer.Option(
        help="Python package directory to write or check; defaults to "
        "<plugin package>/processing. Give --no-python to skip."
    ),
]
_NoPythonOpt = Annotated[
    bool, typer.Option("--no-python", help="Write no Python package.")
]
_WebOutOpt = Annotated[
    Path | None,
    typer.Option(
        help="TypeScript module to write or check; defaults to "
        f"{DEFAULT_WEB_PATH} when the project has a web/ directory."
    ),
]
_NoWebOpt = Annotated[
    bool, typer.Option("--no-web", help="Write no TypeScript module.")
]
_CatalogueOpt = Annotated[
    Path | None,
    typer.Option(
        help="Catalogue JSON a reader already wrote; skips the QGIS subprocess."
    ),
]
_CheckOpt = Annotated[
    bool, typer.Option(help="Fail when any output differs from a fresh generation.")
]
_PrefixOpt = Annotated[
    Path | None, typer.Option(help="QGIS install prefix to read the registry from.")
]


@dataclass(frozen=True, slots=True)
class _GenerateOptions:
    """The resolved ``processing generate`` knobs, as one record."""

    project: Path | None
    provider: list[str] | None
    out: Path | None
    no_python: bool
    web_out: Path | None
    no_web: bool
    catalogue: Path | None
    check: bool
    qgis_prefix: Path | None


def _read_catalogue(runtime: CliRuntime, options: _GenerateOptions, root: Path):
    """Read a catalogue JSON, or the live registry from the project's QGIS."""
    if options.catalogue is not None:
        from qgis_sdk.models import Catalogue

        return Catalogue.from_json(
            runtime.resolve(options.catalogue).read_text(encoding="utf-8")
        )
    install = find_qgis_install(runtime.env, prefix=options.qgis_prefix, project=root)
    typer.echo(
        f"reading the Processing registry of {install.prefix} ({install.source})",
        file=runtime.err,
    )
    return read_host_catalogue(
        install,
        runtime.env,
        runtime.run_process,
        cwd=root,
        providers=options.provider,
    )


def _output_paths(
    root: Path, options: _GenerateOptions
) -> tuple[Path | None, Path | None]:
    """Resolve the Python and TypeScript destinations the options select."""
    python_out = None if options.no_python else _processing_package(root, options.out)
    typescript_out = None
    if not options.no_web:
        if options.web_out is not None:
            typescript_out = root / options.web_out
        elif (root / "web").is_dir():
            typescript_out = root / DEFAULT_WEB_PATH
    return python_out, typescript_out


def _emit_files(
    runtime: CliRuntime, generated, described, options: _GenerateOptions
) -> None:
    """Check or write the rendered files and report what happened."""
    if options.check:
        messages = check_files(generated)
        for message in messages:
            typer.echo(message, file=runtime.err)
        if messages:
            raise typer.Exit(code=1)
        typer.echo(f"{len(generated.files)} generated files are up to date")
        return
    changed = write_files(generated)
    for path in changed:
        typer.echo(f"wrote {path}")
    typer.echo(
        f"{len(described.algorithms)} algorithms from "
        f"{len(described.providers)} providers; "
        f"{len(changed)} of {len(generated.files)} files changed"
    )


def _generate(runtime: CliRuntime, options: _GenerateOptions) -> None:
    """Read the registry, resolve destinations, render and emit every file.

    The registry is read inside the project's QGIS install (never in this
    process); each provider gets a Python module with a TypedDict and request
    class per algorithm, plus a TypeScript module with the parameter/result
    types and the AlgorithmRegistry map (decision-64).
    """
    root = runtime.resolve(options.project or Path())
    try:
        described = _read_catalogue(runtime, options, root)
        python_out, typescript_out = _output_paths(root, options)
        if python_out is None and typescript_out is None:
            raise QgisSdkProcessingGenerateError(
                "nothing to write: give --out, --web-out, or a project with a plugin "
                "package or a web/ directory"
            )
        generated = render_files(
            described,
            out=python_out,
            web_out=typescript_out,
            providers=options.provider,
        )
        _emit_files(runtime, generated, described, options)
    except (QgisSdkQgisNotFoundError, QgisSdkProcessingGenerateError) as error:
        typer.echo(str(error), file=runtime.err)
        raise typer.Exit(code=2) from error


@processing_app.command("generate")
def processing_generate(
    ctx: typer.Context,
    project: _ProjectOpt = None,
    provider: _ProviderOpt = None,
    out: _OutOpt = None,
    no_python: _NoPythonOpt = False,
    web_out: _WebOutOpt = None,
    no_web: _NoWebOpt = False,
    catalogue: _CatalogueOpt = None,
    check: _CheckOpt = False,
    qgis_prefix: _PrefixOpt = None,
) -> None:
    """Read the QGIS Processing registry; write typed Python and TypeScript."""
    options = _GenerateOptions(
        project,
        provider,
        out,
        no_python,
        web_out,
        no_web,
        catalogue,
        check,
        qgis_prefix,
    )
    _generate(ctx.obj, options)


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

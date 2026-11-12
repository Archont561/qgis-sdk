"""``qgis-sdk check``."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import typer
from qgis_sdk._published import REQUIRED, published

from qgis_sdk_tools._commands._app import app
from qgis_sdk_tools.check import QgisSdkCheckError, check_project
from qgis_sdk_tools.cli import CliRuntime
from qgis_sdk_tools.grants import grants_matrix
from qgis_sdk_tools.project import load_project

_PathArg = Annotated[
    Path | None,
    typer.Argument(help="Plugin project root; defaults to the working directory."),
]
_NativeOpt = Annotated[
    list[str] | None,
    typer.Option(
        "--native",
        help="Module glob allowed to import QGIS at load time (repeatable).",
    ),
]
_JsonOpt = Annotated[bool, typer.Option("--json", help="Print the report as JSON.")]
_ImportsOpt = Annotated[
    bool,
    typer.Option(
        "--imports",
        help="Print every import root with the bucket it sorts into.",
    ),
]
_GrantsOpt = Annotated[
    bool,
    typer.Option(
        "--grants",
        help="Print the client x host operation matrix of the grant vocabulary.",
    ),
]


@dataclass(frozen=True, slots=True)
class _CheckOptions:
    """The resolved ``check`` options, as one record."""

    root: Path
    native: tuple[str, ...]
    as_json: bool
    imports: bool
    grants: bool


def _checked_report(runtime: CliRuntime, options: _CheckOptions):
    """Read the project, translating a check error into a CLI exit."""
    try:
        return check_project(options.root, native_modules=options.native)
    except QgisSdkCheckError as error:
        typer.echo(str(error), file=runtime.err)
        raise typer.Exit(code=2) from error


def _render_report(runtime: CliRuntime, report, options: _CheckOptions) -> None:
    """Print the diagnostics, the optional listings and the summary line."""
    if options.as_json:
        typer.echo(json.dumps(report.to_json(), indent=2), file=runtime.out)
        return
    for diagnostic in report.diagnostics:
        typer.echo(diagnostic.render(), file=runtime.out)
    if options.imports and report.imports is not None:
        listing = report.imports.render()
        if listing:
            typer.echo(listing, file=runtime.out)
    if options.grants:
        config, _ = load_project(options.root)
        if config is not None:
            typer.echo(grants_matrix(config).render(), file=runtime.out)
    count = len(report.diagnostics)
    problems = (
        "no problems" if count == 0 else f"{count} problem{'s' if count != 1 else ''}"
    )
    typer.echo(f"checked {report.files_checked} files: {problems}", file=runtime.out)


_CC_SPECS_check_1 = (
    ("ctx", typer.Context, REQUIRED, "positional"),
    ("path", _PathArg, None, "positional"),
    ("native", _NativeOpt, None, "positional"),
    ("as_json", _JsonOpt, False, "positional"),
    ("imports", _ImportsOpt, False, "positional"),
    ("grants", _GrantsOpt, False, "positional"),
)


@app.command("check")
@app.command("check")
@published(_CC_SPECS_check_1, returns=type(None))
def check(_published_values):
    """Read a plugin project and report problems; import, install and change nothing."""
    runtime: CliRuntime = _published_values.ctx.obj
    options = _CheckOptions(
        runtime.resolve(_published_values.path or Path()),
        tuple(_published_values.native or ()),
        _published_values.as_json,
        _published_values.imports,
        _published_values.grants,
    )
    report = _checked_report(runtime, options)
    _render_report(runtime, report, options)
    if not report.ok:
        raise typer.Exit(code=1)

"""``qgis-sdk build``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from qgis_sdk._published import REQUIRED, published

from qgis_sdk_tools._commands._app import app
from qgis_sdk_tools.bundle import (
    QgisSdkBuildError,
    QgisSdkBuildRefusedError,
    build_plugin,
)
from qgis_sdk_tools.bundle.app import build_app
from qgis_sdk_tools.cli import CliRuntime

_CcAnn1 = Annotated[
    Path | None,
    typer.Argument(help="Plugin project root; defaults to the working directory."),
]
_CcAnn2 = Annotated[
    str,
    typer.Option(
        help="plugin (default): the ZIP QGIS's Install-from-ZIP reads. "
        "app: a pip-installable distribution whose console script runs the "
        "application as a standalone PyQGIS app.",
    ),
]
_CcAnn3 = Annotated[
    Path | None,
    typer.Option(
        help="Where to write the archive or the distribution directory; "
        "defaults to <root>/dist."
    ),
]
_CcAnn4 = Annotated[
    bool,
    typer.Option(
        "--no-web",
        help="Do not run the web build; ship <plugin>/web as it is.",
    ),
]
_CcAnn5 = Annotated[bool, typer.Option("--json", help="Print the result as JSON.")]


class _CcReturn:
    """An early return travelling out of a phase."""

    def __init__(_cc_self, value):
        _cc_self.value = value


def _cc_build_p1(_s):
    _s.runtime: CliRuntime = _s.ctx.obj
    _s.root = _s.runtime.resolve(_s.path or Path())
    if _s.target not in TARGETS:
        typer.echo(
            f"unknown target {_s.target!r}; choose one of {', '.join(TARGETS)}",
            file=_s.runtime.err,
        )
        raise typer.Exit(code=2)
    _s.destination = None if _s.out is None else _s.runtime.resolve(_s.out)
    _s.run = lambda argv, cwd: _s.runtime.run_process(argv, cwd)


def _cc_build_p2(_s):
    try:
        _s.result = (
            build_app(_s.root, out=_s.destination, web=not _s.no_web, run=_s.run)
            if _s.target == "app"
            else build_plugin(
                _s.root, out=_s.destination, web=not _s.no_web, run=_s.run
            )
        )
    except QgisSdkBuildRefusedError as error:
        _s.error = error
        for diagnostic in _s.error.diagnostics:
            _s.diagnostic = diagnostic
            typer.echo(_s.diagnostic.render(), file=_s.runtime.out)
        typer.echo(str(_s.error), file=_s.runtime.err)
        raise typer.Exit(code=1) from _s.error
    except QgisSdkBuildError as error:
        _s.error = error
        typer.echo(str(_s.error), file=_s.runtime.err)
        raise typer.Exit(code=2) from _s.error


def _cc_build_p3(_s):
    if _s.as_json:
        typer.echo(json.dumps(_s.result.to_json(), indent=2), file=_s.runtime.out)
        return _CcReturn(None)
    for diagnostic in _s.result.report.diagnostics:
        _s.diagnostic = diagnostic
        typer.echo(_s.diagnostic.render(), file=_s.runtime.out)


def _cc_build_p4(_s):
    if _s.target == "app":
        typer.echo(
            f"built {_s.result.plugin} {_s.result.version}: {_s.result.directory} "
            f"({len(_s.result.files)} files, runtime {_s.result.runtime_version}, "
            f"web: {_s.result.web}); install it with `pip install "
            f"{_s.result.directory}` and run `{_s.result.launcher}`",
            file=_s.runtime.out,
        )
        return _CcReturn(None)
    _build_phase1(_s.result, _s.runtime)


def _build_phase1(result, runtime):
    typer.echo(
        f"built {result.plugin} {result.version}: {result.archive} "
        f"({len(result.files)} files, runtime {result.runtime_version}, "
        f"web: {result.web})",
        file=runtime.out,
    )


#: ``--target``: the plugin ZIP QGIS installs, or an installable app distribution.
TARGETS = ("plugin", "app")


_CC_SPECS_build_1 = (
    ("ctx", typer.Context, REQUIRED, "positional"),
    ("path", _CcAnn1, None, "positional"),
    ("target", _CcAnn2, "plugin", "positional"),
    ("out", _CcAnn3, None, "positional"),
    ("no_web", _CcAnn4, False, "positional"),
    ("as_json", _CcAnn5, False, "positional"),
)


@app.command("build")
@published(_CC_SPECS_build_1, returns=type(None))
def build(_published_values):
    """Check the project and write what QGIS, or a launcher, installs and runs."""
    _s = _published_values
    for _p in (_cc_build_p1, _cc_build_p2, _cc_build_p3, _cc_build_p4):
        _r = _p(_s)
        if isinstance(_r, _CcReturn):
            return _r.value
    return None

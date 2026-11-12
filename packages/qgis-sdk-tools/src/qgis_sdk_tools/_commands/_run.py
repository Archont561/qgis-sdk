"""``qgis-sdk run``: start the project as a standalone app, with the found QGIS."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Annotated

import typer
from qgis_sdk._published import REQUIRED, published

from qgis_sdk_tools._commands._app import app
from qgis_sdk_tools.cli import CliRuntime
from qgis_sdk_tools.devtools import QgisSdkQgisNotFoundError, find_qgis_install
from qgis_sdk_tools.devtools.dev import (
    QgisSdkDevError,
    inspect_project,
    plan_app,
)

_CcAnn1 = Annotated[
    Path | None,
    typer.Argument(help="Plugin project root; defaults to the working directory."),
]
_CcAnn2 = Annotated[
    bool,
    typer.Option(
        "--headless",
        help="No window: jobs, the project and the services still work, the UI "
        "is refused by name.",
    ),
]
_CcAnn3 = Annotated[
    bool,
    typer.Option(
        "--once",
        help="Start, deliver what is already queued, stop - the smoke run a "
        "script or a CI job makes.",
    ),
]
_CcAnn4 = Annotated[
    float | None,
    typer.Option(
        help="Seconds shutdown waits for running jobs before abandoning them "
        "(default: the runtime's 15)."
    ),
]
_CcAnn5 = Annotated[
    str | None,
    typer.Option(help="Window title; defaults to the application's own title."),
]
_CcAnn6 = Annotated[Path | None, typer.Option(help="QGIS install prefix to run.")]


class _CcState:
    """A mutable record shared by the phases of one long function."""

    def __init__(_cc_self, **values):
        _cc_self.__dict__.update(values)


class _CcReturn:
    """An early return travelling out of a phase."""

    def __init__(_cc_self, value):
        _cc_self.value = value


class _CcBreak:
    """A loop break travelling out of a phase."""


class _CcContinue:
    """A loop continue travelling out of a phase."""


def _cc_run_p1(_s):
    try:
        _s.project = inspect_project(_s.root)
        _s.install = find_qgis_install(
            _s.runtime.env, prefix=_s.qgis_prefix, project=_s.root
        )
        _s.plan = plan_app(
            _s.project,
            _s.install,
            env=_s.runtime.env,
            workspace=_s.workspace,
            gui=not _s.headless,
            once=_s.once,
            grace=_s.grace,
            title=_s.title,
        )
    except (QgisSdkDevError, QgisSdkQgisNotFoundError) as error:
        _s.error = error
        typer.echo(str(_s.error), file=_s.runtime.err)
        raise typer.Exit(code=2) from _s.error


def _cc_run_p2(_s):
    for note in _s.plan.notes:
        _s.note = note
        typer.echo(_s.note, file=_s.runtime.err)
    _s.exit_code = _s.runtime.run_process(_s.plan.argv, _s.plan.cwd, _s.plan.env)


def _cc_run_p3(_s):
    # The generated probe lives here, so the workspace is removed only once
    # the app has exited - never before the process that reads it.
    shutil.rmtree(_s.workspace, ignore_errors=True)


def _cc_run_p4(_s):
    _s.runtime: CliRuntime = _s.ctx.obj
    _s.root = _s.runtime.resolve(_s.path or Path())
    _s.workspace = Path(tempfile.mkdtemp(prefix="qgis-sdk-run-"))
    try:
        for _p in (_cc_run_p1, _cc_run_p2):
            _r = _p(_s)
            if isinstance(_r, _CcReturn):
                return _r
    finally:
        for _p in (_cc_run_p3,):
            _p(_s)


def _cc_run_p5(_s):
    if _s.exit_code == 127:
        typer.echo(f"{_s.plan.argv[0]} was not found", file=_s.runtime.err)
    raise typer.Exit(code=_s.exit_code)


_CC_SPECS_run_1 = (
    ("ctx", typer.Context, REQUIRED, "positional"),
    ("path", _CcAnn1, None, "positional"),
    ("headless", _CcAnn2, False, "positional"),
    ("once", _CcAnn3, False, "positional"),
    ("grace", _CcAnn4, None, "positional"),
    ("title", _CcAnn5, None, "positional"),
    ("qgis_prefix", _CcAnn6, None, "positional"),
)


@app.command("run")
@published(_CC_SPECS_run_1, returns=type(None))
def run(_published_values):
    """Run the plugin as a standalone PyQGIS app instead of inside QGIS.

    The app host owns the ``QgsApplication`` (decision-52 point 3): it starts the
    project's ``<plugin>/__main__.py`` through the discovered QGIS interpreter,
    with the SDK's own packages on that interpreter's path. Nothing is installed
    and nothing is written into the project; a project without an app entry runs
    through a generated probe, so a Desktop plugin can be tried as an app.
    """
    _s = _published_values
    for _p in (_cc_run_p4, _cc_run_p5):
        _r = _p(_s)
        if isinstance(_r, _CcReturn):
            return _r.value
    return None

"""``qgis-sdk test``."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Annotated

import typer

from qgis_sdk_tools._commands._app import app
from qgis_sdk_tools.cli import CliRuntime
from qgis_sdk_tools.devtools import (
    QgisSdkQgisNotFoundError,
    find_qgis_install,
)
from qgis_sdk_tools.devtools.testrun import (
    NATIVE_TARGETS,
    QgisSdkTestRunError,
    plan_tests,
)

_CcAnn1 = Annotated[
    list[str] | None,
    typer.Argument(help="Passed to pytest (or the web test script) unchanged."),
]
_CcAnn2 = Annotated[
    Path | None,
    typer.Option(help="Plugin project root; defaults to the working directory."),
]
_CcAnn3 = Annotated[
    str,
    typer.Option(
        help="pure (default, no QGIS), qgis (PyQGIS, headless), "
        "desktop (inside QGIS Desktop), server (QGIS Server bindings) "
        "or web (Vitest)."
    ),
]
_CcAnn4 = Annotated[
    Path | None,
    typer.Option(help="QGIS install prefix for the qgis, desktop and server targets."),
]


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


def _cc_test_p1(_s):
    _s.install = None
    if _s.target in NATIVE_TARGETS:
        _s.install = find_qgis_install(
            _s.runtime.env, prefix=_s.qgis_prefix, project=_s.root
        )
    if _s.target == "desktop":
        _s.workspace = Path(tempfile.mkdtemp(prefix="qgis-sdk-test-"))


def _cc_test_p2(_s):
    _s.plan = plan_tests(
        _s.root,
        _s.target,
        _s.forwarded,
        env=_s.runtime.env,
        install=_s.install,
        workspace=_s.workspace,
    )
    for note in _s.plan.notes:
        _s.note = note
        typer.echo(_s.note, file=_s.runtime.err)
    _s.exit_code = _s.runtime.run_process(_s.plan.argv, _s.plan.cwd, _s.plan.env)


def _cc_test_p3(_s):
    typer.echo(str(_s.error), file=_s.runtime.err)
    raise typer.Exit(code=2) from _s.error


def _cc_test_p4(_s):
    if _s.workspace is not None:
        shutil.rmtree(_s.workspace, ignore_errors=True)


def _cc_test_p5(_s):
    _s.runtime: CliRuntime = _s.ctx.obj
    _s.root = _s.runtime.resolve(_s.project or Path())
    _s.forwarded = (*(_s.pytest_args or ()), *_s.ctx.args)
    _s.workspace: Path | None = None


def _cc_test_p6(_s):
    try:
        for _p in (_cc_test_p1, _cc_test_p2):
            _r = _p(_s)
            if isinstance(_r, _CcReturn):
                return _r
    except (QgisSdkQgisNotFoundError, QgisSdkTestRunError) as error:
        _s.error = error
        for _p in (_cc_test_p3,):
            _r = _p(_s)
            if isinstance(_r, _CcReturn):
                return _r
    finally:
        for _p in (_cc_test_p4,):
            _p(_s)


def _cc_test_p7(_s):
    if _s.exit_code == 127:
        typer.echo(f"{_s.plan.argv[0]} was not found", file=_s.runtime.err)
    raise typer.Exit(code=_s.exit_code)


@app.command(
    "test",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def test(
    ctx: typer.Context,
    pytest_args: _CcAnn1 = None,
    project: _CcAnn2 = None,
    target: _CcAnn3 = "pure",
    qgis_prefix: _CcAnn4 = None,
) -> None:
    """Run the project's tests for one target; other arguments go to pytest."""
    _s = _CcState(
        ctx=ctx,
        pytest_args=pytest_args,
        project=project,
        target=target,
        qgis_prefix=qgis_prefix,
    )
    for _p in (_cc_test_p5, _cc_test_p6, _cc_test_p7):
        _r = _p(_s)
        if isinstance(_r, _CcReturn):
            return _r.value
    return None

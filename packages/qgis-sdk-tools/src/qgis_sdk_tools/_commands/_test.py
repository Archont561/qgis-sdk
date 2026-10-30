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


@app.command(
    "test",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def test(
    ctx: typer.Context,
    pytest_args: Annotated[
        list[str] | None,
        typer.Argument(help="Passed to pytest (or the web test script) unchanged."),
    ] = None,
    project: Annotated[
        Path | None,
        typer.Option(help="Plugin project root; defaults to the working directory."),
    ] = None,
    target: Annotated[
        str,
        typer.Option(
            help="pure (default, no QGIS), qgis (PyQGIS, headless), "
            "desktop (inside QGIS Desktop), server (QGIS Server bindings) "
            "or web (Vitest)."
        ),
    ] = "pure",
    qgis_prefix: Annotated[
        Path | None,
        typer.Option(
            help="QGIS install prefix for the qgis, desktop and server targets."
        ),
    ] = None,
) -> None:
    """Run the project's tests for one target; other arguments go to pytest."""
    runtime: CliRuntime = ctx.obj
    root = runtime.resolve(project or Path())
    forwarded = (*(pytest_args or ()), *ctx.args)
    workspace: Path | None = None
    try:
        install = None
        if target in NATIVE_TARGETS:
            install = find_qgis_install(runtime.env, prefix=qgis_prefix, project=root)
        if target == "desktop":
            workspace = Path(tempfile.mkdtemp(prefix="qgis-sdk-test-"))
        plan = plan_tests(
            root,
            target,
            forwarded,
            env=runtime.env,
            install=install,
            workspace=workspace,
        )
        for note in plan.notes:
            typer.echo(note, file=runtime.err)
        exit_code = runtime.run_process(plan.argv, plan.cwd, plan.env)
    except (QgisSdkQgisNotFoundError, QgisSdkTestRunError) as error:
        typer.echo(str(error), file=runtime.err)
        raise typer.Exit(code=2) from error
    finally:
        if workspace is not None:
            shutil.rmtree(workspace, ignore_errors=True)
    if exit_code == 127:
        typer.echo(f"{plan.argv[0]} was not found", file=runtime.err)
    raise typer.Exit(code=exit_code)

"""``qgis-sdk targets``."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import typer

from qgis_sdk_tools import targets as targets_module
from qgis_sdk_tools._commands._app import app
from qgis_sdk_tools.cli import CliRuntime
from qgis_sdk_tools.devtools import (
    QgisSdkQgisNotFoundError,
    find_qgis_install,
)


@app.command("targets")
def targets(
    ctx: typer.Context,
    qgis_prefix: Annotated[
        Path | None,
        typer.Option(
            "--qgis-prefix",
            help="QGIS install to describe; defaults to the one `qgis-sdk test` finds.",
        ),
    ] = None,
    as_json: Annotated[
        bool, typer.Option("--json", help="Print the matrix and the host as JSON.")
    ] = False,
) -> None:
    """Print the support matrix and where this host stands in it; change nothing.

    The matrix is the record of where the kit was demonstrated (qualified) and
    where it was not (unqualified, with the blocker). The verdict for the host
    is information, not a refusal: the exit code is 0 either way.
    """
    runtime: CliRuntime = ctx.obj
    host = targets_module.describe_host(probe=_host_probe(runtime, qgis_prefix))
    target = targets_module.qualified_target(host)
    status = target.status if target is not None else "unqualified"
    if as_json:
        payload = {
            "targets": [row.to_json() for row in targets_module.SUPPORT_MATRIX],
            "host": host.to_json(),
            "target": target.to_json() if target is not None else None,
            "status": status,
        }
        typer.echo(json.dumps(payload, indent=2), file=runtime.out)
        return
    typer.echo(targets_module.render_markdown(), file=runtime.out)
    typer.echo("", file=runtime.out)
    reason = (
        f" ({target.evidence})" if target is not None else " (no row in the matrix)"
    )
    typer.echo(f"this host: {host.describe()} -> {status}{reason}", file=runtime.out)


def _host_probe(
    runtime: CliRuntime, qgis_prefix: Path | None
) -> Callable[[str], str | None]:
    """Read QGIS the way the other commands find it: an install resolved from
    the option, the configuration, ``QGIS_PREFIX_PATH``, ``PATH`` or the
    interpreter's prefix; without one, whatever this interpreter imports."""
    try:
        install = find_qgis_install(
            runtime.env, prefix=qgis_prefix, project=runtime.cwd
        )
    except QgisSdkQgisNotFoundError:
        return targets_module.probe_installed
    return targets_module.bindings_probe(install.bindings)

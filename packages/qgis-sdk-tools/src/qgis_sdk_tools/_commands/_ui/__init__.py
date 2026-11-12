"""Capture, drive and compare a plugin's native surfaces (decision-51).

``qgis-sdk ui`` is a development command: the surfaces are Qt objects that only
exist where the plugin runs, so ``open``, ``snapshot`` and ``act`` write a
request, run :mod:`qgis_sdk_tools.devtools.ui_probe` inside a QGIS interpreter
and print what it wrote. ``diff`` needs neither - it compares two capture files
- so a snapshot can be approved, reviewed and compared without starting QGIS
again.

Captures on disk are always the runtime's canonical JSON; ``--format yaml`` is
a reading choice this command makes on the way out, and the runtime never
learns about it (decision-51 point 5).
"""

from __future__ import annotations

import json as _json
from dataclasses import dataclass as _dataclass
from pathlib import Path as _Path
from typing import Annotated as _Annotated
from typing import Any as _Any

import typer as _typer
from qgis_sdk._published import REQUIRED as _REQUIRED
from qgis_sdk._published import published as _published

from qgis_sdk_tools._commands._app import app as _app
from qgis_sdk_tools.cli import CliRuntime as _CliRuntime
from qgis_sdk_tools.devtools.dev import STATE_DIRECTORY as _STATE_DIRECTORY
from qgis_sdk_tools.devtools.ui_probe import ActStep as _ActStep
from qgis_sdk_tools.ui_diff import diff_snapshots as _diff_snapshots

from ._capture import capture as _capture
from ._capture import format as _format
from ._capture import print_captures as _print_captures
from ._capture import render as _render
from ._capture import steps as _steps
from ._diff import diff_payload as _diff_payload

__all__ = ["ui_app"]


ui_app = _typer.Typer(
    add_completion=False, help="Capture and compare a plugin's native surfaces."
)
_app.add_typer(ui_app, name="ui")

_STEP_HELP = (
    "One interaction, NODE:VERB[:VALUE] - for example form/distance:set:5 or "
    "buttons/run:click. Repeat it to send several in order."
)

_FORMAT_HELP = (
    "How to print the result: canonical JSON (the capture format), or YAML for "
    "reading. Files written on disk are always JSON."
)

_PROJECT_HELP = "Plugin project directory."

_PREFIX_HELP = "QGIS install prefix to run the probe in."

_SURFACE_HELP = "Surface id the plugin declares."


@ui_app.command("list")
def list_surfaces(
    ctx: _typer.Context,
    project: _Annotated[_Path, _typer.Option(help=_PROJECT_HELP)] = _Path(),
    qgis_prefix: _Annotated[_Path | None, _typer.Option(help=_PREFIX_HELP)] = None,
    fmt: _Annotated[str, _typer.Option("--format", help=_FORMAT_HELP)] = "json",
) -> None:
    """List the surfaces the plugin declares."""
    runtime: _CliRuntime = ctx.obj
    chosen = _format(fmt)
    report = _capture(
        runtime,
        project=project,
        surface="-",
        output=None,
        screenshot=False,
        steps=[],
        qgis_prefix=qgis_prefix,
    )
    _typer.echo(_render(report["surfaces"], chosen), file=runtime.out)


@ui_app.command("open")
def open_surface(
    ctx: _typer.Context,
    surface: _Annotated[str, _typer.Argument(help=_SURFACE_HELP)],
    project: _Annotated[_Path, _typer.Option(help=_PROJECT_HELP)] = _Path(),
    qgis_prefix: _Annotated[_Path | None, _typer.Option(help=_PREFIX_HELP)] = None,
    fmt: _Annotated[str, _typer.Option("--format", help=_FORMAT_HELP)] = "json",
) -> None:
    """Open one surface in the host and report what appeared."""
    runtime: _CliRuntime = ctx.obj
    chosen = _format(fmt)
    report = _capture(
        runtime,
        project=project,
        surface=surface,
        output=None,
        screenshot=False,
        steps=[],
        qgis_prefix=qgis_prefix,
        open_only=True,
    )
    _typer.echo(_render(report["opened"], chosen), file=runtime.out)


_CC_SPECS_snapshot_surface_2 = (
    ("ctx", _typer.Context, _REQUIRED, "positional"),
    (
        "surface",
        _Annotated[str, _typer.Argument(help=_SURFACE_HELP)],
        _REQUIRED,
        "positional",
    ),
    (
        "project",
        _Annotated[_Path, _typer.Option(help=_PROJECT_HELP)],
        _Path(),
        "positional",
    ),
    (
        "out",
        _Annotated[
            _Path | None,
            _typer.Option(
                help=f"Where to write the capture (default: {_STATE_DIRECTORY}/ui)."
            ),
        ],
        None,
        "positional",
    ),
    (
        "screenshot",
        _Annotated[
            bool,
            _typer.Option("--screenshot/--no-screenshot", help="Grab the PNG too."),
        ],
        True,
        "positional",
    ),
    ("act", _Annotated[list[str], _typer.Option(help=_STEP_HELP)], [], "positional"),
    (
        "qgis_prefix",
        _Annotated[_Path | None, _typer.Option(help=_PREFIX_HELP)],
        None,
        "positional",
    ),
    (
        "fmt",
        _Annotated[str, _typer.Option("--format", help=_FORMAT_HELP)],
        "json",
        "positional",
    ),
)


@ui_app.command("snapshot")
@_published(_CC_SPECS_snapshot_surface_2, returns=type(None))
def snapshot_surface(_published_values):
    """Capture one surface as canonical JSON plus a PNG, optionally after acting."""
    runtime: _CliRuntime = _published_values.ctx.obj
    chosen = format(_published_values.fmt)
    report = _capture(
        runtime,
        project=_published_values.project,
        surface=_published_values.surface,
        output=_published_values.out,
        screenshot=_published_values.screenshot,
        steps=_steps(_published_values.act),
        qgis_prefix=_published_values.qgis_prefix,
    )
    _print_captures(runtime, report, chosen)


def _print_step_values(
    runtime: _CliRuntime, report: dict[str, _Any], chosen: str
) -> None:
    """Echo what each widget held after the steps, unless YAML was requested."""
    if chosen == "yaml":
        return
    for applied in report["steps"]:
        # What the widget holds afterwards is the point of acting; the
        # requested value is only what was asked for.
        after = applied.get("value_after", applied.get("value"))
        _typer.echo(
            f"{applied['node']} {applied['verb']} -> {after!r}", file=runtime.out
        )


@_dataclass(frozen=True, slots=True)
class _SurfaceAction:
    """Everything ``ui act`` needs from the CLI, as one record."""

    project: _Path
    surface: str
    out: _Path | None
    screenshot: bool
    steps: list[_ActStep]
    qgis_prefix: _Path | None
    fmt: str


def _drive_surface(runtime: _CliRuntime, action: _SurfaceAction) -> None:
    """Drive a surface through Qt, then capture and report what it became."""
    chosen = _format(action.fmt)
    if not action.steps:
        _typer.echo(
            "ui act needs at least one --step NODE:VERB[:VALUE]", file=runtime.err
        )
        raise _typer.Exit(code=2)
    report = _capture(
        runtime,
        project=action.project,
        surface=action.surface,
        output=action.out,
        screenshot=action.screenshot,
        steps=action.steps,
        qgis_prefix=action.qgis_prefix,
    )
    _print_captures(runtime, report, chosen)
    _print_step_values(runtime, report, chosen)


_CC_SPECS_act_on_surface_1 = (
    ("ctx", _typer.Context, _REQUIRED, "positional"),
    (
        "surface",
        _Annotated[str, _typer.Argument(help=_SURFACE_HELP)],
        _REQUIRED,
        "positional",
    ),
    (
        "step",
        _Annotated[list[str], _typer.Option("--step", help=_STEP_HELP)],
        [],
        "positional",
    ),
    (
        "project",
        _Annotated[_Path, _typer.Option(help=_PROJECT_HELP)],
        _Path(),
        "positional",
    ),
    (
        "out",
        _Annotated[_Path | None, _typer.Option(help="Where to write the captures.")],
        None,
        "positional",
    ),
    (
        "screenshot",
        _Annotated[
            bool,
            _typer.Option("--screenshot/--no-screenshot", help="Grab the PNG too."),
        ],
        True,
        "positional",
    ),
    (
        "qgis_prefix",
        _Annotated[_Path | None, _typer.Option(help=_PREFIX_HELP)],
        None,
        "positional",
    ),
    (
        "fmt",
        _Annotated[str, _typer.Option("--format", help=_FORMAT_HELP)],
        "json",
        "positional",
    ),
)


@ui_app.command("act")
@_published(_CC_SPECS_act_on_surface_1, returns=type(None))
def act_on_surface(_published_values):
    """Drive a surface through Qt, then capture what it became.

    `ui snapshot` with interactions made mandatory: a capture of an untouched
    surface is what `snapshot` is for.
    """
    action = _SurfaceAction(
        _published_values.project,
        _published_values.surface,
        _published_values.out,
        _published_values.screenshot,
        _steps(_published_values.step),
        _published_values.qgis_prefix,
        _published_values.fmt,
    )
    _drive_surface(_published_values.ctx.obj, action)


@ui_app.command("diff")
def diff_captures(
    ctx: _typer.Context,
    before: _Annotated[_Path, _typer.Argument(help="Approved capture JSON.")],
    after: _Annotated[_Path, _typer.Argument(help="New capture JSON.")],
    as_json: _Annotated[
        bool, _typer.Option("--json", help="Print the changes as JSON.")
    ] = False,
    fmt: _Annotated[str, _typer.Option("--format", help=_FORMAT_HELP)] = "json",
) -> None:
    """Compare two captures; exit 1 when anything but the image changed."""
    runtime: _CliRuntime = ctx.obj
    chosen = _format(fmt)
    old = _json.loads(runtime.resolve(before).read_text(encoding="utf-8"))
    new = _json.loads(runtime.resolve(after).read_text(encoding="utf-8"))
    difference = _diff_snapshots(old, new)
    if as_json:
        _typer.echo(_render(_diff_payload(difference), chosen), file=runtime.out)
    else:
        _typer.echo(difference.render(), file=runtime.out)
    if difference:
        raise _typer.Exit(code=1)

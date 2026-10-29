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

import json
from pathlib import Path
from typing import Annotated, Any

import typer

from qgis_sdk_tools._commands._app import app
from qgis_sdk_tools.cli import CliRuntime
from qgis_sdk_tools.devtools.dev import STATE_DIRECTORY, inspect_project
from qgis_sdk_tools.devtools.installs import find_qgis_install, sdk_import_paths
from qgis_sdk_tools.devtools.ui_probe import (
    PROBE_ENTRYPOINT,
    REQUEST_ENV,
    VERBS,
    ActStep,
    CaptureRequest,
)
from qgis_sdk_tools.ui_diff import diff_snapshots
from qgis_sdk_tools.ui_yaml import to_yaml

ui_app = typer.Typer(
    add_completion=False, help="Capture and compare a plugin's native surfaces."
)
app.add_typer(ui_app, name="ui")

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


def _format(raw: str) -> str:
    """Refuse a format this command cannot print instead of guessing."""
    chosen = raw.lower()
    if chosen not in ("json", "yaml"):
        raise typer.BadParameter(f"{raw!r} is not json or yaml")
    return chosen


def _render(payload: Any, fmt: str) -> str:
    if fmt == "yaml":
        return to_yaml(payload).rstrip("\n")
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _steps(raw: list[str]) -> list[ActStep]:
    """Parse ``NODE:VERB[:VALUE]`` arguments, refusing a verb that does not exist."""
    steps: list[ActStep] = []
    for entry in raw:
        node, _, rest = entry.partition(":")
        verb, _, value = rest.partition(":")
        if not node or not verb:
            raise typer.BadParameter(
                f"{entry!r} is not NODE:VERB[:VALUE]; for example form/distance:set:5"
            )
        if verb not in VERBS:
            raise typer.BadParameter(
                f"{verb!r} is not one of {', '.join(VERBS)} (in {entry!r})"
            )
        steps.append(
            ActStep(node=node, verb=verb, value=None if verb == "click" else value)
        )
    return steps


def _capture(
    runtime: CliRuntime,
    *,
    project: Path,
    surface: str,
    output: Path | None,
    screenshot: bool,
    steps: list[ActStep],
    qgis_prefix: Path | None,
    open_only: bool = False,
) -> dict[str, Any]:
    """Run the probe in a QGIS interpreter and return the report it wrote."""
    root = runtime.resolve(project)
    plugin = inspect_project(root).plugin
    workspace = root / STATE_DIRECTORY / "ui"
    workspace.mkdir(parents=True, exist_ok=True)
    out = runtime.resolve(output) if output is not None else workspace
    report_path = workspace / "report.json"
    request = CaptureRequest(
        project=root,
        plugin=plugin,
        surface=surface,
        out=out,
        screenshot=screenshot,
        steps=tuple(steps),
        report=report_path,
        open_only=open_only,
    )
    request_path = workspace / "request.json"
    request_path.write_text(
        json.dumps(request.to_mapping(), indent=2), encoding="utf-8"
    )
    install = find_qgis_install(runtime.env, prefix=qgis_prefix, project=root)
    if install.python is None:
        typer.echo(
            f"{install.prefix} has no Python interpreter to run the capture; "
            "point --qgis-prefix at a QGIS install",
            file=runtime.err,
        )
        raise typer.Exit(code=2)
    report_path.unlink(missing_ok=True)
    env = install.environment(
        runtime.env, extra_paths=(root, *sdk_import_paths()), headless=True
    )
    env[REQUEST_ENV] = str(request_path)
    code = runtime.run_process((str(install.python), "-m", PROBE_ENTRYPOINT), root, env)
    if not report_path.exists():
        typer.echo("the QGIS capture wrote no report", file=runtime.err)
        raise typer.Exit(code=code or 1)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if code != 0 or not report.get("ok"):
        typer.echo(str(report.get("error") or "the capture failed"), file=runtime.err)
        raise typer.Exit(code=code or 1)
    return report


def _print_captures(runtime: CliRuntime, report: dict[str, Any], fmt: str) -> None:
    """Print the capture paths, or the captures themselves when YAML was asked for."""
    if fmt != "yaml":
        for kind, path in sorted(report["files"].items()):
            typer.echo(f"{kind}: {path}", file=runtime.out)
        return
    for kind, path in sorted(report["files"].items()):
        if kind != "json":
            continue
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        typer.echo(to_yaml(payload).rstrip("\n"), file=runtime.out)


@ui_app.command("list")
def list_surfaces(
    ctx: typer.Context,
    project: Annotated[Path, typer.Option(help=_PROJECT_HELP)] = Path("."),
    qgis_prefix: Annotated[Path | None, typer.Option(help=_PREFIX_HELP)] = None,
    fmt: Annotated[str, typer.Option("--format", help=_FORMAT_HELP)] = "json",
) -> None:
    """List the surfaces the plugin declares."""
    runtime: CliRuntime = ctx.obj
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
    typer.echo(_render(report["surfaces"], chosen), file=runtime.out)


@ui_app.command("open")
def open_surface(
    ctx: typer.Context,
    surface: Annotated[str, typer.Argument(help=_SURFACE_HELP)],
    project: Annotated[Path, typer.Option(help=_PROJECT_HELP)] = Path("."),
    qgis_prefix: Annotated[Path | None, typer.Option(help=_PREFIX_HELP)] = None,
    fmt: Annotated[str, typer.Option("--format", help=_FORMAT_HELP)] = "json",
) -> None:
    """Open one surface in the host and report what appeared."""
    runtime: CliRuntime = ctx.obj
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
    typer.echo(_render(report["opened"], chosen), file=runtime.out)


@ui_app.command("snapshot")
def snapshot_surface(
    ctx: typer.Context,
    surface: Annotated[str, typer.Argument(help=_SURFACE_HELP)],
    project: Annotated[Path, typer.Option(help=_PROJECT_HELP)] = Path("."),
    out: Annotated[
        Path | None,
        typer.Option(
            help=f"Where to write the capture (default: {STATE_DIRECTORY}/ui)."
        ),
    ] = None,
    screenshot: Annotated[
        bool, typer.Option("--screenshot/--no-screenshot", help="Grab the PNG too.")
    ] = True,
    act: Annotated[list[str], typer.Option(help=_STEP_HELP)] = [],  # noqa: B006
    qgis_prefix: Annotated[Path | None, typer.Option(help=_PREFIX_HELP)] = None,
    fmt: Annotated[str, typer.Option("--format", help=_FORMAT_HELP)] = "json",
) -> None:
    """Capture one surface as canonical JSON plus a PNG, optionally after acting."""
    runtime: CliRuntime = ctx.obj
    chosen = _format(fmt)
    report = _capture(
        runtime,
        project=project,
        surface=surface,
        output=out,
        screenshot=screenshot,
        steps=_steps(act),
        qgis_prefix=qgis_prefix,
    )
    _print_captures(runtime, report, chosen)


@ui_app.command("act")
def act_on_surface(
    ctx: typer.Context,
    surface: Annotated[str, typer.Argument(help=_SURFACE_HELP)],
    step: Annotated[list[str], typer.Option("--step", help=_STEP_HELP)] = [],  # noqa: B006
    project: Annotated[Path, typer.Option(help=_PROJECT_HELP)] = Path("."),
    out: Annotated[
        Path | None, typer.Option(help="Where to write the captures.")
    ] = None,
    screenshot: Annotated[
        bool, typer.Option("--screenshot/--no-screenshot", help="Grab the PNG too.")
    ] = True,
    qgis_prefix: Annotated[Path | None, typer.Option(help=_PREFIX_HELP)] = None,
    fmt: Annotated[str, typer.Option("--format", help=_FORMAT_HELP)] = "json",
) -> None:
    """Drive a surface through Qt, then capture what it became.

    This is `ui snapshot` with the interactions made mandatory: a capture of a
    surface nobody touched is what `snapshot` is for.
    """
    runtime: CliRuntime = ctx.obj
    chosen = _format(fmt)
    steps = _steps(step)
    if not steps:
        typer.echo(
            "ui act needs at least one --step NODE:VERB[:VALUE]", file=runtime.err
        )
        raise typer.Exit(code=2)
    report = _capture(
        runtime,
        project=project,
        surface=surface,
        output=out,
        screenshot=screenshot,
        steps=steps,
        qgis_prefix=qgis_prefix,
    )
    _print_captures(runtime, report, chosen)
    if chosen != "yaml":
        for applied in report["steps"]:
            # What the widget holds afterwards is the point of acting; the
            # requested value is only what was asked for.
            after = applied.get("value_after", applied.get("value"))
            typer.echo(
                f"{applied['node']} {applied['verb']} -> {after!r}", file=runtime.out
            )


@ui_app.command("diff")
def diff_captures(
    ctx: typer.Context,
    before: Annotated[Path, typer.Argument(help="Approved capture JSON.")],
    after: Annotated[Path, typer.Argument(help="New capture JSON.")],
    as_json: Annotated[
        bool, typer.Option("--json", help="Print the changes as JSON.")
    ] = False,
    fmt: Annotated[str, typer.Option("--format", help=_FORMAT_HELP)] = "json",
) -> None:
    """Compare two captures; exit 1 when anything but the image changed."""
    runtime: CliRuntime = ctx.obj
    chosen = _format(fmt)
    old = json.loads(runtime.resolve(before).read_text(encoding="utf-8"))
    new = json.loads(runtime.resolve(after).read_text(encoding="utf-8"))
    difference = diff_snapshots(old, new)
    if as_json:
        payload = {
            "structural": bool(difference),
            "identical": difference.identical,
            "changes": [
                {
                    "where": change.where,
                    "field": change.field,
                    "before": change.before,
                    "after": change.after,
                }
                for change in difference.changes
            ],
            "pixels": [
                {"where": change.where, "field": change.field}
                for change in difference.pixels
            ],
        }
        typer.echo(_render(payload, chosen), file=runtime.out)
    else:
        typer.echo(difference.render(), file=runtime.out)
    if difference:
        raise typer.Exit(code=1)

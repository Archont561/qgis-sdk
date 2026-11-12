"""Capture a surface: run the probe in a QGIS interpreter and read its report."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypedDict, Unpack

import typer

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
from qgis_sdk_tools.ui_yaml import to_yaml

__all__ = ["capture", "format", "print_captures", "render", "steps"]


def _run_capture_probe(install, report_path, request_path, root, runtime):
    if install.python is None:
        typer.echo(
            f"{install.prefix} has no Python interpreter to run the capture; "
            "point --qgis-prefix at a QGIS install",
            file=runtime.err,
        )
        raise typer.Exit(code=2)
    report_path.unlink(missing_ok=True)
    return _capture_process_environment(
        install, report_path, request_path, root, runtime
    )


def _capture_process_environment(install, report_path, request_path, root, runtime):
    env = install.environment(
        runtime.env, extra_paths=(root, *sdk_import_paths()), headless=True
    )
    env[REQUEST_ENV] = str(request_path)
    code = runtime.run_process((str(install.python), "-m", PROBE_ENTRYPOINT), root, env)
    return _read_capture_report(code, report_path, runtime)


def _read_capture_report(code, report_path, runtime):
    if not report_path.exists():
        typer.echo("the QGIS capture wrote no report", file=runtime.err)
        raise typer.Exit(code=code or 1)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if code != 0 or not report.get("ok"):
        typer.echo(str(report.get("error") or "the capture failed"), file=runtime.err)
        raise typer.Exit(code=code or 1)
    return report


def format(raw: str) -> str:
    """Refuse a format this command cannot print instead of guessing."""
    chosen = raw.lower()
    if chosen not in ("json", "yaml"):
        raise typer.BadParameter(f"{raw!r} is not json or yaml")
    return chosen


def render(payload: Any, fmt: str) -> str:
    if fmt == "yaml":
        return to_yaml(payload).rstrip("\n")
    return json.dumps(payload, ensure_ascii=False, indent=2)


def steps(raw: list[str]) -> list[ActStep]:
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


def capture(runtime: CliRuntime, **options: Unpack[_CaptureOptions]) -> dict[str, Any]:
    """Run the probe in a QGIS interpreter and return the report it wrote."""
    values = _CaptureValues(**options)
    root = runtime.resolve(values.project)
    plugin = inspect_project(root).plugin
    workspace = root / STATE_DIRECTORY / "ui"
    workspace.mkdir(parents=True, exist_ok=True)
    out = runtime.resolve(values.output) if values.output is not None else workspace
    report_path = workspace / "report.json"
    request = CaptureRequest(
        project=root,
        plugin=plugin,
        surface=values.surface,
        out=out,
        screenshot=values.screenshot,
        steps=tuple(values.steps),
        report=report_path,
        open_only=values.open_only,
    )
    request_path = workspace / "request.json"
    request_path.write_text(
        json.dumps(request.to_mapping(), indent=2), encoding="utf-8"
    )
    install = find_qgis_install(runtime.env, prefix=values.qgis_prefix, project=root)
    return _run_capture_probe(install, report_path, request_path, root, runtime)


def print_captures(runtime: CliRuntime, report: dict[str, Any], fmt: str) -> None:
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


class _CaptureOptions(TypedDict, total=False):
    project: Path
    surface: str
    output: Path | None
    screenshot: bool
    steps: list[ActStep]
    qgis_prefix: Path | None
    open_only: bool


@dataclass(frozen=True, slots=True)
class _CaptureValues:
    project: Path
    surface: str
    output: Path | None
    screenshot: bool
    steps: list[ActStep]
    qgis_prefix: Path | None
    open_only: bool = False

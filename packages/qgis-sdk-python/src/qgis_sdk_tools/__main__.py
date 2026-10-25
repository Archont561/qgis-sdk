"""The ``qgis-sdk`` command line: argument parsing over the public API, nothing else.

This module is what the wheel's ``qgis-sdk`` console script points at, and
``python -m qgis_sdk_tools`` reaches the same :func:`main`, so a pip or
``pixi add --pypi`` install gets the command without an activated environment. It is
the one executable-shaped file inside ``src/qgis_sdk`` and it is there for that
reason: unlike the automation tools in ``packages/qgis-sdk-python/scripts``, which are
development-only and are not part of either distribution, generating a project is a
library operation with no display, no QGIS and no Qt, so shipping it is the point.

All behaviour lives in :mod:`qgis_sdk_tools.scaffold`, :mod:`qgis_sdk_tools.check` and
:mod:`qgis_sdk_tools.generate`, so callers that do not want a shell reach the
same API directly. A command that reads or writes anything beyond its
arguments receives a :class:`qgis_sdk_tools.cli.CliRuntime` through ``ctx.obj``
(decision-34): the shell gets the process, a test passes its own.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import typer
from qgis_sdk.bridge.host import host_description
from qgis_sdk.models import QgisSdkBridgeError

from qgis_sdk_tools.check import QgisSdkCheckError, check_project
from qgis_sdk_tools.cli import CliRuntime
from qgis_sdk_tools.devtools import (
    QgisSdkQgisNotFoundError,
    find_qgis_install,
    wants_headless,
)
from qgis_sdk_tools.devtools.dev import (
    QgisSdkDevError,
    free_port,
    inspect_project,
    plan_dev,
    plan_web_server,
    wait_for_port,
)
from qgis_sdk_tools.devtools.testrun import (
    NATIVE_TARGETS,
    QgisSdkTestRunError,
    plan_tests,
)
from qgis_sdk_tools.generate import (
    check_generated,
    describe_plugin_spec,
    generate_host_typescript,
    generate_typescript,
    load_description,
    write_generated,
)
from qgis_sdk_tools.scaffold import (
    QgisSdkScaffoldError,
    ScaffoldOptions,
    plan_scaffold,
    write_scaffold,
)
from qgis_sdk_tools.scaffold.questionnaire import (
    Question,
    WebAnswers,
    ask_web_questions,
)
from qgis_sdk_tools.scaffold.web import install_command

app = typer.Typer(
    add_completion=False,
    help="Generate and inspect qgis-sdk plugin projects.",
)
bridge_app = typer.Typer(
    add_completion=False,
    help="Generate the TypeScript side of a plugin's bridge contract.",
)
app.add_typer(bridge_app, name="bridge")


@app.command("new")
def new(
    ctx: typer.Context,
    target: Annotated[
        Path, typer.Argument(help="Directory to create the plugin project in.")
    ],
    plugin: Annotated[
        str | None,
        typer.Option(help="Plugin package name; defaults to the target name."),
    ] = None,
    title: Annotated[
        str | None, typer.Option(help="Human-readable plugin title.")
    ] = None,
    author: Annotated[
        str | None, typer.Option(help="Author recorded in metadata.txt.")
    ] = None,
    email: Annotated[
        str | None, typer.Option(help="Author email recorded in metadata.txt.")
    ] = None,
    version: Annotated[
        str | None, typer.Option(help="Plugin version recorded in metadata.txt.")
    ] = None,
    qgis_minimum_version: Annotated[
        str | None,
        typer.Option(help="Lowest QGIS version allowed to load the plugin."),
    ] = None,
    web: Annotated[
        str | None,
        typer.Option(help="Add a web UI: vanilla or react (a terminal is asked)."),
    ] = None,
    placement: Annotated[
        str | None,
        typer.Option(help="Show the web UI as a dialog (default) or a dock."),
    ] = None,
    package_manager: Annotated[
        str | None,
        typer.Option(help="npm (default), pnpm or bun for the web UI."),
    ] = None,
    install: Annotated[
        bool | None,
        typer.Option(
            "--install/--no-install",
            help="Run the package manager's install in web/ after writing.",
        ),
    ] = None,
    no_input: Annotated[
        bool, typer.Option("--no-input", help="Never ask; flags and defaults decide.")
    ] = False,
    dry_run: Annotated[
        bool, typer.Option(help="Print the file plan and write nothing.")
    ] = False,
    force: Annotated[
        bool, typer.Option(help="Regenerate files that already exist.")
    ] = False,
) -> None:
    """Write a minimal, loadable plugin project at TARGET, with a web UI if asked."""
    runtime: CliRuntime = ctx.obj
    try:
        answers = _web_answers(
            runtime,
            web=web,
            placement=placement,
            package_manager=package_manager,
            install=install,
            no_input=no_input,
        )
        options = _resolve(
            target,
            plugin=plugin,
            title=title,
            author=author,
            email=email,
            version=version,
            qgis_minimum_version=qgis_minimum_version,
            web=answers.web,
            placement=answers.placement,
            package_manager=answers.package_manager,
        )
        root = runtime.resolve(target)
        _report(runtime, options, root, dry_run=dry_run, force=force)
    except QgisSdkScaffoldError as error:
        typer.echo(str(error), file=runtime.err)
        raise typer.Exit(code=1) from error
    if answers.install and not dry_run and options.web is not None:
        _install(runtime, options, target, root)


def _web_answers(
    runtime: CliRuntime,
    *,
    web: str | None,
    placement: str | None,
    package_manager: str | None,
    install: bool | None,
    no_input: bool,
) -> WebAnswers:
    """Flags when any were given; the questionnaire on a terminal; else no web UI."""
    flagged = any(value is not None for value in (web, placement, package_manager))
    if install and not flagged:
        raise QgisSdkScaffoldError("--install needs --web vanilla or --web react")
    if flagged or no_input or not runtime.interactive:
        return WebAnswers(web, placement, package_manager, bool(install))
    return ask_web_questions(_prompter(runtime))


def _prompter(runtime: CliRuntime) -> Callable[[Question, str | None], str]:
    """Show a question on the runtime's streams and read one line; EOF is silence."""

    def ask(question: Question, error: str | None) -> str:
        if error is not None:
            typer.echo(error, file=runtime.out)
        choices = "/".join(question.choices)
        typer.echo(
            f"{question.prompt} [{choices}] ({question.default}): ",
            file=runtime.out,
            nl=False,
        )
        runtime.out.flush()
        return runtime.inp.readline()

    return ask


def _install(
    runtime: CliRuntime, options: ScaffoldOptions, target: Path, root: Path
) -> None:
    """Run the manager's install in web/; on failure keep every file and say how to retry."""
    assert options.web is not None
    command = install_command(options.web.package_manager)
    shown = " ".join(command)
    # Forward slashes: valid in every shell the managers run in, and the
    # message reads the same on every platform.
    web = (target / "web").as_posix()
    typer.echo(f"{shown} in {web} ...", file=runtime.out)
    exit_code = runtime.run_process(command, root / "web")
    if exit_code == 0:
        typer.echo(f"{shown}: done", file=runtime.out)
        return
    typer.echo(
        f"{shown} failed (exit {exit_code}). The project is complete; retry with:\n"
        f"  cd {web} && {shown}",
        file=runtime.err,
    )
    raise typer.Exit(code=1)


# ``scaffold`` was the command's name through 0.3.0. It keeps working so an
# existing script or tutorial does not break, but it is hidden from --help and
# marked deprecated; ``new`` is the spelling from here on.
app.command("scaffold", hidden=True, deprecated=True)(new)


@bridge_app.command("generate")
def bridge_generate(
    plugin: Annotated[
        str | None,
        typer.Option(help="Plugin class as module:Attribute, described without QGIS."),
    ] = None,
    description: Annotated[
        Path | None,
        typer.Option(help="Plugin description JSON a host already produced."),
    ] = None,
    host: Annotated[
        bool,
        typer.Option(
            "--host", help="Render the curated host surface instead of a plugin."
        ),
    ] = False,
    out: Annotated[
        Path | None, typer.Option(help="TypeScript module to write or check.")
    ] = None,
    check: Annotated[
        bool, typer.Option(help="Fail when OUT differs from a fresh generation.")
    ] = False,
    show: Annotated[
        bool, typer.Option("--print", help="Write the module to stdout instead.")
    ] = False,
) -> None:
    """Turn one plugin description into a typed TypeScript client."""
    try:
        described, generator = _describe(plugin, description, host)
        if show:
            typer.echo(generator(described), nl=False)
        elif out is None:
            raise QgisSdkBridgeError("give --out, --check or --print")
        elif check:
            message = check_generated(out, described, generate=generator)
            if message is not None:
                typer.echo(message, err=True)
                raise typer.Exit(code=1)
            typer.echo(f"{out} is up to date")
        else:
            changed = write_generated(out, described, generate=generator)
            typer.echo(f"{'wrote' if changed else 'unchanged'} {out}")
    except (QgisSdkBridgeError, QgisSdkScaffoldError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1) from error


def _describe(
    plugin: str | None, description: Path | None, host: bool
) -> tuple[dict, Callable[[dict], str]]:
    """Return the description and the renderer named by exactly one source."""
    if host:
        if plugin is not None or description is not None:
            raise QgisSdkBridgeError(
                "--host renders the curated host surface; give no --plugin or --description"
            )
        return host_description(), generate_host_typescript
    if (plugin is None) == (description is None):
        raise QgisSdkBridgeError("give exactly one of --plugin or --description")
    if plugin is not None:
        return describe_plugin_spec(plugin), generate_typescript
    return load_description(description), generate_typescript


@app.command("check")
def check(
    ctx: typer.Context,
    path: Annotated[
        Path | None,
        typer.Argument(help="Plugin project root; defaults to the working directory."),
    ] = None,
    native: Annotated[
        list[str] | None,
        typer.Option(
            "--native",
            help="Module glob allowed to import QGIS at load time (repeatable).",
        ),
    ] = None,
    as_json: Annotated[
        bool, typer.Option("--json", help="Print the report as JSON.")
    ] = False,
) -> None:
    """Read a plugin project and report problems; import, install and change nothing."""
    runtime: CliRuntime = ctx.obj
    root = runtime.resolve(path or Path("."))
    try:
        report = check_project(root, native_modules=tuple(native or ()))
    except QgisSdkCheckError as error:
        typer.echo(str(error), file=runtime.err)
        raise typer.Exit(code=2) from error
    if as_json:
        typer.echo(json.dumps(report.to_json(), indent=2), file=runtime.out)
    else:
        for diagnostic in report.diagnostics:
            typer.echo(diagnostic.render(), file=runtime.out)
        count = len(report.diagnostics)
        problems = (
            "no problems"
            if count == 0
            else f"{count} problem{'s' if count != 1 else ''}"
        )
        typer.echo(
            f"checked {report.files_checked} files: {problems}", file=runtime.out
        )
    if not report.ok:
        raise typer.Exit(code=1)


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
            "desktop (inside QGIS Desktop) or web (Vitest)."
        ),
    ] = "pure",
    qgis_prefix: Annotated[
        Path | None,
        typer.Option(help="QGIS install prefix for the qgis and desktop targets."),
    ] = None,
) -> None:
    """Run the project's tests for one target; other arguments go to pytest."""
    runtime: CliRuntime = ctx.obj
    root = runtime.resolve(project or Path("."))
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


@app.command("dev")
def dev(
    ctx: typer.Context,
    path: Annotated[
        Path | None,
        typer.Argument(help="Plugin project root; defaults to the working directory."),
    ] = None,
    mode: Annotated[
        str,
        typer.Option(
            help="desktop (default: real QGIS Desktop, isolated profile, Reload) "
            "or standalone (bare QgsApplication: no iface, no lifecycle)."
        ),
    ] = "desktop",
    qgis_prefix: Annotated[
        Path | None, typer.Option(help="QGIS install prefix to run.")
    ] = None,
    no_web: Annotated[
        bool,
        typer.Option(
            "--no-web", help="Do not start the Vite dev server; serve web/ as built."
        ),
    ] = False,
    port: Annotated[
        int | None, typer.Option(help="Loopback port for the Vite dev server.")
    ] = None,
    no_watch: Annotated[
        bool,
        typer.Option(
            "--no-watch",
            help="Do not reload on saved Python/metadata changes; "
            "only the Reload button (Ctrl+Shift+R) reloads.",
        ),
    ] = False,
    exercise: Annotated[
        Path | None, typer.Option(hidden=True, help="Self-drive and write a report.")
    ] = None,
) -> None:
    """Run the source plugin inside QGIS, reloading on save, with HMR for a web UI."""
    runtime: CliRuntime = ctx.obj
    root = runtime.resolve(path or Path("."))
    try:
        project = inspect_project(root)
        install = find_qgis_install(runtime.env, prefix=qgis_prefix, project=root)
        server_plan = None if no_web else plan_web_server(project, port or free_port())
    except (QgisSdkDevError, QgisSdkQgisNotFoundError) as error:
        typer.echo(str(error), file=runtime.err)
        raise typer.Exit(code=2) from error
    workspace = Path(tempfile.mkdtemp(prefix="qgis-sdk-dev-"))
    server = None
    origin = None
    try:
        if server_plan is not None:
            shown = " ".join(server_plan.argv)
            typer.echo(f"web: {shown} in web/", file=runtime.err)
            server = runtime.start_process(
                server_plan.argv, server_plan.cwd, runtime.env
            )
            if server is None:
                typer.echo(
                    f"{server_plan.argv[0]} was not found; install it or pass --no-web",
                    file=runtime.err,
                )
                raise typer.Exit(code=2)
            if not wait_for_port(
                server_plan.port, still_running=lambda: server.poll() is None
            ):
                typer.echo(
                    f"the dev server did not answer on {server_plan.origin}; see its "
                    "output above, or pass --no-web to run without it",
                    file=runtime.err,
                )
                raise typer.Exit(code=2)
            origin = server_plan.origin
            typer.echo(f"web: {origin} (hot module replacement)", file=runtime.err)
        plan = plan_dev(
            project,
            mode,
            install,
            env=runtime.env,
            workspace=workspace,
            headless=wants_headless(runtime.env),
            dev_server=origin,
            exercise=exercise,
            watch=not no_watch,
        )
        for note in plan.notes:
            typer.echo(note, file=runtime.err)
        exit_code = runtime.run_process(plan.argv, plan.cwd, plan.env)
    except QgisSdkDevError as error:
        typer.echo(str(error), file=runtime.err)
        raise typer.Exit(code=2) from error
    finally:
        if server is not None and server.poll() is None:
            server.terminate()
            server.wait(timeout=10)
        shutil.rmtree(workspace, ignore_errors=True)
    if exit_code == 127:
        typer.echo(f"{plan.argv[0]} was not found", file=runtime.err)
    raise typer.Exit(code=exit_code)


@app.callback()
def _callback(ctx: typer.Context) -> None:
    """Keep ``new`` a subcommand, and give every command its runtime."""
    if ctx.obj is None:
        ctx.obj = CliRuntime.for_process()


def _resolve(
    target: Path,
    *,
    plugin: str | None,
    title: str | None,
    author: str | None,
    email: str | None,
    version: str | None,
    qgis_minimum_version: str | None,
    web: str | None,
    placement: str | None,
    package_manager: str | None,
) -> ScaffoldOptions:
    """Pass only what the caller chose, so the API keeps its own defaults."""
    given = {"plugin": plugin or target.name}
    for key, value in (
        ("title", title),
        ("author", author),
        ("email", email),
        ("version", version),
        ("qgis_minimum_version", qgis_minimum_version),
        ("web", web),
        ("placement", placement),
        ("package_manager", package_manager),
    ):
        if value is not None:
            given[key] = value
    return ScaffoldOptions.resolve(**given)


def _report(
    runtime: CliRuntime,
    options: ScaffoldOptions,
    root: Path,
    *,
    dry_run: bool,
    force: bool,
) -> None:
    """Echo one project-relative path per line, planned or written."""
    if dry_run:
        for file in plan_scaffold(options):
            typer.echo(file.path, file=runtime.out)
        return
    for path in write_scaffold(options, root, force=force):
        typer.echo(path.relative_to(root).as_posix(), file=runtime.out)


def main() -> None:
    """Run the command line; the wheel registers this as ``qgis-sdk``."""
    app()


if __name__ == "__main__":
    main()

"""``qgis-sdk new`` (and the deprecated ``scaffold`` spelling)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import typer

from qgis_sdk_tools._commands._app import _install, app
from qgis_sdk_tools.cli import CliRuntime
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
from qgis_sdk_tools.scaffold.web import (
    SDK_NPM_VERSION,
    UI_NPM_VERSION,
)


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
    algorithm: Annotated[
        bool,
        typer.Option(
            "--algorithm",
            help="Start with a Processing provider and one function algorithm.",
        ),
    ] = False,
    ui: Annotated[
        str | None,
        typer.Option(
            "--ui",
            help="native: a bound Dialog in pure PyQt plus a toolbar action opening it.",
        ),
    ] = None,
    host: Annotated[
        str,
        typer.Option(
            "--host",
            help=(
                "desktop (default): QGIS loads classFactory. server: QGIS Server "
                "loads serverClassFactory and the starter declares filters, "
                "services and access hooks instead of actions. app: a standalone "
                "PyQGIS application - `python -m <package>` or `qgis-sdk run` - "
                "with its own window and no plugin lifecycle."
            ),
        ),
    ] = "desktop",
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
    sdk_dependency: Annotated[
        str | None,
        typer.Option(
            help=(
                "What web/package.json depends on for @archont561/qgis-sdk: "
                f"the latest release ({SDK_NPM_VERSION}) unless given; inside "
                "the SDK repository pass file:<path to packages/qgis-sdk-typescript>."
            ),
        ),
    ] = None,
    ui_dependency: Annotated[
        str | None,
        typer.Option(
            help=(
                "The same for @archont561/qgis-sdk-ui, the web components the page "
                f"opts into: the latest release ({UI_NPM_VERSION}) unless given."
            ),
        ),
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
            sdk_dependency=sdk_dependency,
            ui_dependency=ui_dependency,
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
            sdk_dependency=sdk_dependency,
            ui_dependency=ui_dependency,
            algorithm=algorithm,
            ui=ui,
            host=host,
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
    sdk_dependency: str | None,
    ui_dependency: str | None = None,
    install: bool | None,
    no_input: bool,
) -> WebAnswers:
    """Flags when any were given; the questionnaire on a terminal; else no web UI."""
    flagged = any(
        value is not None
        for value in (web, placement, package_manager, sdk_dependency, ui_dependency)
    )
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


# ``scaffold`` was the command's name through 0.3.0. It keeps working so an
# existing script or tutorial does not break, but it is hidden from --help and
# marked deprecated; ``new`` is the spelling from here on.
app.command("scaffold", hidden=True, deprecated=True)(new)


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
    sdk_dependency: str | None = None,
    ui_dependency: str | None = None,
    algorithm: bool = False,
    ui: str | None = None,
    host: str = "desktop",
) -> ScaffoldOptions:
    """Pass only what the caller chose, so the API keeps its own defaults."""
    given: dict[str, object] = {"plugin": plugin or target.name}
    if algorithm:
        given["algorithm"] = True
    if ui is not None:
        given["ui"] = ui
    if host != "desktop":
        given["host"] = host
    for key, value in (
        ("title", title),
        ("author", author),
        ("email", email),
        ("version", version),
        ("qgis_minimum_version", qgis_minimum_version),
        ("web", web),
        ("placement", placement),
        ("package_manager", package_manager),
        ("sdk_dependency", sdk_dependency),
        ("ui_dependency", ui_dependency),
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

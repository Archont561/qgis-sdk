"""``qgis-sdk new`` (and the deprecated ``scaffold`` spelling)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, TypedDict, Unpack

import typer
from qgis_sdk._published import REQUIRED, published

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

_CcAnn1 = Annotated[
    Path, typer.Argument(help="Directory to create the plugin project in.")
]
_CcAnn2 = Annotated[
    str | None,
    typer.Option(help="Plugin package name; defaults to the target name."),
]
_CcAnn3 = Annotated[str | None, typer.Option(help="Human-readable plugin title.")]
_CcAnn4 = Annotated[str | None, typer.Option(help="Author recorded in metadata.txt.")]
_CcAnn5 = Annotated[
    str | None, typer.Option(help="Author email recorded in metadata.txt.")
]
_CcAnn6 = Annotated[
    str | None, typer.Option(help="Plugin version recorded in metadata.txt.")
]
_CcAnn7 = Annotated[
    str | None,
    typer.Option(help="Lowest QGIS version allowed to load the plugin."),
]
_CcAnn8 = Annotated[
    bool,
    typer.Option(
        "--algorithm",
        help="Start with a Processing provider and one function algorithm.",
    ),
]
_CcAnn9 = Annotated[
    str | None,
    typer.Option(
        "--ui",
        help="native: a bound Dialog in pure PyQt plus a toolbar action opening it.",
    ),
]
_CcAnn10 = Annotated[
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
]
_CcAnn11 = Annotated[
    str | None,
    typer.Option(help="Add a web UI: vanilla or react (a terminal is asked)."),
]
_CcAnn12 = Annotated[
    str | None,
    typer.Option(help="Show the web UI as a dialog (default) or a dock."),
]
_CcAnn13 = Annotated[
    str | None,
    typer.Option(help="npm (default), pnpm or bun for the web UI."),
]
_CcAnn14 = Annotated[
    str | None,
    typer.Option(
        help=(
            "What web/package.json depends on for @archont561/qgis-sdk: "
            f"the latest release ({SDK_NPM_VERSION}) unless given; inside "
            "the SDK repository pass file:<path to packages/qgis-sdk-typescript>."
        ),
    ),
]
_CcAnn15 = Annotated[
    str | None,
    typer.Option(
        help=(
            "The same for @archont561/qgis-sdk-ui, the web components the page "
            f"opts into: the latest release ({UI_NPM_VERSION}) unless given."
        ),
    ),
]
_CcAnn16 = Annotated[
    bool | None,
    typer.Option(
        "--install/--no-install",
        help="Run the package manager's install in web/ after writing.",
    ),
]
_CcAnn17 = Annotated[
    bool, typer.Option("--no-input", help="Never ask; flags and defaults decide.")
]
_CcAnn18 = Annotated[bool, typer.Option(help="Print the file plan and write nothing.")]
_CcAnn19 = Annotated[bool, typer.Option(help="Regenerate files that already exist.")]


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


def _cc_new_p1(_s):
    _s.answers = _web_answers(
        _s.runtime,
        web=_s.web,
        placement=_s.placement,
        package_manager=_s.package_manager,
        sdk_dependency=_s.sdk_dependency,
        ui_dependency=_s.ui_dependency,
        install=_s.install,
        no_input=_s.no_input,
    )


def _cc_new_p2(_s):
    _s.options = _resolve(
        _s.target,
        plugin=_s.plugin,
        title=_s.title,
        author=_s.author,
        email=_s.email,
        version=_s.version,
        qgis_minimum_version=_s.qgis_minimum_version,
        web=_s.answers.web,
        placement=_s.answers.placement,
        package_manager=_s.answers.package_manager,
        sdk_dependency=_s.sdk_dependency,
        ui_dependency=_s.ui_dependency,
        algorithm=_s.algorithm,
        ui=_s.ui,
        host=_s.host,
    )


def _cc_new_p3(_s):
    _s.root = _s.runtime.resolve(_s.target)
    _report(_s.runtime, _s.options, _s.root, dry_run=_s.dry_run, force=_s.force)


def _cc_new_p4(_s):
    typer.echo(str(_s.error), file=_s.runtime.err)
    raise typer.Exit(code=1) from _s.error


def _cc_new_p5(_s):
    _s.runtime: CliRuntime = _s.ctx.obj
    try:
        for _p in (_cc_new_p1, _cc_new_p2, _cc_new_p3):
            _r = _p(_s)
            if isinstance(_r, _CcReturn):
                return _r
    except QgisSdkScaffoldError as error:
        _s.error = error
        for _p in (_cc_new_p4,):
            _r = _p(_s)
            if isinstance(_r, _CcReturn):
                return _r


def _cc_new_p6(_s):
    if _s.answers.install and not _s.dry_run and _s.options.web is not None:
        _install(_s.runtime, _s.options, _s.target, _s.root)


_CC_SPECS_new_1 = (
    ("ctx", typer.Context, REQUIRED, "positional"),
    ("target", _CcAnn1, REQUIRED, "positional"),
    ("plugin", _CcAnn2, None, "positional"),
    ("title", _CcAnn3, None, "positional"),
    ("author", _CcAnn4, None, "positional"),
    ("email", _CcAnn5, None, "positional"),
    ("version", _CcAnn6, None, "positional"),
    ("qgis_minimum_version", _CcAnn7, None, "positional"),
    ("algorithm", _CcAnn8, False, "positional"),
    ("ui", _CcAnn9, None, "positional"),
    ("host", _CcAnn10, "desktop", "positional"),
    ("web", _CcAnn11, None, "positional"),
    ("placement", _CcAnn12, None, "positional"),
    ("package_manager", _CcAnn13, None, "positional"),
    ("sdk_dependency", _CcAnn14, None, "positional"),
    ("ui_dependency", _CcAnn15, None, "positional"),
    ("install", _CcAnn16, None, "positional"),
    ("no_input", _CcAnn17, False, "positional"),
    ("dry_run", _CcAnn18, False, "positional"),
    ("force", _CcAnn19, False, "positional"),
)


@app.command("new")
@published(_CC_SPECS_new_1, returns=type(None))
def new(_published_values):
    """Write a minimal, loadable plugin project at TARGET, with a web UI if asked."""
    _s = _published_values
    for _p in (_cc_new_p5, _cc_new_p6):
        _r = _p(_s)
        if isinstance(_r, _CcReturn):
            return _r.value
    return None


def _web_answers(runtime: CliRuntime, **options: Unpack[_WebOptions1]) -> WebAnswers:
    """Flags when any were given; the questionnaire on a terminal; else no web UI."""
    values = _WebValues1(**options)
    flagged = any(
        value is not None
        for value in (
            values.web,
            values.placement,
            values.package_manager,
            values.sdk_dependency,
            values.ui_dependency,
        )
    )
    if values.install and not flagged:
        raise QgisSdkScaffoldError("--install needs --web vanilla or --web react")
    if flagged or values.no_input or not runtime.interactive:
        return WebAnswers(
            values.web, values.placement, values.package_manager, bool(values.install)
        )
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


def _resolve(target: Path, **options: Unpack[_ResolveOptions1]) -> ScaffoldOptions:
    """Pass only what the caller chose, so the API keeps its own defaults."""
    values = _ResolveValues1(**options)
    given: dict[str, object] = {"plugin": values.plugin or target.name}
    if values.algorithm:
        given["algorithm"] = True
    if values.ui is not None:
        given["ui"] = values.ui
    if values.host != "desktop":
        given["host"] = values.host
    for key, value in (
        ("title", values.title),
        ("author", values.author),
        ("email", values.email),
        ("version", values.version),
        ("qgis_minimum_version", values.qgis_minimum_version),
        ("web", values.web),
        ("placement", values.placement),
        ("package_manager", values.package_manager),
        ("sdk_dependency", values.sdk_dependency),
        ("ui_dependency", values.ui_dependency),
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


class _WebOptions1(TypedDict, total=False):
    web: str | None
    placement: str | None
    package_manager: str | None
    sdk_dependency: str | None
    ui_dependency: str | None
    install: bool | None
    no_input: bool


@dataclass(frozen=True, slots=True)
class _WebValues1:
    web: str | None
    placement: str | None
    package_manager: str | None
    sdk_dependency: str | None
    install: bool | None
    no_input: bool
    ui_dependency: str | None = None


class _ResolveOptions1(TypedDict, total=False):
    plugin: str | None
    title: str | None
    author: str | None
    email: str | None
    version: str | None
    qgis_minimum_version: str | None
    web: str | None
    placement: str | None
    package_manager: str | None
    sdk_dependency: str | None
    ui_dependency: str | None
    algorithm: bool
    ui: str | None
    host: str


@dataclass(frozen=True, slots=True)
class _ResolveValues1:
    plugin: str | None
    title: str | None
    author: str | None
    email: str | None
    version: str | None
    qgis_minimum_version: str | None
    web: str | None
    placement: str | None
    package_manager: str | None
    sdk_dependency: str | None = None
    ui_dependency: str | None = None
    algorithm: bool = False
    ui: str | None = None
    host: str = "desktop"

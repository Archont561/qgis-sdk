"""The plan behind ``qgis-sdk dev``: the source plugin inside a real QGIS.

Two modes, both explicit (decision-8):

``desktop`` (default)
    the QGIS Desktop binary from the discovered install, an isolated profile
    at ``<project>/.qgis-sdk/profiles/dev``, and a generated host package at
    ``<project>/.qgis-sdk/dev/host/<plugin>/`` on ``QGIS_PLUGINPATH``
    (decision-43): its ``metadata.txt`` is rendered from ``pyproject.toml``
    and its ``__init__.py`` extends the package path with the project's
    sources and binds ``classFactory`` through
    ``qgis_sdk.adapters.desktop.host()`` - the author's tree is loaded *in
    place*, never copied. A bootstrap loads and starts it and adds a
    **Reload** action (toolbar button, ``Ctrl+Shift+R``). Reload is guarded:
    a preflight compiles every module first and a syntax error keeps the
    running revision; a failed unload or a failed start leaves the plugin
    disabled and says so, with ``qgis-sdk dev`` itself as the restart.
``standalone``
    a bare ``QgsApplication`` started by the install's interpreter, the plugin
    constructed through the same generated package's ``classFactory(None)``.
    There is no ``iface``, no plugin menu, no QGIS lifecycle and no reload;
    what it offers is a fast loop for the web page and the declared actions.
``server``
    the install's interpreter with a real ``QgsServer`` in the process,
    answering HTTP on loopback through ``QgsServer.handleRequest``: no FCGI,
    no browser, no profile. The plugin is loaded through the same generated
    package's ``serverClassFactory``, and a saved change reloads it by handing
    QGIS's registration the new hook set (``QgsServerHost.rebind``), because
    QGIS Server cannot withdraw a filter, a service or an access-control
    object once registered. A priority or a service name that changes needs a
    new ``qgis-sdk dev``; a failed reload leaves the endpoint answering 503 and
    says why (``devtools.serverdev``).

``qgis-sdk run`` is the same discovery without QGIS Desktop: it starts the
standalone app host - ``<install python> -m <plugin>``, the project's own
``__main__.py``, or a generated probe for a project that has none - in the
project root, with the install's PyQGIS on ``PYTHONPATH``. Nothing is generated
in the project and nothing is installed; the flags are ``qgis_sdk.app``'s
(``--headless``, ``--once``, ``--grace``, ``--title``).

With a web UI the command starts the project's Vite dev server on loopback
and hands its origin to the plugin through ``QGIS_SDK_DEV_SERVER``; the
runtime's page view loads from there, with HMR, only when that variable is
set. ``vite build`` output never references it.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, TypedDict

from qgis_sdk.environment import DEV_REQUEST_ENV, DEV_SERVER_ENV
from qgis_sdk.models import QgisSdkError

from qgis_sdk_tools.artifacts import (
    QgisSdkArtifactError,
    introspect_plugin,
    write_dev_host,
)
from qgis_sdk_tools.devtools.installs import (
    QgisInstall,
    sdk_import_paths,
)
from qgis_sdk_tools.devtools.testrun import package_manager_for
from qgis_sdk_tools.project import ProjectConfig, QgisSdkProjectError, require_project
from qgis_sdk_tools.scaffold.web import script_command

from ._helpers import LOOPBACK, SERVER_PROBE


def plan_app_phase1(argv, gui, note, process_env, root):
    return DevPlan(
        mode="app",
        argv=argv,
        cwd=root,
        env=process_env,
        notes=(
            note,
            (
                "stop: close the window or press Ctrl+C; the app waits for "
                "running jobs, names every loop it stops, then exits QGIS once"
                if gui
                else "stop: Ctrl+C; the app waits for running jobs, names every loop "
                "it stops, then exits QGIS once"
            ),
        ),
        profile=None,
    )


MODES: Final = ("desktop", "standalone", "server")
PROFILE_NAME: Final = "dev"
STATE_DIRECTORY: Final = ".qgis-sdk"
REQUEST_ENV: Final = DEV_REQUEST_ENV
"""The request file this command writes; the name lives in the runtime (console)."""
DESKTOP_PROBE_NAME: Final = "dev-desktop.py"
STANDALONE_PROBE_NAME: Final = "dev-standalone.py"
SERVER_PROBE_NAME: Final = "dev-server.py"
APP_PROBE_NAME: Final = "run-app.py"
REQUEST_NAME: Final = "dev-request.json"


class QgisSdkDevError(QgisSdkError):
    """``dev`` cannot start: no plugin package, bad mode, or a tool is missing."""


@dataclass(frozen=True, slots=True)
class DevProject:
    """What ``dev`` learned from the project directory."""

    root: Path
    plugin: str
    web: Path | None
    config: ProjectConfig

    @property
    def has_web(self) -> bool:
        return self.web is not None


@dataclass(frozen=True, slots=True)
class WebServerPlan:
    """The Vite dev server: how to start it and where it will answer."""

    argv: tuple[str, ...]
    cwd: Path
    port: int

    @property
    def origin(self) -> str:
        return f"http://{LOOPBACK}:{self.port}"


@dataclass(frozen=True, slots=True)
class DevPlan:
    """The QGIS process to run: binary or interpreter, environment, notes."""

    mode: str
    argv: tuple[str, ...]
    cwd: Path
    env: dict[str, str]
    notes: tuple[str, ...]
    profile: Path | None


def inspect_project(root: Path) -> DevProject:
    """Read ``[tool.qgis-sdk] plugin`` at ``root`` and whether the project has a web UI."""
    root = Path(root).resolve()
    if not root.is_dir():
        raise QgisSdkDevError(f"{root} is not a directory; give a project root")
    try:
        config = require_project(root)
    except QgisSdkProjectError as error:
        raise QgisSdkDevError(str(error)) from error
    package = root / config.plugin
    if not (package / "__init__.py").is_file():
        raise QgisSdkDevError(
            f"[tool.qgis-sdk] plugin = {config.spec!r} names the package "
            f"`{config.plugin}`, but {package} has no __init__.py"
        )
    web = root / "web"
    return DevProject(
        root=root,
        plugin=config.plugin,
        web=web if (web / "package.json").is_file() else None,
        config=config,
    )


def stage_host(project: DevProject) -> Path:
    """Write the generated host package under ``.qgis-sdk/dev/host``; return that dir.

    Imports the plugin application once, in this interpreter, to read its title
    and providers for ``metadata.txt`` - the same facts ``build`` renders,
    so the two files are byte-identical.
    """
    try:
        facts = introspect_plugin(project.config)
    except QgisSdkArtifactError as error:
        raise QgisSdkDevError(str(error)) from error
    return write_dev_host(project.config, facts, state=project.root / STATE_DIRECTORY)


def plan_web_server(project: DevProject, port: int) -> WebServerPlan | None:
    """The Vite dev server for a web project, bound to loopback; None without one."""
    if project.web is None:
        return None
    manager = package_manager_for(project.web)
    if not (project.web / "node_modules").is_dir():
        raise QgisSdkDevError(
            f"web/node_modules is missing; run `{manager} install` in web/ first "
            "(qgis-sdk never installs on your behalf), or pass --no-web"
        )
    argv = [*script_command(manager, "dev")]  # type: ignore[arg-type]
    if manager == "npm":
        argv.append("--")
    argv.extend(("--host", LOOPBACK, "--port", str(port), "--strictPort"))
    return WebServerPlan(argv=tuple(argv), cwd=project.web, port=port)


class DevOptions(TypedDict, total=False):
    """The keyword options ``plan_dev`` accepts; a single typed record.

    Every key is optional because the tests and ``_dev`` command build a plan
    with only the knobs the chosen mode needs (decision-81).
    """

    env: Mapping[str, str]
    workspace: Path
    headless: bool
    dev_server: str | None
    exercise: Path | None
    watch: bool
    port: int | None


class AppOptions(TypedDict, total=False):
    """The keyword options ``plan_app`` accepts; a single typed record."""

    env: Mapping[str, str]
    workspace: Path
    gui: bool
    once: bool
    grace: float | None
    title: str | None
    toolkit_args: Sequence[str]


@dataclass(frozen=True, slots=True)
class DevFacts:
    """Everything a mode planner needs, resolved once from the typed options."""

    project: DevProject
    mode: str
    install: QgisInstall
    env: Mapping[str, str]
    workspace: Path
    headless: bool
    dev_server: str | None
    exercise: Path | None
    watch: bool
    port: int | None
    host_root: Path
    request_path: Path
    served: str


def _dev_request(
    project: DevProject,
    mode: str,
    host_root: Path,
    dev_server: str | None,
    options: DevOptions,
) -> dict[str, object]:
    """The JSON request the generated probe reads from the workspace."""
    exercise = options.get("exercise")
    return {
        "root": str(project.root),
        "plugin": project.plugin,
        "host": str(host_root),
        "mode": mode,
        "web": project.has_web and mode != "server",
        "dev_server": dev_server,
        "port": options.get("port"),
        "exercise": None if exercise is None else str(exercise),
        "watch": options.get("watch", True),
    }


def _validate_dev_mode(mode: str) -> None:
    if mode not in MODES:
        raise QgisSdkDevError(
            f"unknown mode {mode!r}; choose one of {', '.join(MODES)}"
        )


def _write_dev_request(workspace: Path, request: dict[str, object]) -> Path:
    """Write the JSON the generated probe reads; return its path."""
    path = workspace / REQUEST_NAME
    path.write_text(json.dumps(request, indent=2), encoding="utf-8")
    return path


def dev_facts(
    project: DevProject,
    mode: str,
    install: QgisInstall,
    options: DevOptions,
) -> DevFacts:
    """Resolve every mode planner input once from the typed options."""
    _validate_dev_mode(mode)
    workspace = Path(options.get("workspace", "."))
    dev_server = options.get("dev_server")
    host_root = stage_host(project)
    request = _dev_request(project, mode, host_root, dev_server, options)
    request_path = _write_dev_request(workspace, request)
    return DevFacts(
        project=project,
        mode=mode,
        install=install,
        env=options.get("env", {}),
        workspace=workspace,
        headless=options.get("headless", False),
        dev_server=dev_server,
        exercise=options.get("exercise"),
        watch=options.get("watch", True),
        port=options.get("port"),
        host_root=host_root,
        request_path=request_path,
        served="" if dev_server is None else f", page from {dev_server}",
    )


def probe_env(
    facts: DevFacts, *, headless: bool, desktop: bool = False
) -> dict[str, str]:
    """Build the QGIS process environment and point it at the written request."""
    process_env = facts.install.environment(
        facts.env,
        extra_paths=(facts.host_root, *sdk_import_paths()),
        headless=headless,
        desktop=desktop,
    )
    process_env[REQUEST_ENV] = str(facts.request_path)
    if facts.dev_server is not None:
        process_env[DEV_SERVER_ENV] = facts.dev_server
    return process_env


def reload_note(facts: DevFacts, when_on: str, when_off: str) -> str:
    return when_on if facts.watch else when_off


def _server_notes(
    facts: DevFacts, install: QgisInstall, origin: str
) -> tuple[str, ...]:
    """The three console lines a server-mode run prints."""
    return (
        (
            f"server: QGIS Server from {install.prefix} "
            f"({install.source}) answering on {origin} through "
            f"{facts.project.plugin} from {facts.project.root}; nothing is installed "
            "and no FCGI process is started"
        ),
        (
            f"try: curl '{origin}/?MAP=/path/to/project.qgs&SERVICE=WMS"
            "&REQUEST=GetCapabilities', or the SERVICE your plugin declares"
        ),
        reload_note(
            facts,
            "reload: a saved Python change re-imports the plugin and hands "
            "QGIS's registration the new hooks; a changed priority or "
            "service name needs a new `qgis-sdk dev`; Ctrl+C stops it",
            "reload: off (--no-watch); Ctrl+C stops it",
        ),
    )


def server_plan(facts: DevFacts) -> DevPlan:
    """The QGIS Server interpreter answering HTTP on loopback."""
    install = facts.install
    if install.python is None:
        raise QgisSdkDevError(
            f"{install.prefix} has no Python interpreter, so it cannot run "
            "the server mode; QGIS Server bindings only import into the "
            "interpreter they were built for"
        )
    if facts.port is None:
        raise QgisSdkDevError("server mode needs a loopback port")
    probe = facts.workspace / SERVER_PROBE_NAME
    probe.write_text(SERVER_PROBE, encoding="utf-8", newline="\n")
    process_env = probe_env(facts, headless=True)
    origin = f"http://{LOOPBACK}:{facts.port}"
    return DevPlan(
        mode=facts.mode,
        argv=(str(install.python), str(probe)),
        cwd=facts.project.root,
        env=process_env,
        notes=_server_notes(facts, install, origin),
        profile=None,
    )

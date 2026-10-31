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
import os
import socket
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from qgis_sdk.environment import DEV_REQUEST_ENV, DEV_SERVER_ENV
from qgis_sdk.models import QgisSdkError

from qgis_sdk_tools.artifacts import (
    QgisSdkArtifactError,
    introspect_plugin,
    write_dev_host,
)
from qgis_sdk_tools.project import ProjectConfig, QgisSdkProjectError, require_project
from qgis_sdk_tools.scaffold.web import script_command

from .installs import QgisInstall, sdk_import_paths, wants_headless
from .testrun import package_manager_for

__all__ = [
    "DEV_SERVER_ENV",
    "MODES",
    "PROFILE_NAME",
    "REQUEST_ENV",
    "STATE_DIRECTORY",
    "DevPlan",
    "DevProject",
    "QgisSdkDevError",
    "WebServerPlan",
    "free_port",
    "inspect_project",
    "plan_app",
    "plan_dev",
    "plan_web_server",
    "stage_host",
    "wait_for_port",
]

MODES: Final = ("desktop", "standalone", "server")
PROFILE_NAME: Final = "dev"
STATE_DIRECTORY: Final = ".qgis-sdk"
REQUEST_ENV: Final = DEV_REQUEST_ENV
"""The request file this command writes; the name lives in the runtime (console)."""
LOOPBACK: Final = "127.0.0.1"
DESKTOP_PROBE_NAME: Final = "dev-desktop.py"
STANDALONE_PROBE_NAME: Final = "dev-standalone.py"
SERVER_PROBE_NAME: Final = "dev-server.py"
APP_PROBE_NAME: Final = "run-app.py"
REQUEST_NAME: Final = "dev-request.json"
SERVER_START_SECONDS: Final = 60.0


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


def plan_dev(
    project: DevProject,
    mode: str,
    install: QgisInstall,
    *,
    env: Mapping[str, str],
    workspace: Path,
    headless: bool = False,
    dev_server: str | None = None,
    exercise: Path | None = None,
    watch: bool = True,
    port: int | None = None,
) -> DevPlan:
    """The QGIS process for ``mode``; the probe it runs is written to ``workspace``.

    ``dev_server`` is the Vite origin to hand the plugin, if one is running.
    ``watch`` makes the Desktop bootstrap reload on saved Python and
    metadata changes (debounced, serialised; see ``devtools.reloader``);
    the Reload button works either way. ``exercise`` makes the bootstrap
    drive itself through the reload policy, write a JSON report there and
    quit; it is how the harness proves the reload policy without a human at
    the keyboard. The SDK's own packages join ``PYTHONPATH`` so the bootstrap
    imports inside QGIS's interpreter whichever Python runs the CLI.
    """
    if mode not in MODES:
        raise QgisSdkDevError(
            f"unknown mode {mode!r}; choose one of {', '.join(MODES)}"
        )
    workspace = Path(workspace)
    host_root = stage_host(project)
    request = {
        "root": str(project.root),
        "plugin": project.plugin,
        "host": str(host_root),
        "mode": mode,
        "web": project.has_web and mode != "server",
        "dev_server": dev_server,
        "port": port,
        "exercise": None if exercise is None else str(exercise),
        "watch": watch,
    }
    request_path = workspace / REQUEST_NAME
    request_path.write_text(json.dumps(request, indent=2), encoding="utf-8")
    served = "" if dev_server is None else f", page from {dev_server}"
    if mode == "server":
        if install.python is None:
            raise QgisSdkDevError(
                f"{install.prefix} has no Python interpreter, so it cannot run "
                "the server mode; QGIS Server bindings only import into the "
                "interpreter they were built for"
            )
        if port is None:
            raise QgisSdkDevError("server mode needs a loopback port")
        probe = workspace / SERVER_PROBE_NAME
        probe.write_text(SERVER_PROBE, encoding="utf-8", newline="\n")
        process_env = install.environment(
            env, extra_paths=(host_root, *sdk_import_paths()), headless=True
        )
        process_env[REQUEST_ENV] = str(request_path)
        origin = f"http://{LOOPBACK}:{port}"
        return DevPlan(
            mode=mode,
            argv=(str(install.python), str(probe)),
            cwd=project.root,
            env=process_env,
            notes=(
                (
                    f"server: QGIS Server from {install.prefix} "
                    f"({install.source}) answering on {origin} through "
                    f"{project.plugin} from {project.root}; nothing is installed "
                    "and no FCGI process is started"
                ),
                (
                    f"try: curl '{origin}/?MAP=/path/to/project.qgs&SERVICE=WMS"
                    "&REQUEST=GetCapabilities', or the SERVICE your plugin declares"
                ),
                (
                    "reload: a saved Python change re-imports the plugin and hands "
                    "QGIS's registration the new hooks; a changed priority or "
                    "service name needs a new `qgis-sdk dev`; Ctrl+C stops it"
                    if watch
                    else "reload: off (--no-watch); Ctrl+C stops it"
                ),
            ),
            profile=None,
        )
    if mode == "standalone":
        if install.python is None:
            raise QgisSdkDevError(
                f"{install.prefix} has no Python interpreter, so it cannot run the "
                "standalone mode; use --mode desktop"
            )
        probe = workspace / STANDALONE_PROBE_NAME
        probe.write_text(STANDALONE_PROBE, encoding="utf-8", newline="\n")
        process_env = install.environment(
            env, extra_paths=(host_root, *sdk_import_paths()), headless=headless
        )
        process_env[REQUEST_ENV] = str(request_path)
        if dev_server is not None:
            process_env[DEV_SERVER_ENV] = dev_server
        return DevPlan(
            mode=mode,
            argv=(str(install.python), str(probe)),
            cwd=project.root,
            env=process_env,
            notes=(
                (
                    f"standalone: QgsApplication from {install.prefix} "
                    f"({install.source}); no iface, no plugin lifecycle, no reload - "
                    f"{project.plugin} runs through the generated "
                    f"{host_root / project.plugin} classFactory(None){served}"
                ),
            ),
            profile=None,
        )
    if install.executable is None:
        raise QgisSdkDevError(
            f"{install.prefix} has no QGIS Desktop binary (bin/qgis or "
            "bin/qgis-bin.exe); install QGIS Desktop there, point --qgis-prefix at "
            "one, or use --mode standalone"
        )
    probe = workspace / DESKTOP_PROBE_NAME
    probe.write_text(DESKTOP_PROBE, encoding="utf-8", newline="\n")
    # QGIS appends ``profiles/<name>`` to --profiles-path itself.
    state = project.root / STATE_DIRECTORY
    profile = state / "profiles" / PROFILE_NAME
    process_env = install.environment(
        env,
        extra_paths=(host_root, *sdk_import_paths()),
        headless=headless,
        desktop=True,
    )
    process_env[REQUEST_ENV] = str(request_path)
    process_env["QGIS_PLUGINPATH"] = _prepend_path(
        str(host_root), env.get("QGIS_PLUGINPATH")
    )
    if dev_server is not None:
        process_env[DEV_SERVER_ENV] = dev_server
    return DevPlan(
        mode=mode,
        argv=(
            str(install.executable),
            "--profiles-path",
            str(state),
            "--profile",
            PROFILE_NAME,
            "--code",
            str(probe),
        ),
        cwd=project.root,
        env=process_env,
        notes=(
            (
                f"desktop: {install.executable} ({install.source}), profile "
                f"{profile}, {project.plugin} from {project.root} through the "
                f"generated {host_root / project.plugin} on QGIS_PLUGINPATH{served}"
            ),
            (
                "reload: on save of Python changes, the Reload button, "
                "or Ctrl+Shift+R in QGIS; quit QGIS to stop "
                "(a pyproject.toml change needs a new `qgis-sdk dev`)"
                if watch
                else "reload: the Reload button or Ctrl+Shift+R in QGIS; quit QGIS to stop"
            ),
            (
                # decision-48 point 5: the two lines a console needs, printed
                # where a developer is already looking.
                f"console: in Plugins > Python Console: import qgis.utils; "
                f'session = qgis.utils.plugins["{project.plugin}"].console() '
                f"(or: from qgis_sdk.console import connect; session = connect())"
            ),
        ),
        profile=profile,
    )


def plan_app(
    project: DevProject,
    install: QgisInstall,
    *,
    env: Mapping[str, str],
    workspace: Path,
    gui: bool = True,
    once: bool = False,
    grace: float | None = None,
    title: str | None = None,
    toolkit_args: Sequence[str] = (),
) -> DevPlan:
    """The QGIS process that starts ``project`` as a standalone app.

    The entry is the project's own ``<plugin>/__main__.py`` when it has one,
    because that is the file ``qgis-sdk build --target app`` installs as a
    launcher and ``python -m <plugin>`` runs - a project that customises its
    argv should see the same thing from ``qgis-sdk run``. A project without one
    gets a generated probe in ``workspace`` that imports ``config.spec`` and
    calls the same ``qgis_sdk.app.main``, so a Desktop plugin can be tried as
    an app without editing it.

    ``gui`` opens the app's window; ``once`` starts it, delivers what is queued
    and stops, which is the smoke run a CI job makes. ``toolkit_args`` go after
    ``--``, so Qt sees them and the SDK does not.
    """
    _require_application(project)
    if install.python is None:
        raise QgisSdkDevError(
            f"{install.prefix} has no Python interpreter, so it cannot run a "
            "standalone app; the app host imports PyQGIS into the interpreter it "
            "was built for"
        )
    workspace = Path(workspace)
    root = project.root
    package = root / project.plugin
    flags: list[str] = []
    if not gui:
        flags.append("--headless")
    if once:
        flags.append("--once")
    if grace is not None:
        flags.extend(("--grace", f"{grace:g}"))
    if title is not None:
        flags.extend(("--title", title))
    entry = package / "__main__.py"
    if entry.is_file():
        argv = (str(install.python), "-m", project.plugin, *flags)
        where = f"{project.plugin} from {entry}"
    else:
        probe = workspace / APP_PROBE_NAME
        probe.write_text(_app_probe(project), encoding="utf-8", newline="\n")
        argv = (str(install.python), str(probe), *flags)
        where = (
            f"a generated probe for {project.config.spec} "
            f"(the project has no {project.plugin}/__main__.py)"
        )
    if toolkit_args:
        argv = (*argv, "--", *toolkit_args)
    process_env = install.environment(
        env,
        extra_paths=(root, *sdk_import_paths()),
        headless=not gui or wants_headless(env),
    )
    note = (
        f"app: {install.python} ({install.source}) running {where}, "
        f"{'with a window' if gui else 'headless'}"
    )
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


def _require_application(project: DevProject) -> None:
    """Refuse a project whose only host is the server: it declares no application.

    A server plugin's declarations are hooks QGIS Server calls; there is no
    action, no surface and no page for an app host to show, so starting one would
    present an empty window (decision-52 point 1).
    """
    hosts = project.config.hosts
    if {"desktop", "app"} & set(hosts):
        return
    raise QgisSdkDevError(
        f"{project.plugin} declares hosts = [{', '.join(repr(h) for h in hosts)}], "
        "so it is not an application: a server plugin's hooks are called by QGIS "
        "Server, not by an app. Declare `desktop` or `app` in "
        "`[tool.qgis-sdk] hosts` and keep the hooks in a module the server loads "
        "(decision-52 point 1)"
    )


def _app_probe(project: DevProject) -> str:
    """The probe that starts a project without an app entry of its own."""
    module, _, attribute = project.config.spec.partition(":")
    return APP_PROBE.format(module=module, attribute=attribute)


APP_PROBE: Final = '''"""Starts one project as a standalone app; written by `qgis-sdk run`."""

from __future__ import annotations

import importlib

from qgis_sdk.app import main


def _application():
    return getattr(importlib.import_module({module!r}), {attribute!r})


if __name__ == "__main__":
    raise SystemExit(main(_application()))
'''


def _prepend_path(entry: str, existing: str | None) -> str:
    return entry if not existing else os.pathsep.join((entry, existing))


def free_port() -> int:
    """A loopback port nothing is listening on right now."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind((LOOPBACK, 0))
        return int(probe.getsockname()[1])


def port_is_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.2)
        return probe.connect_ex((LOOPBACK, port)) == 0


def wait_for_port(
    port: int,
    *,
    still_running: Callable[[], bool],
    timeout: float = SERVER_START_SECONDS,
    probe: Callable[[int], bool] = port_is_open,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> bool:
    """Wait until ``port`` answers; False when the server died or time ran out."""
    deadline = clock() + timeout
    while clock() < deadline:
        if probe(port):
            return True
        if not still_running():
            return False
        sleep(0.1)
    return False


#: Runs inside QGIS Desktop (``qgis --code``). A thin bootstrap: it reads
#: its request from a file (QGIS treats trailing arguments as project paths)
#: and hands over to ``qgis_sdk_tools.devtools.bootstrap``, which the plan
#: puts on ``PYTHONPATH``. Anything that fails before that point is written
#: to ``sys.__stderr__`` so it survives whatever QGIS does to ``sys.stderr``.
DESKTOP_PROBE: Final = '''"""Load the source plugin and keep it reloadable (qgis-sdk dev)."""

import json
import os
import sys
import traceback
from pathlib import Path

request = json.loads(Path(os.environ["QGIS_SDK_DEV_REQUEST"]).read_text(encoding="utf-8"))

try:
    from qgis_sdk_tools.devtools.bootstrap import bootstrap, report_bootstrap_failure
except BaseException:  # noqa: BLE001 - keep QGIS up, show what happened
    log = sys.__stderr__ or sys.stderr
    log.write("qgis-sdk dev: cannot import qgis_sdk_tools inside QGIS:\\n" + traceback.format_exc())
    log.flush()
    if request.get("exercise"):
        Path(request["exercise"]).write_text(
            json.dumps({"started": False, "error": traceback.format_exc()}), encoding="utf-8"
        )
        os._exit(1)
else:
    try:
        _session = bootstrap(request)  # kept alive: it owns the timers and actions
    except BaseException:  # noqa: BLE001
        report_bootstrap_failure(request.get("exercise"))
'''


#: Runs under the install's interpreter: a real QgsServer on loopback. A thin
#: probe like the other two - the loop lives in ``devtools.serverdev``, which
#: imports ``qgis.server`` only once it is inside the QGIS process.
SERVER_PROBE: Final = '''"""Serve the source plugin from a local QgsServer (qgis-sdk dev)."""

import json
import os
import sys
import traceback
from pathlib import Path

request = json.loads(Path(os.environ["QGIS_SDK_DEV_REQUEST"]).read_text(encoding="utf-8"))
log = sys.__stderr__ or sys.stderr

try:
    from qgis_sdk_tools.devtools.serverdev import bootstrap_server
except BaseException:  # noqa: BLE001 - the terminal is the only place left to say it
    log.write(
        "qgis-sdk dev: cannot import qgis_sdk_tools inside the QGIS interpreter:\\n"
        + traceback.format_exc()
    )
    log.flush()
    os._exit(1)

try:
    bootstrap_server(request)  # blocks until Ctrl+C
except BaseException:  # noqa: BLE001
    log.write("qgis-sdk dev: server loop failed:\\n" + traceback.format_exc())
    log.flush()
    os._exit(1)
'''


#: Runs under the install's interpreter: a bare QgsApplication, no Desktop.
STANDALONE_PROBE: Final = '''"""Run the plugin through classFactory(None) in a bare QgsApplication (qgis-sdk dev)."""

import importlib
import json
import os
import sys
from pathlib import Path

request = json.loads(Path(os.environ["QGIS_SDK_DEV_REQUEST"]).read_text(encoding="utf-8"))
root = Path(request["root"])
host = Path(request["host"])  # the generated package: metadata.txt + classFactory
plugin = request["plugin"]


def say(message):
    sys.stderr.write(f"qgis-sdk dev: {message}\\n")
    sys.stderr.flush()


from qgis.PyQt.QtCore import QCoreApplication, Qt

if request.get("web"):
    # Qt WebEngine must be imported, and contexts shared, before the application.
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    import qgis.PyQt.QtWebEngineWidgets  # noqa: F401

from qgis.core import QgsApplication
from qgis.PyQt.QtWidgets import QLabel, QMainWindow

prefix = os.environ.get("QGIS_PREFIX_PATH")
if prefix:
    QgsApplication.setPrefixPath(prefix, True)
app = QgsApplication([b"qgis-sdk-dev"], True)
app.initQgis()
sys.path.insert(0, str(host))
module = importlib.import_module(plugin)
held = module.classFactory(None)
held.initGui()
say(
    f"standalone: {plugin} running without QGIS Desktop - there is no iface, "
    "QGIS calls no lifecycle hook, and there is no reload: close the window and "
    "run `qgis-sdk dev` again"
)
window = None
if getattr(held, "placement", None) is not None:
    window = held.show_view()
else:
    window = QMainWindow()
    window.setWindowTitle(f"{plugin} (qgis-sdk dev, standalone)")
    actions = ", ".join(sorted(held.runtime.actions)) or "none"
    window.setCentralWidget(QLabel(f"{plugin} is running.\\nDeclared actions: {actions}\\n\\nNo iface: close this window to stop."))
    window.resize(480, 160)
    window.show()
if request.get("exercise"):
    from qgis.PyQt.QtCore import QTimer

    def report():
        Path(request["exercise"]).write_text(
            json.dumps(
                {
                    "running": held.runtime.state.value,
                    "window": window is not None and window.isVisible(),
                    "ping": held.runtime.actions["ping"](1),
                }
            ),
            encoding="utf-8",
        )
        app.quit()

    QTimer.singleShot(500, report)
app.exec()
held.unload()
say(f"standalone: {plugin} {held.runtime.state.value}")
app.exitQgis()
'''

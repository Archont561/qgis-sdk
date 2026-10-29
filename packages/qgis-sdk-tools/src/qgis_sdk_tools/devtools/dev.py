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
from collections.abc import Callable, Mapping
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

from .installs import QgisInstall, sdk_import_paths
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
    "plan_dev",
    "plan_web_server",
    "stage_host",
    "wait_for_port",
]

MODES: Final = ("desktop", "standalone")
PROFILE_NAME: Final = "dev"
STATE_DIRECTORY: Final = ".qgis-sdk"
REQUEST_ENV: Final = DEV_REQUEST_ENV
"""The request file this command writes; the name lives in the runtime (console)."""
LOOPBACK: Final = "127.0.0.1"
DESKTOP_PROBE_NAME: Final = "dev-desktop.py"
STANDALONE_PROBE_NAME: Final = "dev-standalone.py"
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
        raise QgisSdkDevError(f"unknown mode {mode!r}; choose desktop or standalone")
    workspace = Path(workspace)
    host_root = stage_host(project)
    request = {
        "root": str(project.root),
        "plugin": project.plugin,
        "host": str(host_root),
        "mode": mode,
        "web": project.has_web,
        "dev_server": dev_server,
        "exercise": None if exercise is None else str(exercise),
        "watch": watch,
    }
    request_path = workspace / REQUEST_NAME
    request_path.write_text(json.dumps(request, indent=2), encoding="utf-8")
    served = "" if dev_server is None else f", page from {dev_server}"
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

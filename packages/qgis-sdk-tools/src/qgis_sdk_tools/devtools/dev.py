"""The plan behind ``qgis-sdk dev``: the source plugin inside a real QGIS.

Two modes, both explicit (decision-8):

``desktop`` (default)
    the QGIS Desktop binary from the discovered install, an isolated profile
    at ``<project>/.qgis-sdk/profiles/dev``, and the project root on
    ``QGIS_PLUGINPATH`` so QGIS's own plugin machinery discovers the package
    *in place* - no copy, no symlink. A bootstrap loads and starts it and adds
    a **Reload** action (toolbar button, ``Ctrl+Shift+R``). Reload is manual
    (decision-15: automatic Python reload waits for lifecycle evidence) and
    guarded: a preflight compiles every module first and a syntax error keeps
    the running revision; a failed unload or a failed start leaves the plugin
    disabled and says so, with ``qgis-sdk dev`` itself as the restart.
``standalone``
    a bare ``QgsApplication`` started by the install's interpreter, the plugin
    constructed through ``classFactory(None)`` exactly as the starter tests do.
    There is no ``iface``, no plugin menu, no QGIS lifecycle and no reload;
    what it offers is a fast loop for the web page and the declared actions.

With a web UI the command starts the project's Vite dev server on loopback
and hands its origin to the plugin through ``QGIS_SDK_DEV_SERVER``; the
generated ``webview.py`` loads from there, with HMR, only when that variable
is set. ``vite build`` output never references it.
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

from qgis_sdk.environment import DEV_SERVER_ENV
from qgis_sdk.models import QgisSdkError

from qgis_sdk_tools.check import EXCLUDED_DIRECTORIES
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
    "wait_for_port",
]

MODES: Final = ("desktop", "standalone")
PROFILE_NAME: Final = "dev"
STATE_DIRECTORY: Final = ".qgis-sdk"
REQUEST_ENV: Final = "QGIS_SDK_DEV_REQUEST"
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
    """Find the one plugin package at ``root`` and whether it has a web UI."""
    root = Path(root).resolve()
    if not root.is_dir():
        raise QgisSdkDevError(f"{root} is not a directory; give a project root")
    packages = sorted(
        child.name
        for child in root.iterdir()
        if child.is_dir()
        and child.name not in EXCLUDED_DIRECTORIES
        and (child / "__init__.py").is_file()
        and (child / "metadata.txt").is_file()
    )
    if not packages:
        raise QgisSdkDevError(
            f"no plugin package (a directory with __init__.py and metadata.txt) "
            f"under {root}; run from the project `qgis-sdk new` created"
        )
    if len(packages) > 1:
        raise QgisSdkDevError(
            f"{root} holds several plugin packages ({', '.join(packages)}); "
            "`qgis-sdk dev` serves one project at a time"
        )
    web = root / "web"
    return DevProject(
        root=root,
        plugin=packages[0],
        web=web if (web / "package.json").is_file() else None,
    )


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
    quit; it is how the harness proves TASK-21 without a human at the
    keyboard. The SDK's own packages join ``PYTHONPATH`` so the bootstrap
    imports inside QGIS's interpreter whichever Python runs the CLI.
    """
    if mode not in MODES:
        raise QgisSdkDevError(f"unknown mode {mode!r}; choose desktop or standalone")
    workspace = Path(workspace)
    request = {
        "root": str(project.root),
        "plugin": project.plugin,
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
            env, extra_paths=(project.root, *sdk_import_paths()), headless=headless
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
                    f"{project.plugin} runs through classFactory(None){served}"
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
        extra_paths=(project.root, *sdk_import_paths()),
        headless=headless,
        desktop=True,
    )
    process_env[REQUEST_ENV] = str(request_path)
    process_env["QGIS_PLUGINPATH"] = _prepend_path(
        str(project.root), env.get("QGIS_PLUGINPATH")
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
                f"{profile}, {project.plugin} from {project.root} "
                f"via QGIS_PLUGINPATH{served}"
            ),
            (
                "reload: on save of Python/metadata changes, the Reload button, "
                "or Ctrl+Shift+R in QGIS; quit QGIS to stop"
                if watch
                else "reload: the Reload button or Ctrl+Shift+R in QGIS; quit QGIS to stop"
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
sys.path.insert(0, str(root))
module = importlib.import_module(plugin)
held = module.classFactory(None)
held.initGui()
say(
    f"standalone: {plugin} running without QGIS Desktop - there is no iface, "
    "QGIS calls no lifecycle hook, and there is no reload: close the window and "
    "run `qgis-sdk dev` again"
)
window = None
if hasattr(held, "show_view"):
    held.show_view()
    window = held._view
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

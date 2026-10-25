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

from qgis_sdk.check import EXCLUDED_DIRECTORIES
from qgis_sdk.models import QgisSdkError
from qgis_sdk.scaffold.web import script_command

from .installs import QgisInstall
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
DEV_SERVER_ENV: Final = "QGIS_SDK_DEV_SERVER"
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
) -> DevPlan:
    """The QGIS process for ``mode``; the probe it runs is written to ``workspace``.

    ``dev_server`` is the Vite origin to hand the plugin, if one is running.
    ``exercise`` makes the Desktop bootstrap drive itself - start, reload,
    a refused reload, reload again - write a JSON report there and quit; it
    is how the harness proves the reload policy without a human at the
    keyboard.
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
            env, extra_paths=(project.root,), headless=headless
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
        env, extra_paths=(project.root,), headless=headless, desktop=True
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
            "reload: the Reload button or Ctrl+Shift+R in QGIS; quit QGIS to stop",
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


#: Runs inside QGIS Desktop (``qgis --code``). Static source: it reads its
#: request from a file (QGIS treats trailing arguments as project paths) and
#: writes to the terminal through ``sys.__stderr__`` so the report survives
#: whatever QGIS does to ``sys.stderr``.
DESKTOP_PROBE: Final = '''"""Load the source plugin, keep a Reload button, report (qgis-sdk dev)."""

import json
import os
import sys
import traceback
from pathlib import Path

request = json.loads(Path(os.environ["QGIS_SDK_DEV_REQUEST"]).read_text(encoding="utf-8"))
root = Path(request["root"])
plugin = request["plugin"]
exercise = request.get("exercise")
log = sys.__stderr__
state = {"revision": 0, "running": False}


def say(message):
    log.write(f"qgis-sdk dev: {message}\\n")
    log.flush()


import qgis.utils
from qgis.core import Qgis
from qgis.PyQt.QtGui import QKeySequence
from qgis.PyQt.QtWidgets import QAction

iface = qgis.utils.iface


def notify(level, text):
    if iface is not None:
        iface.messageBar().pushMessage("qgis-sdk dev", text, level=level, duration=8)


def preflight():
    """Compile every module of the plugin; a syntax error must never reach unload."""
    problems = []
    for path in sorted((root / plugin).rglob("*.py")):
        try:
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
        except SyntaxError as error:
            problems.append(f"{path.relative_to(root)}:{error.lineno}: {error.msg}")
    return problems


def start():
    """Load and start the package the way QGIS's Plugins dialog would."""
    qgis.utils.updateAvailablePlugins()
    if plugin not in qgis.utils.available_plugins:
        say(f"{plugin} is not a plugin QGIS can see under {root} (metadata.txt?)")
        return False
    if not qgis.utils.loadPlugin(plugin):
        forget = getattr(qgis.utils, "_unloadPluginModules", None)
        if forget is not None:
            forget(plugin)
        say(f"{plugin} failed to import (see the QGIS Python error); fix it and Reload")
        return False
    if not qgis.utils.startPlugin(plugin):
        say(f"{plugin} failed in classFactory/initGui (see the QGIS Python error); fix it and Reload")
        return False
    state["revision"] += 1
    state["running"] = True
    say(f"{plugin} running (revision {state['revision']}) from {root / plugin}")
    return True


def reload():
    """Preflight, unload the running revision, start the source again."""
    problems = preflight()
    if problems:
        more = f" (+{len(problems) - 1} more)" if len(problems) > 1 else ""
        kept = (
            f"revision {state['revision']} keeps running"
            if state["running"]
            else f"{plugin} stays disabled"
        )
        say(f"reload refused, {kept}: {problems[0]}{more}")
        notify(Qgis.MessageLevel.Critical, f"reload refused: {problems[0]}{more}")
        return False
    if state["running"]:
        if not qgis.utils.unloadPlugin(plugin):
            state["running"] = False
            say(
                f"unload of revision {state['revision']} failed; {plugin} is disabled "
                "and its old modules may linger: restart `qgis-sdk dev`"
            )
            notify(Qgis.MessageLevel.Critical, f"{plugin} unload failed: restart qgis-sdk dev")
            return False
        state["running"] = False
    if start():
        notify(Qgis.MessageLevel.Info, f"{plugin} reloaded (revision {state['revision']})")
        return True
    say(f"{plugin} is disabled until a Reload succeeds; fix the error, or restart `qgis-sdk dev`")
    notify(Qgis.MessageLevel.Critical, f"{plugin} is disabled: fix the error and Reload")
    return False


def install_reload_action():
    if iface is None:
        return None
    action = QAction(f"Reload {plugin}", iface.mainWindow())
    action.setShortcut(QKeySequence("Ctrl+Shift+R"))
    action.triggered.connect(lambda _checked=False: reload())
    iface.addToolBarIcon(action)
    return action


def run_exercise(path):
    """Drive the policy end to end and write what happened; the harness reads it."""
    report = {"started": state["running"], "error": None}
    broken = root / plugin / "zz_broken_by_qgis_sdk_dev.py"
    try:
        report["reload_ok"] = reload()
        broken.write_text("def (\\n", encoding="utf-8")
        try:
            report["reload_refused"] = not reload()
            report["kept_running"] = state["running"] and plugin in qgis.utils.active_plugins
        finally:
            broken.unlink()
        # An edit between reloads must be what runs afterwards: that is the point.
        source = root / plugin / "plugin.py"
        original = source.read_text(encoding="utf-8")
        edited = original.replace("return value\\n", "return value + 1000\\n", 1)
        source.write_text(edited, encoding="utf-8")
        try:
            report["reload_after_fix"] = reload()
            report["ping_after_edit"] = qgis.utils.plugins[plugin].runtime.actions["ping"](1)
        finally:
            source.write_text(original, encoding="utf-8")
        report["revision"] = state["revision"]
        if request.get("web"):
            held = qgis.utils.plugins[plugin]
            held.show_view()
            report["view_shown"] = held._view is not None
            from qgis.PyQt.QtCore import QCoreApplication
            QCoreApplication.processEvents()
        report["unloaded"] = qgis.utils.unloadPlugin(plugin)
    except BaseException as error:  # noqa: BLE001 - the report is the only way out
        report["error"] = "".join(traceback.format_exception(error))
    Path(path).write_text(json.dumps(report), encoding="utf-8")
    log.flush()
    os._exit(0 if report["error"] is None else 1)


try:
    started = start()
    reload_action = install_reload_action()
    if exercise:
        run_exercise(exercise)
    if not started:
        say(f"{plugin} is disabled; fix the error and press Reload (Ctrl+Shift+R)")
except BaseException:  # noqa: BLE001 - keep QGIS up, show what happened
    say("bootstrap failed:\\n" + traceback.format_exc())
    if exercise:
        Path(exercise).write_text(
            json.dumps({"started": False, "error": traceback.format_exc()}), encoding="utf-8"
        )
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

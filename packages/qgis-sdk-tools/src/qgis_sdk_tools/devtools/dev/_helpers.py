from __future__ import annotations

import socket
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final, TypedDict

LOOPBACK: Final = "127.0.0.1"
SERVER_START_SECONDS: Final = 60.0


def free_port() -> int:
    """A loopback port nothing is listening on right now."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind((LOOPBACK, 0))
        return int(probe.getsockname()[1])


def port_is_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.2)
        return probe.connect_ex((LOOPBACK, port)) == 0


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


class WaitOptions1(TypedDict, total=False):
    still_running: Callable[[], bool]
    timeout: float
    probe: Callable[[int], bool]
    sleep: Callable[[float], None]
    clock: Callable[[], float]


@dataclass(frozen=True, slots=True)
class WaitValues1:
    still_running: Callable[[], bool]
    timeout: float = SERVER_START_SECONDS
    probe: Callable[[int], bool] = port_is_open
    sleep: Callable[[float], None] = time.sleep
    clock: Callable[[], float] = time.monotonic

"""The app host on a real QGIS, offscreen: TASK-81 AC 1.

``qgis_sdk.app.run`` owns ``QgsApplication``, so it cannot share a process with
the suite's session application - the backend refuses to nest one, on purpose.
Each case here therefore starts a *child* interpreter of the same environment
(the row's Python, which is the QGIS one) with ``QT_QPA_PLATFORM=offscreen``: no
display, no window manager, but real widgets, a real ``QgsMapCanvas`` and a real
``QgsApplication``. The child prints one JSON object and the test reads it, so a
failure names the fact that was wrong instead of a stack trace from a subprocess.

What is proven, in the terms of the acceptance criterion:

* headless - the plugin runs, ``ctx.host`` is ``app``, every non-desktop service
  answers (project, notifications, settings, jobs through the named pump), and
  ``ctx.desktop``/``ctx.ui`` refuse by name;
* ``gui=True`` - the app window is a ``QMainWindow`` with a map canvas, the
  ``@toolbar``/``@menu`` bindings became actions on it, and a ``Dialog`` and a
  ``Dock`` opened through ``ctx.ui`` attach to that window.

The lifecycle itself (drain, loops named, ``exitQgis`` once) is
``test_app_session.py``'s, over the fake backend; here the same shutdown runs
against the toolkit, and the report is asserted too.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from layers import qgis_bindings, source_path

pytestmark = pytest.mark.qgis

try:
    # ``find_spec("qgis.core")`` imports ``qgis`` first; ask for the parent.
    HAVE_QGIS = importlib.util.find_spec("qgis") is not None
except (ImportError, ValueError):  # pragma: no cover - a broken installation
    HAVE_QGIS = False

if not HAVE_QGIS:  # pragma: no cover - host-dependent
    pytest.skip(
        "the app host on a real toolkit needs the QGIS Python bindings",
        allow_module_level=True,
    )

PROBE = '''"""Runs one app host in this interpreter and prints what it found."""

from __future__ import annotations

import json

from qgis.PyQt.QtWidgets import (
    QApplication,
    QDockWidget,
    QDialog,
    QMainWindow,
    QToolBar,
)

from qgis_sdk.adapters.app import QtAppBackend
from qgis_sdk.app import AppSession
from qgis_sdk.core import Host, PluginContext, WorkerContext
from qgis_sdk.jobs import job
from qgis_sdk.models import QgisSdkUnsupportedCapabilityError
from qgis_sdk.ui import Dialog, Dock

GUI = __GUI__
NOTES = []


class Greeting(Dialog):
    """A surface only a windowed host can open."""

    title = "Greeting"

    def build(self):
        from qgis.PyQt.QtWidgets import QLabel

        return QLabel("hello")


class Inspector(Dock):
    """A dock, which the app window has to place itself."""

    title = "Inspector"

    def build(self):
        from qgis.PyQt.QtWidgets import QLabel

        return QLabel("inspector")


@job(id="demo.echo", title="Echo")
def echo(ctx: WorkerContext, value: int) -> int:
    return value


def make_app():
    from qgis_sdk import QgisSdkPlugin, menu, toolbar

    app = QgisSdkPlugin(id="native_app", title="Native app")

    @toolbar(text="Ping")
    @app.action(id="ping", title="Ping")
    def ping(ctx: PluginContext, value: int = 1) -> int:
        return value

    @menu("Plugins/Native app")
    @app.action(id="greet", title="Greet")
    def greet(ctx: PluginContext) -> str:
        ctx.ui.open(Greeting)
        ctx.ui.open(Inspector)
        return "opened"

    app.add_surface(Greeting)
    app.add_surface(Inspector)
    app.jobs = {"echo": echo}
    return app


def note(message):
    """A shutdown line: the session prints one per loop it stops."""
    NOTES.append(message)


def _menu_titles(menu):
    """Every menu title under ``menu`` (the bar itself has no title)."""
    titles = []
    for action in menu.actions():
        child = action.menu()
        if child is not None:
            titles.append(action.text())
            titles.extend(_menu_titles(child))
    return titles


def main() -> int:
    from qgis.core import QgsProject
    from qgis.gui import QgsMapCanvas

    backend = QtAppBackend()
    session = AppSession(make_app(), backend=backend, gui=GUI, grace=1.0, say=note)
    found = {}
    try:
        session.start()
        context = session.context
        found["host"] = context.host.value
        found["ping"] = session.runtime.actions["ping"](value=3)
        found["layers"] = list(context.project.layer_ids())
        found["loops"] = [state.name for state in session.loops.inventory()]
        if GUI:
            window = session.surface.window
            found["window"] = type(window).__name__
            found["is_main_window"] = isinstance(window, QMainWindow)
            found["canvas"] = len(window.findChildren(QgsMapCanvas))
            found["toolbars"] = [
                action.text()
                for bar in window.findChildren(QToolBar)
                for action in bar.actions()
            ]
            # `@menu("Plugins/Native app")` is a submenu, as it is in QGIS, so
            # the titles are read at every depth rather than off the menu bar.
            found["menus"] = _menu_titles(window.menuBar())
            session.runtime.actions["greet"]()
            # A dialog is a top-level window of its own whether or not the host
            # parented it to the app window; a dock has to be inside it.
            found["dialogs"] = [
                widget.windowTitle()
                for widget in QApplication.topLevelWidgets()
                if isinstance(widget, QDialog) and widget.isVisible()
            ]
            found["docks"] = [
                dock.windowTitle()
                for dock in window.findChildren(QDockWidget)
                if dock.windowTitle() == "Inspector"
            ]
        else:
            for refused in ("desktop", "ui"):
                try:
                    getattr(context, refused)
                except QgisSdkUnsupportedCapabilityError as error:
                    found[f"{refused}_refused"] = str(error)
    finally:
        report = session.stop()
    found["report"] = report.to_json()
    found["notes"] = NOTES
    found["project"] = QgsProject.instance() is not None
    print(json.dumps(found))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


def run_probe(tmp_path: Path, *, gui: bool) -> dict[str, object]:
    """Start the app host in a child interpreter and read what it reported."""
    probe = tmp_path / ("app-gui.py" if gui else "app-headless.py")
    probe.write_text(
        PROBE.replace("__GUI__", "True" if gui else "False"),
        encoding="utf-8",
        newline="\n",
    )
    environment = dict(os.environ)
    # The pixi and Debian builds keep PyQGIS in ``share/qgis/python``, off
    # ``sys.path``: this interpreter reaches it because ``layers`` put it there,
    # and the child has to be told the same. Without this the probe dies on
    # ``from qgis.PyQt.QtWidgets import`` on every row whose QGIS is not an
    # installed wheel.
    bindings = qgis_bindings()
    environment["PYTHONPATH"] = source_path(
        tmp_path, *((bindings,) if bindings is not None else ())
    )
    environment["QT_QPA_PLATFORM"] = "offscreen"
    environment.setdefault("QT_LOGGING_RULES", "*.debug=false")
    finished = subprocess.run(
        [sys.executable, str(probe)],
        capture_output=True,
        text=True,
        check=False,
        cwd=tmp_path,
        env=environment,
    )
    assert finished.returncode == 0, finished.stdout + finished.stderr
    lines = [line for line in finished.stdout.splitlines() if line.startswith("{")]
    assert lines, finished.stdout + finished.stderr
    return json.loads(lines[-1])


def test_the_app_runs_headless_on_a_real_qgis(tmp_path: Path) -> None:
    found = run_probe(tmp_path, gui=False)

    assert found["host"] == "app"
    assert found["ping"] == 3
    assert found["project"] is True
    assert found["layers"] == []
    assert found["loops"] == ["job-pump"]
    assert found["desktop_refused"]
    assert found["ui_refused"]
    assert found["report"]["exited"] is True
    assert found["report"]["stopped_loops"] == ["job-pump"]


def test_the_window_carries_the_canvas_and_the_declared_bindings(
    tmp_path: Path,
) -> None:
    found = run_probe(tmp_path, gui=True)

    assert found["host"] == "app"
    assert found["window"] == "QMainWindow"
    assert found["is_main_window"] is True
    assert found["canvas"] >= 1
    assert "Ping" in found["toolbars"]
    # The Plugins family menu, and the plugin's own submenu inside it.
    assert "Plugins" in found["menus"]
    assert "Native app" in found["menus"]
    assert found["dialogs"] == ["Greeting"]
    assert found["docks"] == ["Inspector"]
    assert found["report"]["exited"] is True

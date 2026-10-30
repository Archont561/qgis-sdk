"""The Desktop host on whichever Qt the running QGIS ships.

QGIS 3.44 LTS is a Qt 5 / PyQt5 build and QGIS 4.x is Qt 6 / PyQt6, and the
Debian/Ubuntu packages this workspace can install are the LTS one. The adapters
therefore import Qt through ``qgis.PyQt`` and ask
:mod:`qgis_sdk.adapters._qt` for the two APIs that still differ, so one plugin
runs on either. The `QGIS 3.44 LTS` CI row is where the Qt 5 half is proven;
this module runs on every native job, so the Qt 6 half stays covered too.

The point is not to re-test the adapters - the native suite does that - but to
report which binding this QGIS has and prove the three places the two bindings
disagree, plus that a job still runs on a ``QgsTask`` there.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass

import pytest

pytestmark = pytest.mark.qgis

try:
    from qgis.PyQt.QtCore import QT_VERSION_STR, Qt
    from qgis.PyQt.QtWidgets import (
        QDialog,
        QDockWidget,
        QTableWidget,
        QTableWidgetItem,
        QToolBar,
    )
    from qgis_sdk.adapters._qt import action_class, qt_enum
    from qgis_sdk.adapters.qgis import QgsJobPump, QgsTaskWorkers
    from qgis_sdk.core import PluginContext, ResourceScope, WorkerContext
    from qgis_sdk.jobs import JobRegistry, JobService, JobStatus, job
    from qgis_sdk.testing import RecordingNotifications
except ImportError as error:  # pragma: no cover - depends on the host
    pytest.skip(f"the LTS host needs QGIS: {error}", allow_module_level=True)

DEADLINE_SECONDS = 10.0


@pytest.fixture(scope="module")
def app(qgis_app):
    return qgis_app


@dataclass(frozen=True)
class Reading:
    value: int
    thread: int


@job(id="lts.read", title="Read a value")
def read(ctx: WorkerContext, value: int) -> Reading:
    return Reading(value, threading.get_ident())


def spin(app, until: Callable[[], bool]) -> None:
    deadline = time.monotonic() + DEADLINE_SECONDS
    while not until():
        if time.monotonic() > deadline:
            raise AssertionError("condition not met within the deadline")
        app.processEvents()
        time.sleep(0.001)


def binding() -> str:
    """The PyQt binding this QGIS runs: ``PyQt5`` or ``PyQt6``."""
    major = QT_VERSION_STR.split(".")[0]
    return f"PyQt{major}"


# -- which Qt is this, and can the adapters be imported at all ----------------------


def test_the_adapters_import_on_this_binding() -> None:
    import qgis_sdk.adapters.desktop
    import qgis_sdk.adapters.qgis
    import qgis_sdk.adapters.surfaces

    assert binding() in ("PyQt5", "PyQt6")
    assert QT_VERSION_STR.split(".")[0] in ("5", "6")
    assert qgis_sdk.adapters.desktop is not None


def test_the_reported_binding_matches_the_qt_series() -> None:
    from qgis.PyQt import QtCore

    assert (binding() == "PyQt6") is (QT_VERSION_STR.startswith("6."))
    assert QtCore.QT_VERSION_STR == QT_VERSION_STR


# -- the three places the bindings differ ------------------------------------------


def test_a_dock_area_resolves_on_either_binding(app) -> None:
    window = QDialog()
    try:
        dock = QDockWidget("panel", window)
        window.addDockWidget(qt_enum(Qt, "DockWidgetArea", "RightDockWidgetArea"), dock)
        assert window.dockWidgetArea(dock) == qt_enum(
            Qt, "DockWidgetArea", "RightDockWidgetArea"
        )
    finally:
        window.deleteLater()


def test_an_action_lives_in_whichever_module_this_binding_uses(app) -> None:
    window = QDialog()
    try:
        QAction = action_class()
        toolbar = QToolBar(window)
        action = QAction("Run", window)
        toolbar.addAction(action)
        assert action.text() == "Run"
        assert toolbar.actions() == [action]
    finally:
        window.deleteLater()


def test_an_item_flag_resolves_on_either_binding(app) -> None:
    table = QTableWidget(1, 1)
    try:
        item = QTableWidgetItem("value")
        item.setFlags(item.flags() & ~qt_enum(Qt, "ItemFlag", "ItemIsEditable"))
        table.setItem(0, 0, item)
        assert table.item(0, 0).flags() & qt_enum(Qt, "ItemFlag", "ItemIsEditable") == 0
    finally:
        table.deleteLater()


# -- the job path, on this binding's thread pool and task manager ------------------


def test_a_job_runs_on_a_qgs_task_here(app) -> None:
    scope = ResourceScope()
    workers = QgsTaskWorkers(scope)
    service = JobService(
        scope,
        workers=workers,
        registry=JobRegistry.from_declaration({"read": read}, path="plugin 'lts'"),
    )
    pump = QgsJobPump(service)
    seen: list[Reading] = []
    try:
        pump.start()
        handle = service.read.delay(value=7)
        handle.on_success(seen.append)
        spin(app, lambda: handle.status.settled)
    finally:
        pump.stop()
        if not scope.closed:
            scope.close()

    assert handle.status is JobStatus.SUCCEEDED
    assert seen == [Reading(7, seen[0].thread)]
    assert seen[0].thread != threading.get_ident()


@pytest.fixture
def plugin_scope() -> Iterator[ResourceScope]:
    scope = ResourceScope()
    yield scope
    if not scope.closed:
        scope.close()


def test_a_plugin_context_is_assembled_from_this_host(app, plugin_scope) -> None:
    context = PluginContext(
        scope=plugin_scope,
        notifications=RecordingNotifications(plugin_scope),
        workers=QgsTaskWorkers(plugin_scope),
    )

    assert context.host.value == "desktop"
    assert context.has("workers") is True

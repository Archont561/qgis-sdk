"""The public REST client dispatches onto the real QGIS owner thread."""

from __future__ import annotations

import os
import threading
from pathlib import Path

import pytest

pytestmark = pytest.mark.qgis
qt = pytest.importorskip("qgis.PyQt.QtCore")

from qgis_sdk import QgisSdkPlugin
from qgis_sdk.core import PluginContext, PluginRuntime, ResourceScope
from qgis_sdk.http import PluginHttpServer
from qgis_sdk.testing import RecordingNotifications
from qgis_sdk_tools.rest import PluginClient


class _Post(qt.QObject):
    submitted = qt.pyqtSignal(object)
    finished = qt.pyqtSignal()

    def __init__(self):
        super().__init__()
        self.submitted.connect(self._run, qt.Qt.ConnectionType.QueuedConnection)

    def _run(self, callback):
        callback()


@pytest.mark.skipif(os.name != "posix", reason="private token requires POSIX")
def test_rest_action_runs_on_real_qgis_owner(qgis_app, tmp_path: Path):
    owner = threading.get_ident()
    seen = []
    app = QgisSdkPlugin(id="rest_native", title="REST native")

    @app.action(id="where", title="Where")
    def where(ctx: PluginContext) -> str:
        seen.append(threading.get_ident())
        return "gui"

    scope = ResourceScope()
    runtime = PluginRuntime(
        app, PluginContext(scope=scope, notifications=RecordingNotifications(scope))
    )
    runtime.start()
    post = _Post()
    loop = qt.QEventLoop()
    post.finished.connect(loop.quit, qt.Qt.ConnectionType.QueuedConnection)
    result = []
    errors = []
    token_file = tmp_path / "token"
    try:
        with PluginHttpServer(
            runtime,
            post=post.submitted.emit,
            token_file=token_file,
            actions=("where",),
            deadline=2,
        ) as server:

            def client():
                try:
                    result.append(
                        PluginClient(
                            f"http://127.0.0.1:{server.port}", token_file=token_file
                        ).call("where", {})
                    )
                except BaseException as error:  # noqa: BLE001 - report to the owner thread
                    errors.append(error)
                finally:
                    post.finished.emit()

            worker = threading.Thread(target=client, daemon=True)
            worker.start()
            timer = qt.QTimer()
            timer.setSingleShot(True)
            timer.timeout.connect(loop.quit)
            timer.start(5000)
            loop.exec()
            worker.join(timeout=1)
            assert not worker.is_alive()
            assert not errors, errors
            assert result == ["gui"]
            assert seen == [owner]
    finally:
        runtime.unload()

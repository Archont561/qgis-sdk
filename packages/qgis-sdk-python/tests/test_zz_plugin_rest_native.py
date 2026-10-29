"""The plugin HTTP API on the real QGIS owner thread: dispatch and lifecycle."""

from __future__ import annotations

import http.client
import json
import os
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

pytestmark = pytest.mark.qgis
qt = pytest.importorskip("qgis.PyQt.QtCore")

from qgis_sdk import QgisSdkPlugin
from qgis_sdk.core import PluginContext, PluginRuntime, ResourceScope
from qgis_sdk.http import PluginHttpServer, QgisSdkHttpError
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


def _run_loop(loop, post, remaining: int, timeout: int = 8000) -> None:
    """Pump the real event loop until every client thread has finished."""
    left = [remaining]

    def finished():
        left[0] -= 1
        if left[0] <= 0:
            loop.quit()

    post.finished.connect(finished, qt.Qt.ConnectionType.QueuedConnection)
    timer = qt.QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    timer.start(timeout)
    loop.exec()
    post.finished.disconnect(finished)


def _post_call(port, token, action, payload=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        connection.request(
            "POST",
            f"/actions/{action}",
            body=json.dumps(payload or {}),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        response = connection.getresponse()
        return response.status, json.loads(response.read())
    finally:
        connection.close()


@pytest.mark.skipif(os.name != "posix", reason="private token requires POSIX")
def test_a_nested_qdialog_defers_a_second_call_until_it_returns(
    qgis_app, tmp_path: Path
):
    widgets = pytest.importorskip("qgis.PyQt.QtWidgets")
    entered = threading.Event()
    queued_during_modal = threading.Event()
    events = []
    app = QgisSdkPlugin(id="rest_modal", title="REST modal")
    server_box = []

    @app.action(id="modal", title="Modal")
    def modal(ctx: PluginContext) -> str:
        events.append("modal-start")
        dialog = widgets.QDialog()
        entered.set()
        check = qt.QTimer(dialog)

        def maybe_close():
            # Prove the second request reached the owner queue while the
            # nested loop was running, not merely that the socket was written.
            if server_box[0].pending_requests:
                queued_during_modal.set()
                check.stop()
                # Force any posted work to run inside this nested loop. A
                # listener that lets a second call dispatch here would run it
                # now, before the dialog returns.
                for _ in range(5):
                    qt.QCoreApplication.processEvents()
                    time.sleep(0.01)
                dialog.accept()

        check.timeout.connect(maybe_close)
        check.start(10)
        qt.QTimer.singleShot(4000, dialog.reject)
        dialog.exec()
        events.append("modal-end")
        return "closed"

    @app.action(id="second", title="Second")
    def second(ctx: PluginContext) -> str:
        events.append("second")
        return "ok"

    scope = ResourceScope()
    runtime = PluginRuntime(
        app, PluginContext(scope=scope, notifications=RecordingNotifications(scope))
    )
    runtime.start()
    post = _Post()
    loop = qt.QEventLoop()
    responses = []
    errors = []
    token_file = tmp_path / "token"
    try:
        with PluginHttpServer(
            runtime,
            post=post.submitted.emit,
            token_file=token_file,
            actions=("modal", "second"),
            deadline=5,
        ) as server:
            server_box.append(server)
            token = token_file.read_text().strip()

            def first_client():
                try:
                    responses.append(_post_call(server.port, token, "modal"))
                except BaseException as error:  # noqa: BLE001 - relay to the owner
                    errors.append(error)
                finally:
                    post.finished.emit()

            def second_client():
                try:
                    assert entered.wait(5)
                    responses.append(_post_call(server.port, token, "second"))
                except BaseException as error:  # noqa: BLE001 - relay to the owner
                    errors.append(error)
                finally:
                    post.finished.emit()

            threads = [
                threading.Thread(target=fn, daemon=True)
                for fn in (first_client, second_client)
            ]
            for thread in threads:
                thread.start()
            _run_loop(loop, post, remaining=2, timeout=10000)
            for thread in threads:
                thread.join(timeout=1)
            assert not any(thread.is_alive() for thread in threads)
            assert not errors, errors
            assert [status for status, _ in responses] == [200, 200]
            assert queued_during_modal.is_set(), "the second call never queued"
            assert events == ["modal-start", "modal-end", "second"], (
                f"a nested dialog re-entered a call: {events}"
            )
    finally:
        runtime.unload()


@pytest.mark.skipif(os.name != "posix", reason="private token requires POSIX")
def test_a_long_stream_is_pumped_on_the_real_qgis_owner(qgis_app, tmp_path: Path):
    expected = threading.get_ident()
    seen = []
    app = QgisSdkPlugin(id="rest_native_stream", title="Native stream")

    @app.stream(id="ticks", title="Ticks", events={"data": int})
    def ticks(ctx: PluginContext) -> Iterator[dict]:
        for index in range(40):
            seen.append(threading.get_ident())
            yield {"kind": "data", "payload": index}

    scope = ResourceScope()
    runtime = PluginRuntime(
        app, PluginContext(scope=scope, notifications=RecordingNotifications(scope))
    )
    runtime.start()
    post = _Post()
    loop = qt.QEventLoop()
    frames = []
    errors = []
    token_file = tmp_path / "token"
    try:
        with PluginHttpServer(
            runtime,
            post=post.submitted.emit,
            token_file=token_file,
            actions=("ticks",),
            deadline=5,
        ) as server:
            token = token_file.read_text().strip()

            def client():
                connection = http.client.HTTPConnection(
                    "127.0.0.1", server.port, timeout=10
                )
                try:
                    connection.request(
                        "POST",
                        "/streams/ticks",
                        body="{}",
                        headers={
                            "Authorization": f"Bearer {token}",
                            "Content-Type": "application/json",
                        },
                    )
                    response = connection.getresponse()
                    assert response.status == 200
                    while True:
                        line = response.readline()
                        assert line.startswith(b"data: ")
                        frames.append(json.loads(line.removeprefix(b"data: ")))
                        assert response.readline() == b"\n"
                        if "terminal" in frames[-1]:
                            break
                except BaseException as error:  # noqa: BLE001 - relay to the owner
                    errors.append(error)
                finally:
                    connection.close()
                    post.finished.emit()

            worker = threading.Thread(target=client, daemon=True)
            worker.start()
            _run_loop(loop, post, remaining=1, timeout=10000)
            worker.join(timeout=1)
            assert not worker.is_alive()
            assert not errors, errors
            assert [frame["seq"] for frame in frames] == list(range(41))
            assert [frame["event"]["payload"] for frame in frames[:-1]] == list(
                range(40)
            )
            assert frames[-1]["terminal"]["kind"] == "complete"
            assert seen == [expected] * 40, (
                "a stream frame was produced off the QGIS owner thread"
            )
    finally:
        runtime.unload()


@pytest.mark.skipif(os.name != "posix", reason="private token requires POSIX")
def test_reload_during_a_dialog_fails_the_call_and_disposes_the_stream_after(
    qgis_app, tmp_path: Path
):
    widgets = pytest.importorskip("qgis.PyQt.QtWidgets")
    events = []
    app = QgisSdkPlugin(id="rest_reload", title="Reload")

    @app.stream(id="watch", title="Watch", events={"data": int})
    def watch(ctx: PluginContext) -> Iterator[dict]:
        try:
            while True:
                yield {"kind": "data", "payload": 1}
        finally:
            events.append("stream-disposed")

    @app.action(id="modal", title="Modal")
    def modal(ctx: PluginContext) -> str:
        events.append("modal-start")
        dialog = widgets.QDialog()
        qt.QTimer.singleShot(10, runtime.unload)
        qt.QTimer.singleShot(400, dialog.accept)
        dialog.exec()
        events.append("modal-end")
        return "done"

    scope = ResourceScope()
    runtime = PluginRuntime(
        app, PluginContext(scope=scope, notifications=RecordingNotifications(scope))
    )
    runtime.start()
    post = _Post()
    loop = qt.QEventLoop()
    responses = []
    errors = []
    token_file = tmp_path / "token"
    stream_holder = []
    try:
        with PluginHttpServer(
            runtime,
            post=post.submitted.emit,
            token_file=token_file,
            actions=("watch", "modal"),
            deadline=5,
        ) as server:
            token = token_file.read_text().strip()

            def client():
                try:
                    connection = http.client.HTTPConnection(
                        "127.0.0.1", server.port, timeout=10
                    )
                    try:
                        connection.request(
                            "POST",
                            "/streams/watch",
                            body="{}",
                            headers={
                                "Authorization": f"Bearer {token}",
                                "Content-Type": "application/json",
                            },
                        )
                        response = connection.getresponse()
                        assert response.status == 200
                        stream_holder.append(response)
                        assert response.readline().startswith(b"data: ")
                        responses.append(_post_call(server.port, token, "modal"))
                    finally:
                        connection.close()
                except BaseException as error:  # noqa: BLE001 - relay to the owner
                    errors.append(error)
                finally:
                    post.finished.emit()

            worker = threading.Thread(target=client, daemon=True)
            worker.start()
            _run_loop(loop, post, remaining=1, timeout=12000)
            worker.join(timeout=2)
            assert not worker.is_alive()
            assert not errors, errors
            assert responses[0][0] == 503
            assert responses[0][1]["error"]["code"] == "host_reloaded"
            assert events[0] == "modal-start"
            assert "stream-disposed" in events, events
            assert events[-1] == "stream-disposed", (
                f"the stream must be disposed after the dialog returns: {events}"
            )
            assert not token_file.exists()
    finally:
        for response in stream_holder:
            response.close()
        runtime.unload()


@pytest.mark.skipif(os.name != "posix", reason="private token requires POSIX")
def test_close_during_a_dialog_keeps_the_runtime_reserved_until_it_returns(
    qgis_app, tmp_path: Path
):
    widgets = pytest.importorskip("qgis.PyQt.QtWidgets")
    attempted = threading.Event()
    events = []
    app = QgisSdkPlugin(id="rest_close_race", title="Close race")

    @app.action(id="modal", title="Modal")
    def modal(ctx: PluginContext) -> str:
        events.append("modal-start")
        dialog = widgets.QDialog()
        qt.QTimer.singleShot(10, server.close)
        check = qt.QTimer(dialog)

        def maybe_finish():
            if attempted.is_set():
                check.stop()
                dialog.accept()

        check.timeout.connect(maybe_finish)
        check.start(10)
        qt.QTimer.singleShot(4000, dialog.reject)
        dialog.exec()
        events.append("modal-end")
        return "done"

    scope = ResourceScope()
    runtime = PluginRuntime(
        app, PluginContext(scope=scope, notifications=RecordingNotifications(scope))
    )
    runtime.start()
    post = _Post()
    loop = qt.QEventLoop()
    results = []
    failures = []
    server = PluginHttpServer(
        runtime,
        post=post.submitted.emit,
        token_file=tmp_path / "one",
        actions=("modal",),
        deadline=5,
    )
    candidate = PluginHttpServer(
        runtime,
        post=post.submitted.emit,
        token_file=tmp_path / "two",
        actions=("modal",),
        deadline=5,
    )
    try:
        server.start()
        token = (tmp_path / "one").read_text().strip()

        def client():
            try:
                results.append(_post_call(server.port, token, "modal"))
                try:
                    candidate.start()
                except QgisSdkHttpError:
                    events.append("replacement-refused")
                else:
                    failures.append(
                        AssertionError("a replacement started before the call unwound")
                    )
            except BaseException as error:  # noqa: BLE001 - relay to the owner
                failures.append(error)
            finally:
                attempted.set()
                post.finished.emit()

        worker = threading.Thread(target=client, daemon=True)
        worker.start()
        _run_loop(loop, post, remaining=1, timeout=12000)
        worker.join(timeout=2)
        assert not worker.is_alive()
        assert not failures, failures
        assert results[0][0] == 503
        assert results[0][1]["error"]["code"] == "host_reloaded"
        assert events == ["modal-start", "replacement-refused", "modal-end"], events
        candidate.start()
    finally:
        attempted.set()
        server.close()
        candidate.close()
        runtime.unload()


@pytest.mark.skipif(os.name != "posix", reason="private token requires POSIX")
def test_off_owner_close_disposes_a_live_stream_on_the_owner(qgis_app, tmp_path: Path):
    owner = threading.get_ident()
    disposed = threading.Event()
    disposal_threads = []
    app = QgisSdkPlugin(id="rest_owner_close", title="Owner close")

    @app.stream(id="watch", title="Watch", events={"data": int})
    def watch(ctx: PluginContext) -> Iterator[dict]:
        try:
            while True:
                yield {"kind": "data", "payload": 1}
        finally:
            disposal_threads.append(threading.get_ident())
            disposed.set()

    scope = ResourceScope()
    runtime = PluginRuntime(
        app, PluginContext(scope=scope, notifications=RecordingNotifications(scope))
    )
    runtime.start()
    post = _Post()
    loop = qt.QEventLoop()
    errors = []
    token_file = tmp_path / "token"
    response_holder = []
    try:
        server = PluginHttpServer(
            runtime,
            post=post.submitted.emit,
            token_file=token_file,
            actions=("watch",),
            deadline=5,
        )
        server.start()
        token = token_file.read_text().strip()

        def client():
            connection = http.client.HTTPConnection(
                "127.0.0.1", server.port, timeout=10
            )
            try:
                connection.request(
                    "POST",
                    "/streams/watch",
                    body="{}",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                )
                response = connection.getresponse()
                assert response.status == 200
                response.readline()
                response_holder.append(response)
                # Close from a non-owner thread while the stream is live.
                threading.Thread(target=server.close, daemon=True).start()
                assert disposed.wait(10), "the live stream was never disposed"
            except BaseException as error:  # noqa: BLE001 - relay to the owner
                errors.append(error)
            finally:
                connection.close()
                post.finished.emit()

        worker = threading.Thread(target=client, daemon=True)
        worker.start()
        _run_loop(loop, post, remaining=1, timeout=12000)
        worker.join(timeout=2)
        assert not worker.is_alive()
        assert not errors, errors
        assert server.wait_cleanup(10), "off-owner cleanup never completed"
        assert disposal_threads == [owner], (
            f"the stream was disposed off the QGIS owner thread: {disposal_threads}"
        )
        assert not token_file.exists()
    finally:
        for response in response_holder:
            response.close()
        runtime.unload()

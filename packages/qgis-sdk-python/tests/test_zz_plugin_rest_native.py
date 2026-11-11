"""The plugin HTTP API on the real QGIS owner thread: dispatch and lifecycle."""

from __future__ import annotations

import http.client
import json
import os
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
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


@dataclass(frozen=True, slots=True)
class _Rig:
    runtime: PluginRuntime
    post: _Post
    loop: qt.QEventLoop
    token_file: Path


def _rig(app: QgisSdkPlugin, tmp_path: Path, *, token_name: str = "token") -> _Rig:
    scope = ResourceScope()
    runtime = PluginRuntime(app, PluginContext(RecordingNotifications(scope), scope))
    runtime.start()
    return _Rig(runtime, _Post(), qt.QEventLoop(), tmp_path / token_name)


@dataclass(frozen=True, slots=True)
class _ServerSpec:
    actions: tuple[str, ...]
    deadline: int
    token_file: Path | None = None


def _server(rig: _Rig, spec: _ServerSpec) -> PluginHttpServer:
    return PluginHttpServer(
        rig.runtime,
        post=rig.post.submitted.emit,
        token_file=spec.token_file or rig.token_file,
        actions=spec.actions,
        deadline=spec.deadline,
    )


def _token(rig: _Rig) -> str:
    return rig.token_file.read_text().strip()


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


@dataclass(slots=True)
class _OwnerProbe:
    owner: int
    seen: list[int]
    result: list[str]
    errors: list[BaseException]


def _owner_app(probe: _OwnerProbe) -> QgisSdkPlugin:
    app = QgisSdkPlugin(id="rest_native", title="REST native")

    @app.action(id="where", title="Where")
    def where(ctx: PluginContext) -> str:
        probe.seen.append(threading.get_ident())
        return "gui"

    return app


def _owner_client(rig: _Rig, server, probe: _OwnerProbe):
    def client():
        try:
            probe.result.append(
                PluginClient(
                    f"http://127.0.0.1:{server.port}", token_file=rig.token_file
                ).call("where", {})
            )
        except BaseException as error:  # noqa: BLE001 - report to the owner thread
            probe.errors.append(error)
        finally:
            rig.post.finished.emit()

    worker = threading.Thread(target=client, daemon=True)
    worker.start()
    return worker


def _assert_owner(probe: _OwnerProbe, worker) -> None:
    assert not worker.is_alive()
    assert not probe.errors, probe.errors
    assert probe.result == ["gui"]
    assert probe.seen == [probe.owner]


@pytest.mark.skipif(os.name != "posix", reason="private token requires POSIX")
def test_rest_action_runs_on_real_qgis_owner(qgis_app, tmp_path: Path):
    probe = _OwnerProbe(threading.get_ident(), [], [], [])
    rig = _rig(_owner_app(probe), tmp_path)
    try:
        with _server(rig, _ServerSpec(("where",), 2)) as server:
            worker = _owner_client(rig, server, probe)
            _run_loop(rig.loop, rig.post, remaining=1, timeout=5000)
            _assert_owner(probe, worker)
    finally:
        rig.runtime.unload()


@dataclass(slots=True)
class _ModalProbe:
    entered: threading.Event
    queued_during_modal: threading.Event
    events: list[str]
    server_box: list[PluginHttpServer]
    responses: list[tuple[int, dict]]
    errors: list[BaseException]


def _modal_action(app, widgets, probe: _ModalProbe):
    @app.action(id="modal", title="Modal")
    def modal(ctx: PluginContext) -> str:
        probe.events.append("modal-start")
        dialog = widgets.QDialog()
        probe.entered.set()
        check = qt.QTimer(dialog)

        def maybe_close():
            # Prove the second request reached the owner queue while the
            # nested loop was running, not merely that the socket was written.
            if probe.server_box[0].pending_requests:
                probe.queued_during_modal.set()
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
        probe.events.append("modal-end")
        return "closed"

    return modal


def _second_action(app, probe: _ModalProbe):
    @app.action(id="second", title="Second")
    def second(ctx: PluginContext) -> str:
        probe.events.append("second")
        return "ok"

    return second


def _modal_app(widgets, probe: _ModalProbe) -> QgisSdkPlugin:
    app = QgisSdkPlugin(id="rest_modal", title="REST modal")
    _modal_action(app, widgets, probe)
    _second_action(app, probe)
    return app


def _modal_clients(rig: _Rig, server, probe: _ModalProbe):
    token = _token(rig)

    def first_client():
        try:
            probe.responses.append(_post_call(server.port, token, "modal"))
        except BaseException as error:  # noqa: BLE001 - relay to the owner
            probe.errors.append(error)
        finally:
            rig.post.finished.emit()

    def second_client():
        try:
            assert probe.entered.wait(5)
            probe.responses.append(_post_call(server.port, token, "second"))
        except BaseException as error:  # noqa: BLE001 - relay to the owner
            probe.errors.append(error)
        finally:
            rig.post.finished.emit()

    threads = [
        threading.Thread(target=fn, daemon=True) for fn in (first_client, second_client)
    ]
    for thread in threads:
        thread.start()
    return threads


def _assert_modal(probe: _ModalProbe, threads) -> None:
    for thread in threads:
        thread.join(timeout=1)
    assert not any(thread.is_alive() for thread in threads)
    assert not probe.errors, probe.errors
    assert [status for status, _ in probe.responses] == [200, 200]
    assert probe.queued_during_modal.is_set(), "the second call never queued"
    assert probe.events == ["modal-start", "modal-end", "second"], (
        f"a nested dialog re-entered a call: {probe.events}"
    )


@pytest.mark.skipif(os.name != "posix", reason="private token requires POSIX")
def test_a_nested_qdialog_defers_a_second_call_until_it_returns(
    qgis_app, tmp_path: Path
):
    widgets = pytest.importorskip("qgis.PyQt.QtWidgets")
    probe = _ModalProbe(threading.Event(), threading.Event(), [], [], [], [])
    rig = _rig(_modal_app(widgets, probe), tmp_path)
    try:
        with _server(rig, _ServerSpec(("modal", "second"), 5)) as server:
            probe.server_box.append(server)
            threads = _modal_clients(rig, server, probe)
            _run_loop(rig.loop, rig.post, remaining=2, timeout=10000)
            _assert_modal(probe, threads)
    finally:
        rig.runtime.unload()


@dataclass(slots=True)
class _StreamProbe:
    expected: int
    seen: list[int]
    frames: list[dict]
    errors: list[BaseException]


def _stream_app(probe: _StreamProbe) -> QgisSdkPlugin:
    app = QgisSdkPlugin(id="rest_native_stream", title="Native stream")

    @app.stream(id="ticks", title="Ticks", events={"data": int})
    def ticks(ctx: PluginContext) -> Iterator[dict]:
        for index in range(40):
            probe.seen.append(threading.get_ident())
            yield {"kind": "data", "payload": index}

    return app


def _read_stream(connection, token, probe: _StreamProbe):
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
        probe.frames.append(json.loads(line.removeprefix(b"data: ")))
        assert response.readline() == b"\n"
        if "terminal" in probe.frames[-1]:
            break


def _stream_client(rig: _Rig, server, probe: _StreamProbe):
    token = _token(rig)

    def client():
        connection = http.client.HTTPConnection("127.0.0.1", server.port, timeout=10)
        try:
            _read_stream(connection, token, probe)
        except BaseException as error:  # noqa: BLE001 - relay to the owner
            probe.errors.append(error)
        finally:
            connection.close()
            rig.post.finished.emit()

    worker = threading.Thread(target=client, daemon=True)
    worker.start()
    return worker


def _assert_stream(probe: _StreamProbe, worker) -> None:
    worker.join(timeout=1)
    assert not worker.is_alive()
    assert not probe.errors, probe.errors
    assert [frame["seq"] for frame in probe.frames] == list(range(41))
    assert [frame["event"]["payload"] for frame in probe.frames[:-1]] == list(range(40))
    assert probe.frames[-1]["terminal"]["kind"] == "complete"
    assert probe.seen == [probe.expected] * 40, (
        "a stream frame was produced off the QGIS owner thread"
    )


@pytest.mark.skipif(os.name != "posix", reason="private token requires POSIX")
def test_a_long_stream_is_pumped_on_the_real_qgis_owner(qgis_app, tmp_path: Path):
    probe = _StreamProbe(threading.get_ident(), [], [], [])
    rig = _rig(_stream_app(probe), tmp_path)
    try:
        with _server(rig, _ServerSpec(("ticks",), 5)) as server:
            worker = _stream_client(rig, server, probe)
            _run_loop(rig.loop, rig.post, remaining=1, timeout=10000)
            _assert_stream(probe, worker)
    finally:
        rig.runtime.unload()


@dataclass(slots=True)
class _ReloadProbe:
    events: list[str]
    responses: list[tuple[int, dict]]
    errors: list[BaseException]
    stream_holder: list[object]


def _reload_stream(app, probe: _ReloadProbe):
    @app.stream(id="watch", title="Watch", events={"data": int})
    def watch(ctx: PluginContext) -> Iterator[dict]:
        try:
            while True:
                yield {"kind": "data", "payload": 1}
        finally:
            probe.events.append("stream-disposed")

    return watch


def _reload_modal(app, widgets, probe: _ReloadProbe, runtime_holder):
    @app.action(id="modal", title="Modal")
    def modal(ctx: PluginContext) -> str:
        probe.events.append("modal-start")
        dialog = widgets.QDialog()
        qt.QTimer.singleShot(10, runtime_holder[0].unload)
        qt.QTimer.singleShot(400, dialog.accept)
        dialog.exec()
        probe.events.append("modal-end")
        return "done"

    return modal


def _reload_app(widgets, probe: _ReloadProbe, runtime_holder) -> QgisSdkPlugin:
    app = QgisSdkPlugin(id="rest_reload", title="Reload")
    _reload_stream(app, probe)
    _reload_modal(app, widgets, probe, runtime_holder)
    return app


def _reload_request(connection, token, server, probe: _ReloadProbe):
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
    probe.stream_holder.append(response)
    assert response.readline().startswith(b"data: ")
    probe.responses.append(_post_call(server.port, token, "modal"))


def _reload_client(rig: _Rig, server, probe: _ReloadProbe):
    token = _token(rig)

    def client():
        connection = http.client.HTTPConnection("127.0.0.1", server.port, timeout=10)
        try:
            _reload_request(connection, token, server, probe)
        except BaseException as error:  # noqa: BLE001 - relay to the owner
            probe.errors.append(error)
        finally:
            connection.close()
            rig.post.finished.emit()

    worker = threading.Thread(target=client, daemon=True)
    worker.start()
    return worker


def _assert_reload(rig: _Rig, probe: _ReloadProbe, worker) -> None:
    worker.join(timeout=2)
    assert not worker.is_alive()
    assert not probe.errors, probe.errors
    assert probe.responses[0][0] == 503
    assert probe.responses[0][1]["error"]["code"] == "host_reloaded"
    assert probe.events[0] == "modal-start"
    assert "stream-disposed" in probe.events, probe.events
    assert probe.events[-1] == "stream-disposed", (
        f"the stream must be disposed after the dialog returns: {probe.events}"
    )
    assert not rig.token_file.exists()


@pytest.mark.skipif(os.name != "posix", reason="private token requires POSIX")
def test_reload_during_a_dialog_fails_the_call_and_disposes_the_stream_after(
    qgis_app, tmp_path: Path
):
    widgets = pytest.importorskip("qgis.PyQt.QtWidgets")
    probe = _ReloadProbe([], [], [], [])
    runtime_holder = []
    rig = _rig(_reload_app(widgets, probe, runtime_holder), tmp_path)
    runtime_holder.append(rig.runtime)
    try:
        with _server(rig, _ServerSpec(("watch", "modal"), 5)) as server:
            worker = _reload_client(rig, server, probe)
            _run_loop(rig.loop, rig.post, remaining=1, timeout=12000)
            _assert_reload(rig, probe, worker)
    finally:
        for response in probe.stream_holder:
            response.close()
        rig.runtime.unload()


@dataclass(slots=True)
class _CloseProbe:
    attempted: threading.Event
    events: list[str]
    results: list[tuple[int, dict]]
    failures: list[BaseException]


def _close_action(app, widgets, probe: _CloseProbe, server_holder):
    @app.action(id="modal", title="Modal")
    def modal(ctx: PluginContext) -> str:
        probe.events.append("modal-start")
        dialog = widgets.QDialog()
        qt.QTimer.singleShot(10, server_holder[0].close)
        check = qt.QTimer(dialog)

        def maybe_finish():
            if probe.attempted.is_set():
                check.stop()
                dialog.accept()

        check.timeout.connect(maybe_finish)
        check.start(10)
        qt.QTimer.singleShot(4000, dialog.reject)
        dialog.exec()
        probe.events.append("modal-end")
        return "done"

    return modal


def _close_app(widgets, probe: _CloseProbe, server_holder) -> QgisSdkPlugin:
    app = QgisSdkPlugin(id="rest_close_race", title="Close race")
    _close_action(app, widgets, probe, server_holder)
    return app


@dataclass(frozen=True, slots=True)
class _CloseCase:
    rig: _Rig
    server: PluginHttpServer
    candidate: PluginHttpServer
    token: str
    probe: _CloseProbe


def _close_client(case: _CloseCase):
    def client():
        try:
            case.probe.results.append(_post_call(case.server.port, case.token, "modal"))
            try:
                case.candidate.start()
            except QgisSdkHttpError:
                case.probe.events.append("replacement-refused")
            else:
                case.probe.failures.append(
                    AssertionError("a replacement started before the call unwound")
                )
        except BaseException as error:  # noqa: BLE001 - relay to the owner
            case.probe.failures.append(error)
        finally:
            case.probe.attempted.set()
            case.rig.post.finished.emit()

    worker = threading.Thread(target=client, daemon=True)
    worker.start()
    return worker


def _assert_close(case: _CloseCase, worker) -> None:
    worker.join(timeout=2)
    assert not worker.is_alive()
    assert not case.probe.failures, case.probe.failures
    assert case.probe.results[0][0] == 503
    assert case.probe.results[0][1]["error"]["code"] == "host_reloaded"
    assert case.probe.events == [
        "modal-start",
        "replacement-refused",
        "modal-end",
    ], case.probe.events


@pytest.mark.skipif(os.name != "posix", reason="private token requires POSIX")
def test_close_during_a_dialog_keeps_the_runtime_reserved_until_it_returns(
    qgis_app, tmp_path: Path
):
    widgets = pytest.importorskip("qgis.PyQt.QtWidgets")
    probe = _CloseProbe(threading.Event(), [], [], [])
    server_holder = []
    rig = _rig(_close_app(widgets, probe, server_holder), tmp_path)
    server = _server(rig, _ServerSpec(("modal",), 5, tmp_path / "one"))
    candidate = _server(rig, _ServerSpec(("modal",), 5, tmp_path / "two"))
    server_holder.append(server)
    try:
        server.start()
        token = (tmp_path / "one").read_text().strip()
        case = _CloseCase(rig, server, candidate, token, probe)
        worker = _close_client(case)
        _run_loop(rig.loop, rig.post, remaining=1, timeout=12000)
        _assert_close(case, worker)
        candidate.start()
    finally:
        probe.attempted.set()
        server.close()
        candidate.close()
        rig.runtime.unload()


@dataclass(slots=True)
class _OwnerCloseProbe:
    owner: int
    disposed: threading.Event
    disposal_threads: list[int]
    errors: list[BaseException]
    response_holder: list[object]


def _owner_close_app(probe: _OwnerCloseProbe) -> QgisSdkPlugin:
    app = QgisSdkPlugin(id="rest_owner_close", title="Owner close")

    @app.stream(id="watch", title="Watch", events={"data": int})
    def watch(ctx: PluginContext) -> Iterator[dict]:
        try:
            while True:
                yield {"kind": "data", "payload": 1}
        finally:
            probe.disposal_threads.append(threading.get_ident())
            probe.disposed.set()

    return app


@dataclass(frozen=True, slots=True)
class _OwnerCloseCase:
    rig: _Rig
    server: PluginHttpServer
    token: str
    probe: _OwnerCloseProbe


def _owner_close_request(connection, token, case: _OwnerCloseCase):
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
    case.probe.response_holder.append(response)
    # Close from a non-owner thread while the stream is live.
    threading.Thread(target=case.server.close, daemon=True).start()
    assert case.probe.disposed.wait(10), "the live stream was never disposed"


def _owner_close_client(case: _OwnerCloseCase):
    def client():
        connection = http.client.HTTPConnection(
            "127.0.0.1", case.server.port, timeout=10
        )
        try:
            _owner_close_request(connection, case.token, case)
        except BaseException as error:  # noqa: BLE001 - relay to the owner
            case.probe.errors.append(error)
        finally:
            connection.close()
            case.rig.post.finished.emit()

    worker = threading.Thread(target=client, daemon=True)
    worker.start()
    return worker


def _assert_owner_close(case: _OwnerCloseCase, worker) -> None:
    worker.join(timeout=2)
    assert not worker.is_alive()
    assert not case.probe.errors, case.probe.errors
    assert case.server.wait_cleanup(10), "off-owner cleanup never completed"
    assert case.probe.disposal_threads == [case.probe.owner], (
        f"the stream was disposed off the QGIS owner thread: "
        f"{case.probe.disposal_threads}"
    )
    assert not case.rig.token_file.exists()


@pytest.mark.skipif(os.name != "posix", reason="private token requires POSIX")
def test_off_owner_close_disposes_a_live_stream_on_the_owner(qgis_app, tmp_path: Path):
    probe = _OwnerCloseProbe(threading.get_ident(), threading.Event(), [], [], [])
    rig = _rig(_owner_close_app(probe), tmp_path)
    server = _server(rig, _ServerSpec(("watch",), 5))
    try:
        server.start()
        token = _token(rig)
        case = _OwnerCloseCase(rig, server, token, probe)
        worker = _owner_close_client(case)
        _run_loop(rig.loop, rig.post, remaining=1, timeout=12000)
        _assert_owner_close(case, worker)
    finally:
        for response in probe.response_holder:
            response.close()
        rig.runtime.unload()

"""Dispatch serialization and transport limits of the plugin HTTP listener."""

from __future__ import annotations

import http.client
import json
import os
import queue
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from qgis_sdk import QgisSdkPlugin
from qgis_sdk.core import PluginContext, PluginRuntime, ResourceScope
from qgis_sdk.testing import RecordingNotifications

pytestmark = pytest.mark.skipif(
    os.name != "posix", reason="private token requires POSIX"
)


class _Overlap:
    """Count handlers running at once so a test can prove serialization."""

    def __init__(self) -> None:
        self.active = 0
        self.seen: list[int] = []
        self.lock = threading.Lock()

    def enter(self) -> None:
        with self.lock:
            self.active += 1
            self.seen.append(self.active)

    def leave(self) -> None:
        with self.lock:
            self.active -= 1


def _runtime(app):
    scope = ResourceScope()
    runtime = PluginRuntime(
        app, PluginContext(scope=scope, notifications=RecordingNotifications(scope))
    )
    runtime.start()
    return runtime


def _call(port, token, action, payload):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        connection.request(
            "POST",
            f"/actions/{action}",
            body=json.dumps(payload),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        response = connection.getresponse()
        return response.status, response.read()
    finally:
        connection.close()


def test_a_nested_event_loop_defers_the_second_call_instead_of_reentering(
    tmp_path: Path,
):
    from qgis_sdk.http import PluginHttpServer

    pending: queue.Queue = queue.Queue()
    inner_done = threading.Event()
    modal_entered = threading.Event()
    finished: dict[str, float] = {}
    state = _Overlap()
    app = QgisSdkPlugin(id="nested", title="Nested")

    @app.action(id="modal", title="Modal")
    def modal(ctx: PluginContext, value: str) -> str:
        # A native dialog pumps the owner thread: queued work runs inside it.
        modal_entered.set()
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and not inner_done.is_set():
            try:
                pending.get(timeout=0.02)()
            except queue.Empty:
                pass
        state.enter()
        try:
            return value
        finally:
            state.leave()
            finished["modal"] = time.monotonic()

    @app.action(id="echo", title="Echo")
    def echo(ctx: PluginContext, value: str) -> str:
        state.enter()
        try:
            return value
        finally:
            state.leave()
            finished["echo"] = time.monotonic()

    runtime = _runtime(app)
    try:
        with PluginHttpServer(
            runtime,
            post=pending.put,
            token_file=tmp_path / "token",
            actions=("modal", "echo"),
            deadline=10,
        ) as server:
            token = (tmp_path / "token").read_text().strip()
            first: dict = {}
            second: dict = {}
            threads = [
                threading.Thread(
                    target=lambda: first.update(
                        r=_call(server.port, token, "modal", {"value": "outer"})
                    )
                ),
                threading.Thread(
                    target=lambda: (
                        second.update(
                            r=_call(server.port, token, "echo", {"value": "inner"})
                        ),
                        inner_done.set(),
                    )
                ),
            ]
            threads[0].start()
            # Only ask for the second call once the first handler is inside its
            # nested loop, so the ordering under test is deterministic.
            threading.Thread(
                target=lambda: (
                    modal_entered.wait(5),
                    threads[1].start(),
                ),
                daemon=True,
            ).start()
            deadline = time.monotonic() + 15
            while any(thread.is_alive() for thread in threads):
                assert time.monotonic() < deadline, "nested dispatch did not finish"
                try:
                    pending.get(timeout=0.02)()
                except queue.Empty:
                    pass
            assert first["r"][0] == 200, first
            assert second["r"][0] == 200, second
            assert json.loads(first["r"][1]) == {"value": "outer"}
            assert json.loads(second["r"][1]) == {"value": "inner"}
            assert max(state.seen) == 1, (
                f"a nested loop dispatched a second call: {state.seen}"
            )
            assert finished["echo"] >= finished["modal"], (
                "the second call ran inside the first handler"
            )
    finally:
        runtime.unload()


def test_an_inline_post_host_still_serializes_concurrent_calls(tmp_path: Path):
    from qgis_sdk.http import PluginHttpServer

    state = _Overlap()
    app = QgisSdkPlugin(id="serialized", title="Serialized")

    @app.action(id="slow", title="Slow")
    def slow(ctx: PluginContext, value: str) -> str:
        state.enter()
        try:
            time.sleep(0.2)
            return value
        finally:
            state.leave()

    runtime = _runtime(app)
    try:
        with PluginHttpServer(
            runtime,
            post=lambda callback: callback(),
            token_file=tmp_path / "token",
            actions=("slow",),
            deadline=10,
        ) as server:
            token = (tmp_path / "token").read_text().strip()
            results: list = []
            threads = [
                threading.Thread(
                    target=lambda value=value: results.append(
                        _call(server.port, token, "slow", {"value": value})
                    )
                )
                for value in ("one", "two")
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=20)
            assert sorted(status for status, _ in results) == [200, 200]
            assert max(state.seen) == 1, f"handlers overlapped: {state.seen}"
    finally:
        runtime.unload()


def test_a_handler_waiting_on_its_own_api_gets_host_busy(tmp_path: Path):
    import http.client

    from qgis_sdk.http import PluginHttpServer

    nested: dict = {}
    app = QgisSdkPlugin(id="reentrant", title="Reentrant")

    @app.action(id="outer", title="Outer")
    def outer(ctx: PluginContext, value: str) -> str:
        connection = http.client.HTTPConnection("127.0.0.1", nested["port"], timeout=15)
        try:
            connection.request(
                "POST",
                "/actions/outer",
                body=json.dumps({"value": "inner"}),
                headers={
                    "Authorization": f"Bearer {nested['token']}",
                    "Content-Type": "application/json",
                },
            )
            response = connection.getresponse()
            nested["result"] = (response.status, response.read())
        finally:
            connection.close()
        return value

    runtime = _runtime(app)
    try:
        with PluginHttpServer(
            runtime,
            post=lambda callback: callback(),
            token_file=tmp_path / "token",
            actions=("outer",),
            deadline=0.5,
        ) as server:
            nested["port"] = server.port
            nested["token"] = (tmp_path / "token").read_text().strip()
            started = time.monotonic()
            status, body = _call(server.port, nested["token"], "outer", {"value": "x"})
            elapsed = time.monotonic() - started
            # The inner request waits for its turn, then fails rather than
            # running inside the outer handler; the outer call still succeeds.
            assert status == 200 and json.loads(body) == {"value": "x"}
            inner_status, inner_body = nested["result"]
            assert inner_status == 503
            assert json.loads(inner_body)["error"]["code"] == "host_busy"
            assert elapsed < 10, "the listener must not deadlock"
    finally:
        runtime.unload()


def test_the_owner_thread_is_refused_promptly_instead_of_waiting(
    tmp_path: Path,
):
    from qgis_sdk.http._queue import GuiQueue, QgisSdkHostBusyError

    outcome: dict = {}

    def work():
        started = time.monotonic()
        try:
            queue.call(lambda: "inner")
        except QgisSdkHostBusyError as error:
            outcome["error"] = error
            outcome["elapsed"] = time.monotonic() - started
        return "outer"

    queue = GuiQueue(post=lambda callback: callback(), deadline=10)
    assert queue.call(work) == "outer"
    assert outcome["error"].code == "host_busy"
    assert outcome["elapsed"] < 1, (
        "re-entry from the running work must not burn the whole deadline"
    )
    # The queue is usable again once the work returns.
    assert queue.call(lambda: "later") == "later"


def test_connection_limit_rejects_overload_and_recovers(tmp_path: Path):
    import socket

    from qgis_sdk.http import PluginHttpServer

    app = QgisSdkPlugin(id="limited", title="Limited")

    @app.action(id="echo", title="Echo")
    def echo(ctx: PluginContext, value: str) -> str:
        return value

    runtime = _runtime(app)
    stalled = []
    try:
        with PluginHttpServer(
            runtime,
            post=lambda callback: callback(),
            token_file=tmp_path / "token",
            actions=("echo",),
            max_connections=2,
            request_read_timeout=2,
        ) as server:
            token = (tmp_path / "token").read_text().strip()
            try:
                # Silent connections hold both handler slots without sending a
                # request line, which is how a slow or hostile client behaves.
                for _ in range(2):
                    stalled.append(
                        socket.create_connection(("127.0.0.1", server.port), timeout=3)
                    )
                # A fixed sleep would race connection acceptance under load, so
                # wait until the slots are actually held.
                status = _until_busy(
                    lambda: _probe_status(server.port, token, "echo", {"value": "x"}),
                    budget=10,
                )
                assert status == 503, f"an overloaded listener answered {status}"
            finally:
                for sock in stalled:
                    sock.close()
                stalled.clear()
            deadline = time.monotonic() + 5
            status = 503
            while status == 503 and time.monotonic() < deadline:
                status = _probe_status(server.port, token, "echo", {"value": "x"})
                if status == 503:
                    time.sleep(0.05)
            assert status == 200, "capacity must recover after the clients leave"
    finally:
        runtime.unload()


def test_slow_header_trickle_hits_an_absolute_deadline(tmp_path: Path):
    import socket

    from qgis_sdk.http import PluginHttpServer

    app = QgisSdkPlugin(id="slow_header", title="Slow header")

    @app.action(id="echo", title="Echo")
    def echo(ctx: PluginContext, value: str) -> str:
        return value

    runtime = _runtime(app)
    try:
        with PluginHttpServer(
            runtime,
            post=lambda callback: callback(),
            token_file=tmp_path / "token",
            actions=("echo",),
            max_connections=1,
            request_read_timeout=0.4,
        ) as server:
            token = (tmp_path / "token").read_text().strip()
            sock = socket.create_connection(("127.0.0.1", server.port), timeout=3)
            try:
                sock.sendall(b"POST /actions/echo HTTP/1.1\r\nHost: ")
                closed = _trickle_until_closed(sock)
            finally:
                sock.close()
            assert closed, "a client must not hold a request open by trickling bytes"
            status = _eventually(
                lambda: _call(server.port, token, "echo", {"value": "x"})[0]
            )
            assert status == 200, "the connection slot must return after the deadline"
    finally:
        runtime.unload()


def test_slow_body_trickle_times_out_without_dispatch(tmp_path: Path):
    import socket

    from qgis_sdk.http import PluginHttpServer

    seen: list[str] = []
    app = QgisSdkPlugin(id="slow_body", title="Slow body")

    @app.action(id="save", title="Save")
    def save(ctx: PluginContext, value: str) -> str:
        seen.append(value)
        return value

    runtime = _runtime(app)
    try:
        with PluginHttpServer(
            runtime,
            post=lambda callback: callback(),
            token_file=tmp_path / "token",
            actions=("save",),
            request_read_timeout=0.4,
        ) as server:
            token = (tmp_path / "token").read_text().strip()
            header = (
                f"POST /actions/save HTTP/1.1\r\nHost: 127.0.0.1:{server.port}\r\n"
                f"Authorization: Bearer {token}\r\n"
                "Content-Type: application/json\r\nContent-Length: 1000\r\n\r\n"
            ).encode()
            sock = socket.create_connection(("127.0.0.1", server.port), timeout=3)
            try:
                sock.sendall(header)
                closed = _trickle_until_closed(sock)
            finally:
                sock.close()
            assert closed
            assert seen == [], "a partial body must never reach the handler"
    finally:
        runtime.unload()


def test_a_truncated_body_never_dispatches(tmp_path: Path):
    import socket

    from qgis_sdk.http import PluginHttpServer

    seen: list[str] = []
    app = QgisSdkPlugin(id="truncated", title="Truncated")

    @app.action(id="save", title="Save")
    def save(ctx: PluginContext, value: str) -> str:
        seen.append(value)
        return value

    runtime = _runtime(app)
    try:
        with PluginHttpServer(
            runtime,
            post=lambda callback: callback(),
            token_file=tmp_path / "token",
            actions=("save",),
        ) as server:
            token = (tmp_path / "token").read_text().strip()
            header = (
                f"POST /actions/save HTTP/1.1\r\nHost: 127.0.0.1:{server.port}\r\n"
                f"Authorization: Bearer {token}\r\n"
                "Content-Type: application/json\r\nContent-Length: 200\r\n\r\n"
            ).encode()
            body = b'{"value": "sneaky"}'
            with socket.create_connection(("127.0.0.1", server.port), timeout=3) as s:
                s.sendall(header + body)
                s.shutdown(socket.SHUT_WR)
                assert s.recv(4096)
            assert seen == [], "a truncated body must never reach the handler"
            assert _call(server.port, token, "save", {"value": "ok"})[0] == 200
            assert seen == ["ok"]
    finally:
        runtime.unload()


def test_oversized_and_ambiguous_bodies_are_rejected_before_dispatch(
    tmp_path: Path,
):
    from qgis_sdk.http import PluginHttpServer

    seen: list[str] = []
    app = QgisSdkPlugin(id="bodies", title="Bodies")

    @app.action(id="save", title="Save")
    def save(ctx: PluginContext, value: str) -> str:
        seen.append(value)
        return value

    runtime = _runtime(app)
    try:
        with PluginHttpServer(
            runtime,
            post=lambda callback: callback(),
            token_file=tmp_path / "token",
            actions=("save",),
        ) as server:
            token = (tmp_path / "token").read_text().strip()
            oversized = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Content-Length": str(1024 * 1024 + 1),
            }
            assert _raw(server.port, "POST", "/actions/save", oversized, b"{}") == 413
            doubled = (
                f"POST /actions/save HTTP/1.1\r\nHost: 127.0.0.1:{server.port}\r\n"
                f"Authorization: Bearer {token}\r\n"
                "Content-Type: application/json\r\n"
                "Content-Length: 2\r\nContent-Length: 2\r\n\r\n{}"
            ).encode()
            with socket_connection(server.port) as sock:
                sock.sendall(doubled)
                assert b"400" in sock.recv(4096)
            assert (
                _raw(
                    server.port,
                    "POST",
                    "/actions/save",
                    {"Authorization": f"Bearer {token}", "Content-Length": "2"},
                    b"[]",
                )
                == 400
            ), "a non-object payload is refused"
            assert seen == []
    finally:
        runtime.unload()


def test_sse_capacity_reserves_a_connection_for_calls(tmp_path: Path):

    from qgis_sdk.http import PluginHttpServer

    app = QgisSdkPlugin(id="stream_capacity", title="Stream capacity")

    @app.stream(id="watch", title="Watch", events={"data": int})
    def watch(ctx: PluginContext) -> Iterator[dict]:
        while True:
            yield {"kind": "data", "payload": 1}

    @app.action(id="echo", title="Echo")
    def echo(ctx: PluginContext, value: str) -> str:
        return value

    runtime = _runtime(app)
    first = None
    second = None
    try:
        with PluginHttpServer(
            runtime,
            post=lambda callback: callback(),
            token_file=tmp_path / "token",
            actions=("watch", "echo"),
            max_connections=3,
            max_event_streams=1,
        ) as server:
            token = (tmp_path / "token").read_text().strip()
            first = _open_stream(server.port, token, "watch")
            assert first.status == 200
            second = _open_stream(server.port, token, "watch")
            assert second.status == 503, "a second stream must not exhaust calls"
            assert _call(server.port, token, "echo", {"value": "ok"})[0] == 200
            first.close()
            first = None
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                second.close()
                second = _open_stream(server.port, token, "watch")
                if second.status == 200:
                    break
                time.sleep(0.05)
            assert second is not None and second.status == 200
    finally:
        for response in (first, second):
            if response is not None:
                response.close()
        runtime.unload()


def test_a_stalled_sse_reader_is_disposed(tmp_path: Path):
    from qgis_sdk.http import PluginHttpServer

    disposed = threading.Event()
    payload = "x" * (64 * 1024)
    app = QgisSdkPlugin(id="stalled_reader", title="Stalled reader")

    @app.stream(id="watch", title="Watch", events={"data": str})
    def watch(ctx: PluginContext) -> Iterator[dict]:
        try:
            while True:
                yield {"kind": "data", "payload": payload}
        finally:
            disposed.set()

    runtime = _runtime(app)
    try:
        with PluginHttpServer(
            runtime,
            post=lambda callback: callback(),
            token_file=tmp_path / "token",
            actions=("watch",),
            stream_write_timeout=0.3,
        ) as server:
            token = (tmp_path / "token").read_text().strip()
            response = _open_stream(server.port, token, "watch")
            try:
                assert response.status == 200
                assert disposed.wait(15), (
                    "a client that never reads must not hold the subscription"
                )
            finally:
                response.close()
    finally:
        runtime.unload()


def test_an_oversized_sse_frame_closes_and_disposes_the_stream(tmp_path: Path):
    from qgis_sdk.http import PluginHttpServer

    disposed = threading.Event()
    app = QgisSdkPlugin(id="huge_frame", title="Huge frame")

    @app.stream(id="watch", title="Watch", events={"data": str})
    def watch(ctx: PluginContext) -> Iterator[dict]:
        try:
            yield {"kind": "data", "payload": "x" * (600 * 1024)}
            while True:
                yield {"kind": "data", "payload": "x"}
        finally:
            disposed.set()

    runtime = _runtime(app)
    try:
        with PluginHttpServer(
            runtime,
            post=lambda callback: callback(),
            token_file=tmp_path / "token",
            actions=("watch",),
        ) as server:
            token = (tmp_path / "token").read_text().strip()
            response = _open_stream(server.port, token, "watch")
            try:
                assert response.status == 200
                assert disposed.wait(10), "an oversized frame must end the stream"
            finally:
                response.close()
    finally:
        runtime.unload()


def _probe_status(port, token, action, payload) -> int:
    """The status of a call on a listener that may reject by closing.

    An overloaded listener answers 503 and closes without reading the
    request, so the client can see a broken pipe instead of a response.
    """
    try:
        return _call(port, token, action, payload)[0]
    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
        return 503


def _trickle_until_closed(sock, budget: float = 4.0) -> bool:
    import select

    end = time.monotonic() + budget
    while time.monotonic() < end:
        try:
            sock.sendall(b"x")
            ready, _, _ = select.select([sock], [], [], 0.07)
            if ready and not sock.recv(4096):
                return True
        except OSError:
            return True
    return False


def _until_busy(probe, budget: float = 10.0):
    """Probe until the listener reports overload, never past it."""
    end = time.monotonic() + budget
    value = probe()
    while value != 503 and time.monotonic() < end:
        time.sleep(0.02)
        value = probe()
    return value


def _eventually(probe, budget: float = 5.0):
    end = time.monotonic() + budget
    value = probe()
    while value == 503 and time.monotonic() < end:
        time.sleep(0.05)
        value = probe()
    return value


def _raw(port, method, path, headers, body):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        response.read()
        return response.status
    finally:
        connection.close()


def _open_stream(port, token, stream):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        connection.request(
            "POST",
            f"/streams/{stream}",
            body="{}",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        return connection.getresponse()
    except BaseException:
        connection.close()
        raise


def socket_connection(port):
    import socket

    return socket.create_connection(("127.0.0.1", port), timeout=3)


def test_the_frame_buffer_bounds_aggregate_bytes_not_just_one_frame():
    from queue import Full

    from qgis_sdk.http._server import _FrameBuffer

    buffer = _FrameBuffer()
    frame = "x" * (512 * 1024 - 8)  # under the per-frame cap
    for _ in range(4):
        buffer.put_nowait(frame)
    with pytest.raises(Full):
        buffer.put_nowait(frame)
    assert buffer.get(timeout=1) == frame, "the buffer stays usable after a refusal"


def test_start_refuses_a_platform_without_private_token_permissions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """The documented support boundary: no Windows ACL implementation yet."""
    from types import SimpleNamespace

    from qgis_sdk.http import PluginHttpServer, QgisSdkHttpError, _server

    app = QgisSdkPlugin(id="platform", title="Platform")

    @app.action(id="echo", title="Echo")
    def echo(ctx: PluginContext, value: str) -> str:
        return value

    runtime = _runtime(app)
    token_file = tmp_path / "token"
    try:
        server = PluginHttpServer(
            runtime,
            post=lambda callback: callback(),
            token_file=token_file,
            actions=("echo",),
        )
        # Patch the module's view of the platform, not the process's.
        monkeypatch.setattr(_server, "os", SimpleNamespace(name="nt"))
        with pytest.raises(QgisSdkHttpError, match="POSIX"):
            server.start()
        assert not token_file.exists(), "a refused start must not leave a token"
        # The refusal does not consume the runtime: the same server starts once
        # the platform check passes again.
        monkeypatch.undo()
        server.start()
        assert server.port
    finally:
        runtime.unload()


def test_error_codes_map_to_one_status_table():
    """Retryable conditions answer 503 and every other code answers 400."""
    from qgis_sdk.http import PluginHttpServer

    def status(code):
        return PluginHttpServer._error_status({"error": {"code": code, "message": ""}})

    assert status("host_busy") == 503
    assert status("host_reloaded") == 503
    assert status("capacity") == 503
    assert status("invalid_request") == 400
    assert status("operation_failed") == 400
    assert status("something_new") == 400


def test_the_session_budget_answers_503_with_its_code(tmp_path: Path):
    """An exhausted session budget is a retryable condition, not bad input."""
    from qgis_sdk.http import PluginHttpServer

    app = QgisSdkPlugin(id="session_budget", title="Session budget")

    @app.stream(id="watch", title="Watch", events={"data": int})
    def watch(ctx: PluginContext) -> Iterator[dict]:
        while True:
            yield {"kind": "data", "payload": 1}

    runtime = _runtime(app)
    streams = []
    try:
        with PluginHttpServer(
            runtime,
            post=lambda callback: callback(),
            token_file=tmp_path / "token",
            actions=("watch",),
            max_connections=130,
            max_event_streams=128,
        ) as server:
            token = (tmp_path / "token").read_text().strip()
            for _ in range(64):
                response = _open_stream(server.port, token, "watch")
                streams.append(response)
                assert response.status == 200, "the budget must hold 64 sessions"
            refused = _open_stream(server.port, token, "watch")
            streams.append(refused)
            assert refused.status == 503, "an exhausted budget must not look like 400"
            assert json.loads(refused.read())["error"]["code"] == "capacity"
    finally:
        for response in streams:
            response.close()
        runtime.unload()


def _port_is_open(server) -> bool:
    """Whether the listener still reports its port, i.e. close has not begun."""
    from qgis_sdk.http import QgisSdkHttpError

    try:
        port = server.port
    except QgisSdkHttpError:
        return False
    return port > 0


def test_a_close_delivers_the_reload_reply_before_severing_the_socket(tmp_path: Path):
    """A withdrawn caller must still receive its 503, not a reset connection.

    The close wakes the caller out of the queue, and that reply has to travel
    over a socket the same close is about to shut down; the handler is held in
    the action until the close is already waiting, so only an ordered close can
    deliver it.
    """
    from qgis_sdk.http import PluginHttpServer

    app = QgisSdkPlugin(id="reload_reply", title="Reload reply")
    entered = threading.Event()
    release = threading.Event()

    @app.action(id="hold", title="Hold")
    def hold(ctx: PluginContext) -> str:
        entered.set()
        assert release.wait(10), "the test must release the action"
        return "held"

    runtime = _runtime(app)
    responses = []
    errors = []
    closers = []
    client = None
    try:
        server = PluginHttpServer(
            runtime,
            post=lambda callback: callback(),
            token_file=tmp_path / "token",
            actions=("hold",),
            deadline=10,
            close_grace=10,
        )
        server.start()
        token = (tmp_path / "token").read_text().strip()

        def caller():
            try:
                responses.append(_call(server.port, token, "hold", {}))
            except BaseException as error:  # noqa: BLE001 - relay to the test
                errors.append(error)

        client = threading.Thread(target=caller, daemon=True)
        client.start()
        assert entered.wait(10), "the action never started"

        closers.append(threading.Thread(target=server.close, daemon=True))
        closers[0].start()
        # ``port`` refuses once the close has begun; give the close time to
        # reach the point where it would sever the connections, so only an
        # ordered close can still deliver the reply after the release.
        deadline = time.monotonic() + 10
        while _port_is_open(server):
            assert time.monotonic() < deadline, "the close never started"
            time.sleep(0.01)
        # Longer than serve_forever's poll, so an unordered close has already
        # shut the connections down by now and an ordered one has not.
        time.sleep(1.5)
        released_at = time.monotonic()
        release.set()

        client.join(timeout=10)
        assert not client.is_alive()
        assert not errors, f"the client lost its reply: {errors!r}"
        status, payload = responses[0]
        assert status == 503
        assert json.loads(payload)["error"]["code"] == "host_reloaded"
        assert time.monotonic() - released_at < 5, "the reply came late, not ordered"
    finally:
        release.set()
        for thread in closers:
            thread.join(timeout=10)
        if client is not None:
            client.join(timeout=5)
        runtime.unload()


def test_a_hung_handler_cannot_hold_a_close_open(tmp_path: Path):
    """The grace is bounded: a close returns even if an action never finishes."""
    from qgis_sdk.http import PluginHttpServer

    app = QgisSdkPlugin(id="hung_close", title="Hung close")
    entered = threading.Event()
    stuck = threading.Event()

    @app.action(id="never", title="Never")
    def never(ctx: PluginContext) -> str:
        entered.set()
        assert stuck.wait(30), "the test released the stuck action"
        return "late"

    runtime = _runtime(app)
    errors = []
    client = None
    try:
        server = PluginHttpServer(
            runtime,
            post=lambda callback: callback(),
            token_file=tmp_path / "token",
            actions=("never",),
            deadline=10,
            close_grace=0.2,
        )
        server.start()
        token = (tmp_path / "token").read_text().strip()

        def caller():
            try:
                _call(server.port, token, "never", {})
            except BaseException as error:  # noqa: BLE001 - the socket is cut
                errors.append(error)

        client = threading.Thread(target=caller, daemon=True)
        client.start()
        assert entered.wait(10), "the action never started"

        started = time.monotonic()
        server.close()
        elapsed = time.monotonic() - started
        assert elapsed < 5, f"a close waited {elapsed:.1f}s for a stuck handler"
        client.join(timeout=10)
        assert not client.is_alive()
        assert errors, "a severed reply must surface as a client error"
    finally:
        stuck.set()
        if client is not None:
            client.join(timeout=5)
        runtime.unload()

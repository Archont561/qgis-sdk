"""The explicitly hosted plugin HTTP interface, exercised over loopback."""

from __future__ import annotations

import http.client
import json
import os
import stat
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from qgis_sdk import QgisSdkPlugin
from qgis_sdk.core import PluginContext, PluginRuntime, ResourceScope
from qgis_sdk.testing import RecordingNotifications

pytestmark = pytest.mark.skipif(
    os.name != "posix", reason="private token requires POSIX"
)


def request(port, method, path, *, token=None, origin=None, body=None, host=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
    headers = {}
    if token is not None:
        headers["Authorization"] = "Bearer " + token
    if origin is not None:
        headers["Origin"] = origin
    if host is not None:
        headers["Host"] = host
    data = None if body is None else json.dumps(body)
    if data is not None:
        headers["Content-Type"] = "application/json"
    try:
        connection.request(method, path, body=data, headers=headers)
        response = connection.getresponse()
        return response.status, response.read()
    finally:
        connection.close()


def test_rest_lists_only_selected_actions_and_calls_them(tmp_path: Path):
    from qgis_sdk.http import PluginHttpServer

    app = QgisSdkPlugin(id="rest_test", title="REST test")

    @app.action(id="echo", title="Echo")
    def echo(ctx: PluginContext, value: str) -> str:
        return value

    @app.action(id="private", title="Private")
    def private(ctx: PluginContext) -> str:
        return "secret"

    scope = ResourceScope()
    runtime = PluginRuntime(
        app, PluginContext(scope=scope, notifications=RecordingNotifications(scope))
    )
    runtime.start()
    token_file = tmp_path / "token"
    try:
        with PluginHttpServer(
            runtime,
            post=lambda callback: callback(),
            token_file=token_file,
            actions=("echo",),
        ) as server:
            token = token_file.read_text().strip()
            assert request(server.port, "GET", "/plugin")[0] == 401
            assert request(server.port, "GET", "/plugin", token="wrong")[0] == 401
            assert (
                request(
                    server.port,
                    "GET",
                    "/plugin",
                    token=token,
                    origin="https://evil.example",
                )[0]
                == 403
            )
            assert request(server.port, "POST", "/sessions", token=token)[0] == 404
            status, body = request(server.port, "GET", "/plugin", token=token)
            assert status == 200
            assert [entry["id"] for entry in json.loads(body)["actions"]] == ["echo"]
            status, body = request(
                server.port,
                "POST",
                "/actions/echo",
                token=token,
                body={"value": "hello"},
            )
            assert status == 200
            assert json.loads(body) == {"value": "hello"}
            status, _ = request(
                server.port, "POST", "/actions/private", token=token, body={}
            )
            assert status == 404
    finally:
        runtime.unload()


def test_rest_stream_sends_ordered_events_and_closes(tmp_path: Path):
    import http.client

    from qgis_sdk.http import PluginHttpServer

    app = QgisSdkPlugin(id="rest_stream", title="REST stream")

    @app.stream(id="ticks", title="Ticks", events={"data": int})
    def ticks(ctx: PluginContext, start: int) -> Iterator[dict]:
        yield {"kind": "data", "payload": start}
        yield {"kind": "data", "payload": start + 1}

    scope = ResourceScope()
    runtime = PluginRuntime(
        app, PluginContext(scope=scope, notifications=RecordingNotifications(scope))
    )
    runtime.start()
    token_file = tmp_path / "token"
    try:
        with PluginHttpServer(
            runtime,
            post=lambda callback: callback(),
            token_file=token_file,
            actions=("ticks",),
        ) as server:
            token = token_file.read_text().strip()
            conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=3)
            try:
                conn.request(
                    "POST",
                    "/streams/ticks",
                    body='{"start": 3}',
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                )
                response = conn.getresponse()
                assert response.status == 200
                assert response.getheader("Content-Type") == "text/event-stream"
                frames = []
                for _ in range(3):
                    line = response.readline().decode().strip()
                    assert line.startswith("data: ")
                    frames.append(json.loads(line.removeprefix("data: ")))
                    assert response.readline() == b"\n"
                assert [f["seq"] for f in frames] == [0, 1, 2]
                assert [f["event"]["payload"] for f in frames[:2]] == [3, 4]
                assert frames[-1]["terminal"]["kind"] == "complete"
            finally:
                conn.close()
    finally:
        runtime.unload()


def test_python_client_and_cli_can_call_a_running_plugin(tmp_path: Path):
    import subprocess
    import sys

    from qgis_sdk.http import PluginHttpServer
    from qgis_sdk_tools.rest import PluginClient, PluginClientError

    app = QgisSdkPlugin(id="client_test", title="Client test")

    @app.action(id="echo", title="Echo")
    def echo(ctx: PluginContext, value: str) -> str:
        return value

    @app.stream(id="ticks", title="Ticks", events={"data": int})
    def ticks(ctx: PluginContext) -> Iterator[dict]:
        yield {"kind": "data", "payload": 7}

    scope = ResourceScope()
    runtime = PluginRuntime(
        app, PluginContext(scope=scope, notifications=RecordingNotifications(scope))
    )
    runtime.start()
    token_file = tmp_path / "token"
    try:
        with PluginHttpServer(
            runtime,
            post=lambda callback: callback(),
            token_file=token_file,
            actions=("echo", "ticks"),
        ) as server:
            url = f"http://127.0.0.1:{server.port}"
            client = PluginClient(url, token_file=token_file)
            assert client.describe()["actions"][0]["id"] == "echo"
            assert client.call("echo", {"value": "python"}) == "python"
            frames = list(client.stream("ticks", {}))
            assert frames[0]["event"]["payload"] == 7
            assert frames[-1]["terminal"]["kind"] == "complete"
            with pytest.raises(PluginClientError):
                PluginClient("http://example.com:1234", token_file=token_file)
            with pytest.raises(PluginClientError):
                client.call("echo", {})
            command = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "qgis_sdk_tools",
                    "plugin",
                    "call",
                    "echo",
                    "--url",
                    url,
                    "--token-file",
                    str(token_file),
                    "--args",
                    '{"value":"cli"}',
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            assert command.returncode == 0, command.stderr
            assert json.loads(command.stdout) == "cli"
    finally:
        runtime.unload()


def test_closing_the_client_stream_disposes_its_generator(tmp_path: Path):
    import threading

    from qgis_sdk.http import PluginHttpServer
    from qgis_sdk_tools.rest import PluginClient

    closed = threading.Event()
    app = QgisSdkPlugin(id="rest_close", title="REST close")

    @app.stream(id="watch", title="Watch", events={"data": int})
    def watch(ctx: PluginContext) -> Iterator[dict]:
        try:
            while True:
                yield {"kind": "data", "payload": 1}
        finally:
            closed.set()

    scope = ResourceScope()
    runtime = PluginRuntime(
        app, PluginContext(scope=scope, notifications=RecordingNotifications(scope))
    )
    runtime.start()
    token_file = tmp_path / "token"
    try:
        with PluginHttpServer(
            runtime,
            post=lambda callback: callback(),
            token_file=token_file,
            actions=("watch",),
        ) as server:
            client = PluginClient(
                f"http://127.0.0.1:{server.port}", token_file=token_file
            )
            stream = client.stream("watch", {})
            assert next(stream)["event"]["payload"] == 1
            stream.close()
            assert closed.wait(5), "server did not dispose disconnected stream"
    finally:
        runtime.unload()


def test_runtime_has_no_agent_module():
    import importlib.util

    assert importlib.util.find_spec("qgis_sdk.agent") is None


def _echo_app(name: str = "rest_security"):
    app = QgisSdkPlugin(id=name, title=name)

    @app.action(id="echo", title="Echo")
    def echo(ctx: PluginContext, value: str) -> str:
        return value

    return app


def _started(app):
    scope = ResourceScope()
    runtime = PluginRuntime(
        app, PluginContext(scope=scope, notifications=RecordingNotifications(scope))
    )
    runtime.start()
    return runtime


def test_token_is_private_and_removed_when_the_server_closes(tmp_path: Path):
    from qgis_sdk.http import PluginHttpServer

    runtime = _started(_echo_app())
    token_file = tmp_path / "plugin.token"
    try:
        with PluginHttpServer(
            runtime,
            post=lambda callback: callback(),
            token_file=token_file,
            actions=("echo",),
        ) as server:
            assert stat.S_IMODE(token_file.stat().st_mode) == 0o600
            assert len(token_file.read_text().strip()) >= 32
            assert request(server.port, "POST", "/actions/echo", body={})[0] == 401
    finally:
        runtime.unload()
    assert not token_file.exists()


def test_rejects_untrusted_host_header_and_non_loopback_bind(tmp_path: Path):
    from qgis_sdk.http import PluginHttpServer, QgisSdkHttpError

    runtime = _started(_echo_app())
    try:
        with pytest.raises(QgisSdkHttpError, match="127.0.0.1"):
            PluginHttpServer(
                runtime,
                post=lambda callback: callback(),
                token_file=tmp_path / "bad",
                host="0.0.0.0",
            )
        with PluginHttpServer(
            runtime,
            post=lambda callback: callback(),
            token_file=tmp_path / "token",
            actions=("echo",),
        ) as server:
            token = (tmp_path / "token").read_text().strip()
            status, _ = request(
                server.port,
                "GET",
                "/plugin",
                token=token,
                host="evil.example",
            )
            assert status == 403
    finally:
        runtime.unload()


def test_only_one_endpoint_per_runtime_and_a_closed_one_cannot_restart(
    tmp_path: Path,
):
    from qgis_sdk.http import PluginHttpServer, QgisSdkHttpError

    runtime = _started(_echo_app())
    try:
        first = PluginHttpServer(
            runtime,
            post=lambda callback: callback(),
            token_file=tmp_path / "one",
            actions=("echo",),
        )
        first.start()
        with (
            pytest.raises(QgisSdkHttpError, match="already"),
            PluginHttpServer(
                runtime,
                post=lambda callback: callback(),
                token_file=tmp_path / "two",
                actions=("echo",),
            ),
        ):
            pass
        assert not (tmp_path / "two").exists()
        first.close()
        with pytest.raises(QgisSdkHttpError):
            first.start()
        assert not (tmp_path / "one").exists()
        with PluginHttpServer(
            runtime,
            post=lambda callback: callback(),
            token_file=tmp_path / "again",
            actions=("echo",),
        ):
            pass
    finally:
        runtime.unload()


def test_failed_start_releases_the_runtime_reservation(tmp_path: Path):
    from qgis_sdk.http import PluginHttpServer

    runtime = _started(_echo_app())
    occupied = tmp_path / "occupied"
    occupied.write_text("keep")
    try:
        with pytest.raises(FileExistsError):
            PluginHttpServer(
                runtime,
                post=lambda callback: callback(),
                token_file=occupied,
                actions=("echo",),
            ).start()
        assert occupied.read_text() == "keep"
        with PluginHttpServer(
            runtime,
            post=lambda callback: callback(),
            token_file=tmp_path / "new",
            actions=("echo",),
        ):
            pass
    finally:
        runtime.unload()


def test_constructing_the_server_neither_listens_nor_creates_a_token(tmp_path: Path):
    from qgis_sdk.http import PluginHttpServer, QgisSdkHttpError

    runtime = _started(_echo_app())
    token_file = tmp_path / "token"
    try:
        server = PluginHttpServer(
            runtime,
            post=lambda callback: callback(),
            token_file=token_file,
            actions=("echo",),
        )
        assert not token_file.exists()
        with pytest.raises(QgisSdkHttpError):
            _ = server.port
        server.close()
    finally:
        runtime.unload()


def test_busy_deadline_withdraws_a_queued_call_before_it_runs(tmp_path: Path):
    from qgis_sdk.http import PluginHttpServer

    seen = []
    app = QgisSdkPlugin(id="rest_deadline", title="Deadline")

    @app.action(id="echo", title="Echo")
    def echo(ctx: PluginContext, value: str) -> str:
        seen.append(value)
        return value

    runtime = _started(app)
    queued = []
    submitted = threading.Event()

    def post(callback):
        queued.append(callback)
        submitted.set()

    server = PluginHttpServer(
        runtime,
        post=post,
        token_file=tmp_path / "token",
        actions=("echo",),
        deadline=0.2,
    )
    server.start()
    try:
        token = (tmp_path / "token").read_text().strip()
        status, body = request(
            server.port, "POST", "/actions/echo", token=token, body={"value": "late"}
        )
        assert status == 503
        assert json.loads(body)["error"]["code"] == "host_busy"
        assert submitted.is_set()
        queued.pop()()
        assert seen == []
    finally:
        runtime.unload()
        server.close()


def test_unload_withdraws_a_queued_request_and_reports_reload(tmp_path: Path):
    from qgis_sdk.http import PluginHttpServer

    seen = []
    app = QgisSdkPlugin(id="rest_reload", title="Reload")

    @app.action(id="echo", title="Echo")
    def echo(ctx: PluginContext, value: str) -> str:
        seen.append(value)
        return value

    scope = ResourceScope()
    runtime = PluginRuntime(
        app, PluginContext(scope=scope, notifications=RecordingNotifications(scope))
    )
    runtime.start()
    queued = []
    submitted = threading.Event()
    stall = False

    def post(callback):
        if stall:
            queued.append(callback)
            submitted.set()
        else:
            callback()

    server = PluginHttpServer(
        runtime,
        post=post,
        token_file=tmp_path / "token",
        actions=("echo",),
        # Long enough that only the reload, never the deadline, can end this call.
        deadline=60,
    )
    server.start()
    token = (tmp_path / "token").read_text().strip()
    port = server.port
    stall = True
    responses = []
    thread = threading.Thread(
        target=lambda: responses.append(
            request(
                port, "POST", "/actions/echo", token=token, body={"value": "unsafe"}
            )
        )
    )
    thread.start()
    assert submitted.wait(2)
    runtime.unload()
    thread.join(timeout=3)
    assert not thread.is_alive()
    assert responses[0][0] == 503
    assert json.loads(responses[0][1])["error"]["code"] == "host_reloaded"
    assert not (tmp_path / "token").exists()
    queued.pop()()
    assert seen == []
    server.close()

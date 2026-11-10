"""The explicitly hosted plugin HTTP interface, exercised over loopback."""

from __future__ import annotations

import contextlib
import http.client
import json
import os
import stat
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from qgis_sdk import QgisSdkPlugin
from qgis_sdk.core import PluginContext, PluginRuntime, ResourceScope
from qgis_sdk.testing import RecordingNotifications

pytestmark = pytest.mark.skipif(
    os.name != "posix", reason="private token requires POSIX"
)


@dataclass(frozen=True, slots=True)
class _Request:
    """One loopback HTTP request, including its optional headers and JSON body."""

    port: int
    method: str
    path: str
    token: str | None = None
    origin: str | None = None
    body: object | None = None
    host: str | None = None


def request(req: _Request):
    connection = http.client.HTTPConnection("127.0.0.1", req.port, timeout=3)
    headers = {}
    if req.token is not None:
        headers["Authorization"] = "Bearer " + req.token
    if req.origin is not None:
        headers["Origin"] = req.origin
    if req.host is not None:
        headers["Host"] = req.host
    data = None if req.body is None else json.dumps(req.body)
    if data is not None:
        headers["Content-Type"] = "application/json"
    try:
        connection.request(req.method, req.path, body=data, headers=headers)
        response = connection.getresponse()
        return response.status, response.read()
    finally:
        connection.close()


@dataclass(frozen=True, slots=True)
class _ServerOptions:
    """How one loopback plugin server is wired for a test."""

    actions: tuple[str, ...] = ()
    post: Callable[[Callable[[], None]], None] | None = None
    token_name: str = "token"
    deadline: float = 10
    host: str = "127.0.0.1"


def _server(runtime, tmp_path, options=None):
    """One server over an already started runtime, with the test defaults."""
    from qgis_sdk.http import PluginHttpServer

    options = options or _ServerOptions()
    return PluginHttpServer(
        runtime,
        post=options.post or (lambda callback: callback()),
        token_file=tmp_path / options.token_name,
        actions=options.actions,
        host=options.host,
        deadline=options.deadline,
    )


@contextlib.contextmanager
def _serving(app, tmp_path, options=None):
    """Start a plugin, serve it over loopback, then close and unload it."""
    options = options or _ServerOptions()
    runtime = _started(app)
    token_file = tmp_path / options.token_name
    try:
        with _server(runtime, tmp_path, options) as server:
            yield server, token_file
    finally:
        runtime.unload()


def _selected_actions_app():
    app = QgisSdkPlugin(id="rest_test", title="REST test")

    @app.action(id="echo", title="Echo")
    def echo(ctx: PluginContext, value: str) -> str:
        return value

    @app.action(id="private", title="Private")
    def private(ctx: PluginContext) -> str:
        return "secret"

    return app


def _assert_selected_description(server, token):
    assert request(_Request(server.port, "GET", "/plugin"))[0] == 401
    assert request(_Request(server.port, "GET", "/plugin", token="wrong"))[0] == 401
    assert (
        request(
            _Request(
                server.port,
                "GET",
                "/plugin",
                token=token,
                origin="https://evil.example",
            )
        )[0]
        == 403
    )
    assert request(_Request(server.port, "POST", "/sessions", token=token))[0] == 404
    status, body = request(_Request(server.port, "GET", "/plugin", token=token))
    assert status == 200
    assert [entry["id"] for entry in json.loads(body)["actions"]] == ["echo"]


def _assert_selected_calls(server, token):
    status, body = request(
        _Request(
            server.port,
            "POST",
            "/actions/echo",
            token=token,
            body={"value": "hello"},
        )
    )
    assert status == 200
    assert json.loads(body) == {"value": "hello"}
    status, _ = request(
        _Request(server.port, "POST", "/actions/private", token=token, body={})
    )
    assert status == 404


def _assert_selected_actions(server, token):
    _assert_selected_description(server, token)
    _assert_selected_calls(server, token)


def _finite_stream_app():
    app = QgisSdkPlugin(id="rest_stream", title="REST stream")

    @app.stream(id="ticks", title="Ticks", events={"data": int})
    def ticks(ctx: PluginContext, start: int) -> Iterator[dict]:
        yield {"kind": "data", "payload": start}
        yield {"kind": "data", "payload": start + 1}

    return app


def _read_frames(response, count=3):
    frames = []
    for _ in range(count):
        line = response.readline().decode().strip()
        assert line.startswith("data: ")
        frames.append(json.loads(line.removeprefix("data: ")))
        assert response.readline() == b"\n"
    return frames


def _assert_ordered_stream(port, token):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
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
        frames = _read_frames(response)
    finally:
        conn.close()
    assert [frame["seq"] for frame in frames] == [0, 1, 2]
    assert [frame["event"]["payload"] for frame in frames[:2]] == [3, 4]
    assert frames[-1]["terminal"]["kind"] == "complete"


def _client_app():
    app = QgisSdkPlugin(id="client_test", title="Client test")

    @app.action(id="echo", title="Echo")
    def echo(ctx: PluginContext, value: str) -> str:
        return value

    @app.stream(id="ticks", title="Ticks", events={"data": int})
    def ticks(ctx: PluginContext) -> Iterator[dict]:
        yield {"kind": "data", "payload": 7}

    return app


def _assert_python_client(url, token_file):
    from qgis_sdk_tools.rest import PluginClient, PluginClientError

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


def _call_cli(url, token_file, args):
    import subprocess
    import sys

    return subprocess.run(
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
            args,
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def _closing_stream_app(closed):
    app = QgisSdkPlugin(id="rest_close", title="REST close")

    @app.stream(id="watch", title="Watch", events={"data": int})
    def watch(ctx: PluginContext) -> Iterator[dict]:
        try:
            while True:
                yield {"kind": "data", "payload": 1}
        finally:
            closed.set()

    return app


def _recording_app(seen, name):
    app = QgisSdkPlugin(id=name, title=name)

    @app.action(id="echo", title="Echo")
    def echo(ctx: PluginContext, value: str) -> str:
        seen.append(value)
        return value

    return app


class _PostProbe:
    """An owner-thread post that can hold callbacks instead of running them."""

    def __init__(self, *, stall=False):
        self.callbacks = []
        self.submitted = threading.Event()
        self.stall = stall

    def __call__(self, callback):
        if self.stall:
            self.callbacks.append(callback)
            self.submitted.set()
        else:
            callback()


def _assert_single_endpoint(runtime, tmp_path):
    from qgis_sdk.http import QgisSdkHttpError

    first = _server(
        runtime, tmp_path, _ServerOptions(actions=("echo",), token_name="one")
    )
    first.start()
    with (
        pytest.raises(QgisSdkHttpError, match="already"),
        _server(runtime, tmp_path, _ServerOptions(actions=("echo",), token_name="two")),
    ):
        pass
    assert not (tmp_path / "two").exists()
    first.close()
    with pytest.raises(QgisSdkHttpError):
        first.start()
    assert not (tmp_path / "one").exists()
    with _server(
        runtime, tmp_path, _ServerOptions(actions=("echo",), token_name="again")
    ):
        pass


def _request_in_thread(req, *, daemon=False):
    responses = []
    thread = threading.Thread(
        target=lambda req=req: responses.append(request(req)), daemon=daemon
    )
    thread.start()
    return thread, responses


class _QueueProbe:
    """Hold one action, queue another, then release both in order."""

    def __init__(self, tmp_path):
        self.entered = threading.Event()
        self.released = threading.Event()
        self.responses = []
        self.holders = []
        self.runtime = _started(self._app())
        self.server = _server(
            self.runtime,
            tmp_path,
            _ServerOptions(actions=("hold", "after"), deadline=10),
        )
        self.server.start()
        self.token = (tmp_path / "token").read_text().strip()

    def _app(self):
        app = QgisSdkPlugin(id="rest_pending", title="REST pending")

        @app.action(id="hold", title="Hold")
        def hold(ctx: PluginContext) -> str:
            self.entered.set()
            assert self.released.wait(10)
            return "released"

        @app.action(id="after", title="After")
        def after(ctx: PluginContext) -> str:
            return "after"

        return app

    def start(self, action):
        req = _Request(
            self.server.port,
            "POST",
            f"/actions/{action}",
            token=self.token,
            body={},
        )
        holder = threading.Thread(
            target=lambda req=req: self.responses.append(request(req)), daemon=True
        )
        self.holders.append(holder)
        holder.start()

    def assert_transitions(self):
        assert self.server.pending_requests == 0
        assert self.server.busy is False
        self.start("hold")
        assert self.entered.wait(10)
        assert self.server.busy is True
        self.start("after")
        self._wait_for_pending()
        assert self.server.pending_requests == 1, "the second call never queued"
        assert self.responses == [], "queued work must not run inside the first call"
        self.released.set()
        self._join_holders()
        assert [status for status, _ in self.responses] == [200, 200]
        assert self.server.pending_requests == 0
        assert self.server.busy is False

    def _wait_for_pending(self):
        deadline = time.monotonic() + 10
        while self.server.pending_requests == 0 and time.monotonic() < deadline:
            time.sleep(0.01)

    def _join_holders(self):
        for thread in self.holders:
            thread.join(timeout=10)
        assert not any(thread.is_alive() for thread in self.holders)

    def close(self):
        try:
            self.server.close()
        finally:
            for thread in self.holders:
                thread.join(timeout=1)
            self.runtime.unload()


def test_rest_lists_only_selected_actions_and_calls_them(tmp_path: Path):
    with _serving(
        _selected_actions_app(), tmp_path, _ServerOptions(actions=("echo",))
    ) as (server, token_file):
        _assert_selected_actions(server, token_file.read_text().strip())


def test_rest_stream_sends_ordered_events_and_closes(tmp_path: Path):
    with _serving(
        _finite_stream_app(), tmp_path, _ServerOptions(actions=("ticks",))
    ) as (server, token_file):
        _assert_ordered_stream(server.port, token_file.read_text().strip())


def test_python_client_and_cli_can_call_a_running_plugin(tmp_path: Path):
    with _serving(
        _client_app(), tmp_path, _ServerOptions(actions=("echo", "ticks"))
    ) as (server, token_file):
        url = f"http://127.0.0.1:{server.port}"
        _assert_python_client(url, token_file)
        command = _call_cli(url, token_file, '{"value":"cli"}')
        assert command.returncode == 0, command.stderr
        assert json.loads(command.stdout) == "cli"


def test_closing_the_client_stream_disposes_its_generator(tmp_path: Path):
    from qgis_sdk_tools.rest import PluginClient

    closed = threading.Event()
    with _serving(
        _closing_stream_app(closed), tmp_path, _ServerOptions(actions=("watch",))
    ) as (server, token_file):
        client = PluginClient(f"http://127.0.0.1:{server.port}", token_file=token_file)
        stream = client.stream("watch", {})
        assert next(stream)["event"]["payload"] == 1
        stream.close()
        assert closed.wait(5), "server did not dispose disconnected stream"


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
    runtime = PluginRuntime(app, PluginContext(RecordingNotifications(scope), scope))
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
            assert (
                request(_Request(server.port, "POST", "/actions/echo", body={}))[0]
                == 401
            )
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
                _Request(
                    server.port, "GET", "/plugin", token=token, host="evil.example"
                )
            )
            assert status == 403
    finally:
        runtime.unload()


def test_only_one_endpoint_per_runtime_and_a_closed_one_cannot_restart(
    tmp_path: Path,
):
    runtime = _started(_echo_app())
    try:
        _assert_single_endpoint(runtime, tmp_path)
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
    seen = []
    post = _PostProbe(stall=True)
    with _serving(
        _recording_app(seen, "rest_deadline"),
        tmp_path,
        _ServerOptions(actions=("echo",), post=post, deadline=0.2),
    ) as (server, token_file):
        token = token_file.read_text().strip()
        status, body = request(
            _Request(
                server.port,
                "POST",
                "/actions/echo",
                token=token,
                body={"value": "late"},
            )
        )
        assert status == 503
        assert json.loads(body)["error"]["code"] == "host_busy"
        assert post.submitted.is_set()
        post.callbacks.pop()()
        assert seen == []


def test_unload_withdraws_a_queued_request_and_reports_reload(tmp_path: Path):
    seen = []
    runtime = _started(_recording_app(seen, "rest_reload"))
    post = _PostProbe()
    server = _server(
        runtime,
        tmp_path,
        _ServerOptions(actions=("echo",), post=post, deadline=60),
    )
    server.start()
    token = (tmp_path / "token").read_text().strip()
    port = server.port
    post.stall = True
    thread, responses = _request_in_thread(
        _Request(port, "POST", "/actions/echo", token=token, body={"value": "unsafe"})
    )
    assert post.submitted.wait(2)
    runtime.unload()
    thread.join(timeout=3)
    assert not thread.is_alive()
    assert responses[0][0] == 503
    assert json.loads(responses[0][1])["error"]["code"] == "host_reloaded"
    assert not (tmp_path / "token").exists()
    # Every callback the stalled host was holding: a withdrawn request must
    # never reach the action once the runtime is gone.
    for callback in post.callbacks:
        callback()
    assert seen == []
    server.close()


def test_pending_requests_and_busy_expose_queue_state(tmp_path: Path):
    """The dispatch state is readable without touching private queue internals."""
    probe = _QueueProbe(tmp_path)
    try:
        probe.assert_transitions()
    finally:
        probe.close()


@contextlib.contextmanager
def _stub_response(payload: bytes):
    """Serve one fixed JSON body from a throwaway loopback listener."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_POST(self) -> None:
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_a_response_without_a_value_is_a_client_error(tmp_path: Path):
    """A 200 body that omits the value must not escape as a bare KeyError."""
    from qgis_sdk_tools.rest import PluginClient, PluginClientError

    token_file = tmp_path / "token"
    token_file.write_text("x" * 32, encoding="ascii")
    with _stub_response(b'{"ok": true}') as url:
        client = PluginClient(url, token_file=token_file)
        with pytest.raises(PluginClientError, match="no value"):
            client.call("echo", {"value": "unused"})


def test_an_oversized_response_names_the_bound(tmp_path: Path):
    """An oversized body is reported as too large, not as broken JSON."""
    from qgis_sdk_tools.rest import PluginClient, PluginClientError

    token_file = tmp_path / "token"
    token_file.write_text("x" * 32, encoding="ascii")
    payload = json.dumps({"value": "x" * (2 * 1024 * 1024)}).encode()
    with _stub_response(payload) as url:
        client = PluginClient(url, token_file=token_file)
        with pytest.raises(PluginClientError, match="exceeds 1048576 bytes"):
            client.call("echo", {})


def test_a_response_exactly_at_the_bound_still_parses(tmp_path: Path):
    """The bound rejects only bodies that actually exceed it."""
    from qgis_sdk_tools.rest import PluginClient

    token_file = tmp_path / "token"
    token_file.write_text("x" * 32, encoding="ascii")
    filler = 1024 * 1024 - len('{"value": ""}')
    payload = json.dumps({"value": "x" * filler}).encode()
    assert len(payload) == 1024 * 1024
    with _stub_response(payload) as url:
        client = PluginClient(url, token_file=token_file)
        assert client.call("echo", {}) == "x" * filler

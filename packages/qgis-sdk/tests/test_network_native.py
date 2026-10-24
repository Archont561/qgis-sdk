"""``NativeNetworkTransport`` against loopback servers (TASK-5, acceptance criterion 3).

The QGIS-free suite pins the client, the response model and the fake; this file
proves the native transport does what the decision-4 contract says on a real
``QgsNetworkAccessManager``: requests suspend the job instead of the GUI thread,
timeouts and cancellations are told apart, redirects are followed here with
credentials dropped at an origin change, the body ceiling aborts the download,
and the QGIS proxy / authentication / certificate configuration is honoured.

Every server is a loopback ``http.server`` started per module; nothing here
contacts the internet. The imports are guarded like ``test_ui_native.py`` so a
machine without QGIS reports what it lacks instead of failing collection.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import ssl
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_BINDINGS = Path(sys.prefix) / "share" / "qgis" / "python"
if _BINDINGS.is_dir() and str(_BINDINGS) not in sys.path:
    sys.path.insert(0, str(_BINDINGS))
os.environ.setdefault("QGIS_PREFIX_PATH", sys.prefix)
os.environ.setdefault("PROJ_LIB", str(Path(sys.prefix) / "share" / "proj"))
# The authentication tests set a master password, which must never touch a
# developer's real auth database: point QGIS at a throwaway one before any
# module in the session starts the application.
_AUTH_DIR = os.environ.setdefault(
    "QGIS_AUTH_DB_DIR_PATH", tempfile.mkdtemp(prefix="qgis-sdk-auth-")
)

try:
    from PyQt6.QtCore import QCoreApplication, QRunnable, QThread, QThreadPool
    from PyQt6.QtWidgets import QApplication
    from qgis.core import QgsApplication, QgsAuthMethodConfig, QgsNetworkAccessManager
    from qgis_sdk.adapters.qgis import NativeNetworkTransport
    from qgis_sdk.core import ResourceScope
    from qgis_sdk.core.scheduling import Job, JobState, StepScheduler
    from qgis_sdk.models import (
        Headers,
        NetworkRequest,
        QgisSdkAuthenticationError,
        QgisSdkBlockingOnGuiThreadError,
        QgisSdkConnectionError,
        QgisSdkRedirectError,
        QgisSdkRequestTimeoutError,
        QgisSdkResponseTooLargeError,
        QgisSdkTlsError,
        Response,
    )
    from qgis_sdk.network import NetworkClient, NetworkGrant
except ImportError as error:  # pragma: no cover - depends on the host
    pytest.skip(
        f"native networking needs Qt and QGIS: {error}", allow_module_level=True
    )

BASIC_USER = "alice"
BASIC_PASSWORD = "wonder"
_BASIC_TOKEN = base64.b64encode(f"{BASIC_USER}:{BASIC_PASSWORD}".encode()).decode()
DEADLINE_SECONDS = 10.0


# -- loopback servers --------------------------------------------------------------


class _Handler(BaseHTTPRequestHandler):
    """One handler for every route the tests need; the server records requests."""

    protocol_version = "HTTP/1.1"
    server: _Server

    def log_message(self, format: str, *args: object) -> None:
        pass

    def _seen(self, body: bytes) -> dict[str, object]:
        record = {
            "method": self.command,
            "path": self.path,
            "headers": {name.lower(): value for name, value in self.headers.items()},
            "body": body.decode("utf-8", "replace"),
        }
        self.server.seen.append(record)
        return record

    def _reply(
        self,
        status: int,
        body: bytes = b"",
        *,
        content_type: str = "application/json",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status: int, payload: object, **headers: str) -> None:
        self._reply(status, json.dumps(payload).encode(), headers=headers)

    def do_GET(self) -> None:
        self._handle(b"")

    def do_HEAD(self) -> None:
        self._handle(b"")

    def do_POST(self) -> None:
        self._handle(self._read_body())

    def do_PUT(self) -> None:
        self._handle(self._read_body())

    def do_PATCH(self) -> None:
        self._handle(self._read_body())

    def do_DELETE(self) -> None:
        self._handle(b"")

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length) if length else b""

    def _handle(self, body: bytes) -> None:
        record = self._seen(body)
        parts = urlsplit(self.path)
        query = {key: values[-1] for key, values in parse_qs(parts.query).items()}
        route = parts.path
        if route == "/json":
            self._json(200, {"hello": "world"}, **{"X-Server": self.server.label})
        elif route == "/echo":
            self._json(200, record)
        elif route.startswith("/status/"):
            self._reply(
                int(route.rsplit("/", 1)[1]), b"status body", content_type="text/plain"
            )
        elif route.startswith("/redirect/"):
            remaining = int(route.rsplit("/", 1)[1])
            if remaining == 0:
                self._json(200, {"hops": "done"})
            else:
                self._reply(302, headers={"Location": f"/redirect/{remaining - 1}"})
        elif route == "/to":
            self._reply(
                int(query.get("code", "302")), headers={"Location": query["url"]}
            )
        elif route == "/slow":
            time.sleep(int(query.get("ms", "1000")) / 1000)
            self._json(200, {"slow": True})
        elif route.startswith("/bytes/"):
            self._reply(
                200, b"x" * int(route.rsplit("/", 1)[1]), content_type="text/plain"
            )
        elif route == "/basic":
            if self.headers.get("Authorization") == f"Basic {_BASIC_TOKEN}":
                self._json(200, {"user": BASIC_USER})
            else:
                self._json(
                    401,
                    {"error": "unauthorised"},
                    **{"WWW-Authenticate": 'Basic realm="x"'},
                )
        elif route == "/secure":
            self._json(200, {"tls": True})
        else:
            self._reply(404, b"no such route", content_type="text/plain")


class _ProxyHandler(_Handler):
    """Answers every absolute-URI request itself, so reaching it proves the proxy."""

    def _handle(self, body: bytes) -> None:
        record = self._seen(body)
        self._json(200, {"via": "proxy", "target": record["path"]})


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def handle_error(self, request: object, client_address: object) -> None:
        """A client that aborted mid-body is the point of several tests, not noise."""

    def __init__(self, handler: type[BaseHTTPRequestHandler], label: str) -> None:
        super().__init__(("127.0.0.1", 0), handler)
        self.label = label
        self.seen: list[dict[str, object]] = []
        self.scheme = "http"

    @property
    def origin(self) -> str:
        return f"{self.scheme}://127.0.0.1:{self.server_port}"

    def url(self, path: str) -> str:
        return self.origin + path

    def last(self) -> dict[str, object]:
        return self.seen[-1]


def _serve(server: _Server) -> Iterator[_Server]:
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.05}
    )
    thread.daemon = True
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture(scope="module")
def origin_a() -> Iterator[_Server]:
    yield from _serve(_Server(_Handler, "a"))


@pytest.fixture(scope="module")
def origin_b() -> Iterator[_Server]:
    yield from _serve(_Server(_Handler, "b"))


@pytest.fixture(scope="module")
def proxy() -> Iterator[_Server]:
    yield from _serve(_Server(_ProxyHandler, "proxy"))


@pytest.fixture(scope="module")
def tls_origin(tmp_path_factory: pytest.TempPathFactory) -> Iterator[_Server]:
    """A self-signed HTTPS origin, if ``openssl`` is around to mint the certificate."""
    openssl = shutil.which("openssl")
    if openssl is None:  # pragma: no cover - depends on the host
        pytest.skip("openssl is needed to mint a self-signed certificate")
    directory = tmp_path_factory.mktemp("tls")
    key, cert = directory / "key.pem", directory / "cert.pem"
    subprocess.run(
        [
            openssl,
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(key),
            "-out",
            str(cert),
            "-days",
            "2",
            "-subj",
            "/CN=127.0.0.1",
            "-addext",
            "subjectAltName=IP:127.0.0.1",
        ],
        check=True,
        capture_output=True,
    )
    server = _Server(_Handler, "tls")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    server.scheme = "https"
    server.certificate = cert  # type: ignore[attr-defined]
    yield from _serve(server)


# -- QGIS application and drivers ----------------------------------------------------


@pytest.fixture(scope="module")
def app():
    """One headless QGIS application; reuse whatever another module started."""
    existing = QApplication.instance()
    if existing is not None:
        return existing
    prefix = Path(sys.prefix)
    QgsApplication.setPrefixPath(str(prefix), True)
    application = QgsApplication([b"qgis-sdk-native-network"], True)
    application.initQgis()
    return application


@pytest.fixture()
def scope() -> Iterator[ResourceScope]:
    scope = ResourceScope()
    yield scope
    if not scope.closed:
        scope.close()


@pytest.fixture()
def client(app, scope: ResourceScope) -> NetworkClient:
    return NetworkClient(NativeNetworkTransport(scope), scope)


@pytest.fixture()
def scheduler(scope: ResourceScope) -> StepScheduler:
    return StepScheduler(scope)


def pump(app, until: Callable[[], bool], *, deadline: float = DEADLINE_SECONDS) -> None:
    """Spin the GUI event loop the way a host would, until ``until`` holds."""
    end = time.monotonic() + deadline
    while not until():
        if time.monotonic() > end:
            raise AssertionError("condition not met within the deadline")
        app.processEvents()
        time.sleep(0.002)


def run(app, scheduler: StepScheduler, coro) -> Job:
    """Submit a coroutine and tick the scheduler between event-loop turns."""
    job = scheduler.submit(coro)

    def advance() -> bool:
        scheduler.tick()
        return job.settled

    pump(app, advance)
    return job


def result(app, scheduler: StepScheduler, coro) -> Response:
    job = run(app, scheduler, coro)
    if job.error is not None:
        raise job.error
    assert isinstance(job.result, Response)
    return job.result


def failure(app, scheduler: StepScheduler, coro) -> BaseException:
    job = run(app, scheduler, coro)
    assert job.state is JobState.FAILED, job.state
    assert job.error is not None
    return job.error


# -- coroutine form ------------------------------------------------------------------


def test_a_get_suspends_the_job_and_delivers_a_buffered_response(
    app, scheduler, client, origin_a
) -> None:
    """The job waits on a handoff while Qt works; the result is a plain ``Response``."""
    states: list[JobState] = []

    async def fetch():
        return await client.get(origin_a.url("/json"), params={"q": "1"})

    job = scheduler.submit(fetch())

    def advance() -> bool:
        scheduler.tick()
        states.append(job.state)
        app.processEvents()
        return job.settled

    pump(app, advance)
    assert JobState.WAITING in states
    response = job.result
    assert isinstance(response, Response)
    assert response.status_code == 200
    assert response.reason == "OK"
    assert response.headers["x-server"] == "a"
    assert response.json() == {"hello": "world"}
    assert response.url.endswith("/json?q=1")
    assert origin_a.last()["path"] == "/json?q=1"
    assert client.in_flight == 0


def test_the_transport_delivers_on_the_thread_that_sent(app, scope, origin_a) -> None:
    transport = NativeNetworkTransport(scope)
    seen: list[tuple[object, object]] = []
    transport.send(
        NetworkRequest(method="GET", url=origin_a.url("/json")),
        lambda outcome: seen.append((outcome, QThread.currentThread())),
    )
    assert transport.in_flight == 1
    pump(app, lambda: bool(seen))
    outcome, thread = seen[0]
    assert isinstance(outcome, Response)
    assert thread is QCoreApplication.instance().thread()
    assert transport.in_flight == 0


def test_post_json_sends_the_encoded_body_and_content_type(
    app, scheduler, client, origin_a
) -> None:
    response = result(
        app,
        scheduler,
        client.post(
            origin_a.url("/echo"), json={"a": [1, 2]}, headers={"X-Trace": "t1"}
        ),
    )
    echoed = response.json()
    assert echoed["method"] == "POST"
    assert json.loads(echoed["body"]) == {"a": [1, 2]}
    assert echoed["headers"]["content-type"] == "application/json"
    assert echoed["headers"]["x-trace"] == "t1"


def test_other_methods_go_through_the_custom_request_path(
    app, scheduler, client, origin_a
) -> None:
    put = result(
        app, scheduler, client.request("PUT", origin_a.url("/echo"), data=b"raw")
    )
    assert put.json()["method"] == "PUT"
    assert put.json()["body"] == "raw"
    patch = result(
        app, scheduler, client.request("PATCH", origin_a.url("/echo"), data="p")
    )
    assert patch.json()["method"] == "PATCH"
    delete = result(app, scheduler, client.request("DELETE", origin_a.url("/echo")))
    assert delete.json()["method"] == "DELETE"
    head = result(app, scheduler, client.request("HEAD", origin_a.url("/json")))
    assert head.status_code == 200
    assert head.content == b""


def test_an_error_status_is_a_response_until_the_caller_raises(
    app, scheduler, client, origin_a
) -> None:
    response = result(app, scheduler, client.get(origin_a.url("/status/404")))
    assert response.status_code == 404
    assert not response.ok
    assert response.text == "status body"


def test_a_timeout_is_reported_as_a_timeout_within_budget(
    app, scheduler, client, origin_a
) -> None:
    started = time.monotonic()
    error = failure(
        app, scheduler, client.get(origin_a.url("/slow?ms=3000"), timeout=0.3)
    )
    elapsed = time.monotonic() - started
    assert isinstance(error, QgisSdkRequestTimeoutError)
    assert error.timeout_seconds == 0.3
    assert elapsed < 2.0, elapsed
    assert client.in_flight == 0


def test_cancelling_the_job_aborts_the_reply_and_settles_cancelled(
    app, scheduler, client, origin_a
) -> None:
    job = scheduler.submit(client.get(origin_a.url("/slow?ms=3000")))
    scheduler.tick()
    assert job.state is JobState.WAITING
    assert client.in_flight == 1
    started = time.monotonic()
    assert job.cancel()

    def advance() -> bool:
        scheduler.tick()
        return job.settled

    pump(app, advance)
    assert job.state is JobState.CANCELLED
    assert time.monotonic() - started < 2.0
    assert client.in_flight == 0


def test_closing_the_scope_aborts_what_is_in_flight(app, origin_a) -> None:
    scope = ResourceScope()
    transport = NativeNetworkTransport(scope)
    outcomes: list[object] = []
    transport.send(
        NetworkRequest(method="GET", url=origin_a.url("/slow?ms=3000")),
        outcomes.append,
    )
    scope.close()
    pump(app, lambda: bool(outcomes))
    assert transport.in_flight == 0
    assert type(outcomes[0]).__name__ == "QgisSdkRequestCancelledError"


def test_a_refused_connection_is_a_connection_error(app, scheduler, client) -> None:
    probe = _Server(_Handler, "closed")
    port = probe.server_port
    probe.server_close()
    error = failure(
        app, scheduler, client.get(f"http://127.0.0.1:{port}/json", timeout=5)
    )
    assert isinstance(error, QgisSdkConnectionError)


# -- redirects -----------------------------------------------------------------------


def test_redirects_are_followed_up_to_the_configured_limit(
    app, scheduler, client, origin_a
) -> None:
    response = result(app, scheduler, client.get(origin_a.url("/redirect/3")))
    assert response.status_code == 200
    assert response.json() == {"hops": "done"}
    assert response.url.endswith("/redirect/0")

    limited = client.configure(max_redirects=2)
    error = failure(app, scheduler, limited.get(origin_a.url("/redirect/3")))
    assert isinstance(error, QgisSdkRedirectError)
    assert "2 redirects" in str(error)


def test_a_cross_origin_redirect_drops_credentials_but_keeps_other_headers(
    app, scheduler, client, origin_a, origin_b
) -> None:
    """The measurement showed Qt forwards both headers; the transport must not."""
    response = result(
        app,
        scheduler,
        client.get(
            origin_a.url("/to"),
            params={"url": origin_b.url("/echo")},
            headers={
                "Authorization": "Bearer s3cret",
                "Cookie": "sid=1",
                "X-Trace": "keep",
            },
        ),
    )
    assert response.status_code == 200
    first, second = origin_a.last()["headers"], origin_b.last()["headers"]
    assert first["authorization"] == "Bearer s3cret"
    assert first["cookie"] == "sid=1"
    assert "authorization" not in second
    assert "cookie" not in second
    assert second["x-trace"] == "keep"


def test_a_redirect_out_of_the_granted_origins_is_refused_before_the_hop(
    app, scope, origin_a, origin_b
) -> None:
    """A granted origin cannot hand a view's request to one that was not (TASK-20)."""
    transport = NativeNetworkTransport(scope)
    grant = NetworkGrant(origins=(origin_a.origin,))
    before = len(origin_b.seen)
    outcomes: list[object] = []

    transport.send(
        grant.constrain(
            NetworkRequest(
                method="GET",
                url=origin_a.url("/to") + "?url=" + origin_b.url("/echo"),
                headers=Headers({"Authorization": "Bearer s3cret"}),
            )
        ),
        outcomes.append,
    )
    pump(app, lambda: bool(outcomes))

    (outcome,) = outcomes
    assert isinstance(outcome, QgisSdkRedirectError)
    assert "leaves the granted origins" in str(outcome)
    assert "s3cret" not in str(outcome)
    assert len(origin_b.seen) == before

    # The same hop inside the grant is just a redirect.
    inside: list[object] = []
    transport.send(
        NetworkGrant(origins=(origin_a.origin, origin_b.origin)).constrain(
            NetworkRequest(
                method="GET",
                url=origin_a.url("/to") + "?url=" + origin_b.url("/echo"),
            )
        ),
        inside.append,
    )
    pump(app, lambda: bool(inside))
    assert isinstance(inside[0], Response)
    assert len(origin_b.seen) == before + 1


def test_a_same_origin_redirect_keeps_credentials(
    app, scheduler, client, origin_a
) -> None:
    result(
        app,
        scheduler,
        client.get(
            origin_a.url("/to"),
            params={"url": "/echo"},
            headers={"Authorization": "Bearer s3cret"},
        ),
    )
    assert origin_a.last()["path"] == "/echo"
    assert origin_a.last()["headers"]["authorization"] == "Bearer s3cret"


def test_a_303_turns_a_post_into_a_get_without_the_body(
    app, scheduler, client, origin_a
) -> None:
    response = result(
        app,
        scheduler,
        client.post(origin_a.url("/to?code=303&url=/echo"), json={"submitted": True}),
    )
    echoed = response.json()
    assert echoed["method"] == "GET"
    assert echoed["body"] == ""
    assert "content-type" not in echoed["headers"]


# -- body ceiling --------------------------------------------------------------------


def test_a_body_over_the_ceiling_is_aborted_while_downloading(
    app, scheduler, client, origin_a
) -> None:
    small = client.configure(max_body_bytes=64 * 1024)
    error = failure(app, scheduler, small.get(origin_a.url("/bytes/1048576")))
    assert isinstance(error, QgisSdkResponseTooLargeError)
    assert error.limit == 64 * 1024
    within = result(app, scheduler, small.get(origin_a.url("/bytes/1024")))
    assert len(within.content) == 1024


# -- blocking form -------------------------------------------------------------------


def test_the_blocking_form_refuses_the_gui_thread(app, client, origin_a) -> None:
    with pytest.raises(QgisSdkBlockingOnGuiThreadError):
        client.blocking.get(origin_a.url("/json"))


def test_the_blocking_form_works_from_a_python_thread(app, client, origin_a) -> None:
    outcome: list[object] = []

    def work() -> None:
        try:
            outcome.append(client.blocking.get(origin_a.url("/json")))
        except Exception as error:  # noqa: BLE001 - reported through the list
            outcome.append(error)

    thread = threading.Thread(target=work)
    thread.start()
    pump(app, lambda: not thread.is_alive())
    thread.join()
    response = outcome[0]
    assert isinstance(response, Response), response
    assert response.json() == {"hello": "world"}


def test_the_blocking_form_works_from_the_qt_thread_pool(app, client, origin_a) -> None:
    outcome: list[object] = []

    class _Task(QRunnable):
        def run(self) -> None:
            try:
                outcome.append(
                    client.blocking.post(origin_a.url("/echo"), json={"pool": 1})
                )
            except Exception as error:  # noqa: BLE001
                outcome.append(error)

    pool = QThreadPool.globalInstance()
    pool.start(_Task())
    pump(app, lambda: bool(outcome))
    pool.waitForDone(2000)
    response = outcome[0]
    assert isinstance(response, Response), response
    assert json.loads(response.json()["body"]) == {"pool": 1}


def test_a_blocking_request_is_cancelled_when_its_scope_closes(app, origin_a) -> None:
    scope = ResourceScope()
    client = NetworkClient(NativeNetworkTransport(scope), scope)
    outcome: list[object] = []

    def work() -> None:
        try:
            outcome.append(client.blocking.get(origin_a.url("/slow?ms=3000")))
        except Exception as error:  # noqa: BLE001
            outcome.append(error)

    thread = threading.Thread(target=work)
    thread.start()
    pump(
        app, lambda: bool(origin_a.seen) and origin_a.last()["path"].startswith("/slow")
    )
    started = time.monotonic()
    scope.close()
    pump(app, lambda: not thread.is_alive())
    thread.join()
    assert type(outcome[0]).__name__ == "QgisSdkRequestCancelledError"
    assert time.monotonic() - started < 2.0


# -- QGIS configuration --------------------------------------------------------------


@pytest.fixture()
def qgis_proxy(app, proxy) -> Iterator[_Server]:
    """Route QGIS through the loopback proxy via its own settings, then restore.

    These are the entries the Options dialog writes (``proxy/proxy-*`` in the
    QGIS settings tree); the SDK never reads them, ``setupDefaultProxyAndCache``
    does.
    """
    from qgis.core import QgsSettingsTree

    node = QgsSettingsTree.node("proxy")
    entries = {
        name: node.childSetting(name)
        for name in ("proxy-enabled", "proxy-type", "proxy-host", "proxy-port")
    }
    previous = {name: entry.valueAsVariant() for name, entry in entries.items()}
    entries["proxy-enabled"].setVariantValue(True)
    entries["proxy-type"].setVariantValue("HttpProxy")
    entries["proxy-host"].setVariantValue("127.0.0.1")
    entries["proxy-port"].setVariantValue(proxy.server_port)
    QgsNetworkAccessManager.instance().setupDefaultProxyAndCache()
    try:
        yield proxy
    finally:
        for name, entry in entries.items():
            if previous[name] is None:
                entry.remove()
            else:
                entry.setVariantValue(previous[name])
        QgsNetworkAccessManager.instance().setupDefaultProxyAndCache()


def test_the_qgis_proxy_setting_is_honoured(app, scheduler, client, qgis_proxy) -> None:
    """``example.invalid`` cannot resolve; only the configured proxy can answer."""
    response = result(
        app, scheduler, client.get("http://example.invalid/through", timeout=5)
    )
    assert response.json() == {
        "via": "proxy",
        "target": "http://example.invalid/through",
    }
    assert qgis_proxy.last()["headers"]["host"] == "example.invalid"


@pytest.fixture()
def basic_auth_config(app) -> str:
    """A Basic auth configuration stored in the throwaway QGIS auth database."""
    manager = QgsApplication.authManager()
    database = QgsApplication.qgisAuthDatabaseUri()
    if manager.isDisabled() or _AUTH_DIR not in database:
        pytest.skip(
            "the QGIS auth database is not the throwaway one this module set up"
        )
    if not manager.masterPasswordIsSet() and not manager.setMasterPassword(
        "qgis-sdk-test", True
    ):
        pytest.skip("could not set a master password on the throwaway auth database")
    config = QgsAuthMethodConfig("Basic")
    config.setName("qgis-sdk-basic")
    config.setConfig("username", BASIC_USER)
    config.setConfig("password", BASIC_PASSWORD)
    stored, config = manager.storeAuthenticationConfig(config)
    assert stored
    return config.id()


def test_a_qgis_auth_configuration_is_applied_by_qgis_not_by_the_sdk(
    app, scheduler, client, origin_a, basic_auth_config
) -> None:
    anonymous = result(app, scheduler, client.get(origin_a.url("/basic")))
    assert anonymous.status_code == 401
    assert anonymous.headers["www-authenticate"].startswith("Basic")

    authenticated = client.configure(auth_config=basic_auth_config)
    response = result(app, scheduler, authenticated.get(origin_a.url("/basic")))
    assert response.status_code == 200
    assert response.json() == {"user": BASIC_USER}
    assert origin_a.last()["headers"]["authorization"] == f"Basic {_BASIC_TOKEN}"


def test_an_unknown_auth_configuration_fails_before_any_request_leaves(
    app, scheduler, client, origin_a, basic_auth_config
) -> None:
    before = len(origin_a.seen)
    error = failure(
        app,
        scheduler,
        client.configure(auth_config="nope123").get(origin_a.url("/basic")),
    )
    assert isinstance(error, QgisSdkAuthenticationError)
    assert len(origin_a.seen) == before


def test_an_auth_configuration_is_not_forwarded_across_origins(
    app, scheduler, client, origin_a, origin_b, basic_auth_config
) -> None:
    authenticated = client.configure(auth_config=basic_auth_config)
    result(
        app,
        scheduler,
        authenticated.get(origin_a.url("/to"), params={"url": origin_b.url("/echo")}),
    )
    assert "authorization" in origin_a.last()["headers"]
    assert "authorization" not in origin_b.last()["headers"]


def test_an_untrusted_certificate_is_a_tls_error(
    app, scheduler, client, tls_origin
) -> None:
    error = failure(app, scheduler, client.get(tls_origin.url("/secure"), timeout=5))
    assert isinstance(error, QgisSdkTlsError)


@pytest.fixture()
def trusted_tls_origin(app, tls_origin, basic_auth_config) -> Iterator[_Server]:
    """The self-signed origin, trusted the way a user would do it in QGIS.

    Rebuilding the trusted-CA cache is what updates Qt's default TLS
    configuration. Qt keeps an open connection per host with the configuration
    it was created with, so the connection cache is cleared as well, which is
    what QGIS does when its own network settings change.
    """
    from PyQt6.QtNetwork import QSslCertificate

    certificates = QSslCertificate.fromPath(str(tls_origin.certificate))
    assert certificates
    manager = QgsApplication.authManager()
    assert manager.storeCertAuthorities(certificates)
    assert manager.rebuildCaCertsCache()
    assert manager.rebuildTrustedCaCertsCache()
    QgsNetworkAccessManager.instance().clearConnectionCache()
    try:
        yield tls_origin
    finally:
        for certificate in certificates:
            manager.removeCertAuthority(certificate)
        manager.rebuildCaCertsCache()
        manager.rebuildTrustedCaCertsCache()
        QgsNetworkAccessManager.instance().clearConnectionCache()


def test_a_certificate_trusted_in_qgis_is_accepted(
    app, scheduler, client, trusted_tls_origin
) -> None:
    """Trust is QGIS's: storing the CA in its auth manager is all the plugin does."""
    response = result(
        app, scheduler, client.get(trusted_tls_origin.url("/secure"), timeout=5)
    )
    assert response.json() == {"tls": True}


def test_a_redirect_from_https_to_http_is_refused(
    app, scheduler, client, origin_a, trusted_tls_origin
) -> None:
    before = len(origin_a.seen)
    error = failure(
        app,
        scheduler,
        client.get(
            trusted_tls_origin.url("/to"), params={"url": origin_a.url("/json")}
        ),
    )
    assert isinstance(error, QgisSdkRedirectError)
    assert "https to http" in str(error)
    assert len(origin_a.seen) == before

"""The client over a scripted transport: non-blocking by construction.

Every coroutine test drives a real :class:`StepScheduler` by hand, so "the UI
thread was never blocked" is not a claim about ``async def`` but a count of
ticks: the job suspends on the transport's handoff and resumes only at the tick
after the fake delivered. The transport is injected per client (decision-4,
decision-23); nothing here reaches a socket.
"""

from __future__ import annotations

from collections.abc import Coroutine

import pytest
from qgis_sdk.core import JobState, ResourceScope, StepScheduler
from qgis_sdk.core.contexts import AlgorithmContext, PluginContext, UiContext
from qgis_sdk.models import (
    DEFAULT_TIMEOUT_SECONDS,
    QgisSdkBlockingOnGuiThreadError,
    QgisSdkConnectionError,
    QgisSdkHttpStatusError,
    QgisSdkJobCancelledError,
    QgisSdkRequestCancelledError,
    QgisSdkRequestRejectedError,
    QgisSdkRequestTimeoutError,
    QgisSdkResponseTooLargeError,
    QgisSdkScopeClosedError,
    QgisSdkUnsupportedCapabilityError,
    Response,
)
from qgis_sdk.network import NetworkClient
from qgis_sdk.testing import FakeNetworkTransport, QgisSdkNetworkFakeError, reply

URL = "https://api.example.test/things"


def run(scope: ResourceScope, coro: Coroutine[object, None, object]) -> object:
    """Drain a coroutine on a scheduler owned by ``scope``; return its result."""
    scheduler = StepScheduler(scope.child())
    job = scheduler.submit(coro)
    scheduler.drain(max_ticks=100)
    if job.error is not None:
        raise job.error
    assert job.state is JobState.COMPLETED
    return job.result


@pytest.fixture
def scope() -> ResourceScope:
    return ResourceScope()


@pytest.fixture
def transport() -> FakeNetworkTransport:
    return FakeNetworkTransport()


@pytest.fixture
def network(transport: FakeNetworkTransport, scope: ResourceScope) -> NetworkClient:
    return NetworkClient(transport, scope)


# -- the coroutine form ---------------------------------------------------------------


def test_a_get_suspends_the_job_and_resumes_with_the_buffered_response(
    network: NetworkClient, transport: FakeNetworkTransport, scope: ResourceScope
) -> None:
    transport.expect("GET", URL, reply(json={"items": [1, 2]}), hold=True)
    seen: list[Response] = []

    async def body() -> None:
        seen.append(await network.get(URL))

    scheduler = StepScheduler(scope.child())
    job = scheduler.submit(body())

    scheduler.tick()
    assert job.state is JobState.WAITING, "the job must suspend, not block the tick"
    assert transport.pending[0].request.method == "GET"
    assert network.in_flight == 1

    # The host answers whenever it does; nothing resumes inside that delivery.
    transport.pending[0].deliver()
    assert seen == []

    scheduler.tick()
    assert job.state is JobState.COMPLETED
    assert seen[0].json() == {"items": [1, 2]}
    assert network.in_flight == 0
    transport.assert_satisfied()


def test_a_request_carries_the_defaults_and_the_call_site_options(
    network: NetworkClient, transport: FakeNetworkTransport, scope: ResourceScope
) -> None:
    transport.expect("POST", f"{URL}?page=2&flag=true&q=a+b")

    run(
        scope,
        network.post(
            URL,
            params={"page": 2, "flag": True, "q": "a b", "skip": None},
            json={"name": "x"},
            headers={"X-Trace": "1"},
            timeout=5,
        ),
    )

    sent = transport.requests[0]
    assert sent.body == b'{"name":"x"}'
    assert sent.headers["content-type"] == "application/json"
    assert sent.headers["x-trace"] == "1"
    assert sent.timeout_seconds == 5.0
    assert sent.auth_config is None


def test_every_request_has_a_timeout_even_when_none_was_given(
    network: NetworkClient, transport: FakeNetworkTransport, scope: ResourceScope
) -> None:
    transport.expect("GET", URL)

    run(scope, network.get(URL))

    assert transport.requests[0].timeout_seconds == DEFAULT_TIMEOUT_SECONDS


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"json": {"a": 1}, "data": b"x"}, "mutually exclusive"),
        ({"timeout": 0}, "positive"),
        ({"timeout": float("inf")}, "positive"),
    ],
)
def test_bad_options_are_refused_before_the_transport_is_touched(
    network: NetworkClient,
    transport: FakeNetworkTransport,
    scope: ResourceScope,
    kwargs: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(QgisSdkRequestRejectedError, match=message):
        run(scope, network.request("POST", URL, **kwargs))  # type: ignore[arg-type]
    assert transport.requests == []


@pytest.mark.parametrize(
    ("url", "message"),
    [
        ("ftp://files.example.test/a", "not http or https"),
        ("https://user:pw@example.test/a", "credentials in URLs are refused"),
        ("things", "relative URL needs a client configured with base_url"),
        ("https:///nohost", "no host"),
    ],
)
def test_unsafe_or_unresolvable_urls_are_refused(
    network: NetworkClient,
    transport: FakeNetworkTransport,
    scope: ResourceScope,
    url: str,
    message: str,
) -> None:
    with pytest.raises(QgisSdkRequestRejectedError, match=message) as caught:
        run(scope, network.get(url))
    assert "pw" not in str(caught.value)
    assert transport.requests == []


def test_a_classified_transport_failure_reaches_the_awaiting_job_as_is(
    network: NetworkClient, transport: FakeNetworkTransport, scope: ResourceScope
) -> None:
    transport.expect(
        "GET", URL, QgisSdkConnectionError("refused", method="GET", url=URL)
    )

    with pytest.raises(QgisSdkConnectionError) as caught:
        run(scope, network.get(URL))
    assert caught.value.code == "connection_failed"


def test_a_timeout_is_its_own_error_class(
    network: NetworkClient, transport: FakeNetworkTransport, scope: ResourceScope
) -> None:
    transport.expect("GET", URL, hold=True)

    scheduler = StepScheduler(scope.child())
    job = scheduler.submit(network.get(URL, timeout=2))
    scheduler.tick()
    transport.pending[0].deliver_with(
        QgisSdkRequestTimeoutError(2, method="GET", url=URL)
    )
    scheduler.drain(max_ticks=10)

    assert isinstance(job.error, QgisSdkRequestTimeoutError)
    assert job.error.timeout_seconds == 2
    assert job.error.code == "request_timeout"


def test_a_4xx_is_data_until_raise_for_status_says_otherwise(
    network: NetworkClient, transport: FakeNetworkTransport, scope: ResourceScope
) -> None:
    transport.expect("GET", URL, reply(404, json={"detail": "gone"}))

    response = run(scope, network.get(URL))

    assert isinstance(response, Response)
    assert response.status_code == 404
    assert response.json() == {"detail": "gone"}
    with pytest.raises(QgisSdkHttpStatusError):
        response.raise_for_status()


def test_cancelling_the_job_cancels_the_transport_request_on_the_way_out(
    network: NetworkClient, transport: FakeNetworkTransport, scope: ResourceScope
) -> None:
    transport.expect("GET", URL, hold=True)
    cleaned: list[str] = []

    async def body() -> None:
        try:
            await network.get(URL)
        except QgisSdkJobCancelledError:
            cleaned.append("author finally ran")
            raise

    scheduler = StepScheduler(scope.child())
    job = scheduler.submit(body())
    scheduler.tick()

    job.cancel()
    scheduler.drain(max_ticks=10)

    assert job.state is JobState.CANCELLED
    assert cleaned == ["author finally ran"]
    assert transport.cancelled == [transport.requests[0]]
    assert network.in_flight == 0


def test_closing_the_owner_scope_cancels_in_flight_requests_and_refuses_new_ones(
    network: NetworkClient, transport: FakeNetworkTransport, scope: ResourceScope
) -> None:
    transport.expect("GET", URL, hold=True)
    scheduler = StepScheduler(scope.child())
    job = scheduler.submit(network.get(URL))
    scheduler.tick()
    assert network.in_flight == 1

    scope.close()

    assert transport.cancelled == [transport.requests[0]]
    assert network.in_flight == 0
    assert job.settled
    with pytest.raises(QgisSdkScopeClosedError):
        network.blocking.get(URL)


def test_a_late_delivery_after_cancellation_reaches_no_one(
    network: NetworkClient, transport: FakeNetworkTransport, scope: ResourceScope
) -> None:
    transport.expect("GET", URL, hold=True)
    scheduler = StepScheduler(scope.child())
    job = scheduler.submit(network.get(URL))
    scheduler.tick()
    pending = transport.pending[0]

    job.cancel()
    scheduler.drain(max_ticks=10)
    assert pending.cancelled
    with pytest.raises(QgisSdkNetworkFakeError, match="already settled"):
        pending.deliver()
    assert job.state is JobState.CANCELLED


def test_a_body_over_the_ceiling_is_refused_even_if_a_transport_buffered_it(
    transport: FakeNetworkTransport, scope: ResourceScope
) -> None:
    small = NetworkClient(transport, scope).configure(max_body_bytes=8)
    transport.expect("GET", URL, reply(body=b"123456789"))

    with pytest.raises(QgisSdkResponseTooLargeError) as caught:
        run(scope, small.get(URL))
    assert caught.value.limit == 8
    assert caught.value.code == "response_too_large"


def test_a_cancelled_request_is_a_distinct_error_from_a_failed_one() -> None:
    error = QgisSdkRequestCancelledError("owner closed", method="GET", url=URL)

    assert error.code == "request_cancelled"
    assert str(error) == f"GET {URL}: owner closed"


# -- derived clients -----------------------------------------------------------------


def test_configure_derives_an_immutable_client_sharing_the_transport(
    network: NetworkClient, transport: FakeNetworkTransport, scope: ResourceScope
) -> None:
    service = network.configure(
        base_url="https://svc.example.test/v1/",
        headers={"Accept": "application/json"},
        timeout=7,
        auth_config="abc123",
        max_redirects=3,
    )
    transport.expect("GET", "https://svc.example.test/v1/collections")
    transport.expect("GET", URL)

    run(scope, service.get("/collections"))
    run(scope, network.get(URL))

    derived, original = transport.requests
    assert derived.headers["accept"] == "application/json"
    assert derived.timeout_seconds == 7
    assert derived.auth_config == "abc123"
    assert derived.max_redirects == 3
    assert "accept" not in original.headers
    assert original.auth_config is None
    assert network.defaults.base_url is None


@pytest.mark.parametrize(
    "kwargs",
    [{"max_redirects": -1}, {"max_body_bytes": 0}, {"timeout": 0}],
)
def test_configure_refuses_nonsense_limits(
    network: NetworkClient, kwargs: dict[str, object]
) -> None:
    with pytest.raises(QgisSdkRequestRejectedError):
        network.configure(**kwargs)  # type: ignore[arg-type]


# -- the blocking form ---------------------------------------------------------------


def test_the_blocking_form_is_explicit_and_returns_the_response_directly(
    network: NetworkClient, transport: FakeNetworkTransport
) -> None:
    transport.expect("POST", URL, reply(201, json={"id": 1}))

    response = network.blocking.post(URL, data={"name": "a b"})

    assert response.status_code == 201
    assert transport.requests[0].body == b"name=a+b"
    assert transport.requests[0].headers["content-type"] == (
        "application/x-www-form-urlencoded"
    )


def test_the_blocking_form_is_refused_on_the_gui_thread(scope: ResourceScope) -> None:
    gui = FakeNetworkTransport(gui_thread=True)
    network = NetworkClient(gui, scope)
    gui.expect("GET", URL)

    with pytest.raises(QgisSdkBlockingOnGuiThreadError) as caught:
        network.blocking.get(URL)
    assert caught.value.code == "blocking_on_gui_thread"
    # The refusal happens before anything is sent.
    assert gui.requests == []


def test_a_blocking_failure_raises_the_classified_error(
    network: NetworkClient, transport: FakeNetworkTransport
) -> None:
    transport.expect("GET", URL, QgisSdkConnectionError("down", method="GET", url=URL))

    with pytest.raises(QgisSdkConnectionError):
        network.blocking.get(URL)


# -- contexts -----------------------------------------------------------------------


def test_contexts_expose_the_injected_client_and_refuse_its_absence(
    network: NetworkClient, scope: ResourceScope
) -> None:
    from qgis_sdk.testing import RecordingNotifications

    notifications = RecordingNotifications(scope)
    with_network = PluginContext(notifications, scope, network=network)
    without = PluginContext(notifications, scope)

    assert with_network.require_network() is network
    with pytest.raises(QgisSdkUnsupportedCapabilityError) as caught:
        without.require_network()
    assert caught.value.capability == "network"

    class Closeable:
        def request_close(self) -> None:
            return

    assert (
        UiContext(notifications, Closeable(), scope, network=network).require_network()
        is network
    )
    algorithm = AlgorithmContext(
        progress=_Progress(),
        cancellation=_Never(),
        scope=scope,
        algorithms=_NoAlgorithms(),
    )
    with pytest.raises(QgisSdkUnsupportedCapabilityError):
        algorithm.require_network()


class _Progress:
    def report(self, fraction: float) -> None:
        return


class _Never:
    def is_cancelled(self) -> bool:
        return False


class _NoAlgorithms:
    def execute(self, request: object) -> object:
        raise AssertionError("not used")

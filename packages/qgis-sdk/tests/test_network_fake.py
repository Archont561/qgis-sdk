"""The scripted transport fails loudly: unexpected, unmet and still-pending requests."""

from __future__ import annotations

import pytest
from qgis_sdk.models import (
    NetworkRequest,
    QgisSdkRequestCancelledError,
    QgisSdkRequestTimeoutError,
    Response,
)
from qgis_sdk.testing import FakeNetworkTransport, QgisSdkNetworkFakeError, reply

URL = "https://example.test/a"


def _request(method: str = "GET", url: str = URL) -> NetworkRequest:
    return NetworkRequest(method=method, url=url)


def _collect() -> tuple[list[Response | Exception], object]:
    outcomes: list[Response | Exception] = []
    return outcomes, outcomes.append


def test_an_unexpected_request_is_refused_at_once_and_remembered() -> None:
    transport = FakeNetworkTransport()
    outcomes, deliver = _collect()

    with pytest.raises(QgisSdkNetworkFakeError, match="no expectation covers GET"):
        transport.send(_request(), deliver)  # type: ignore[arg-type]

    assert outcomes == []
    assert transport.unexpected == (_request(),)
    with pytest.raises(QgisSdkNetworkFakeError, match="unexpected requests: GET"):
        transport.assert_satisfied()


def test_expectations_are_consumed_in_order_and_reported_when_unmet() -> None:
    transport = FakeNetworkTransport()
    transport.expect("GET", URL, reply(body=b"first"))
    transport.expect("GET", URL, reply(body=b"second"))
    transport.expect("POST", URL)
    outcomes, deliver = _collect()

    transport.send(_request(), deliver)  # type: ignore[arg-type]
    transport.send(_request(), deliver)  # type: ignore[arg-type]

    assert [o.content for o in outcomes if isinstance(o, Response)] == [
        b"first",
        b"second",
    ]
    assert transport.unmet == (f"POST {URL}",)
    with pytest.raises(
        QgisSdkNetworkFakeError, match=f"unmet expectations: POST {URL}"
    ):
        transport.assert_satisfied()


def test_a_held_request_is_delivered_only_when_the_test_says_so() -> None:
    transport = FakeNetworkTransport()
    transport.expect("GET", URL, reply(json={"ok": True}), hold=True)
    outcomes, deliver = _collect()

    transport.send(_request(), deliver)  # type: ignore[arg-type]
    assert outcomes == []
    with pytest.raises(QgisSdkNetworkFakeError, match="still pending"):
        transport.assert_satisfied()

    transport.pending[0].deliver()
    assert isinstance(outcomes[0], Response)
    assert outcomes[0].json() == {"ok": True}
    transport.assert_satisfied()


def test_a_held_request_can_be_failed_with_a_classified_error_instead() -> None:
    transport = FakeNetworkTransport()
    transport.expect("GET", URL, hold=True)
    outcomes, deliver = _collect()
    transport.send(_request(), deliver)  # type: ignore[arg-type]

    transport.pending[0].deliver_with(
        QgisSdkRequestTimeoutError(3, method="GET", url=URL)
    )

    assert isinstance(outcomes[0], QgisSdkRequestTimeoutError)


def test_cancelling_delivers_a_cancelled_outcome_once() -> None:
    transport = FakeNetworkTransport()
    transport.expect("GET", URL, hold=True)
    outcomes, deliver = _collect()
    cancel = transport.send(_request(), deliver)  # type: ignore[arg-type]

    cancel()
    cancel()

    assert len(outcomes) == 1
    assert isinstance(outcomes[0], QgisSdkRequestCancelledError)
    assert transport.cancelled == [_request()]
    transport.assert_satisfied()


def test_a_responder_sees_the_request_it_answers() -> None:
    transport = FakeNetworkTransport()
    transport.expect(
        "GET", URL, lambda request: reply(body=request.method.encode())(request)
    )
    outcomes, deliver = _collect()

    transport.send(_request(), deliver)  # type: ignore[arg-type]

    assert isinstance(outcomes[0], Response)
    assert outcomes[0].content == b"GET"


def test_a_fixed_response_or_exception_can_be_scripted_directly() -> None:
    transport = FakeNetworkTransport()
    fixed = reply(204)(_request())
    transport.expect("GET", URL, fixed)
    transport.expect("GET", URL, RuntimeError("scripted"))
    outcomes, deliver = _collect()

    transport.send(_request(), deliver)  # type: ignore[arg-type]
    transport.send(_request(), deliver)  # type: ignore[arg-type]

    assert outcomes[0] is fixed
    assert isinstance(outcomes[1], RuntimeError)


def test_reply_builds_a_response_with_a_reason_and_a_final_url() -> None:
    response = reply(301, url="https://example.test/b", headers={"Location": "/b"})(
        _request()
    )

    assert response.status_code == 301
    assert response.reason == ""
    assert response.url == "https://example.test/b"
    assert response.headers["location"] == "/b"
    assert reply(404)(_request()).reason == "Not Found"
    assert reply(200, body="text")(_request()).content == b"text"
